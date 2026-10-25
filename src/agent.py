from contextlib import nullcontext
import json
import os
import re
import time
import uuid
from typing import Any

import requests
from groq import Groq

from src.config import (
    DEFAULT_TICKER,
    GPT6_LUNA_CACHE_WRITE_PRICE_PER_1M,
    GPT6_LUNA_CACHED_INPUT_PRICE_PER_1M,
    GPT6_LUNA_INPUT_PRICE_PER_1M,
    GPT6_LUNA_OUTPUT_PRICE_PER_1M,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_TIMEOUT,
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_PROVIDER,
    LLM_TIMEOUT,
    OPENAI_KEY,
    OPENAI_MODEL,
    OPENAI_URL,
    propagate_trace_attributes,
)
from src.guard import check_citations, verify_citations
from src.tools import calculator, get_financial_data, search_filings

_groq_client: Groq | None = None
_http_session: requests.Session | None = None
_langfuse_client: Any = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
    return _http_session


def _get_langfuse() -> Any:
    """Initializes Langfuse v4 client if credentials are configured in .env."""
    global _langfuse_client
    if _langfuse_client is False:
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse

            _langfuse_client = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
            )
            return _langfuse_client
        except Exception:
            _langfuse_client = False
            return None
    _langfuse_client = False
    return None


def _obs_context(lf: Any, **kwargs: Any) -> Any:
    """Returns a Langfuse start_as_current_observation context manager if enabled, else nullcontext."""
    if lf is not None:
        try:
            return lf.start_as_current_observation(**kwargs)
        except Exception:
            return nullcontext(None)
    return nullcontext(None)


