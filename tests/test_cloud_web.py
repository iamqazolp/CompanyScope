import json
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from src.agent import get_model_pricing
from src.app import app
from src.db import consume_quota, get_quota_status, make_guest_cookie, save_shared_report
from src.embeddings import embed_query_cloud, embed_texts_cloud
from src.guard import verify_citations
from src.market import resolve_tradingview_symbol
from src.multi_agent import run_multi_agent_query
from src.tier_router import (
    escalate_on_guard_failure,
    resolve_single_agent_tier,
    resolve_subagent_tier,
    resolve_supervisor_tier,
)

app.state.limiter.enabled = False
client = TestClient(app)


def test_health_and_showcase_endpoints() -> None:
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    body = r_health.json()
    assert body["status"] == "ok"
    assert body["daily_query_limit"] == 5
    assert body["tier1_model"] == "gpt-6.1-terra"
    assert body["tier2_model"] == "gpt-6-luna"

    r_show = client.get("/api/showcase")
    assert r_show.status_code == 200
    reports = r_show.json()["reports"]
    assert len(reports) >= 2

    slug = reports[0]["slug"]
    r_rep = client.get(f"/api/reports/{slug}")
    assert r_rep.status_code == 200
    rep_data = r_rep.json()
    assert rep_data["slug"] == slug
    assert len(rep_data["result"]["citations"]) > 0


def test_five_per_day_guest_quota_without_login() -> None:
    unique_ip = f"203.0.113.{uuid.uuid4().hex[:8]}"
    cookie_val = make_guest_cookie()
    gid = cookie_val.split(".", 1)[0]

    initial = get_quota_status(unique_ip, gid, daily_limit=5)
    assert initial["remaining"] == 5

    for expected_rem in (4, 3, 2, 1, 0):
        ok, status = consume_quota(unique_ip, gid, daily_limit=5)
        assert ok is True
        assert status["remaining"] == expected_rem

    # 6th attempt on the same UTC day must be rejected
    ok_sixth, status_sixth = consume_quota(unique_ip, gid, daily_limit=5)
    assert ok_sixth is False
    assert status_sixth["remaining"] == 0

    # Clearing cookie from the same IP still cannot bypass the 5/day cap
    new_gid = make_guest_cookie().split(".", 1)[0]
    ok_bypass, _ = consume_quota(unique_ip, new_gid, daily_limit=5)
    assert ok_bypass is False


def test_shared_report_persistence_roundtrip() -> None:
    sample_payload = {
        "answer": "Revenue grew 8% YoY.",
        "citations": [{"type": "numeric", "ticker": "AAPL", "year": 2025, "concept": "Revenues"}],
        "needs_clarification": "",
    }
    slug = save_shared_report(
        question="What was AAPL revenue growth?",
        tickers=["AAPL"],
        mode="single",
        payload=sample_payload,
    )
    resp = client.get(f"/api/reports/{slug}")
    assert resp.status_code == 200
    fetched = resp.json()
    assert fetched["slug"] == slug
    assert fetched["result"]["answer"] == "Revenue grew 8% YoY."


def test_guard_citation_enrichment_attaches_source_context() -> None:
    tool_results = {
        "c1": [
            {
                "chunk_id": "AAPL_2025_10-K_Item1A_2700",
                "chunk_text": "Because of single or limited sources, the Company is subject to significant supply and pricing risks.",
                "ticker": "AAPL",
                "year": 2025,
                "section": "Item 1A",
            }
        ],
        "c2": {
            "ticker": "AAPL",
            "concept": "GrossProfit",
            "period": "2025",
            "value": 195201000000.0,
            "unit": "USD",
            "form": "10-K",
        },
    }
    raw_out: dict[str, Any] = {
        "answer": "Gross profit was $195,201,000,000 while the Company is subject to significant supply and pricing risks.",
        "citations": [
            {
                "type": "narrative",
                "ticker": "AAPL",
                "year": 2025,
                "section": "Item 1A",
                "chunk_id": "AAPL_2025_10-K_Item1A_2700",
                "quote": "the Company is subject to significant supply and pricing risks.",
            },
            {
                "type": "numeric",
                "ticker": "AAPL",
                "year": 2025,
                "concept": "GrossProfit",
            },
        ],
        "needs_clarification": "",
    }
    verified = verify_citations(raw_out, tool_results)
    assert len(verified["citations"]) == 2
    assert "source_context" in verified["citations"][0]
    assert verified["citations"][1]["verified_value"] == 195201000000.0


