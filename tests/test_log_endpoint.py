from app import app
from audit import AUDIT_LOG_PATH


def test_log_endpoint_returns_entries(monkeypatch, tmp_path):
    temp_audit_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr("audit.AUDIT_LOG_PATH", temp_audit_path)

    import audit
    import services

    def fake_assess_text_with_groq(text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": "likely_human",
            "ai_likelihood": 0.2,
            "confidence": 0.8,
            "reasoning": "Mocked human-like writing.",
            "evidence": ["Personal tone", "Vivid description"],
        }

    monkeypatch.setattr("services.assess_text_with_groq", fake_assess_text_with_groq)
    audit.AUDIT_LOG.clear()
    services.process_submission(creator_id="test-user-1", text="A short sample submission.")

    with app.test_client() as client:
        response = client.get("/log")

    assert response.status_code == 200
    payload = response.get_json()
    assert "entries" in payload
    assert isinstance(payload["entries"], list)
    assert len(payload["entries"]) >= 1
    latest = payload["entries"][-1]
    assert latest["event_type"] == "submission_created"
    assert latest["creator_id"] == "test-user-1"
    assert latest["status"] == "classified"
