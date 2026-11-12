# CompanyScope

**Zero-Hallucination Multi-Agent Financial Analyst for SEC Filings, XBRL, Live Market Multiples, TradingView Charts & Smart-Money Feeds**

CompanyScope is an agentic equity research terminal that synthesizes primary SEC `10-K`, `10-Q`, `8-K` (Exhibit `99.1`), and `Form 4` insider filings alongside authoritative XBRL financial statements, live TradingView equity quotes & valuation multiples, interactive TradingView OHLCV charts, and fresh multi-source market news & sentiment to answer equity research questions with **100% verified citations**. Every numeric or live market figure is cross-checked against structured SEC EDGAR XBRL facts or live market snapshots, and every narrative, earnings, insider, or news claim is fuzzy-verified against retrieved source text before reaching the user.

<img width="2803" height="1550" alt="CompanyScope Analyst Workspace" src="https://github.com/user-attachments/assets/65d9f1d7-b6ed-4235-b103-b0175dbac471" />

---

## Key Capabilities

- **Multi-Tier Agent Hierarchy (`src/multi_agent.py`, `src/tier_router.py`)**
  - **Tier-1 Frontier Supervisor & Synthesizer (`gpt-6.1-terra`):** Orchestrates cross-company planning and executive synthesis across all verified specialist findings.
  - **Tier-2 Fast Specialist Sub-Agents (`gpt-6-luna`):** Executes concurrent **Quantitative** (`get_financial_data` + `get_live_market_data` + AST `calculator`), **Qualitative** (`search_filings` + `get_earnings_transcripts` + `get_insider_and_events`), and **Market Sentiment** (`get_market_sentiment` + `get_insider_and_events`) tool loops via `ThreadPoolExecutor` at ~90% lower token cost.
  - **Dynamic Complexity & Guardrail Escalation:** Proactively upgrades demanding sub-tasks (multi-year CAGR/ROIC derivations, forensic accounting audits, cross-source contradiction synthesis, or 3+ peer cohorts) and Citation Guard self-correction retries from `gpt-6-luna` directly to `gpt-6.1-terra`.
  - Supports **Multi-Company Peer Comparison** across up to 4 tickers in parallel (`/compare`, `/ask`, and `/api/ask/stream` SSE).
- **All-Market Search, TradingView Multiples, Smart-Money Radar & 0-Quota Market Recap (`src/market.py`)**
  - **6,000+ US Equity Search & Live Movers (`/api/market/search`, `/api/market/movers`):** Instant ticker and company-name autocomplete (`⌘K`) across NASDAQ, NYSE, and AMEX, real-time `$ Value.Traded` market leaders strip, and dynamic sector peer suggestions (`+Peers`).
  - **Live Quotes & Valuation Multiples (`get_live_market_data`):** Fetches spot price, `1D %` move, `52-Week High/Low`, `Market Cap`, `Enterprise Value`, `Trailing & Forward P/E`, `EV/EBITDA`, sector classification, and Wall Street consensus target price & rating via TradingView's Scanner API (with Yahoo Finance fallback), cached for 5 minutes.
  - **SEC Form 4 Insider & Live 8-K Radar (`get_insider_and_events`):** Streams executive/director open-market buys & sales (`Code P` / `Code S`) from SEC EDGAR `Form 4` XML filings alongside recent `Form 8-K` material events via `edgartools`.
  - **0-Quota Daily Market News Recap (`/api/market/recap`):** Slim cross-asset live benchmark tape (`S&P 500`, `Nasdaq 100`, `Dow 30`, `US 10Y Yield`, `VIX`, `Bitcoin`) paired with a 30-minute cached, Citation-Guard-verified `gpt-6-luna` AI market briefing inside the dual-mode `SourceInspector`.
  - **3-Mode TradingView Chart & XBRL Financials Deck (`TradingViewChart.tsx`, `FinancialChart.tsx`):** Toggle seamlessly between **Live OHLCV Candlesticks & Volume** (`lightweight-charts` v4 across `1D`, `5D`, `1M`, `6M`, `1Y`, `5Y` with floating OHLCV HUD), **TradingView Studio** (isolated iframe technical studio with RSI/drawings), and an **Institutional 4-Statement SEC XBRL Workbench** (`Income`, `Balance Sheet`, `Cash Flow`, `Margins & ROE` across `Annual 10-K` and `Quarterly 10-Q` with 1-click `✨ Ask` AI row audits).