def test_gemini_embedding_2_rest_client() -> None:
    mock_resp_single = MagicMock()
    mock_resp_single.status_code = 200
    mock_resp_single.ok = True
    mock_resp_single.json.return_value = {"embedding": {"values": [3.0, 4.0]}}

    mock_resp_batch = MagicMock()
    mock_resp_batch.status_code = 200
    mock_resp_batch.ok = True
    mock_resp_batch.json.return_value = {
        "embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 5.0]}]
    }

    with (
        patch("src.embeddings.GEMINI_API_KEY", "test-gemini-key"),
        patch("src.embeddings.requests.post", side_effect=[mock_resp_single, mock_resp_batch]) as p_post,
    ):
        q_vec = embed_query_cloud("Apple supply chain", output_dim=2)
        assert round(q_vec[0], 4) == 0.6
        assert round(q_vec[1], 4) == 0.8

        b_vecs = embed_texts_cloud(["chunk one", "chunk two"], output_dim=2)
        assert len(b_vecs) == 2
        assert round(b_vecs[1][1], 4) == 1.0
        assert "gemini-embedding-2" in p_post.call_args_list[0][0][0]


def test_sse_stream_endpoint_emits_events() -> None:
    def fake_dispatch(payload: Any, event_cb: Any = None) -> tuple[dict[str, Any], list[str], str]:
        if event_cb:
            event_cb({"type": "plan", "mode": "single", "tickers": ["AAPL"], "specialists": ["unified"]})
        return (
            {
                "answer": "Verified SSE test answer.",
                "citations": [],
                "needs_clarification": "",
            },
            ["AAPL"],
            "single",
        )

    with patch("src.app._execute_query_dispatch", side_effect=fake_dispatch):
        with client.stream(
            "POST",
            "/api/ask/stream",
            json={"question": "Test SSE?", "ticker": "AAPL", "mode": "single"},
        ) as resp:
            assert resp.status_code == 200
            lines = [ln for ln in resp.iter_lines() if ln.startswith("data: ")]

    events = [
        json.loads(ln[6:]) for ln in lines if ln != "data: [DONE]"
    ]
    event_types = [e["type"] for e in events]
    assert "quota" in event_types
    assert "plan" in event_types
    assert "result" in event_types
    result_ev = next(e for e in events if e["type"] == "result")
    assert result_ev["data"]["answer"] == "Verified SSE test answer."
    assert result_ev["report_slug"].startswith("aapl-")


def test_multi_tier_router_decisions_and_pricing() -> None:
    sup = resolve_supervisor_tier()
    assert sup.tier == "tier1"
    assert sup.model == "gpt-6.1-terra"

    routine_quant = resolve_subagent_tier(
        question="What was Apple's FY2025 revenue and supply chain risk?",
        role="quant",
        tickers=["AAPL"],
    )
    assert routine_quant.tier == "tier2"
    assert routine_quant.model == "gpt-6-luna"
    assert routine_quant.escalated is False

    demanding_quant = resolve_subagent_tier(
        question="Calculate Apple's 3-year revenue CAGR from 2022 to 2025 and ROIC.",
        role="quant",
        tickers=["AAPL"],
    )
    assert demanding_quant.tier == "tier1"
    assert demanding_quant.model == "gpt-6.1-terra"
    assert demanding_quant.escalated is True

    demanding_qual = resolve_subagent_tier(
        question="Reconcile contradictions between 8-K remarks and 10-K antitrust risks.",
        role="qual",
        tickers=["AAPL"],
    )
    assert demanding_qual.tier == "tier1"
    assert demanding_qual.model == "gpt-6.1-terra"
    assert demanding_qual.escalated is True

    routine_single = resolve_single_agent_tier("What was AAPL 2025 Net Income?", "AAPL")
    assert routine_single.model == "gpt-6-luna"

    guard_esc = escalate_on_guard_failure(routine_quant)
    assert guard_esc.tier == "tier1"
    assert guard_esc.model == "gpt-6.1-terra"
    assert guard_esc.escalated is True

    terra_rates = get_model_pricing("gpt-6.1-terra")
    luna_rates = get_model_pricing("gpt-6-luna")
    assert terra_rates["input_per_1m"] > luna_rates["input_per_1m"]
    assert terra_rates["output_per_1m"] > luna_rates["output_per_1m"]


