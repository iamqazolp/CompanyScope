from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
import uuid
from typing import Any

from src.agent import (
    TOOL_FUNCTIONS,
    TOOLS_LIST,
    _call_llm,
    _emit_event,
    _extract_json,
    _get_langfuse,
    _obs_context,
)
from src.config import (
    DEFAULT_TICKER,
    TIER1_MODEL,
    TIER2_MODEL,
    propagate_trace_attributes,
)
from src.guard import check_citations, verify_citations
from src.tier_router import (
    TierDecision,
    escalate_on_guard_failure,
    resolve_subagent_tier,
    resolve_supervisor_tier,
)

QUANT_TOOLS = [
    t
    for t in TOOLS_LIST
    if t["function"]["name"] in ("get_financial_data", "calculator")
]
QUAL_TOOLS = [
    t
    for t in TOOLS_LIST
    if t["function"]["name"] in ("search_filings", "get_earnings_transcripts")
]
SENTIMENT_TOOLS = [
    t for t in TOOLS_LIST if t["function"]["name"] in ("get_market_sentiment",)
]

QUANT_SYSTEM_PROMPT = """You are the Quantitative XBRL Financial Sub-Agent for CompanyScope.
Your sole responsibility is to fetch authoritative numeric financial metrics from SEC 10-K filings using `get_financial_data` and perform exact calculations using `calculator`.

Rules:
- ALWAYS call `get_financial_data` for every requested metric and year.
- ALWAYS call `calculator` for any growth rate, difference, margin, or ratio.
- Output ONLY a valid JSON object matching this schema:
{
  "answer": "Detailed quantitative findings with exact USD figures and calculated percentages.",
  "citations": [
    {"type": "numeric", "ticker": "AAPL", "year": 2023, "concept": "Revenues"}
  ],
  "needs_clarification": ""
}
"""

QUAL_SYSTEM_PROMPT = """You are the Qualitative SEC Narrative Sub-Agent for CompanyScope.
Your sole responsibility is to search 10-K and 10-Q narrative sections (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 7A) using `search_filings` and extract exact verbatim quotes.

Rules:
- ALWAYS call `search_filings` for the assigned ticker.
- Every narrative citation's `"quote"` field MUST be an exact, contiguous verbatim substring copied character-for-character from `chunk_text`.
- Output ONLY a valid JSON object matching this schema:
{
  "answer": "Detailed qualitative analysis incorporating exact verbatim quotes from the filings.",
  "citations": [
    {
      "type": "narrative",
      "ticker": "AAPL",
      "year": 2024,
      "section": "Item 1A",
      "chunk_id": "AAPL_2024_10-K_Item1A_0",
      "quote": "Exact verbatim substring from chunk_text."
    }
  ],
  "needs_clarification": ""
}
"""

SENTIMENT_SYSTEM_PROMPT = """You are the Market Sentiment & Financial News Sub-Agent for CompanyScope.
Your sole responsibility is to fetch public retail investor discussions (Reddit r/stocks, r/investing, r/wallstreetbets) and recent financial news headlines (Yahoo Finance) using `get_market_sentiment` and extract exact verbatim quotes.

Rules:
- ALWAYS call `get_market_sentiment` for the assigned ticker.
- Clearly frame findings as public market sentiment / news commentary (distinct from audited SEC filings).
- Every citation's `"quote"` field MUST be an exact, contiguous verbatim substring copied character-for-character from `chunk_text`.
- Output ONLY a valid JSON object matching this schema:
{
  "answer": "Detailed market sentiment and news analysis incorporating exact verbatim quotes.",
  "citations": [
    {
      "type": "sentiment",
      "ticker": "AAPL",
      "year": 2026,
      "section": "Reddit (r/stocks)",
      "chunk_id": "AAPL_2026_REDDIT_abc123",
      "quote": "Exact verbatim substring from chunk_text."
    }
  ],
  "needs_clarification": ""
}
"""

