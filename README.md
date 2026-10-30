# CompanyScope

**Zero-Hallucination Multi-Agent Financial Analyst for SEC Filings, XBRL, Earnings & Market Sentiment**

CompanyScope is an agentic financial research platform that synthesizes primary SEC `10-K`, `10-Q`, and `8-K` (Exhibit `99.1`) filings, authoritative XBRL financial statements, earnings commentary, and live public market sentiment (Reddit & Yahoo Finance) to answer equity research questions with **100% verified citations**. Every numeric figure is cross-checked against structured SEC EDGAR XBRL facts, and every narrative, earnings, or sentiment claim is fuzzy-verified against retrieved source text before reaching the user.

<img width="2803" height="1550" alt="CompanyScope Analyst Workspace" src="https://github.com/user-attachments/assets/65d9f1d7-b6ed-4235-b103-b0175dbac471" />

---

## Key Capabilities

- **Native Multi-Agent Supervisor (`src/multi_agent.py`)**
  - Routes queries dynamically via `classify_needed_specialists` across three concurrent specialists—**Quantitative** (`get_financial_data` + AST `calculator`), **Qualitative** (`search_filings` + `get_earnings_transcripts`), and **Market Sentiment** (`get_market_sentiment`)—via `ThreadPoolExecutor`.
  - Supports **Multi-Company Peer Comparison** across up to 4 tickers in parallel (`/compare` and `/ask`).
- **Hybrid RAG + RAPTOR-Lite Filing Retrieval (`src/ingest.py`, `src/embed.py`, `src/tools.py`)**
  - Extracts narrative sections across `10-K` (`Item 1`, `1A`, `7`, `7A`), `10-Q` (`Item 1A`, `2`), and `8-K` (`Item 2.02` + Exhibit `99.1` earnings releases, `1.01`, `5.02`, `7.01`, `8.01`) while preserving compact financial/segment HTML tables as inline Markdown.
  - Builds collision-free accession chunk IDs across granular leaf chunks (`chunk_level="leaf"`) and hierarchical **RAPTOR-lite verbatim section summaries** (`chunk_level="summary"`).
  - Combines **ChromaDB** dense vector embeddings (`all-MiniLM-L6-v2`) with **`rank-bm25`** lexical search via **Reciprocal Rank Fusion (RRF)**, with automatic on-demand ingestion for unindexed tickers.
- **Authoritative XBRL Pipeline & Exact Arithmetic (`src/tools.py`)**
  - Two-tier XBRL lookup across `10-K` (with `10-Q` fallback) balance sheet, income statement, cash flow statement, product/geographic segments, and derived Free Cash Flow (`OperatingCashFlow - CapEx`) via `edgartools`.
  - Performs deterministic growth, margin, and ratio calculations via an AST-validated `calculator` tool—never relying on LLM mental math.
- **Earnings Commentary & Public Market Sentiment (`src/tools.py`)**
  - **4-Tier Earnings Cascade (`get_earnings_transcripts`):** Queries FMP and Finnhub call transcripts when API keys are present, automatically falling back to indexed and live SEC EDGAR `8-K` Item `2.02` / Exhibit `99.1` releases ranked by `BM25`.
  - **Zero-Key Sentiment & News (`get_market_sentiment`):** Aggregates retail investor discussions from Reddit (`r/stocks`, `r/investing`, `r/wallstreetbets`) alongside Yahoo Finance search news and headline RSS feeds.
- **Self-Correcting Citation Guard (`src/guard.py`)**
  - Validates `numeric`, `narrative`, `earnings`, and `sentiment` citations using `rapidfuzz` (`partial_ratio >= 88.0`) and significant-digit verification against retrieved tool outputs.
  - Automatically enters a **self-correction retry loop** with exact failure feedback if any citation fails verification.
- **Langfuse v4 Observability & Cost Management (`src/config.py`, `scripts/manage_model_pricing.py`)**
  - Full OpenTelemetry hierarchical tracing across `agent`, `generation`, `retriever`, `tool`, and `guardrail` spans.
  - Built-in model pricing registry (`src/model_pricing.json`) with tiered token accounting (`input`, `input_cached_tokens`, `cache_write_tokens`, `output`) and an interactive CLI to sync custom models and backfill historical Langfuse traces.

---

## System Architecture

```mermaid
flowchart TD
    User["Analyst Query (Single Ticker or Peer Comparison)"] --> API["FastAPI Backend (/ask, /compare)"]
    API --> Mode{"Orchestration Mode"}

    Mode -- "mode = multi_agent | auto" --> Sup["Supervisor Router (classify_needed_specialists)"]
    Mode -- "mode = single" --> Single["Unified ReAct Agent (src/agent.py)"]

    Sup --> Pool["Concurrent ThreadPoolExecutor (Per Ticker & Specialist)"]
    Pool --> Quant["Quant Specialist (get_financial_data + calculator)"]
    Pool --> Qual["Qual Specialist (search_filings + get_earnings_transcripts)"]
    Pool --> Sent["Sentiment Specialist (get_market_sentiment)"]

    Quant --> XBRL["SEC EDGAR XBRL Statements & Segments"]
    Quant --> Calc["AST Safe Calculator"]
    Qual --> RRF["Hybrid RAG (ChromaDB Dense + BM25 RRF + RAPTOR-lite)"]
    Qual --> Earn["FMP / Finnhub / SEC 8-K Ex. 99.1 Earnings"]
    Sent --> Mkt["Reddit (r/stocks, r/investing, r/wallstreetbets) + Yahoo Finance"]

    Single --> XBRL & Calc & RRF & Earn & Mkt

    Quant & Qual & Sent --> Synth["Lead Financial Synthesizer"]
    Single --> Guard["Citation Guard (src/guard.py)"]
    Synth --> Guard

    Guard -- "Failed Citations (Self-Correction)" --> Synth
    Guard -- "100% Verified" --> Output["Verified Answer + Sub-Agent Reports + Langfuse v4 Trace"]
```

