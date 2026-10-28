from fastapi.testclient import TestClient

from src.app import app
from src.guard import check_citations, verify_citations
from src.multi_agent import classify_needed_specialists
from src.tools import (
    get_earnings_transcripts,
    get_financial_data,
    get_market_sentiment,
)

app.state.limiter.enabled = False
client = TestClient(app)


def test_expanded_xbrl_lookup() -> None:
    gross_profit = get_financial_data("AAPL", "GrossProfit", "2025")
    assert "error" not in gross_profit
    assert gross_profit["value"] == 195201000000.0

    ocf = get_financial_data("AAPL", "OperatingCashFlow", "2025")
    assert "error" not in ocf
    assert ocf["value"] == 111482000000.0

    fcf = get_financial_data("AAPL", "FreeCashFlow", "2025")
    assert "error" not in fcf
    assert fcf["value"] == 98767000000.0

    rd = get_financial_data("AAPL", "ResearchAndDevelopmentExpense", "2025")
    assert "error" not in rd
    assert rd["value"] == 34550000000.0

    iphone_rev = get_financial_data("AAPL", "iPhone", "2025")
    assert "error" not in iphone_rev
    assert iphone_rev["value"] == 209586000000.0


def test_get_earnings_transcripts() -> None:
    chunks = get_earnings_transcripts(
        "AAPL", year=2025, query="Tim Cook CEO Services revenue record", k=3
    )
    assert len(chunks) > 0
    first = chunks[0]
    assert first["ticker"] == "AAPL"
    assert "chunk_text" in first and len(first["chunk_text"]) > 50
    assert "chunk_id" in first


def test_get_market_sentiment() -> None:
    items = get_market_sentiment("AAPL", query="AI iPhone", limit=4)
    assert len(items) > 0
    first = items[0]
    assert first["ticker"] == "AAPL"
    assert "chunk_text" in first and len(first["chunk_text"]) > 10
    assert first.get("source_type") in ("social_sentiment", "financial_news")


def test_guard_verifies_earnings_and_sentiment_citations() -> None:
    mock_tool_results = {
        "call_1": [
            {
                "chunk_id": "AAPL_2025_8-K_000077_Item2.02_0",
                "chunk_text": "Apple posted quarterly revenue of $94.9 billion, up 6 percent year over year.",
                "ticker": "AAPL",
                "year": 2025,
                "section": "Item 2.02",
            }
        ],
        "call_2": [
            {
                "chunk_id": "AAPL_2026_REDDIT_xyz",
                "chunk_text": "[r/stocks | Score: 142] Title: Apple Services growth remains the strongest moat.",
                "ticker": "AAPL",
                "year": 2026,
                "section": "Reddit (r/stocks)",
            }
        ],
    }
    output = {
        "answer": "Apple posted quarterly revenue of $94.9 billion, and Reddit users note Apple Services growth remains the strongest moat.",
        "citations": [
            {
                "type": "earnings",
                "ticker": "AAPL",
                "year": 2025,
                "section": "Item 2.02",
                "chunk_id": "AAPL_2025_8-K_000077_Item2.02_0",
                "quote": "Apple posted quarterly revenue of $94.9 billion, up 6 percent year over year.",
            },
            {
                "type": "sentiment",
                "ticker": "AAPL",
                "year": 2026,
                "section": "Reddit (r/stocks)",
                "chunk_id": "AAPL_2026_REDDIT_xyz",
                "quote": "Apple Services growth remains the strongest moat.",
            },
        ],
        "needs_clarification": "",
    }
    valid, invalid = check_citations(output, mock_tool_results)
    assert len(valid) == 2
    assert len(invalid) == 0
    verified = verify_citations(output, mock_tool_results)
    assert len(verified["citations"]) == 2


def test_specialist_routing_includes_sentiment() -> None:
    roles = classify_needed_specialists(
        "Compare Apple's 2025 revenue growth with Reddit social media sentiment and news headlines."
    )
    assert "quant" in roles
    assert "sentiment" in roles


def test_end_to_end_earnings_and_sentiment_queries() -> None:
    r_earn = client.post(
        "/ask",
        json={
            "question": "What did Apple highlight in its 2025 8-K earnings releases regarding quarterly revenue or Services?",
            "ticker": "AAPL",
        },
    )
    assert r_earn.status_code == 200
    data_earn = r_earn.json()
    assert "error" not in data_earn
    assert any(
        t in data_earn.get("used_tools", [])
        for t in ("get_earnings_transcripts", "search_filings")
    )

    r_sent = client.post(
        "/ask",
        json={
            "question": "What are recent Yahoo Finance news headlines and Reddit sentiment saying about AAPL?",
            "ticker": "AAPL",
            "mode": "multi_agent",
        },
    )
    assert r_sent.status_code == 200
    data_sent = r_sent.json()
    assert "error" not in data_sent
    assert "get_market_sentiment" in data_sent.get("used_tools", [])
