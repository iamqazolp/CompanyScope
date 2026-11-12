from typing import Any

SHOWCASE_REPORTS: list[dict[str, Any]] = [
    {
        "slug": "nvda-fy2026-ai-compute-cashflow-audit",
        "title": "NVIDIA (NVDA) FY2026 AI Data Center Scale, Gross Margin & Free Cash Flow Audit",
        "category": "Semiconductors · 10-K + XBRL",
        "question": "Analyze NVIDIA's FY2026 Revenue, Gross Profit, R&D investment, and Free Cash Flow conversion alongside supply-chain and export-control risk disclosures.",
        "tickers": ["NVDA"],
        "mode": "multi_agent",
        "result": {
            "answer": (
                "**Executive Summary — NVIDIA Corp. (`NVDA`) FY2026 Financial & Risk Audit**\n\n"
                "1. **Hyper-Scale Profitability & Cash Conversion (`10-K FY2026` XBRL):**\n"
                "   - **Total Revenue:** Surged `65.47%` YoY from **$130,497,000,000** ($130.50B in FY2025) to **$215,938,000,000** ($215.94B in FY2026) on Blackwell data-center ramp.\n"
                "   - **Gross Profit:** Reached **$153,463,000,000** ($153.46B), representing a **`71.07%` GAAP Gross Margin**, while **Net Income** climbed to **$120,067,000,000** ($120.07B).\n"
                "   - **R&D & Cash Flow:** R&D spend scaled to **$18,497,000,000** ($18.50B), while **Operating Cash Flow** of **$102,718,000,000** ($102.72B) converted into **$96,676,000,000** ($96.68B) of **Free Cash Flow** (`94.12%` OCF-to-FCF conversion).\n\n"
                "2. **Statutory Supply-Chain & Export Control Risks (`Form 10-K, Item 1A`):**\n"
                "   - **Foundry & CoWoS Packaging Concentration:** NVIDIA relies on third-party semiconductor foundries and advanced packaging capacity, exposing multi-quarter Blackwell/Rubin delivery schedules to wafer, HBM memory, and CoWoS substrate bottlenecks.\n"
                "   - **USG Licensing & Geopolitical Controls:** Export licensing restrictions on accelerated computing interconnects and GPUs constrain addressable data-center demand in restricted jurisdictions and heighten custom-ASIC competitive pressure."
            ),
            "citations": [
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "Revenues",
                    "verified_value": 215938000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "GrossProfit",
                    "verified_value": 153463000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "NetIncomeLoss",
                    "verified_value": 120067000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "ResearchAndDevelopmentExpense",
                    "verified_value": 18497000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "FreeCashFlow",
                    "verified_value": 96676000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
            ],
            "needs_clarification": "",
            "used_tools": [
                "get_financial_data",
                "calculator",
                "search_filings",
            ],
            "sub_agent_reports": [
                {
                    "agent": "QUANT_NVDA",
                    "role": "quant",
                    "ticker": "NVDA",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Retrieved FY2026 XBRL statements: Revenue $215.94B (+65.47% YoY vs FY2025 $130.50B), Gross Profit $153.46B (71.07% margin), Net Income $120.07B, R&D $18.50B, and Free Cash Flow $96.68B.",
                    "citations_count": 5,
                    "self_corrections": 0,
                    "cost_usd": 0.00044,
                },
                {
                    "agent": "QUAL_NVDA",
                    "role": "qual",
                    "ticker": "NVDA",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Audited FY2026 Form 10-K Item 1A disclosures covering TSMC foundry/packaging concentration, long-term supply purchase obligations, and US export control licensing rules.",
                    "citations_count": 0,
                    "self_corrections": 0,
                    "cost_usd": 0.00049,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.00792,
            "model": "gpt-6.1-terra",
            "tier": "tier1",
            "escalated": False,
            "tier_breakdown": {
                "supervisor_model": "gpt-6.1-terra",
                "tier1_model": "gpt-6.1-terra",
                "tier2_model": "gpt-6-luna",
                "tier1_agents": ["SUPERVISOR_SYNTH"],
                "tier2_agents": ["QUANT_NVDA", "QUAL_NVDA"],
                "escalated_agents": [],
            },
            "latency_ms": 4280,
        },
    },
    {
        "slug": "jpm-fy2025-banking-revenue-balance-sheet",
        "title": "JPMorgan Chase (JPM) FY2025 Net Revenue, Earnings & $4.42T Balance Sheet Audit",
        "category": "Global Banking · 10-K + XBRL",
        "question": "Audit JPMorgan Chase's FY2025 Total Net Revenue, Net Income, and $4.42T Balance Sheet leverage alongside regulatory capital and credit cycle risks.",
        "tickers": ["JPM"],
        "mode": "multi_agent",
        "result": {
            "answer": (
                "**Executive Summary — JPMorgan Chase & Co. (`JPM`) FY2025 Banking & Capital Audit**\n\n"
                "1. **Net Revenue & Earnings Resilience (`10-K FY2025` XBRL):**\n"
                "   - **Total Net Revenue (`RevenuesNetOfInterestExpense`):** Expanded `2.75%` YoY from **$177,556,000,000** ($177.56B in FY2024) to **$182,447,000,000** ($182.45B in FY2025) as investment-banking and asset-management fees offset rate normalization.\n"
                "   - **GAAP Net Income:** Generated **$57,048,000,000** ($57.05B), translating to a **`31.27%` net profit margin** on net revenue.\n"
                "   - **Balance Sheet Scale:** **Total Assets** grew `10.54%` YoY to **$4,424,900,000,000** ($4.42T) against **Total Liabilities** of **$4,062,462,000,000** ($4.06T), implying **$362.44B** in book equity cushion (`8.19%` equity-to-assets).\n\n"
                "2. **Credit Provisioning & Basel III Endgame Posture (`Form 10-K`):**\n"
                "   - Card services charge-offs and commercial real estate office exposure remain the primary credit-quality watchpoints, while excess CET1 capital preserves buyback flexibility pending final US Basel III capital rules."
            ),
            "citations": [
                {
                    "type": "numeric",
                    "ticker": "JPM",
                    "year": 2025,
                    "concept": "Revenues",
                    "verified_value": 182447000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "JPM",
                    "year": 2025,
                    "concept": "NetIncomeLoss",
                    "verified_value": 57048000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "JPM",
                    "year": 2025,
                    "concept": "Assets",
                    "verified_value": 4424900000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "JPM",
                    "year": 2025,
                    "concept": "Liabilities",
                    "verified_value": 4062462000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
            ],
            "needs_clarification": "",
            "used_tools": [
                "get_financial_data",
                "calculator",
                "search_filings",
            ],
            "sub_agent_reports": [
                {
                    "agent": "QUANT_JPM",
                    "role": "quant",
                    "ticker": "JPM",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Extracted FY2025 XBRL banking metrics: Total Net Revenue $182.45B (+2.75% YoY), Net Income $57.05B (31.27% net margin), Total Assets $4.425T, and Total Liabilities $4.062T.",
                    "citations_count": 4,
                    "self_corrections": 0,
                    "cost_usd": 0.00039,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.00685,
            "model": "gpt-6.1-terra",
            "tier": "tier1",
            "escalated": False,
            "tier_breakdown": {
                "supervisor_model": "gpt-6.1-terra",
                "tier1_model": "gpt-6.1-terra",
                "tier2_model": "gpt-6-luna",
                "tier1_agents": ["SUPERVISOR_SYNTH"],
                "tier2_agents": ["QUANT_JPM"],
                "escalated_agents": [],
            },
            "latency_ms": 3910,
        },
    },
    {
        "slug": "nvda-vs-msft-ai-capex-cash-conversion",
        "title": "NVIDIA vs. Microsoft (NVDA vs MSFT) AI CapEx & Free Cash Flow Comparison",
        "category": "Cross-Company Peer Compare",
        "question": "Compare FY2026 Revenue, Operating Income, Operating Cash Flow, and Free Cash Flow conversion between NVIDIA (NVDA) and Microsoft (MSFT).",
        "tickers": ["NVDA", "MSFT"],
        "mode": "multi_agent",
        "result": {
            "answer": (
                "**Peer Comparison — NVIDIA (`NVDA`) vs. Microsoft (`MSFT`) FY2026 Cash Conversion**\n\n"
                "| Metric (`FY2026 10-K XBRL`) | NVIDIA (`NVDA`) | Microsoft (`MSFT`) |\n"
                "| :--- | :---: | :---: |\n"
                "| **Revenue** | **$215.94B** (`$215,938M`) | **$331.84B** (`$331,839M`) |\n"
                "| **Operating Income** | **$130.39B** (`60.38%` margin) | **$155.24B** (`46.78%` margin) |\n"
                "| **Operating Cash Flow** | **$102.72B** (`$102,718M`) | **$182.94B** (`$182,935M`) |\n"
                "| **Free Cash Flow** | **$96.68B** (`94.12%` of OCF) | **$66.99B** (`36.62%` of OCF) |\n\n"
                "**Key Takeaway:** While Microsoft generates **`1.54×`** NVIDIA's top-line revenue and **`1.78×`** its operating cash flow, hyperscale cloud/AI data-center CapEx absorbed **$115.95B** of MSFT's operating cash flow—allowing asset-light **NVIDIA (`$96.68B` FCF)** to surpass **Microsoft (`$66.99B` FCF)** in annual Free Cash Flow by **`+44.32%`**."
            ),
            "citations": [
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "Revenues",
                    "verified_value": 215938000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "NVDA",
                    "year": 2026,
                    "concept": "FreeCashFlow",
                    "verified_value": 96676000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "MSFT",
                    "year": 2026,
                    "concept": "Revenues",
                    "verified_value": 331839000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "MSFT",
                    "year": 2026,
                    "concept": "OperatingCashFlow",
                    "verified_value": 182935000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "MSFT",
                    "year": 2026,
                    "concept": "FreeCashFlow",
                    "verified_value": 66987000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
            ],
            "needs_clarification": "",
            "used_tools": ["get_financial_data", "calculator"],
            "sub_agent_reports": [
                {
                    "agent": "QUANT_NVDA",
                    "role": "quant",
                    "ticker": "NVDA",
                    "model": "gpt-6.1-terra",
                    "tier": "tier1",
                    "escalated": True,
                    "escalation_reason": "multi_ticker_peer_comparison",
                    "answer": "NVDA FY2026 Revenue $215.94B, Operating Income $130.39B (60.38% margin), OCF $102.72B, FCF $96.68B (94.12% OCF conversion).",
                    "citations_count": 2,
                    "self_corrections": 0,
                    "cost_usd": 0.00412,
                },
                {
                    "agent": "QUANT_MSFT",
                    "role": "quant",
                    "ticker": "MSFT",
                    "model": "gpt-6.1-terra",
                    "tier": "tier1",
                    "escalated": True,
                    "escalation_reason": "multi_ticker_peer_comparison",
                    "answer": "MSFT FY2026 Revenue $331.84B, Operating Income $155.24B (46.78% margin), OCF $182.94B, FCF $66.99B after $115.95B cloud/AI CapEx.",
                    "citations_count": 3,
                    "self_corrections": 0,
                    "cost_usd": 0.00438,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.01420,
            "model": "gpt-6.1-terra",
            "tier": "tier1",
            "escalated": True,
            "tier_breakdown": {
                "supervisor_model": "gpt-6.1-terra",
                "tier1_model": "gpt-6.1-terra",
                "tier2_model": "gpt-6-luna",
                "tier1_agents": ["SUPERVISOR_SYNTH", "QUANT_NVDA", "QUANT_MSFT"],
                "tier2_agents": [],
                "escalated_agents": ["QUANT_NVDA", "QUANT_MSFT"],
            },
            "latency_ms": 5140,
        },
    },
    {
        "slug": "aapl-fy2025-segment-cashflow-audit",
        "title": "Apple (AAPL) FY2025 Profitability, Segment Revenue & Supply Chain Audit",
        "category": "Single-Ticker Deep Dive",
        "question": "Analyze Apple's FY2025 Gross Profit, R&D spend, iPhone segment revenue, and Free Cash Flow conversion alongside primary 10-K supply chain and tariff risks.",
        "tickers": ["AAPL"],
        "mode": "multi_agent",
        "result": {
            "answer": (
                "**Executive Summary — Apple Inc. (`AAPL`) FY2025 Financial & Risk Audit**\n\n"
                "1. **Profitability & Cash Flow Conversion (XBRL 10-K FY2025):**\n"
                "   - **Gross Profit:** Reached **$195,201,000,000** ($195.20B) in FY2025, supported by high-margin Services expansion.\n"
                "   - **iPhone Segment Revenue:** Generated **$209,586,000,000** ($209.59B), remaining the core hardware anchor.\n"
                "   - **R&D Investment:** Rose to **$34,550,000,000** ($34.55B) as Apple scaled silicon and Apple Intelligence investments.\n"
                "   - **Cash Generation:** Operating Cash Flow reached **$111,482,000,000** ($111.48B), converting to **$98,767,000,000** ($98.77B) in **Free Cash Flow** (`88.60%` FCF-to-OCF conversion).\n\n"
                "2. **Primary Supply Chain & Geopolitical Risk Disclosures (FY2025 Form 10-K, Item 1A):**\n"
                "   - **Single-Source Component Exposure:** Management warns that because critical components come from single or limited sources, *\"the Company is subject to significant supply and pricing risks.\"* (`[10-K 2025, Item 1A]`)\n"
                "   - **Reciprocal Tariffs & Trade Friction:** Apple highlights heightened tariff exposure across Asia and Europe, noting that *\"several countries have imposed, or threatened to impose, reciprocal tariffs on imports from the U.S. and other retaliatory measures.\"* (`[10-K 2025, Item 1A]`)\n"
                "   - **Q4 Momentum (Form 8-K Ex. 99.1):** Apple reported *\"September quarter records for total company revenue, iPhone revenue and EPS\"* as Services hit a new all-time high. (`[8-K 2025, Item 2.02]`)"
            ),
            "citations": [
                {
                    "type": "numeric",
                    "ticker": "AAPL",
                    "year": 2025,
                    "concept": "GrossProfit",
                    "verified_value": 195201000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "AAPL",
                    "year": 2025,
                    "concept": "iPhone",
                    "verified_value": 209586000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "AAPL",
                    "year": 2025,
                    "concept": "ResearchAndDevelopmentExpense",
                    "verified_value": 34550000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "AAPL",
                    "year": 2025,
                    "concept": "OperatingCashFlow",
                    "verified_value": 111482000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "numeric",
                    "ticker": "AAPL",
                    "year": 2025,
                    "concept": "FreeCashFlow",
                    "verified_value": 98767000000.0,
                    "unit": "USD",
                    "form": "10-K",
                },
                {
                    "type": "narrative",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 1A",
                    "chunk_id": "AAPL_2025_10-K_Item1A_2700",
                    "quote": "single or limited sources, the Company is subject to significant supply and pricing risks.",
                    "source_context": "Because the Company currently obtains certain components from single or limited sources, the Company is subject to significant supply and pricing risks. Many components, including those that are available from multiple sources, are at times subject to industry-wide shortages and significant commodity pricing fluctuations that can materially adversely affect the Company’s business, results of operations and financial condition.",
                },
                {
                    "type": "narrative",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 1A",
                    "chunk_id": "AAPL_2025_10-K_Item1A_900",
                    "quote": "several countries have imposed, or threatened to impose, reciprocal tariffs on imports from the U.S. and other retaliatory measures.",
                    "source_context": "The U.S. government has announced tariffs on imports from various jurisdictions, including China, India, Japan, South Korea, Taiwan, Vietnam and the European Union (“EU”), among others. In response, several countries have imposed, or threatened to impose, reciprocal tariffs on imports from the U.S. and other retaliatory measures.",
                },
                {
                    "type": "earnings",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 2.02",
                    "chunk_id": "AAPL_2025_8-K_000077_Item2.02_0",
                    "quote": "September quarter records for total company revenue, iPhone revenue and EPS",
                    "source_context": "Item 2.02. Results of Operations and Financial Condition (Exhibit 99.1 Earnings Release) — Apple reports fourth quarter results: September quarter records for total company revenue, iPhone revenue and EPS; Services revenue reaches new all-time high.",
                },
            ],
            "needs_clarification": "",
            "used_tools": [
                "get_financial_data",
                "calculator",
                "search_filings",
                "get_earnings_transcripts",
            ],
            "sub_agent_reports": [
                {
                    "agent": "QUANT_AAPL",
                    "role": "quant",
                    "ticker": "AAPL",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Fetched FY2025 XBRL statements: Gross Profit $195.20B, iPhone revenue $209.59B, R&D $34.55B, Operating Cash Flow $111.48B, and derived Free Cash Flow $98.77B (88.60% conversion via AST calculator).",
                    "citations_count": 5,
                    "self_corrections": 0,
                    "cost_usd": 0.00042,
                },
                {
                    "agent": "QUAL_AAPL",
                    "role": "qual",
                    "ticker": "AAPL",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Retrieved FY2025 10-K Item 1A supply-chain concentration and reciprocal tariff disclosures plus Q4 2025 Form 8-K Exhibit 99.1 record iPhone and Services commentary.",
                    "citations_count": 3,
                    "self_corrections": 0,
                    "cost_usd": 0.00051,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.00843,
            "model": "gpt-6.1-terra",
            "tier": "tier1",
            "escalated": False,
            "tier_breakdown": {
                "supervisor_model": "gpt-6.1-terra",
                "tier1_model": "gpt-6.1-terra",
                "tier2_model": "gpt-6-luna",
                "tier1_agents": ["SUPERVISOR_SYNTH"],
                "tier2_agents": ["QUANT_AAPL", "QUAL_AAPL"],
                "escalated_agents": [],
            },
            "latency_ms": 4820,
        },
    },
    {
        "slug": "aapl-ai-risks-and-market-sentiment",
        "title": "Apple AI Safety Disclosures vs. Live Investor & News Sentiment",
        "category": "SEC Filing vs. Street Sentiment",
        "question": "How do Apple's FY2025 10-K Risk Factors frame Artificial Intelligence risks compared to how retail investors and financial news view Apple's Services & AI moat?",
        "tickers": ["AAPL"],
        "mode": "multi_agent",
        "result": {
            "answer": (
                "**SEC Legal Risk Framing vs. Public Market Sentiment (`AAPL`)**\n\n"
                "1. **Audited SEC 10-K AI & IP Risk Posture (`Item 1A`):**\n"
                "   - **User Safety & Hallucination Liability:** Apple explicitly cautions in its FY2025 `10-K` that integrating *\"new and complex technologies, such as artificial intelligence features, can increase these and other safety risks, including exposing users to harmful, inaccurate or other negative content and experiences.\"* (`[10-K 2025, Item 1A]`)\n"
                "   - **IP Infringement Exposure:** Management further warns that third-party IP claims *\"may be exacerbated by the use of new and emerging technologies, including machine learning and artificial intelligence.\"* (`[10-K 2025, Item 1A]`)\n\n"
                "2. **Quarterly Execution & Public Market Commentary (`8-K` + Sentiment):**\n"
                "   - While statutory filings emphasize downside legal and safety exposure, quarterly earnings releases highlight ecosystem monetization—posting *\"June quarter records for total company revenue, iPhone revenue and EPS\"* alongside record Services scale (`[8-K 2025, Item 2.02]`), which retail discussions on `r/stocks` and `r/investing` consistently frame as Apple's primary recurring-margin buffer during its staggered AI rollout."
            ),
            "citations": [
                {
                    "type": "narrative",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 1A",
                    "chunk_id": "AAPL_2025_10-K_Item1A_3150",
                    "quote": "new and complex technologies, such as artificial intelligence features, can increase these and other safety risks, including exposing users to harmful, inaccurate or other negative content and experiences.",
                    "source_context": "The introduction of new and complex technologies, such as artificial intelligence features, can increase these and other safety risks, including exposing users to harmful, inaccurate or other negative content and experiences. The Company may not be able to detect, prevent or remediate all such issues in a timely manner.",
                },
                {
                    "type": "narrative",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 1A",
                    "chunk_id": "AAPL_2025_10-K_Item1A_3600",
                    "quote": "This risk may be exacerbated by the use of new and emerging technologies, including machine learning and artificial intelligence.",
                    "source_context": "Across successive product generations, the Company’s products and services may be alleged to infringe existing intellectual property rights of others. This risk may be exacerbated by the use of new and emerging technologies, including machine learning and artificial intelligence.",
                },
                {
                    "type": "earnings",
                    "ticker": "AAPL",
                    "year": 2025,
                    "section": "Item 2.02",
                    "chunk_id": "AAPL_2025_8-K_000071_Item2.02_0",
                    "quote": "June quarter records for total company revenue, iPhone revenue and EPS",
                    "source_context": "Item 2.02. Results of Operations and Financial Condition (Exhibit 99.1 Earnings Release) — Apple reports third quarter results: June quarter records for total company revenue, iPhone revenue and EPS; Services revenue reaches new all-time high.",
                },
            ],
            "needs_clarification": "",
            "used_tools": [
                "search_filings",
                "get_earnings_transcripts",
                "get_market_sentiment",
            ],
            "sub_agent_reports": [
                {
                    "agent": "QUAL_AAPL",
                    "role": "qual",
                    "ticker": "AAPL",
                    "model": "gpt-6.1-terra",
                    "tier": "tier1",
                    "escalated": True,
                    "escalation_reason": "cross_source_contradiction_synthesis",
                    "answer": "Extracted verbatim FY2025 10-K Item 1A disclosures covering AI safety/content risks and machine learning IP litigation risks alongside Q3 2025 8-K Exhibit 99.1 Services record commentary.",
                    "citations_count": 3,
                    "self_corrections": 0,
                    "cost_usd": 0.00612,
                },
                {
                    "agent": "SENTIMENT_AAPL",
                    "role": "sentiment",
                    "ticker": "AAPL",
                    "model": "gpt-6-luna",
                    "tier": "tier2",
                    "escalated": False,
                    "escalation_reason": "routine_specialist_workhorse",
                    "answer": "Aggregated Reddit (r/stocks, r/investing) investor discussions and Yahoo Finance headlines highlighting Services recurring-margin resilience despite staggered Apple Intelligence rollout.",
                    "citations_count": 0,
                    "self_corrections": 0,
                    "cost_usd": 0.00038,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.01190,
            "model": "gpt-6.1-terra",
            "tier": "tier1",
            "escalated": True,
            "tier_breakdown": {
                "supervisor_model": "gpt-6.1-terra",
                "tier1_model": "gpt-6.1-terra",
                "tier2_model": "gpt-6-luna",
                "tier1_agents": ["SUPERVISOR_SYNTH", "QUAL_AAPL"],
                "tier2_agents": ["SENTIMENT_AAPL"],
                "escalated_agents": ["QUAL_AAPL"],
            },
            "latency_ms": 3690,
        },
    },
]


def list_showcase_summaries() -> list[dict[str, Any]]:
    return [
        {
            "slug": item["slug"],
            "title": item["title"],
            "category": item["category"],
            "question": item["question"],
            "tickers": item["tickers"],
            "mode": item["mode"],
            "citations_count": len(item["result"].get("citations", [])),
            "latency_ms": item["result"].get("latency_ms", 0),
        }
        for item in SHOWCASE_REPORTS
    ]


def get_showcase_by_slug(slug: str) -> dict[str, Any] | None:
    for item in SHOWCASE_REPORTS:
        if item["slug"] == slug:
            return {
                "slug": item["slug"],
                "title": item["title"],
                "category": item["category"],
                "question": item["question"],
                "tickers": item["tickers"],
                "mode": item["mode"],
                "result": item["result"],
                "is_showcase": True,
                "created_at": "2026-11-12T00:00:00+00:00",
            }
    return None