- **Hybrid RAG + RAPTOR-Lite Filing Retrieval (`src/ingest.py`, `src/embed.py`, `src/tools.py`)**
  - Extracts narrative sections across `10-K` (`Item 1`, `1A`, `7`, `7A`), `10-Q` (`Item 1A`, `2`), and `8-K` (`Item 2.02` + Exhibit `99.1` earnings releases, `1.01`, `5.02`, `7.01`, `8.01`) while preserving compact financial/segment HTML tables as inline Markdown.
  - Builds collision-free accession chunk IDs across granular leaf chunks (`chunk_level="leaf"`) and hierarchical **RAPTOR-lite verbatim section summaries** (`chunk_level="summary"`).
  - Combines **Neon `pgvector` + `tsvector`** (cloud), **ChromaDB + `rank-bm25`** (local), or **Zero-DB Serverless BM25** via **Reciprocal Rank Fusion (RRF)**, with automatic on-demand ingestion for unindexed tickers.
- **Authoritative Sub-Second XBRL Pipeline & Exact Arithmetic (`src/tools.py`)**
  - Extracts 5-year Annual (`10-K`) and 6-quarter (`10-Q`) multi-statement series in `~0.5s` via SEC EDGAR `CompanyFacts` (including non-December fiscal years and bank `RevenuesNetOfInterestExpense` accounting), plus granular `get_financial_data(..., year="latest")` statement & segment lookup via `edgartools`.
  - Performs deterministic growth, margin, and ratio calculations via an AST-validated `calculator` tool—never relying on LLM mental math.
- **Earnings Commentary & Fresh Multi-Source News (`src/tools.py`, `src/market.py`)**
  - **4-Tier Earnings Cascade (`get_earnings_transcripts`):** Queries FMP and Finnhub call transcripts when API keys are present, automatically falling back to indexed and live SEC EDGAR `8-K` Item `2.02` / Exhibit `99.1` releases ranked by `BM25`.
  - **Fresh 24h–7d News & Investor Pulse (`get_market_sentiment`):** Aggregates timestamped Google News `when:7d` RSS headlines, optional Finnhub 14d company news, Yahoo Finance search news, and fresh `t="month"` Reddit discussions across `r/stocks`, `r/investing`, `r/wallstreetbets`, and `r/SecurityAnalysis`, ranked by `BM25 + recency`.