SYNTHESIZER_SYSTEM_PROMPT = """You are the Tier-1 Lead Financial Synthesizer Agent for CompanyScope.
You receive verified findings and citations from specialized Quantitative (XBRL), Qualitative (SEC 10-K/10-Q/8-K Narrative), and Market Sentiment (Reddit & Financial News) sub-agents across one or more companies.

Rules:
- Synthesize the sub-agent reports into a cohesive, executive-grade comparative answer.
- Preserve the exact numeric figures and exact verbatim narrative quotes provided by the sub-agents.
- Include all relevant verified citations from the sub-agents in your `"citations"` array without modifying the `"quote"`, `"chunk_id"`, `"concept"`, or `"year"` fields.
- Output ONLY a valid JSON object matching this schema:
{
  "answer": "Comprehensive synthesized answer combining all company and specialist findings.",
  "citations": [ ... ],
  "needs_clarification": ""
}
"""

COMMON_COMPANY_MAP = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "NVIDIA": "NVDA",
    "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL",
    "AMAZON": "AMZN",
    "META": "META",
    "TESLA": "TSLA",
    "NETFLIX": "NFLX",
    "AMD": "AMD",
    "INTEL": "INTC",
}


def detect_tickers(
    question: str, default_ticker: str, extra_tickers: list[str] | None = None
) -> list[str]:
    """Detects all ticker symbols referenced in the question or explicitly passed."""
    tickers: list[str] = []
    if extra_tickers:
        for t in extra_tickers:
            clean = t.upper().strip()
            if clean and clean not in tickers:
                tickers.append(clean)

    q_upper = question.upper()
    for name, sym in COMMON_COMPANY_MAP.items():
        if re.search(rf"\b{name}\b", q_upper) and sym not in tickers:
            tickers.append(sym)

    stopwords = {
        "SEC", "USD", "CEO", "CFO", "AI", "RAG", "XBRL", "MD", "MDA",
        "ITEM", "WHAT", "HOW", "DID", "AND", "THE", "FOR", "FROM", "WITH",
        "VS", "IN", "TO", "OF", "ON", "IS", "ARE", "WAS", "WERE", "GAAP",
    }
    for match in re.findall(r"\b[A-Z]{2,5}\b", question):
        if match not in stopwords and match not in tickers:
            tickers.append(match)

    if not tickers:
        tickers.append((default_ticker or DEFAULT_TICKER).upper().strip())

    return tickers[:4]


def classify_needed_specialists(question: str) -> list[str]:
    """Determines whether the query needs Quantitative (XBRL/Math), Qualitative (Narrative), or both."""
    q_lower = question.lower()

    quant_keywords = (
        "revenue", "sales", "net income", "profit", "operating income",
        "asset", "liabilit", "equity", "cash flow", "capex", "capital expenditure",
        "growth", "calculate", "difference", "margin", "ratio", "how much",
        "compare", "financial", "numbers", "metrics",
    )
    qual_keywords = (
        "risk", "supply chain", "cyber", "strategy", "md&a", "management",
        "competit", "artificial intelligence", "ai ", "business", "item 1",
        "item 7", "narrative", "summarize", "summary", "mention", "say about",
        "outlook", "challenge", "litigation", "regulation", "earnings call",
        "transcript", "press release", "ceo", "cfo", "guidance", "commentary",
    )

    sentiment_keywords = (
        "sentiment", "reddit", "social media", "wallstreetbets", "wsb",
        "news", "headline", "retail investor", "chatter", "buzz", "public opinion",
        "what are people saying", "what do investors think",
    )

    needs_quant = any(kw in q_lower for kw in quant_keywords)
    needs_qual = any(kw in q_lower for kw in qual_keywords)
    needs_sentiment = any(kw in q_lower for kw in sentiment_keywords)

    roles: list[str] = []
    if needs_quant:
        roles.append("quant")
    if needs_qual:
        roles.append("qual")
    if needs_sentiment:
        roles.append("sentiment")

    return roles if roles else ["quant", "qual"]