def test_multi_agent_uses_luna_subagents_and_terra_synthesizer_with_guard_escalation() -> None:
    called_models: list[tuple[str, str]] = []

    def fake_call_llm(
        messages: list[dict[str, Any]],
        use_tools: bool = True,
        provider: str | None = None,
        model: str | None = None,
        tools_override: list[dict[str, Any]] | None = None,
        obs_name: str = "llm",
    ) -> tuple[dict[str, Any], str]:
        active = model or "gpt-6-luna"
        called_models.append((obs_name, active))

        if obs_name == "subagent_quant_AAPL_llm":
            return (
                {
                    "content": json.dumps(
                        {
                            "answer": "AAPL revenue was $391,035,000,000.",
                            "citations": [],
                            "needs_clarification": "",
                        }
                    ),
                    "tool_calls": [],
                    "_cost_details": {"total": 0.0002},
                },
                active,
            )

        if obs_name == "subagent_qual_AAPL_llm":
            # First call on gpt-6-luna returns an unverified citation -> triggers guard retry escalation to gpt-6.1-terra!
            if active == "gpt-6-luna":
                return (
                    {
                        "content": json.dumps(
                            {
                                "answer": "Supply chain risk.",
                                "citations": [
                                    {
                                        "type": "narrative",
                                        "ticker": "AAPL",
                                        "year": 2025,
                                        "section": "Item 1A",
                                        "chunk_id": "MISSING_CHUNK",
                                        "quote": "hallucinated quote",
                                    }
                                ],
                                "needs_clarification": "",
                            }
                        ),
                        "tool_calls": [],
                        "_cost_details": {"total": 0.0002},
                    },
                    active,
                )
            return (
                {
                    "content": json.dumps(
                        {
                            "answer": "Verified qualitative summary.",
                            "citations": [],
                            "needs_clarification": "",
                        }
                    ),
                    "tool_calls": [],
                    "_cost_details": {"total": 0.002},
                },
                active,
            )

        # Synthesizer call
        return (
            {
                "content": json.dumps(
                    {
                        "answer": "Executive Terra synthesis combining Quant and Qual.",
                        "citations": [],
                        "needs_clarification": "",
                    }
                ),
                "tool_calls": [],
                "_cost_details": {"total": 0.004},
            },
            active,
        )

    events: list[dict[str, Any]] = []
    with patch("src.multi_agent._call_llm", side_effect=fake_call_llm):
        out = run_multi_agent_query(
            question="What was AAPL revenue and primary supply chain risk?",
            ticker="AAPL",
            event_cb=events.append,
        )

    assert out["model"] == "gpt-6.1-terra"
    assert out["tier"] == "tier1"
    assert out["tier_breakdown"]["supervisor_model"] == "gpt-6.1-terra"
    assert ("subagent_quant_AAPL_llm", "gpt-6-luna") in called_models
    assert ("subagent_qual_AAPL_llm", "gpt-6-luna") in called_models
    assert ("subagent_qual_AAPL_llm", "gpt-6.1-terra") in called_models
    assert ("multi_agent_tier1_synthesizer", "gpt-6.1-terra") in called_models
    assert any(ev.get("type") == "tier_escalation" for ev in events)


def test_tradingview_symbol_resolution() -> None:
    assert resolve_tradingview_symbol("aapl", "NMS") == "NASDAQ:AAPL"
    assert resolve_tradingview_symbol("JPM", "") == "NYSE:JPM"
    assert resolve_tradingview_symbol("NVDA", "NGM") == "NASDAQ:NVDA"
    assert resolve_tradingview_symbol("SPY", "PCX") == "AMEX:SPY"


