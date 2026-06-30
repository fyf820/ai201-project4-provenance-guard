import json

import pytest

import audit
from app import app
from storage import AUDIT_LOG, SUBMISSIONS


@pytest.fixture(autouse=True)
def clear_state():
    SUBMISSIONS.clear()
    AUDIT_LOG.clear()
    if audit.AUDIT_LOG_PATH.exists():
        audit.AUDIT_LOG_PATH.unlink()
    yield
    SUBMISSIONS.clear()
    AUDIT_LOG.clear()
    if audit.AUDIT_LOG_PATH.exists():
        audit.AUDIT_LOG_PATH.unlink()


@pytest.fixture
def classified_submission(monkeypatch, tmp_path):
    temp_audit_path = tmp_path / "audit_log.jsonl"

    def fake_assess_text_with_groq(text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": "likely_ai",
            "ai_likelihood": 0.90,
            "confidence": 0.90,
            "reasoning": "Mocked AI-like writing.",
            "evidence": ["Polished generic phrasing"],
        }

    def fake_assess_text_with_stylometric_heuristics(text):
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": 0.70,
            "confidence": 0.70,
            "reasoning": "Mocked stylometric result.",
            "evidence": ["Formal and uniform"],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(text):
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": 0.80,
            "confidence": 0.80,
            "reasoning": "Mocked repetition result.",
            "evidence": ["Boilerplate phrasing"],
            "metrics": {},
        }

    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", temp_audit_path)
    monkeypatch.setattr("services.assess_text_with_groq", fake_assess_text_with_groq)
    monkeypatch.setattr("services.assess_text_with_stylometric_heuristics", fake_assess_text_with_stylometric_heuristics)
    monkeypatch.setattr("services.assess_text_with_repetition_redundancy", fake_assess_text_with_repetition_redundancy)

    with app.test_client() as client:
        response = client.post(
            "/submit",
            json={
                "text": "This is a polished test submission.",
                "creator_id": "creator-appeal-1",
            },
        )

    assert response.status_code == 201
    return response.get_json(), temp_audit_path


def test_appeal_endpoint_updates_status_and_logs_original_decision(classified_submission):
    submission_payload, temp_audit_path = classified_submission
    content_id = submission_payload["content_id"]

    with app.test_client() as client:
        response = client.post(
            "/appeal",
            json={
                "content_id": content_id,
                "creator_reasoning": "I wrote this myself and can provide draft notes.",
            },
        )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"] == "Appeal received and queued for human review."
    assert payload["content_id"] == content_id
    assert payload["status"] == "under_review"
    assert payload["appeal"]["appeal_reasoning"] == "I wrote this myself and can provide draft notes."
    assert payload["appeal"]["creator_reasoning"] == "I wrote this myself and can provide draft notes."
    assert payload["appeal"]["original_decision"]["attribution"] == "likely_ai"
    assert payload["appeal"]["original_decision"]["llm_score"] == 0.90
    assert payload["appeal"]["original_decision"]["stylometric_score"] == 0.70
    assert payload["appeal"]["original_decision"]["repetition_score"] == 0.80

    stored_submission = SUBMISSIONS[content_id]
    assert stored_submission["status"] == "under_review"
    assert stored_submission["appeals"][0]["creator_reasoning"] == "I wrote this myself and can provide draft notes."

    appeal_log = AUDIT_LOG[-1]
    assert appeal_log["event_type"] == "appeal_received"
    assert appeal_log["content_id"] == content_id
    assert appeal_log["status"] == "under_review"
    assert appeal_log["appeal_filed"] is True
    assert appeal_log["appeal_reasoning"] == "I wrote this myself and can provide draft notes."
    assert appeal_log["original_decision"]["label"] == submission_payload["label"]
    assert appeal_log["original_decision"]["confidence"] == submission_payload["confidence"]

    file_lines = temp_audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(file_lines) == 2
    file_entry = json.loads(file_lines[-1])
    assert file_entry["event_type"] == "appeal_received"
    assert file_entry["appeal_filed"] is True
    assert file_entry["original_decision"]["attribution"] == "likely_ai"


def test_appeal_endpoint_rejects_unknown_content_id():
    with app.test_client() as client:
        response = client.post(
            "/appeal",
            json={
                "content_id": "cnt_missing",
                "creator_reasoning": "This should not exist.",
            },
        )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Submission not found."


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({}, "Request body must be valid JSON."),
        ({"creator_reasoning": "Missing content ID."}, "Field 'content_id' is required and must be a non-empty string."),
        ({"content_id": "cnt_123"}, "Field 'creator_reasoning' is required and must be a non-empty string."),
    ],
)
def test_appeal_endpoint_validates_required_fields(payload, expected_error):
    with app.test_client() as client:
        response = client.post("/appeal", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error