- **Self-Correcting Citation Guard (`src/guard.py`)**
  - Validates `numeric`, `market`, `narrative`, `earnings`, `insider`, and `sentiment` citations using `rapidfuzz` (`partial_ratio >= 88.0`) and significant-digit / compact-unit (`$5.17T`, `37.73x`) verification against retrieved tool outputs.
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

    Mode -- "mode = multi_agent | auto" --> Sup["Tier-1 Supervisor Router (gpt-6.1-terra + src/tier_router.py)"]
    Mode -- "mode = single" --> Single["Tiered Single Agent (gpt-6-luna routine / gpt-6.1-terra demanding)"]

    Sup --> Pool["Concurrent ThreadPoolExecutor (Tier-2 gpt-6-luna default / Tier-1 gpt-6.1-terra escalation)"]
    Pool --> Quant["Quant Specialist (get_financial_data + get_live_market_data + calculator)"]
    Pool --> Qual["Qual Specialist (search_filings + get_earnings_transcripts + get_insider_and_events)"]
    Pool --> Sent["Sentiment Specialist (get_market_sentiment + get_insider_and_events)"]

    Quant --> XBRL["SEC EDGAR XBRL Statements & Segments"]
    Quant --> LiveQ["TradingView Live Quotes, Multiples & Targets"]
    Quant --> Calc["AST Safe Calculator"]
    Qual --> RRF["Hybrid RAG (Neon pgvector + tsvector RRF + RAPTOR-lite)"]
    Qual --> Earn["FMP / Finnhub / SEC 8-K Ex. 99.1 Earnings"]
    Qual & Sent --> Ins["SEC Form 4 Insider Trades & Live 8-K Radar"]
    Sent --> Mkt["Google News 7d RSS + Finnhub + Yahoo + Fresh Reddit"]

    Single --> XBRL & LiveQ & Calc & RRF & Earn & Ins & Mkt

    Quant & Qual & Sent --> Synth["Tier-1 Lead Financial Synthesizer (gpt-6.1-terra)"]
    Single --> Guard["Citation Guard (src/guard.py)"]
    Synth --> Guard

    Guard -- "Failed Citations (Escalate Retry to gpt-6.1-terra)" --> Synth
    Guard -- "100% Verified" --> Output["Verified Answer + Sub-Agent Reports + Langfuse v4 Trace"]
```

---

## Project Structure

```text
CompanyScope/
├── app/                        # Next.js 15 App Router (Home terminal & /report/[slug] permalinks)
├── components/                 # Research Terminal, TradingView OHLCV/Studio Deck, Market Recap Bar & Source Inspector
├── lib/                        # Shared TypeScript interfaces & financial formatters
├── api/
│   └── index.py                # Vercel Fluid Compute Python ASGI entrypoint (maxDuration: 300s)
├── src/
│   ├── app.py                  # FastAPI server (/api/ask/stream SSE, /market/*, /quota, /showcase, /reports)
│   ├── agent.py                # Tiered single-agent loop with SSE events & Terra guard escalation
│   ├── multi_agent.py          # Multi-Agent Supervisor (Tier-1 Terra Synth + Tier-2 Luna Sub-Agents)
│   ├── tier_router.py          # Complexity classifier & dynamic Luna -> Terra escalation router
│   ├── market.py               # TradingView quotes/multiples, Nasdaq/Yahoo OHLCV, Form 4 radar & AI market recap
│   ├── embeddings.py           # Cloud Gemini Embedding 2 (768-dim MRL) REST client
│   ├── db.py                   # Neon Postgres (pgvector + tsvector RRF, 5/day guest quota, market & XBRL cache)
│   ├── showcase.py             # Pre-verified zero-quota showcase equity research reports
│   ├── tools.py                # XBRL, Hybrid RAG, 8-K/earnings transcripts, fresh news & AST calculator
│   ├── guard.py                # RapidFuzz quote, Form 4 insider & XBRL/market numeric verifier + enrichment
│   ├── ingest.py               # SEC EDGAR 10-K/10-Q/8-K (Ex. 99.1) parser, inline tables, RAPTOR-lite
│   ├── embed.py                # Cloud pgvector / local ChromaDB dual-mode indexer
│   ├── config.py               # Unified cloud/local settings, Langfuse v4 helpers, and cost computation
│   └── model_pricing.json      # Per-1M token pricing registry (input, cached, cache write, output)
├── prompts/
│   └── system.txt              # Grounded financial analyst system prompt
├── scripts/
│   ├── seed_cloud.py           # CLI to ingest & index S&P 500 filings into Neon pgvector via Gemini
│   ├── manage_model_pricing.py # CLI/interactive tool to update model rates & backfill Langfuse
│   ├── backfill_langfuse_costs.py
│   └── check_thresholds.py     # CI evaluation pass-rate gate (>= 90%)
├── tests/
│   ├── eval_data.yaml          # Golden evaluation dataset
│   ├── test_eval.py            # End-to-end golden evaluation benchmark (15 test cases)
│   ├── test_data_sources.py    # Unit & E2E tests for XBRL, 8-K earnings, sentiment & guard
│   └── test_cloud_web.py       # Unit & SSE tests for 5/day quota, permalinks & Gemini Embedding 2
├── vercel.json                 # Single-project Next.js + FastAPI Fluid Compute configuration
├── Dockerfile                  # Multi-service container image
└── Makefile                    # Developer workflow shortcuts
```

---

## Quickstart (Local & Vercel Cloud)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/iamqazolp/CompanyScope.git
cd CompanyScope
uv sync --all-extras
npm install
```

