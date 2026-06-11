import yaml
import pytest
from fastapi.testclient import TestClient
from src.app import app

# Disable rate limiter for testing to prevent 429 Too Many Requests
app.state.limiter.enabled = False

client = TestClient(app)

def load_eval_data():
    with open("tests/eval_data.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

@pytest.mark.parametrize("case", load_eval_data())
def test_eval_case(case):
    question = case["question"]
    ticker = case.get("ticker", "AAPL")
    
    print(f"\nTesting: {question}")
    response = client.post("/ask", json={"question": question, "ticker": ticker})
    assert response.status_code == 200, f"Request failed: {response.text}"
    
    data = response.json()
    
    assert "error" not in data, f"Agent returned an error: {data.get('error')}"
    
    answer = data.get("answer", "").lower()
    clarification = data.get("needs_clarification", "")
    used_tools = data.get("used_tools", [])
    
    if case.get("expected_refusal"):
        refusal_keywords = ["unavailable", "not available", "out of scope", "does not contain", "not specify", "unable to provide", "cannot find"]
        has_refusal = any(kw in answer for kw in refusal_keywords)
        assert has_refusal, f"Expected refusal, but got: {answer}"
        
    if case.get("expected_clarification"):
        assert clarification != "", "Expected clarification but got empty string."
        
    if case.get("expected_answer_contains"):
        expected = case["expected_answer_contains"].lower()
        assert expected in answer, f"Expected '{expected}' in answer: {answer}"
        
    if case.get("expected_tools"):
        for tool in case["expected_tools"]:
            assert tool in used_tools, f"Expected tool '{tool}' to be used, but got {used_tools}. Agent response: {data}"