def _run_sub_agent(
    role: str,
    ticker: str,
    question: str,
    provider: str | None = None,
    model: str | None = None,
    tier_decision: TierDecision | None = None,
    event_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Executes a single specialized sub-agent (quant, qual, or sentiment) on Tier 2 (Luna) or escalated Tier 1 (Terra)."""
    if role == "quant":
        sys_prompt = QUANT_SYSTEM_PROMPT
        tools_subset = QUANT_TOOLS
    elif role == "sentiment":
        sys_prompt = SENTIMENT_SYSTEM_PROMPT
        tools_subset = SENTIMENT_TOOLS
    else:
        sys_prompt = QUAL_SYSTEM_PROMPT
        tools_subset = QUAL_TOOLS

    active_decision = tier_decision or resolve_subagent_tier(
        question=question,
        role=role,
        tickers=[ticker],
        explicit_model=model,
    )
    agent_label = f"{role.upper()}_{ticker}"
    _emit_event(
        event_cb,
        {
            "type": "specialist_start",
            "agent": agent_label,
            "role": role,
            "ticker": ticker,
            "model": active_decision.model,
            "tier": active_decision.tier,
            "escalated": active_decision.escalated,
            "escalation_reason": active_decision.reason,
        },
    )
    lf = _get_langfuse()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": (
                f"Assigned Company Ticker: {ticker}\n"
                f"Sub-Agent Role: {role.upper()}\n"
                f"User Question: {question}\n"
                f"Focus strictly on {ticker}'s {role} data and return the JSON schema."
            ),
        },
    ]

    tool_results_history: dict[str, Any] = {}
    used_tools: list[str] = []
    tool_trace: list[dict[str, Any]] = []
    self_corrections = 0
    sub_cost_usd = 0.0
    active_model_used = active_decision.model

    with _obs_context(
        lf,
        as_type="agent",
        name=f"subagent:{role}:{ticker}",
        input={
            "question": question,
            "ticker": ticker,
            "role": role,
            "tier": active_decision.tier,
            "initial_model": active_decision.model,
            "escalated": active_decision.escalated,
        },
    ) as agent_span:
        for _step in range(5):
            try:
                msg, active_model_used = _call_llm(
                    messages=messages,
                    use_tools=True,
                    provider=provider,
                    model=active_decision.model,
                    tools_override=tools_subset,
                    obs_name=f"subagent_{role}_{ticker}_llm",
                )
                sub_cost_usd += float(
                    (msg.get("_cost_details") or {}).get("total", 0.0)
                )
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": msg.get("content") or "",
                            "tool_calls": tool_calls,
                        }
                    )
                    for tc in tool_calls:
                        tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                        fn_info = tc.get("function") or {}
                        fn_name = fn_info.get("name", "")
                        raw_args = fn_info.get("arguments", "{}")
                        used_tools.append(fn_name)

                        try:
                            fn_args = (
                                json.loads(raw_args)
                                if isinstance(raw_args, str)
                                else dict(raw_args)
                            )
                        except json.JSONDecodeError:
                            fn_args = {}

                        if fn_name in (
                            "get_financial_data",
                            "search_filings",
                            "get_earnings_transcripts",
                            "get_market_sentiment",
                        ) and not fn_args.get("ticker"):
                            fn_args["ticker"] = ticker

                        obs_type = (
                            "retriever" if fn_name == "search_filings" else "tool"
                        )
                        _emit_event(
                            event_cb,
                            {
                                "type": "tool_call",
                                "agent": agent_label,
                                "ticker": ticker,
                                "role": role,
                                "tool": fn_name,
                                "args": fn_args,
                            },
                        )
                        with _obs_context(
                            lf,
                            as_type=obs_type,
                            name=f"tool:{fn_name}",
                            input=fn_args,
                        ) as t_span:
                            if fn_name in TOOL_FUNCTIONS:
                                try:
                                    res = TOOL_FUNCTIONS[fn_name](**fn_args)
                                    tool_results_history[tc_id] = res
                                    res_str = json.dumps(res)
                                except Exception as ex:
                                    res = {"error": str(ex)}
                                    res_str = json.dumps(res)
                            else:
                                res = {"error": f"Unsupported tool {fn_name}"}
                                res_str = json.dumps(res)

                            if t_span is not None:
                                try:
                                    t_span.update(output=res)
                                except Exception:
                                    pass

                        tool_trace.append(
                            {
                                "agent": agent_label,
                                "tool": fn_name,
                                "arguments": fn_args,
                                "result": res,
                            }
                        )
                        messages.append(
                            {
                                "tool_call_id": tc_id,
                                "role": "tool",
                                "name": fn_name,
                                "content": res_str,
                            }
                        )
                else:
                    content = msg.get("content") or "{}"
                    try:
                        parsed = _extract_json(content)
                    except json.JSONDecodeError:
                        if self_corrections < 1:
                            self_corrections += 1
                            next_dec = escalate_on_guard_failure(
                                active_decision, explicit_model=model
                            )
                            if next_dec.model != active_decision.model:
                                _emit_event(
                                    event_cb,
                                    {
                                        "type": "tier_escalation",
                                        "agent": agent_label,
                                        "role": role,
                                        "ticker": ticker,
                                        "from_model": active_decision.model,
                                        "to_model": next_dec.model,
                                        "reason": "json_schema_retry_escalation",
                                    },
                                )
                                active_decision = next_dec
                            messages.append({"role": "assistant", "content": content})
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "Your output was not valid JSON. Output ONLY a strictly valid JSON object matching the schema.",
                                }
                            )
                            continue
                        raise

                    _valid_cits, invalid_cits = check_citations(
                        parsed, tool_results_history
                    )
                    if invalid_cits and self_corrections < 1:
                        self_corrections += 1
                        next_dec = escalate_on_guard_failure(
                            active_decision, explicit_model=model
                        )
                        if next_dec.model != active_decision.model:
                            _emit_event(
                                event_cb,
                                {
                                    "type": "tier_escalation",
                                    "agent": agent_label,
                                    "role": role,
                                    "ticker": ticker,
                                    "from_model": active_decision.model,
                                    "to_model": next_dec.model,
                                    "reason": next_dec.reason,
                                },
                            )
                            active_decision = next_dec
                        messages.append({"role": "assistant", "content": content})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Citation verification failed for: {json.dumps(invalid_cits)}\n"
                                    "Please self-correct your JSON so all quotes are exact verbatim substrings of chunk_text and all numbers match fetched tool results."
                                ),
                            }
                        )
                        continue

                    verified = verify_citations(parsed, tool_results_history)
                    _emit_event(
                        event_cb,
                        {
                            "type": "specialist_done",
                            "agent": agent_label,
                            "role": role,
                            "ticker": ticker,
                            "model": active_model_used,
                            "tier": active_decision.tier,
                            "escalated": active_decision.escalated,
                            "citations_count": len(verified.get("citations", [])),
                            "self_corrections": self_corrections,
                        },
                    )
                    out_payload = {
                        "agent": agent_label,
                        "role": role,
                        "ticker": ticker,
                        "answer": verified.get("answer", ""),
                        "citations": verified.get("citations", []),
                        "needs_clarification": verified.get(
                            "needs_clarification", ""
                        ),
                        "used_tools": list(dict.fromkeys(used_tools)),
                        "tool_trace": tool_trace,
                        "tool_results_history": tool_results_history,
                        "self_corrections": self_corrections,
                        "cost_usd": round(sub_cost_usd, 6),
                        "model": active_model_used,
                        "tier": active_decision.tier,
                        "escalated": active_decision.escalated,
                        "escalation_reason": active_decision.reason,
                    }
                    if agent_span is not None:
                        try:
                            agent_span.update(
                                output={
                                    "answer": out_payload["answer"],
                                    "citations": out_payload["citations"],
                                    "cost_usd": out_payload["cost_usd"],
                                    "model": out_payload["model"],
                                    "tier": out_payload["tier"],
                                    "escalated": out_payload["escalated"],
                                }
                            )
                        except Exception:
                            pass
                    return out_payload
            except Exception as e:
                return {
                    "agent": agent_label,
                    "role": role,
                    "ticker": ticker,
                    "answer": f"Sub-agent {agent_label} encountered an issue: {e}",
                    "citations": [],
                    "needs_clarification": "",
                    "used_tools": list(dict.fromkeys(used_tools)),
                    "tool_trace": tool_trace,
                    "tool_results_history": tool_results_history,
                    "self_corrections": self_corrections,
                    "cost_usd": round(sub_cost_usd, 6),
                    "model": active_model_used,
                    "tier": active_decision.tier,
                    "escalated": active_decision.escalated,
                    "escalation_reason": active_decision.reason,
                }

    return {
        "agent": agent_label,
        "role": role,
        "ticker": ticker,
        "answer": f"Sub-agent {agent_label} reached max iterations.",
        "citations": [],
        "needs_clarification": "",
        "used_tools": list(dict.fromkeys(used_tools)),
        "tool_trace": tool_trace,
        "tool_results_history": tool_results_history,
        "self_corrections": self_corrections,
        "cost_usd": round(sub_cost_usd, 6),
        "model": active_model_used,
        "tier": active_decision.tier,
        "escalated": active_decision.escalated,
        "escalation_reason": active_decision.reason,
    }


def run_multi_agent_query(
    question: str,
    ticker: str = DEFAULT_TICKER,
    tickers: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    provider: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    event_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Supervisor orchestrator that decomposes a query across companies and specialist roles
    (Quantitative XBRL + Qualitative Narrative), executes sub-agents in parallel via
    ThreadPoolExecutor, and synthesizes a citation-verified final response.
    """
    start_time = time.time()
    target_tickers = detect_tickers(question, ticker, tickers)
    roles = classify_needed_specialists(question)
    supervisor_decision = resolve_supervisor_tier(explicit_model=model)

    tasks: list[tuple[str, str]] = [
        (r, t) for t in target_tickers for r in roles
    ]
    is_sole_specialist = len(tasks) == 1
    task_decisions: dict[tuple[str, str], TierDecision] = {
        (r, t): resolve_subagent_tier(
            question=question,
            role=r,
            tickers=target_tickers,
            explicit_model=model,
            sole_specialist=is_sole_specialist,
        )
        for r, t in tasks
    }

    _emit_event(
        event_cb,
        {
            "type": "plan",
            "mode": "multi_agent",
            "tickers": target_tickers,
            "specialists": roles,
            "supervisor_model": supervisor_decision.model,
            "subagent_default_model": model or TIER2_MODEL,
            "escalated_tasks": [
                f"{r.upper()}_{t}"
                for (r, t), dec in task_decisions.items()
                if dec.escalated
            ],
        },
    )

    lf = _get_langfuse()
    trace_url: str | None = None

    with _obs_context(
        lf,
        as_type="agent",
        name="companyscope_multi_agent_supervisor",
        input={
            "question": question,
            "target_tickers": target_tickers,
            "specialist_roles": roles,
            "tier1_supervisor_model": supervisor_decision.model,
            "tier2_subagent_model": model or TIER2_MODEL,
        },
    ) as root_span, propagate_trace_attributes(
        lf,
        session_id=session_id,
        user_id=user_id,
        tags=[
            "company-scope",
            "multi-agent",
            f"supervisor:{supervisor_decision.model}",
        ]
        + [f"ticker:{t}" for t in target_tickers],
        trace_name="companyscope_multi_agent_supervisor",
    ):
        if lf is not None:
            try:
                trace_url = lf.get_trace_url()
            except Exception:
                trace_url = None

        sub_reports: list[dict[str, Any]] = []
        max_workers = min(len(tasks), 6) if tasks else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    _run_sub_agent,
                    role=r,
                    ticker=t,
                    question=question,
                    provider=provider,
                    model=model,
                    tier_decision=task_decisions[(r, t)],
                    event_cb=event_cb,
                ): (r, t)
                for r, t in tasks
            }
            for future in as_completed(future_to_task):
                sub_reports.append(future.result())

        order_map = {
            f"{r.upper()}_{t}": idx for idx, (r, t) in enumerate(tasks)
        }
        sub_reports.sort(key=lambda rep: order_map.get(rep["agent"], 999))

        combined_tool_results: dict[str, Any] = {}
        combined_used_tools: list[str] = []
        combined_tool_trace: list[dict[str, Any]] = []
        total_self_corrections = 0
        total_cost_usd = 0.0

        for rep in sub_reports:
            for k, v in rep.get("tool_results_history", {}).items():
                combined_tool_results[f"{rep['agent']}_{k}"] = v
            for ut in rep.get("used_tools", []):
                if ut not in combined_used_tools:
                    combined_used_tools.append(ut)
            combined_tool_trace.extend(rep.get("tool_trace", []))
            total_self_corrections += int(rep.get("self_corrections", 0))
            total_cost_usd += float(rep.get("cost_usd", 0.0))

        if len(sub_reports) == 1:
            single = sub_reports[0]
            final_single: dict[str, Any] = {
                "answer": single["answer"],
                "citations": single["citations"],
                "needs_clarification": single.get("needs_clarification", ""),
                "used_tools": combined_used_tools,
                "tool_trace": combined_tool_trace,
                "sub_agent_reports": [
                    {
                        "agent": single["agent"],
                        "role": single["role"],
                        "ticker": single["ticker"],
                        "answer": single["answer"],
                        "citations_count": len(single["citations"]),
                        "self_corrections": single["self_corrections"],
                        "cost_usd": single.get("cost_usd", 0.0),
                        "model": single.get("model"),
                        "tier": single.get("tier", "tier1"),
                        "escalated": bool(single.get("escalated", False)),
                        "escalation_reason": single.get("escalation_reason", ""),
                    }
                ],
                "self_corrections": total_self_corrections,
                "cost_usd": round(total_cost_usd, 6),
                "model": single.get("model"),
                "tier": single.get("tier", "tier1"),
                "escalated": bool(single.get("escalated", False)),
                "escalation_reason": single.get("escalation_reason", ""),
                "tier_breakdown": {
                    "supervisor_model": single.get("model") or supervisor_decision.model,
                    "tier1_model": TIER1_MODEL,
                    "tier2_model": TIER2_MODEL,
                    "tier1_agents": (
                        [single["agent"]] if single.get("tier") == "tier1" else []
                    ),
                    "tier2_agents": (
                        [single["agent"]] if single.get("tier") == "tier2" else []
                    ),
                    "escalated_agents": (
                        [single["agent"]] if single.get("escalated") else []
                    ),
                },
                "latency_ms": round((time.time() - start_time) * 1000),
            }
            if trace_url:
                final_single["trace_url"] = trace_url
            if root_span is not None:
                try:
                    root_span.update(
                        output={
                            "answer": final_single["answer"],
                            "citations": final_single["citations"],
                            "cost_usd": final_single["cost_usd"],
                            "model": final_single["model"],
                        }
                    )
                except Exception:
                    pass
            if lf is not None:
                try:
                    lf.flush()
                except Exception:
                    pass
            return final_single

        reports_payload = [
            {
                "sub_agent": rep["agent"],
                "ticker": rep["ticker"],
                "role": rep["role"],
                "model": rep.get("model"),
                "verified_answer": rep["answer"],
                "verified_citations": rep["citations"],
            }
            for rep in sub_reports
        ]

        synth_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
        ]
        if history:
            for turn in history[-4:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    synth_messages.append(
                        {"role": turn["role"], "content": turn["content"]}
                    )

        synth_messages.append(
            {
                "role": "user",
                "content": (
                    f"User Question: {question}\n"
                    f"Target Companies: {', '.join(target_tickers)}\n\n"
                    f"Sub-Agent Verified Reports:\n{json.dumps(reports_payload, indent=2)}\n\n"
                    "Synthesize these findings into the final JSON response while preserving exact numbers and exact verbatim citation quotes."
                ),
            }
        )

        active_model_used = supervisor_decision.model
        _emit_event(
            event_cb,
            {
                "type": "synthesizing",
                "reports_count": len(sub_reports),
                "tickers": target_tickers,
                "model": supervisor_decision.model,
                "tier": supervisor_decision.tier,
            },
        )
        try:
            synth_msg, active_model_used = _call_llm(
                messages=synth_messages,
                use_tools=False,
                provider=provider,
                model=supervisor_decision.model,
                obs_name="multi_agent_tier1_synthesizer",
            )
            total_cost_usd += float(
                (synth_msg.get("_cost_details") or {}).get("total", 0.0)
            )
            parsed = _extract_json(synth_msg.get("content") or "{}")
            _valid_cits, invalid_cits = check_citations(
                parsed, combined_tool_results
            )
            _emit_event(
                event_cb,
                {
                    "type": "guard_check",
                    "scope": "synthesis",
                    "valid_count": len(_valid_cits),
                    "invalid_count": len(invalid_cits),
                },
            )

            if invalid_cits:
                total_self_corrections += 1
                synth_messages.append(
                    {"role": "assistant", "content": synth_msg.get("content") or "{}"}
                )
                synth_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Citation verification failed in synthesis: {json.dumps(invalid_cits)}\n"
                            "Re-output the JSON using ONLY the exact `verified_citations` from the sub-agent reports."
                        ),
                    }
                )
                retry_msg, active_model_used = _call_llm(
                    messages=synth_messages,
                    use_tools=False,
                    provider=provider,
                    model=supervisor_decision.model,
                    obs_name="multi_agent_tier1_synthesizer_self_correction",
                )
                total_cost_usd += float(
                    (retry_msg.get("_cost_details") or {}).get("total", 0.0)
                )
                parsed = _extract_json(retry_msg.get("content") or "{}")

            verified_final = verify_citations(parsed, combined_tool_results)
        except Exception:
            merged_cits: list[dict[str, Any]] = []
            for rep in sub_reports:
                merged_cits.extend(rep.get("citations", []))
            verified_final = {
                "answer": "\n\n".join(
                    f"**{rep['agent']}**: {rep['answer']}" for rep in sub_reports
                ),
                "citations": merged_cits,
                "needs_clarification": "",
            }

        tier1_agents = ["SUPERVISOR_SYNTH"] + [
            rep["agent"] for rep in sub_reports if rep.get("tier") == "tier1"
        ]
        tier2_agents = [
            rep["agent"] for rep in sub_reports if rep.get("tier") == "tier2"
        ]
        escalated_agents = [
            rep["agent"] for rep in sub_reports if rep.get("escalated")
        ]

        verified_final["used_tools"] = combined_used_tools
        verified_final["tool_trace"] = combined_tool_trace
        verified_final["sub_agent_reports"] = [
            {
                "agent": rep["agent"],
                "role": rep["role"],
                "ticker": rep["ticker"],
                "answer": rep["answer"],
                "citations_count": len(rep.get("citations", [])),
                "self_corrections": rep.get("self_corrections", 0),
                "cost_usd": rep.get("cost_usd", 0.0),
                "model": rep.get("model"),
                "tier": rep.get("tier", "tier2"),
                "escalated": bool(rep.get("escalated", False)),
                "escalation_reason": rep.get("escalation_reason", ""),
            }
            for rep in sub_reports
        ]
        verified_final["self_corrections"] = total_self_corrections
        verified_final["cost_usd"] = round(total_cost_usd, 6)
        verified_final["model"] = active_model_used
        verified_final["tier"] = supervisor_decision.tier
        verified_final["escalated"] = bool(escalated_agents)
        verified_final["tier_breakdown"] = {
            "supervisor_model": active_model_used,
            "tier1_model": TIER1_MODEL,
            "tier2_model": TIER2_MODEL,
            "tier1_agents": tier1_agents,
            "tier2_agents": tier2_agents,
            "escalated_agents": escalated_agents,
        }
        verified_final["latency_ms"] = round((time.time() - start_time) * 1000)
        if trace_url:
            verified_final["trace_url"] = trace_url

        if root_span is not None:
            try:
                root_span.update(
                    output={
                        "answer": verified_final.get("answer"),
                        "citations": verified_final.get("citations"),
                        "cost_usd": verified_final.get("cost_usd"),
                    }
                )
            except Exception:
                pass
        if lf is not None:
            try:
                lf.flush()
            except Exception:
                pass

        return verified_final