### 2. Configure Environment Variables (`.env`)
Create a `.env` file in the repository root:
```env
# Multi-Tier OpenAI-compatible LLM endpoint
OPENAI_URL=https://api.shopaikey.com
OPENAI_KEY=your_openai_api_key
TIER1_MODEL=gpt-6.1-terra
TIER2_MODEL=gpt-6-luna

# Cloud Embeddings (Google AI Studio — gemini-embedding-2, 768-dim MRL)
GOOGLE_AI_STUDIO_KEY=your_google_ai_studio_key
GEMINI_EMBEDDING_MODEL=gemini-embedding-2

# Cloud Vector & State Store (Vercel Neon Serverless Postgres with pgvector)
DATABASE_URL=postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require

# SEC EDGAR identity & No-Login Daily Guest Quota
EDGAR_IDENTITY=your_email@example.com
DEFAULT_TICKER=AAPL
DAILY_QUERY_LIMIT=5

# Optional: Langfuse v4 Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

### 3. Seed Index (Cloud `pgvector` or Local `ChromaDB`)
```bash
# Cloud Mode (Neon Postgres + Gemini Embedding 2)
make seed-cloud

# Or Local Dev Mode (ChromaDB + SentenceTransformers)
make ingest && make index
```

### 4. Launch the Next.js Research Terminal & FastAPI Backend
```bash
# Terminal 1 — FastAPI Backend with SSE Streaming (http://localhost:8000)
make api

# Terminal 2 — Next.js 15 Equity Research Terminal (http://localhost:3000)
make web
```

To deploy both frontend and backend as a **single Vercel project**, connect the repository in Vercel, attach **Neon Serverless Postgres** from the Vercel Storage tab, set the environment variables above, and deploy.

---

## API Reference (`/api/*`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Active LLM, embedding model (`gemini-embedding-2`), vector backend, and service health |
| `GET` | `/api/quota` | Remaining daily free guest queries (`5/day`, HMAC IP + signed cookie, no login) |
| `GET` | `/api/showcase` | Pre-verified zero-quota institutional showcase reports |
| `GET` | `/api/reports/{slug}` | Fetch a saved shareable research report permalink |
| `GET` | `/api/tickers` | Indexed tickers, chunk counts, filing years, and sections |
| `GET` | `/api/financials/{ticker}` | 24h-cached multi-year structured `10-K` XBRL metrics for charting |
| `GET` | `/api/market/recap` | **0-quota** live 6-benchmark cross-asset tape + 30m cached `gpt-6-luna` AI Market Recap |
| `GET` | `/api/market/quote/{ticker}` | **0-quota** live TradingView spot quote, `1D %`, `Market Cap`, `P/E`, `EV/EBITDA` & target price |
| `GET` | `/api/market/chart/{ticker}` | **0-quota** OHLCV candlesticks & volume (`1D`, `5D`, `1M`, `6M`, `1Y`, `5Y`) for `lightweight-charts` |
| `POST` | `/api/ask/stream` | Real-time **Server-Sent Events (SSE)** stream of specialist steps, guard checks & result |
| `POST` | `/api/ask` | Synchronous JSON query (`single`, `multi_agent`, or `auto`) |
| `POST` | `/api/compare` | Concurrent multi-agent peer comparison across multiple tickers |
| `POST` | `/api/ingest` | Admin-protected SEC EDGAR download (`10-K`/`10-Q`/`8-K`) and vector indexing |

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
