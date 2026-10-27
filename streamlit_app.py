import os
import uuid
from typing import Any

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="CompanyScope | SEC Financial Analyst",
    page_icon="📊",
    layout="wide",
)

DEFAULT_API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

st.markdown(
    """
    <style>
    .metric-pill {
        display: inline-block;
        padding: 3px 10px;
        margin-right: 6px;
        margin-bottom: 6px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        background-color: rgba(59, 130, 246, 0.14);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.3);
    }
    .citation-card-num {
        padding: 10px 14px;
        border-left: 4px solid #3b82f6;
        background-color: rgba(59, 130, 246, 0.08);
        border-radius: 6px;
        margin-bottom: 8px;
    }
    .citation-card-nar {
        padding: 10px 14px;
        border-left: 4px solid #10b981;
        background-color: rgba(16, 185, 129, 0.08);
        border-radius: 6px;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_backend_status(base_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    health_data: dict[str, Any] = {}
    index_data: dict[str, Any] = {}
    try:
        r_health = requests.get(f"{base_url}/health", timeout=3)
        if r_health.ok:
            health_data = r_health.json()
        r_tickers = requests.get(f"{base_url}/tickers", timeout=5)
        if r_tickers.ok:
            index_data = r_tickers.json()
    except Exception:
        pass
    return health_data, index_data


if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{uuid.uuid4().hex[:12]}"
if "current_query" not in st.session_state:
    st.session_state.current_query = None
if "financials_cache" not in st.session_state:
    st.session_state.financials_cache = {}

with st.sidebar:
    st.title("📊 CompanyScope")
    st.caption("Zero-Hallucination SEC Filing & XBRL Financial Intelligence")

    api_base = st.text_input("Backend API Base URL", value=DEFAULT_API_BASE).rstrip("/")
    health_info, index_info = fetch_backend_status(api_base)

    if health_info.get("status") == "ok":
        active_prov = health_info.get("provider", "openai").upper()
        active_mod = health_info.get("model", "gpt-6-luna")
        lf_status = " • 🔭 Langfuse Active" if health_info.get("langfuse_enabled") else ""
        st.success(f"Backend Online • **{active_prov}** (`{active_mod}`){lf_status}")
    else:
        st.error("Backend Offline — start with `uvicorn src.app:app --reload`")

    st.divider()

    st.subheader("🏢 Target Companies")
    indexed_tickers = list((index_info.get("tickers") or {}).keys())
    default_ticker_str = indexed_tickers[0] if indexed_tickers else "AAPL"
    ticker = st.text_input("Primary Ticker Symbol", value=default_ticker_str).upper().strip()
    peer_tickers_input = st.text_input(
        "Peer Comparison Tickers (optional, comma-separated)",
        value="",
        placeholder="e.g. MSFT, NVDA",
    )

    ticker_stats = (index_info.get("tickers") or {}).get(ticker)
    if ticker_stats:
        yrs = ", ".join(str(y) for y in ticker_stats.get("years", []))
        st.caption(
            f"✅ **{ticker}** indexed: **{ticker_stats.get('chunks', 0)}** chunks "
            f"(Years: {yrs})"
        )
    else:
        st.caption(
            f"ℹ️ **{ticker}** has no narrative chunks indexed yet. "
            "XBRL numeric lookup works immediately; ingest filings below for narrative RAG."
        )

    with st.expander("📥 Ingest SEC Filings (On-Demand)"):
        ingest_years = st.multiselect(
            "Filing Years (10-K / 10-Q)",
            options=[2020, 2021, 2022, 2023, 2024, 2025, 2026],
            default=[2022, 2023, 2024, 2025],
        )
        if st.button(f"Download & Index {ticker}", use_container_width=True):
            with st.spinner(
                f"Downloading {ticker} SEC filings & building Hybrid + RAPTOR-lite index..."
            ):
                try:
                    resp = requests.post(
                        f"{api_base}/ingest",
                        json={"ticker": ticker, "years": ingest_years},
                        timeout=300,
                    )
                    if resp.ok and "error" not in resp.json():
                        res_data = resp.json()
                        st.success(
                            f"Indexed {res_data.get('chunks_indexed', 0)} chunks "
                            f"from {res_data.get('filings_processed', 0)} filings!"
                        )
                        st.rerun()
                    else:
                        st.error(f"Ingestion failed: {resp.text}")
                except Exception as ex:
                    st.error(f"Failed to connect to backend: {ex}")

    st.divider()

    st.subheader("🧠 Agent & Model Settings")
    agent_mode_label = st.selectbox(
        "Orchestration Mode",
        options=[
            "Auto (Multi-Agent on Peer Queries)",
            "Multi-Agent Supervisor (Parallel Quant + Qual Sub-Agents)",
            "Single Agent",
        ],
        index=0,
    )
    provider_choice = st.selectbox(
        "LLM Provider",
        options=[
            "Default (Configured)",
            "openai (gpt-6-luna)",
        ],
        index=0,
    )
    multi_turn_enabled = st.toggle("Multi-Turn Conversation Context", value=True)
    st.caption(f"Session ID: `{st.session_state.session_id}`")

    st.divider()

    st.subheader("⚡ Analyst Prompt Library")
    if st.button("🤝 Compare AAPL vs MSFT 2023 Revenue", use_container_width=True):
        st.session_state.current_query = (
            "Compare Apple (AAPL) and Microsoft (MSFT) total revenue and net income in 2023."
        )
    if st.button(f"📈 {ticker} Revenue & Growth (2022–2023)", use_container_width=True):
        st.session_state.current_query = (
            f"Calculate {ticker}'s revenue growth from 2022 to 2023."
        )
    if st.button(f"🛡️ {ticker} Supply Chain & Cyber Risks", use_container_width=True):
        st.session_state.current_query = (
            f"What does {ticker} say about supply chain and cybersecurity risks?"
        )
    if st.button("🚫 Hallucination Guard Test", use_container_width=True):
        st.session_state.current_query = f"What is {ticker}'s secret car project?"

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = f"session_{uuid.uuid4().hex[:12]}"
        st.rerun()


def render_message_extras(msg: dict[str, Any]) -> None:
    """Renders metadata pills, sub-agent specialist reports, verified citations, and tool execution trace."""
    used_tools = msg.get("used_tools") or []
    citations = msg.get("citations") or []
    tool_trace = msg.get("tool_trace") or []
    sub_reports = msg.get("sub_agent_reports") or []
    self_corrections = msg.get("self_corrections", 0)
    model_used = msg.get("model")
    latency_ms = msg.get("latency_ms")

    pills_html = ""
    if model_used:
        pills_html += f'<span class="metric-pill">🤖 {model_used}</span>'
    if sub_reports:
        pills_html += (
            f'<span class="metric-pill">🕸️ {len(sub_reports)} Sub-Agents</span>'
        )
    if latency_ms is not None:
        pills_html += f'<span class="metric-pill">⏱️ {latency_ms / 1000:.1f}s</span>'
    cost_usd = msg.get("cost_usd")
    if cost_usd is not None and cost_usd > 0:
        pills_html += f'<span class="metric-pill">💰 ${cost_usd:.5f}</span>'
    if used_tools:
        pills_html += (
            f'<span class="metric-pill">🛠️ Tools: {", ".join(used_tools)}</span>'
        )
    pills_html += (
        f'<span class="metric-pill">✅ {len(citations)} Verified Citations</span>'
    )
    if self_corrections:
        pills_html += (
            f'<span class="metric-pill">🔄 {self_corrections} Guard Self-Correction</span>'
        )
    trace_url = msg.get("trace_url")
    if trace_url:
        pills_html += (
            f'<a href="{trace_url}" target="_blank" style="text-decoration:none;">'
            f'<span class="metric-pill">🔭 Langfuse Trace ↗</span></a>'
        )
    st.markdown(pills_html, unsafe_allow_html=True)

    if sub_reports:
        with st.expander(
            f"🕸️ Parallel Sub-Agent Specialist Reports ({len(sub_reports)} agents)"
        ):
            for rep in sub_reports:
                st.markdown(
                    f"**`{rep.get('agent')}`** ({rep.get('role', '').upper()} Specialist • "
                    f"Ticker: `{rep.get('ticker')}` • "
                    f"Citations: `{rep.get('citations_count', 0)}`)"
                )
                st.caption(rep.get("answer", ""))
                st.divider()

    if citations:
        with st.expander(f"📚 Verified Citations & Sources ({len(citations)})"):
            for idx, cit in enumerate(citations, 1):
                c_type = cit.get("type")
                if c_type == "numeric":
                    st.markdown(
                        f'<div class="citation-card-num">'
                        f"<strong>{idx}. XBRL Numeric Fact</strong> • "
                        f"<code>{cit.get('ticker')}</code> | "
                        f"Concept: <code>{cit.get('concept')}</code> | "
                        f"Period: <strong>{cit.get('year')}</strong>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                elif c_type == "narrative":
                    st.markdown(
                        f'<div class="citation-card-nar">'
                        f"<strong>{idx}. SEC Filing Quote</strong> • "
                        f"<code>{cit.get('ticker')}</code> | "
                        f"<strong>{cit.get('section')} ({cit.get('year')})</strong> | "
                        f"Chunk: <code>{cit.get('chunk_id')}</code><br/>"
                        f'<em>"{cit.get("quote")}"</em>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    if tool_trace:
        with st.expander(f"🔍 Agent Tool Execution Trace ({len(tool_trace)} calls)"):
            for step_idx, step in enumerate(tool_trace, 1):
                agent_tag = f"[{step.get('agent')}] " if step.get("agent") else ""
                st.markdown(
                    f"**Step {step_idx}: {agent_tag}`{step.get('tool')}`** — Args: `{step.get('arguments')}`"
                )
                st.json(step.get("result"), expanded=False)


tab_chat, tab_explorer = st.tabs(
    ["💬 AI Financial Analyst", "📊 Financial Snapshot & Filing Index"]
)

with tab_chat:
    st.markdown(
        f"### {ticker} Research Workspace\n"
        "Ask natural language questions or compare multiple public companies across SEC 10-K/10-Q filings and XBRL financials."
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and not message.get("is_error"):
                render_message_extras(message)

    user_input = st.chat_input(
        f"Ask about {ticker} or compare peers (e.g. 'Compare AAPL and MSFT 2023 revenue')..."
    )
    prompt = st.session_state.get("current_query") or user_input

    if prompt:
        st.session_state.current_query = None
        st.chat_message("user").markdown(prompt)

        history_payload: list[dict[str, str]] = []
        if multi_turn_enabled and st.session_state.messages:
            for m in st.session_state.messages[-6:]:
                history_payload.append(
                    {"role": m["role"], "content": str(m["content"])}
                )

        st.session_state.messages.append({"role": "user", "content": prompt})

        req_provider = None
        req_model = None
        if provider_choice.startswith("openai"):
            req_provider = "openai"
            req_model = "gpt-6-luna"

        if agent_mode_label.startswith("Multi-Agent"):
            req_mode = "multi_agent"
        elif agent_mode_label.startswith("Single"):
            req_mode = "single"
        else:
            req_mode = "auto"

        extra_tickers = [
            t.strip().upper()
            for t in peer_tickers_input.split(",")
            if t.strip()
        ]
        all_tickers = [ticker] + [t for t in extra_tickers if t != ticker]

        with st.chat_message("assistant"):
            with st.spinner(
                f"Running {req_mode.replace('_', '-')} financial analysis..."
            ):
                try:
                    response = requests.post(
                        f"{api_base}/ask",
                        json={
                            "question": prompt,
                            "ticker": ticker,
                            "tickers": all_tickers if len(all_tickers) > 1 else None,
                            "mode": req_mode,
                            "history": history_payload if history_payload else None,
                            "provider": req_provider,
                            "model": req_model,
                            "session_id": st.session_state.session_id,
                        },
                        timeout=180,
                    )

                    if response.status_code == 200:
                        data = response.json()

                        if "error" in data:
                            err_text = f"Agent encountered an error: {data['error']}"
                            st.error(err_text)
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": err_text,
                                    "is_error": True,
                                }
                            )
                        elif data.get("needs_clarification"):
                            clarification = data["needs_clarification"]
                            st.warning(f"**Clarification Needed:** {clarification}")
                            assistant_entry = {
                                "role": "assistant",
                                "content": clarification,
                                "citations": [],
                                "used_tools": data.get("used_tools", []),
                                "tool_trace": data.get("tool_trace", []),
                                "sub_agent_reports": data.get("sub_agent_reports", []),
                                "self_corrections": data.get("self_corrections", 0),
                                "cost_usd": data.get("cost_usd"),
                                "model": data.get("model"),
                                "latency_ms": data.get("latency_ms"),
                                "trace_url": data.get("trace_url"),
                            }
                            render_message_extras(assistant_entry)
                            st.session_state.messages.append(assistant_entry)
                        else:
                            answer = data.get("answer", "No answer provided.")
                            st.markdown(answer)
                            assistant_entry = {
                                "role": "assistant",
                                "content": answer,
                                "citations": data.get("citations", []),
                                "used_tools": data.get("used_tools", []),
                                "tool_trace": data.get("tool_trace", []),
                                "sub_agent_reports": data.get("sub_agent_reports", []),
                                "self_corrections": data.get("self_corrections", 0),
                                "cost_usd": data.get("cost_usd"),
                                "model": data.get("model"),
                                "latency_ms": data.get("latency_ms"),
                                "trace_url": data.get("trace_url"),
                            }
                            render_message_extras(assistant_entry)
                            st.session_state.messages.append(assistant_entry)

                    elif response.status_code == 429:
                        error_msg = "Rate limit exceeded! Please wait a moment."
                        st.error(error_msg)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": error_msg, "is_error": True}
                        )
                    else:
                        st.error(f"Server Error {response.status_code}: {response.text}")

                except requests.exceptions.ConnectionError:
                    st.error(
                        f"Failed to connect to the backend at {api_base}. Is the FastAPI server running?"
                    )

with tab_explorer:
    st.subheader(f"📈 {ticker} Multi-Year XBRL Financial Snapshot")
    st.caption(
        "Fetched directly from SEC EDGAR 10-K filings via `edgartools`."
    )

    col_btn, _col_info = st.columns([1, 3])
    with col_btn:
        load_fin = st.button(
            f"🔄 Load {ticker} Financials", use_container_width=True
        )

    if load_fin:
        with st.spinner(f"Fetching SEC 10-K XBRL financials for {ticker}..."):
            try:
                r_fin = requests.get(f"{api_base}/financials/{ticker}", timeout=60)
                if r_fin.ok and "financials" in r_fin.json():
                    st.session_state.financials_cache[ticker] = r_fin.json()[
                        "financials"
                    ]
                else:
                    st.error(f"Could not load financials: {r_fin.text}")
            except Exception as ex:
                st.error(f"Error fetching financials: {ex}")

    fin_rows = st.session_state.financials_cache.get(ticker)
    if fin_rows:
        df = pd.DataFrame(fin_rows)
        df["year"] = df["year"].astype(str)
        df_indexed = df.set_index("year")

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("##### Revenue vs. Net Income (USD)")
            cols_1 = [
                c
                for c in ["Revenue", "Net Income", "Operating Income"]
                if c in df_indexed.columns
            ]
            if cols_1:
                st.bar_chart(df_indexed[cols_1])
        with chart_col2:
            st.markdown("##### Assets vs. Liabilities (USD)")
            cols_2 = [
                c
                for c in ["Total Assets", "Total Liabilities"]
                if c in df_indexed.columns
            ]
            if cols_2:
                st.bar_chart(df_indexed[cols_2])

        st.markdown("##### Structured 10-K Financial Table (USD)")
        st.dataframe(df_indexed, use_container_width=True)
    else:
        st.info(
            f"Click **Load {ticker} Financials** above to pull multi-year 10-K XBRL metrics from EDGAR."
        )

    st.divider()
    st.subheader("🗂️ ChromaDB Vector & BM25 Index Coverage")
    tickers_map = index_info.get("tickers") or {}
    if tickers_map:
        coverage_rows = [
            {
                "Ticker": t,
                "Indexed Chunks (Leaf + RAPTOR Summaries)": info.get("chunks", 0),
                "Years Covered": ", ".join(str(y) for y in info.get("years", [])),
                "Filing Sections": ", ".join(info.get("sections", [])),
            }
            for t, info in tickers_map.items()
        ]
        st.dataframe(
            pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True
        )
    else:
        st.warning("No chunks currently indexed in ChromaDB.")
