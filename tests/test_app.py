from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_serves_page():
    r = client.get("/")
    assert r.status_code == 200 and "PII Shield" in r.text


def test_scan_returns_all_three_engines():
    r = client.post("/api/scan", json={"text": "Call (555) 123-4567 or +44 20 7946 0958"})
    body = r.json()
    assert set(body) == {"original", "pr98", "v2"}
    assert body["v2"]["scrubbed"] == "Call [REDACTED] or [REDACTED]"
    assert body["v2"]["typed"] == "Call [PHONE_1] or [PHONE_2]"
    assert "(555) 123-4567" in body["original"]["scrubbed"]  # the bug PR #98 fixed


def test_llm_dry_run(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/llm", json={"text": "Mail ana@example.com", "instruction": "Summarize."})
    body = r.json()
    assert r.status_code == 200 and body["dry_run"] is True
    assert "ana@example.com" not in body["prompt"]


def test_input_size_limit():
    assert client.post("/api/scan", json={"text": "x" * 20_001}).status_code == 422


def test_samples_and_health():
    assert client.get("/api/samples").json()
    assert client.get("/api/health").json()["ok"] is True