def get_model_pricing(model_name: str = "gpt-6-luna") -> dict[str, float]:
    """Loads per-1M-token USD pricing for a model from src/model_pricing.json, falling back to config defaults."""
    pricing_path = os.path.join(os.path.dirname(__file__), "model_pricing.json")
    if os.path.exists(pricing_path):
        try:
            with open(pricing_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
            entry = registry.get(model_name) or registry.get(model_name.lower())
            if isinstance(entry, dict):
                return {
                    "input_per_1m": float(
                        entry.get("input_per_1m", GPT6_LUNA_INPUT_PRICE_PER_1M)
                    ),
                    "cached_input_per_1m": float(
                        entry.get(
                            "cached_input_per_1m", GPT6_LUNA_CACHED_INPUT_PRICE_PER_1M
                        )
                    ),
                    "cache_write_per_1m": float(
                        entry.get(
                            "cache_write_per_1m", GPT6_LUNA_CACHE_WRITE_PRICE_PER_1M
                        )
                    ),
                    "output_per_1m": float(
                        entry.get("output_per_1m", GPT6_LUNA_OUTPUT_PRICE_PER_1M)
                    ),
                }
        except Exception:
            pass
    return {
        "input_per_1m": GPT6_LUNA_INPUT_PRICE_PER_1M,
        "cached_input_per_1m": GPT6_LUNA_CACHED_INPUT_PRICE_PER_1M,
        "cache_write_per_1m": GPT6_LUNA_CACHE_WRITE_PRICE_PER_1M,
        "output_per_1m": GPT6_LUNA_OUTPUT_PRICE_PER_1M,
    }


def compute_gpt6_luna_usage_and_cost(
    raw_usage: dict[str, Any] | None,
    fallback_input_text: str = "",
    fallback_output_text: str = "",
    model_name: str = "gpt-6-luna",
) -> tuple[dict[str, int], dict[str, float]]:
    """
    Converts provider usage into Langfuse mutually-exclusive usage_details buckets and
    computes exact USD cost_details using the pricing registry in src/model_pricing.json.
    """
    rates = get_model_pricing(model_name)
    usage = raw_usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )

    prompt_details = usage.get("prompt_tokens_details") or {}
    if not isinstance(prompt_details, dict):
        prompt_details = {}

    cached_tokens = int(
        prompt_details.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
        or usage.get("input_cached_tokens")
        or 0
    )
    cache_write_tokens = int(
        prompt_details.get("cache_write_tokens")
        or prompt_details.get("cache_creation_tokens")
        or usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_tokens")
        or 0
    )

    if prompt_tokens == 0 and fallback_input_text:
        prompt_tokens = max(1, len(fallback_input_text) // 4)
    if completion_tokens == 0 and fallback_output_text:
        completion_tokens = max(1, len(fallback_output_text) // 4)

    # Convert inclusive prompt_tokens into mutually exclusive buckets per Langfuse contract
    non_cached_input = max(0, prompt_tokens - cached_tokens - cache_write_tokens)
    total_tokens = (
        non_cached_input + cached_tokens + cache_write_tokens + completion_tokens
    )

    usage_details: dict[str, int] = {
        "input": non_cached_input,
        "output": completion_tokens,
        "total": total_tokens,
    }
    if cached_tokens > 0:
        usage_details["input_cached_tokens"] = cached_tokens
    if cache_write_tokens > 0:
        usage_details["cache_write_tokens"] = cache_write_tokens

    input_cost = round(
        non_cached_input * (rates["input_per_1m"] / 1_000_000.0), 10
    )
    cached_cost = round(
        cached_tokens * (rates["cached_input_per_1m"] / 1_000_000.0), 10
    )
    cache_write_cost = round(
        cache_write_tokens * (rates["cache_write_per_1m"] / 1_000_000.0), 10
    )
    output_cost = round(
        completion_tokens * (rates["output_per_1m"] / 1_000_000.0), 10
    )
    total_cost = round(
        input_cost + cached_cost + cache_write_cost + output_cost, 10
    )

    cost_details: dict[str, float] = {
        "input": input_cost,
        "output": output_cost,
        "total": total_cost,
    }
    if cached_tokens > 0:
        cost_details["input_cached_tokens"] = cached_cost
    if cache_write_tokens > 0:
        cost_details["cache_write_tokens"] = cache_write_cost

    return usage_details, cost_details


TOOLS_LIST: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_financial_data",
            "description": "Fetches exact financial facts (e.g., 'Revenues', 'NetIncomeLoss', 'OperatingIncomeLoss', 'Assets', 'Liabilities', 'StockholdersEquity', 'OperatingCashFlow', 'FreeCashFlow') for a given company and year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol, e.g., AAPL",
                    },
                    "concept": {
                        "type": "string",
                        "description": "The financial concept to fetch, e.g., Revenues, NetIncomeLoss, Assets, Liabilities",
                    },
                    "year": {
                        "type": "string",
                        "description": "The year of the financial data, e.g., '2024'",
                    },
                },
                "required": ["ticker", "concept", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_filings",
            "description": "Performs a hybrid semantic + lexical search over SEC filings (10-K, 10-Q) to retrieve narrative chunks and section summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "ticker": {
                        "type": "string",
                        "description": "Optional stock ticker symbol filter, e.g., AAPL",
                    },
                    "year": {
                        "type": "string",
                        "description": "Optional year filter, e.g., '2024'",
                    },
                    "section": {
                        "type": "string",
                        "description": "Optional section filter (e.g., 'Item 1', 'Item 1A', 'Item 7', 'Item 7A')",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Safely evaluates simple arithmetic expressions (+, -, *, /, %, ()).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '(383285000000 - 394328000000) / 394328000000 * 100'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

TOOL_FUNCTIONS: dict[str, Any] = {
    "get_financial_data": get_financial_data,
    "search_filings": search_filings,
    "calculator": calculator,
}


def load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "system.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_json(content: str) -> dict[str, Any]:
    """Extracts a JSON object from raw model output, handling markdown fences or surrounding text."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise json.JSONDecodeError("Could not parse JSON object", text, 0)


def _call_llm(
    messages: list[dict[str, Any]],
    use_tools: bool = True,
    provider: str | None = None,
    model: str | None = None,
    tools_override: list[dict[str, Any]] | None = None,
    obs_name: str = "llm_chat_completion",
) -> tuple[dict[str, Any], str]:
    """
    Calls the configured LLM provider (OpenAI-compatible endpoint with gpt-6-luna by default,
    or Groq) and records a child generation in Langfuse with exact usage_details and cost_details.
    """
    active_provider = (provider or LLM_PROVIDER).lower()
    lf = _get_langfuse()
    active_tools = tools_override if tools_override is not None else TOOLS_LIST

    if active_provider == "openai" and OPENAI_KEY:
        active_model = model or OPENAI_MODEL
        url = f"{OPENAI_URL}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "temperature": 0.0,
        }
        if use_tools and active_tools:
            payload["tools"] = active_tools
            payload["tool_choice"] = "auto"

        session = _get_http_session()
        last_err: Exception | None = None
        with _obs_context(
            lf,
            as_type="generation",
            name=obs_name,
            model=active_model,
            input=messages,
            model_parameters={"temperature": 0.0, "use_tools": use_tools},
        ) as gen:
            for attempt in range(2):
                try:
                    resp = session.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {OPENAI_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=LLM_TIMEOUT,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    raw_usage = data.get("usage")
                    result_msg: dict[str, Any] = {
                        "content": msg.get("content") or "",
                        "tool_calls": msg.get("tool_calls") or [],
                    }
                    usage_details, cost_details = compute_gpt6_luna_usage_and_cost(
                        raw_usage,
                        fallback_input_text=json.dumps(messages),
                        fallback_output_text=json.dumps(result_msg),
                        model_name=active_model,
                    )
                    result_msg["_usage_details"] = usage_details
                    result_msg["_cost_details"] = cost_details

                    if gen is not None:
                        try:
                            gen.update(
                                output={
                                    "content": result_msg["content"],
                                    "tool_calls": result_msg["tool_calls"],
                                },
                                usage_details=usage_details,
                                cost_details=cost_details,
                            )
                        except Exception:
                            pass
                    return result_msg, active_model
                except Exception as e:
                    last_err = e
                    if attempt == 0:
                        time.sleep(1.0)

        if not GROQ_API_KEY:
            raise RuntimeError(f"OpenAI call failed: {last_err}")

    # Groq provider (primary if configured, or automatic fallback)
    active_model = (
        model if (model and active_provider == "groq") else GROQ_MODEL
    )
    groq_client = _get_groq_client()
    kwargs: dict[str, Any] = {
        "model": active_model,
        "messages": messages,
        "timeout": GROQ_TIMEOUT,
        "temperature": 0.0,
    }
    if use_tools and active_tools:
        kwargs["tools"] = active_tools
        kwargs["tool_choice"] = "auto"
        kwargs["parallel_tool_calls"] = False

    with _obs_context(
        lf,
        as_type="generation",
        name=obs_name,
        model=active_model,
        input=messages,
    ) as gen:
        response = groq_client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        normalized_tool_calls: list[dict[str, Any]] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                normalized_tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )
        result_msg = {
            "content": message.content or "",
            "tool_calls": normalized_tool_calls,
        }
        raw_groq_usage = None
        if getattr(response, "usage", None) is not None:
            raw_groq_usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
            }
        usage_details, cost_details = compute_gpt6_luna_usage_and_cost(
            raw_groq_usage,
            fallback_input_text=json.dumps(messages),
            fallback_output_text=json.dumps(result_msg),
            model_name=active_model,
        )
        result_msg["_usage_details"] = usage_details
        result_msg["_cost_details"] = cost_details
        if gen is not None:
            try:
                gen.update(
                    output={
                        "content": result_msg["content"],
                        "tool_calls": result_msg["tool_calls"],
                    },
                    usage_details=usage_details,
                    cost_details=cost_details,
                )
            except Exception:
                pass
        return result_msg, active_model


def perform_fallback_rag(
    question: str,
    ticker: str,
    system_prompt: str,
    reason: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    chunks = search_filings(query=question, ticker=ticker, k=5)
    context_str = "\n".join(
        [
            f"Chunk ID {c.get('chunk_id')} ({c.get('year')} {c.get('section', '')}):\n{c.get('chunk_text')}"
            for c in chunks
        ]
    )

    fallback_prompt = f"""
You encountered an issue while trying to use tools: {reason}

We have automatically fetched the following context from {ticker}'s filings for you:
{context_str}

Please try to answer the user's question using ONLY this context. If the answer is not here, cleanly state that the information is unavailable. Remember to output ONLY a strictly formatted JSON object matching the requested schema.
"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Context Ticker: {ticker}\nQuestion: {question}\n\n{fallback_prompt}",
        },
    ]
    try:
        msg, active_model = _call_llm(
            messages=messages, use_tools=False, provider=provider, model=model
        )
        content = msg.get("content") or "{}"
        parsed = _extract_json(content)
        mock_history = {"fallback_search": chunks}
        parsed = verify_citations(parsed, mock_history)
        parsed["used_tools"] = ["search_filings"]
        parsed["model"] = active_model
        parsed["cost_usd"] = (msg.get("_cost_details") or {}).get("total", 0.0)
        return parsed
    except Exception as e:
        return {"error": f"Fallback RAG failed: {str(e)}"}


