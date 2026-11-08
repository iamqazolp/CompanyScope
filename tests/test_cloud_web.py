import json
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from src.app import app
from src.db import consume_quota, get_quota_status, make_guest_cookie, save_shared_report
from src.embeddings import embed_query_cloud, embed_texts_cloud
from src.guard import verify_citations

app.state.limiter.enabled = False
client = TestClient(app)


def test_health_and_showcase_endpoints() -> None:
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    body = r_health.json()
    assert body["status"] == "ok"
    assert body["daily_query_limit"] == 5

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
