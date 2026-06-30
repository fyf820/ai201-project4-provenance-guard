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
            "verdict": "likely_human",
            "ai_likelihood": 0.15,
            "confidence": 0.85,
            "reasoning": "Mocked human-like writing.",
            "evidence": ["Personal voice"],
        }

    def fake_assess_text_with_stylometric_heuristics(text):
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": 0.20,
            "confidence": 0.80,
            "reasoning": "Mocked stylometric result.",
            "evidence": ["Varied style"],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(text):
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": 0.10,
            "confidence": 0.90,
            "reasoning": "Mocked repetition result.",
            "evidence": ["Low redundancy"],
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
                "text": "I wrote this from a personal draft.",
                "creator_id": "creator-verify-1",
            },
        )

    assert response.status_code == 201
    return response.get_json(), temp_audit_path


def test_verify_human_endpoint_queues_human_review_and_logs_original_decision(classified_submission):
    submission_payload, temp_audit_path = classified_submission
    content_id = submission_payload["content_id"]

    with app.test_client() as client:
        response = client.post(
            "/verify-human",
            json={
                "content_id": content_id,
                "creator_reasoning": "I wrote this myself and can provide draft history.",
                "supporting_context": "Draft notes are available in my writing folder.",
            },
        )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"] == "Verified-human request received and queued for human review."
    assert payload["content_id"] == content_id
    assert payload["status"] == "under_review"
    assert payload["credential_status"] == "pending_review"
    assert payload["badge_text"] is None
    assert payload["display_badge"] is False
    assert payload["verification_request"]["creator_reasoning"] == "I wrote this myself and can provide draft history."
    assert payload["verification_request"]["supporting_context"] == "Draft notes are available in my writing folder."
    assert payload["verification_request"]["original_decision"]["attribution"] == "likely_human"
    assert payload["verification_request"]["original_decision"]["label"] == submission_payload["label"]

    stored_submission = SUBMISSIONS[content_id]
    assert stored_submission["status"] == "under_review"
    assert stored_submission["provenance_certificate"]["credential"] == "verified_human"
    assert stored_submission["provenance_certificate"]["status"] == "pending_review"
    assert stored_submission["provenance_certificate"]["display_badge"] is False
    assert stored_submission["provenance_verification_requests"][0]["credential_status"] == "pending_review"

    verification_log = AUDIT_LOG[-1]
    assert verification_log["event_type"] == "human_verification_requested"
    assert verification_log["content_id"] == content_id
    assert verification_log["status"] == "under_review"
    assert verification_log["credential_status"] == "pending_review"
    assert verification_log["display_badge"] is False
    assert verification_log["appeal_filed"] is False
    assert verification_log["original_decision"]["confidence"] == submission_payload["confidence"]

    file_lines = temp_audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(file_lines) == 2
    file_entry = json.loads(file_lines[-1])
    assert file_entry["event_type"] == "human_verification_requested"
    assert file_entry["original_decision"]["attribution"] == "likely_human"


def test_verify_human_approval_displays_verified_badge(classified_submission):
    submission_payload, temp_audit_path = classified_submission
    content_id = submission_payload["content_id"]

    with app.test_client() as client:
        request_response = client.post(
            "/verify-human",
            json={
                "content_id": content_id,
                "creator_reasoning": "I wrote this myself and can provide draft history.",
            },
        )
        approve_response = client.post(
            "/verify-human/approve",
            json={
                "content_id": content_id,
                "reviewer_id": "reviewer-1",
                "reviewer_notes": "Draft history reviewed and authorship claim accepted.",
            },
        )

    assert request_response.status_code == 201
    assert approve_response.status_code == 200
    payload = approve_response.get_json()
    assert payload["message"] == "Verified-human credential approved."
    assert payload["content_id"] == content_id
    assert payload["credential_status"] == "approved"
    assert payload["badge_text"] == "Verified human"
    assert payload["display_badge"] is True
    assert payload["standard_transparency_label"] == submission_payload["label"]
    assert payload["provenance_certificate"]["status"] == "approved"
    assert payload["provenance_certificate"]["badge_text"] == "Verified human"
    assert payload["provenance_certificate"]["display_badge"] is True

    stored_submission = SUBMISSIONS[content_id]
    assert stored_submission["status"] == "classified"
    assert stored_submission["label"] == submission_payload["label"]
    assert stored_submission["provenance_certificate"]["badge_text"] == "Verified human"
    assert stored_submission["provenance_certificate"]["display_badge"] is True
    assert stored_submission["provenance_verification_requests"][0]["credential_status"] == "approved"

    approval_log = AUDIT_LOG[-1]
    assert approval_log["event_type"] == "human_verification_approved"
    assert approval_log["credential_status"] == "approved"
    assert approval_log["badge_text"] == "Verified human"
    assert approval_log["display_badge"] is True
    assert approval_log["standard_transparency_label"] == submission_payload["label"]

    file_lines = temp_audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(file_lines) == 3
    file_entry = json.loads(file_lines[-1])
    assert file_entry["event_type"] == "human_verification_approved"
    assert file_entry["badge_text"] == "Verified human"


def test_verify_human_endpoint_rejects_unknown_content_id():
    with app.test_client() as client:
        response = client.post(
            "/verify-human",
            json={
                "content_id": "cnt_missing",
                "creator_reasoning": "Please verify my authorship.",
            },
        )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Submission not found."


def test_verify_human_approval_requires_pending_request(classified_submission):
    submission_payload, _ = classified_submission

    with app.test_client() as client:
        response = client.post(
            "/verify-human/approve",
            json={
                "content_id": submission_payload["content_id"],
                "reviewer_id": "reviewer-1",
            },
        )

    assert response.status_code == 400
    assert response.get_json()["error"] == "No pending verified-human request found."


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({}, "Request body must be valid JSON."),
        ({"creator_reasoning": "Missing content ID."}, "Field 'content_id' is required and must be a non-empty string."),
        ({"content_id": "cnt_123"}, "Field 'creator_reasoning' is required and must be a non-empty string."),
        (
            {
                "content_id": "cnt_123",
                "creator_reasoning": "Please verify this.",
                "supporting_context": ["not", "a", "string"],
            },
            "Field 'supporting_context' must be a string if provided.",
        ),
    ],
)
def test_verify_human_endpoint_validates_required_fields(payload, expected_error):
    with app.test_client() as client:
        response = client.post("/verify-human", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({}, "Request body must be valid JSON."),
        ({"reviewer_id": "reviewer-1"}, "Field 'content_id' is required and must be a non-empty string."),
        ({"content_id": "cnt_123"}, "Field 'reviewer_id' is required and must be a non-empty string."),
        (
            {
                "content_id": "cnt_123",
                "reviewer_id": "reviewer-1",
                "reviewer_notes": ["not", "a", "string"],
            },
            "Field 'reviewer_notes' must be a string if provided.",
        ),
    ],
)
def test_verify_human_approval_validates_required_fields(payload, expected_error):
    with app.test_client() as client:
        response = client.post("/verify-human/approve", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error