---

## Project Structure

```text
company-scope/
├── src/
│   ├── app.py                  # FastAPI server (/health, /tickers, /ingest, /financials, /compare, /ask)
│   ├── agent.py                # Single-agent tool-calling loop with Citation Guard retry
│   ├── multi_agent.py          # Multi-Agent Supervisor (Quant, Qual & Sentiment + peer comparison)
│   ├── tools.py                # XBRL, Hybrid RAG, 8-K/earnings transcripts, sentiment & AST calculator
│   ├── guard.py                # RapidFuzz narrative/earnings/sentiment & XBRL numeric citation verifier
│   ├── ingest.py               # SEC EDGAR 10-K/10-Q/8-K (Ex. 99.1) parser, inline tables, RAPTOR-lite
│   ├── embed.py                # ChromaDB indexer with collision-free accession chunk IDs
│   ├── config.py               # Unified settings, Langfuse v4 helpers, and cost computation
│   └── model_pricing.json      # Per-1M token pricing registry (input, cached, cache write, output)
├── prompts/
│   └── system.txt              # Grounded financial analyst system prompt
├── scripts/
│   ├── manage_model_pricing.py # CLI/interactive tool to update model rates & backfill Langfuse
│   ├── backfill_langfuse_costs.py
│   └── check_thresholds.py     # CI evaluation pass-rate gate (>= 90%)
├── tests/
│   ├── eval_data.yaml          # Golden evaluation dataset
│   ├── test_eval.py            # End-to-end golden evaluation benchmark (15 test cases)
│   └── test_data_sources.py    # Unit & E2E tests for XBRL, 8-K earnings, sentiment & guard
├── streamlit_app.py            # Streamlit Analyst Workspace UI
├── Dockerfile                  # Multi-service container image
├── docker-compose.yml          # FastAPI + Streamlit orchestration
└── Makefile                    # Developer workflow shortcuts
```

---

## Quickstart

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/iamqazolp/CompanyScope.git
cd CompanyScope
uv sync
```

### 2. Configure Environment Variables (`.env`)
Create a `.env` file in the repository root:
```env
# Primary OpenAI-compatible LLM endpoint
OPENAI_URL=https://api.shopaikey.com
OPENAI_KEY=your_openai_api_key
OPENAI_MODEL=gpt-6-luna

# SEC EDGAR identity (required by SEC fair-access policy)
EDGAR_IDENTITY=your_email@example.com
DEFAULT_TICKER=AAPL

# Optional: Earnings Call Transcript Providers (falls back to SEC 8-K Ex. 99.1)
FMP_API_KEY=
FINNHUB_API_KEY=

# Optional: Langfuse v4 Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

### 3. Ingest SEC Filings & Build the Hybrid Index
```bash
make ingest   # Downloads 10-K/10-Q/8-K (Ex. 99.1) filings and builds RAPTOR-lite + leaf chunks
make index    # Indexes chunks into ChromaDB
```

### 4. Launch the Backend & Analyst Workspace
```bash
# Terminal 1 — FastAPI Backend (http://localhost:8000)
make api

# Terminal 2 — Streamlit Analyst Dashboard (http://localhost:8501)
make ui
```

Or run both services via **Docker Compose**:
```bash
docker compose up --build
```

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Active LLM provider, model, Langfuse status, and service health |
| `GET` | `/tickers` | Indexed tickers, chunk counts, filing years, and sections in ChromaDB |
| `POST` | `/ingest` | On-demand SEC EDGAR download (`10-K`/`10-Q`/`8-K`) and ChromaDB indexing for any ticker |
| `GET` | `/financials/{ticker}` | Multi-year structured `10-K` XBRL financial metrics for charting |
| `POST` | `/compare` | Concurrent multi-agent peer comparison across multiple tickers |
| `POST` | `/ask` | Run a `single`, `multi_agent`, or `auto` query across one or more tickers |

### Example `POST /ask` Request (Multi-Agent Peer Comparison)
```json
{
  "question": "Compare revenue growth, key supply chain risks, and recent market sentiment between Apple and Microsoft.",
  "ticker": "AAPL",
  "tickers": ["AAPL", "MSFT"],
  "mode": "multi_agent",
  "provider": "openai"
}
```

---

## Model Pricing & Langfuse Cost Backfill

CompanyScope includes a CLI and interactive wizard ([`scripts/manage_model_pricing.py`](scripts/manage_model_pricing.py)) to manage custom model token rates in [`src/model_pricing.json`](src/model_pricing.json), sync them to Langfuse, and backfill historical `GENERATION` observations via OpenTelemetry OTLP:

```bash
# Interactive wizard
make pricing

# Non-interactive CLI update + historical backfill
python -m scripts.manage_model_pricing \
  --model gpt-6-luna \
  --input 0.10 \
  --cached-input 0.01 \
  --cache-write 0.125 \
  --output 0.50 \
  --backfill

# List all configured models and pricing tiers
python -m scripts.manage_model_pricing --list
```

---

## Evaluation & Quality Checks

Run Ruff linting, MyPy static type checking, data-source & guardrail tests, and the 15-case golden evaluation suite (`>= 90%` pass-rate gate):

```bash
make lint
make typecheck
make test
make eval
```

---

Built by **Dang Quan**
