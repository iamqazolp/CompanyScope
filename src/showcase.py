from typing import Any

SHOWCASE_REPORTS: list[dict[str, Any]] = [
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
                    "answer": "Fetched FY2025 XBRL statements: Gross Profit $195.20B, iPhone revenue $209.59B, R&D $34.55B, Operating Cash Flow $111.48B, and derived Free Cash Flow $98.77B (88.60% conversion via AST calculator).",
                    "citations_count": 5,
                    "self_corrections": 0,
                    "cost_usd": 0.00042,
                },
                {
                    "agent": "QUAL_AAPL",
                    "role": "qual",
                    "ticker": "AAPL",
                    "answer": "Retrieved FY2025 10-K Item 1A supply-chain concentration and reciprocal tariff disclosures plus Q4 2025 Form 8-K Exhibit 99.1 record iPhone and Services commentary.",
                    "citations_count": 3,
                    "self_corrections": 0,
                    "cost_usd": 0.00051,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.00128,
            "model": "gpt-6-luna",
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
                    "answer": "Extracted verbatim FY2025 10-K Item 1A disclosures covering AI safety/content risks and machine learning IP litigation risks alongside Q3 2025 8-K Exhibit 99.1 Services record commentary.",
                    "citations_count": 3,
                    "self_corrections": 0,
                    "cost_usd": 0.00049,
                },
            ],
            "self_corrections": 0,
            "cost_usd": 0.00089,
            "model": "gpt-6-luna",
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