def test_guard_verifies_live_market_and_insider_citations() -> None:
    tool_results: dict[str, Any] = {
        "live_1": {
            "ticker": "AAPL",
            "as_of": "2026-11-12T08:15:00+00:00",
            "metrics": {
                "MarketCap": {"value": 5168942100000.0, "unit": "USD"},
                "ForwardPE": {"value": 33.72, "unit": "x"},
                "SpotPrice": {"value": 248.5, "unit": "USD"},
            },
        },
        "ins_1": [
            {
                "chunk_id": "AAPL_2026_FORM4_001",
                "chunk_text": "[SEC Form 4 · 2026-11-04] Insider: Luca Maestri (SVP, CFO) executed Sale (Code S) of 55,000 shares at $246.10 ($13,535,500).",
                "ticker": "AAPL",
                "year": 2026,
                "section": "Form 4 (Insider)",
                "url": "https://www.sec.gov/Archives/edgar/data/320193/form4.xml",
            }
        ],
    }
    raw_out: dict[str, Any] = {
        "answer": (
            "Apple trades at $248.50 with a $5.17T market cap (33.72x forward P/E), "
            "while Luca Maestri (SVP, CFO) executed Sale (Code S) of 55,000 shares at $246.10."
        ),
        "citations": [
            {
                "type": "market",
                "ticker": "AAPL",
                "year": 2026,
                "concept": "MarketCap",
            },
            {
                "type": "market",
                "ticker": "AAPL",
                "year": 2026,
                "concept": "ForwardPE",
            },
            {
                "type": "insider",
                "ticker": "AAPL",
                "year": 2026,
                "section": "Form 4 (Insider)",
                "chunk_id": "AAPL_2026_FORM4_001",
                "quote": "Luca Maestri (SVP, CFO) executed Sale (Code S) of 55,000 shares at $246.10",
            },
        ],
        "needs_clarification": "",
    }
    verified = verify_citations(raw_out, tool_results)
    assert verified["answer"].startswith("Apple trades at $248.50")
    assert len(verified["citations"]) == 3
    mcap_cit = verified["citations"][0]
    assert mcap_cit["verified_value"] == 5168942100000.0
    assert mcap_cit["as_of"] == "2026-11-12T08:15:00+00:00"
    ins_cit = verified["citations"][2]
    assert "Luca Maestri" in ins_cit["source_context"]
    assert ins_cit["source_url"].endswith("form4.xml")


def test_zero_quota_live_market_quote_chart_and_recap_endpoints() -> None:
    fake_quote = {
        "ticker": "AAPL",
        "short_name": "Apple Inc.",
        "tradingview_symbol": "NASDAQ:AAPL",
        "price": 248.50,
        "change_1d_pct": 1.24,
        "market_cap": 3820000000000.0,
        "forward_pe": 31.4,
        "as_of": "2026-11-12T08:20:00+00:00",
        "metrics": {"SpotPrice": {"value": 248.50, "unit": "USD"}},
    }
    fake_chart = {
        "ticker": "AAPL",
        "tradingview_symbol": "NASDAQ:AAPL",
        "timeframe": "1M",
        "interval": "1d",
        "period_change_pct": 4.15,
        "candles": [
            {
                "time": "2026-11-10",
                "open": 244.0,
                "high": 249.0,
                "low": 243.5,
                "close": 248.5,
                "volume": 41200000,
            }
        ],
    }
    fake_recap = {
        "as_of": "2026-11-12T08:20:00+00:00",
        "model": "gpt-6-luna",
        "benchmarks": [
            {
                "symbol": "^GSPC",
                "label": "S&P 500",
                "tradingview_symbol": "SP:SPX",
                "price": 6012.4,
                "change_1d_pct": 0.62,
            }
        ],
        "headline": "Tech Leads Wall Street Higher as Yields Stabilize",
        "summary": "Equities advanced on mega-cap semiconductor strength.",
        "bullets": ["S&P 500 rose 0.62% to 6,012.40."],
        "citations": [],
    }

    with (
        patch("src.app.get_live_market_data", return_value=fake_quote),
        patch("src.app.get_ohlcv_chart_data", return_value=fake_chart),
        patch("src.app.get_market_pulse_and_recap", return_value=fake_recap),
    ):
        r_quote = client.get("/api/market/quote/AAPL")
        assert r_quote.status_code == 200
        assert r_quote.json()["tradingview_symbol"] == "NASDAQ:AAPL"
        assert r_quote.json()["price"] == 248.50

        r_chart = client.get("/api/market/chart/AAPL?timeframe=1M")
        assert r_chart.status_code == 200
        assert len(r_chart.json()["candles"]) == 1
        assert r_chart.json()["period_change_pct"] == 4.15

        r_recap = client.get("/api/market/recap")
        assert r_recap.status_code == 200
        assert r_recap.json()["model"] == "gpt-6-luna"
        assert r_recap.json()["benchmarks"][0]["label"] == "S&P 500"

        # Verify zero guest quota was consumed by any of the three endpoints
        r_quota = client.get("/api/quota")
        assert r_quota.status_code == 200
        assert r_quota.json()["remaining"] == 5