def process_query(
    question: str,
    ticker: str = DEFAULT_TICKER,
    history: list[dict[str, str]] | None = None,
    provider: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Process query using LLM and tools with multi-turn support, citation verification,
    self-correction loop on guard failure, and full Langfuse v4 tracing + cost tracking.
    """
    start_time = time.time()
    ticker = (ticker or DEFAULT_TICKER).upper().strip()

    try:
        system_prompt = load_system_prompt()
    except Exception as e:
        return {"error": f"Failed to load system prompt: {e}"}

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]

    if history:
        for turn in history[-6:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append(
        {"role": "user", "content": f"Context Ticker: {ticker}\nQuestion: {question}"}
    )

    tool_results_history: dict[str, Any] = {}
    used_tools: list[str] = []
    tool_trace: list[dict[str, Any]] = []
    self_correction_count = 0
    total_cost_usd = 0.0
    active_model_used = model or (
        OPENAI_MODEL if LLM_PROVIDER == "openai" else GROQ_MODEL
    )

    lf = _get_langfuse()
    trace_url: str | None = None

    with _obs_context(
        lf,
        as_type="agent",
        name="companyscope_query",
        input={"question": question, "ticker": ticker},
    ) as root_span, propagate_trace_attributes(
        lf,
        session_id=session_id,
        user_id=user_id,
        tags=["company-scope", "single-agent", f"ticker:{ticker}"],
        trace_name="companyscope_query",
    ):
        if lf is not None:
            try:
                trace_url = lf.get_trace_url()
            except Exception:
                trace_url = None

        for _iteration in range(6):
            try:
                message, active_model_used = _call_llm(
                    messages=messages,
                    use_tools=True,
                    provider=provider,
                    model=model,
                )
                total_cost_usd += float(
                    (message.get("_cost_details") or {}).get("total", 0.0)
                )

                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                    messages.append(assistant_msg)

                    for tool_call in tool_calls:
                        tc_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                        func_info = tool_call.get("function") or {}
                        func_name = func_info.get("name", "")
                        raw_args = func_info.get("arguments", "{}")
                        used_tools.append(func_name)

                        try:
                            func_args = (
                                json.loads(raw_args)
                                if isinstance(raw_args, str)
                                else dict(raw_args)
                            )
                        except json.JSONDecodeError:
                            func_args = {}

                        obs_type = (
                            "retriever" if func_name == "search_filings" else "tool"
                        )
                        with _obs_context(
                            lf,
                            as_type=obs_type,
                            name=f"tool:{func_name}",
                            input=func_args,
                        ) as tool_span:
                            if func_name in TOOL_FUNCTIONS:
                                func = TOOL_FUNCTIONS[func_name]
                                try:
                                    result = func(**func_args)
                                    tool_results_history[tc_id] = result
                                    tool_result = json.dumps(result)
                                except Exception as e:
                                    result = {"error": str(e)}
                                    tool_result = json.dumps(result)
                            else:
                                result = {"error": f"Tool '{func_name}' not found."}
                                tool_result = json.dumps(result)

                            if tool_span is not None:
                                try:
                                    tool_span.update(output=result)
                                except Exception:
                                    pass

                        tool_trace.append(
                            {
                                "tool": func_name,
                                "arguments": func_args,
                                "result": result,
                            }
                        )

                        messages.append(
                            {
                                "tool_call_id": tc_id,
                                "role": "tool",
                                "name": func_name,
                                "content": tool_result,
                            }
                        )
                else:
                    content = message.get("content") or "{}"
                    try:
                        parsed = _extract_json(content)
                        if all(
                            k in parsed
                            for k in ["answer", "citations", "needs_clarification"]
                        ):
                            _valid_cits, invalid_cits = check_citations(
                                parsed, tool_results_history
                            )
                            if invalid_cits and self_correction_count < 1:
                                self_correction_count += 1
                                with _obs_context(
                                    lf,
                                    as_type="guardrail",
                                    name="guard:self_correction",
                                    input={"invalid_citations": invalid_cits},
                                ) as sc_span:
                                    if sc_span is not None:
                                        try:
                                            sc_span.update(
                                                output={
                                                    "status": "re-prompting_agent_to_fix_citations"
                                                }
                                            )
                                        except Exception:
                                            pass

                                tool_trace.append(
                                    {
                                        "tool": "citation_guard_self_correction",
                                        "arguments": {
                                            "attempt": self_correction_count
                                        },
                                        "result": {
                                            "invalid_citations": invalid_cits
                                        },
                                    }
                                )
                                messages.append(
                                    {"role": "assistant", "content": content}
                                )
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "CITATION GUARD VERIFICATION FAILED for the following citations:\n"
                                            f"{json.dumps(invalid_cits, indent=2)}\n\n"
                                            "Please self-correct your JSON output immediately:\n"
                                            "1. Every narrative 'quote' MUST be an exact, contiguous verbatim substring copied character-for-character from the retrieved chunk_text in tool results.\n"
                                            "2. Every numeric citation MUST match a concept and year fetched via get_financial_data, and its exact digits must appear in your 'answer'.\n"
                                            "3. Drop any unverified citation or replace its quote with an exact verbatim substring from chunk_text. Output ONLY the corrected JSON object."
                                        ),
                                    }
                                )
                                continue

                            parsed = verify_citations(parsed, tool_results_history)
                            parsed["used_tools"] = list(dict.fromkeys(used_tools))
                            parsed["tool_trace"] = tool_trace
                            parsed["self_corrections"] = self_correction_count
                            parsed["model"] = active_model_used
                            parsed["cost_usd"] = round(total_cost_usd, 6)
                            parsed["latency_ms"] = round(
                                (time.time() - start_time) * 1000
                            )
                            if trace_url:
                                parsed["trace_url"] = trace_url

                            if root_span is not None:
                                try:
                                    root_span.update(
                                        output={
                                            "answer": parsed.get("answer"),
                                            "citations": parsed.get("citations"),
                                            "used_tools": parsed.get("used_tools"),
                                            "cost_usd": parsed.get("cost_usd"),
                                        }
                                    )
                                except Exception:
                                    pass
                            if lf is not None:
                                try:
                                    lf.flush()
                                except Exception:
                                    pass

                            return parsed
                        else:
                            err_out = {
                                "error": "Invalid JSON schema: missing required keys.",
                                "raw": content,
                            }
                            if root_span is not None:
                                try:
                                    root_span.update(output=err_out)
                                except Exception:
                                    pass
                            return err_out
                    except json.JSONDecodeError:
                        err_out = {
                            "error": "Model failed to output valid JSON.",
                            "raw": content,
                        }
                        if root_span is not None:
                            try:
                                root_span.update(output=err_out)
                            except Exception:
                                pass
                        return err_out

            except Exception as e:
                err_str = str(e)
                if "failed_generation" in err_str and "<function=" in err_str:
                    match = re.search(
                        r"<function=([a-zA-Z0-9_]+)(\{.*?\})</function>", err_str
                    )
                    if match:
                        func_name = match.group(1)
                        func_args_str = match.group(2)
                        used_tools.append(func_name)

                        try:
                            func_args = json.loads(func_args_str)
                        except json.JSONDecodeError:
                            func_args = {}

                        if func_name in TOOL_FUNCTIONS:
                            func = TOOL_FUNCTIONS[func_name]
                            try:
                                result = func(**func_args)
                                fake_id = "call_" + str(uuid.uuid4())[:8]
                                tool_results_history[fake_id] = result
                                tool_result = json.dumps(result)
                            except Exception as ex:
                                tool_result = json.dumps({"error": str(ex)})
                        else:
                            tool_result = json.dumps(
                                {"error": f"Tool '{func_name}' not found."}
                            )

                        messages.append(
                            {
                                "role": "user",
                                "content": f"You tried to call the tool '{func_name}' with arguments {func_args_str}. The result is: {tool_result}\nNow, please use this information to provide the final JSON answer or make another tool call.",
                            }
                        )
                        continue
                else:
                    fb_res = perform_fallback_rag(
                        question,
                        ticker,
                        system_prompt,
                        f"Agent loop encountered an error: {err_str}",
                        provider=provider,
                        model=model,
                    )
                    if trace_url:
                        fb_res["trace_url"] = trace_url
                    if root_span is not None:
                        try:
                            root_span.update(output=fb_res)
                        except Exception:
                            pass
                    if lf is not None:
                        try:
                            lf.flush()
                        except Exception:
                            pass
                    return fb_res

        fb_res = perform_fallback_rag(
            question,
            ticker,
            system_prompt,
            "Max iterations (6) reached without a final answer.",
            provider=provider,
            model=model,
        )
        if trace_url:
            fb_res["trace_url"] = trace_url
        if root_span is not None:
            try:
                root_span.update(output=fb_res)
            except Exception:
                pass
        if lf is not None:
            try:
                lf.flush()
            except Exception:
                pass
        return fb_res
