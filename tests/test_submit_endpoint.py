import json

import pytest

from app import app
import audit
from rate_limit import limiter
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


def test_submit_endpoint_returns_content_id_and_attribution(monkeypatch, tmp_path):
    temp_audit_path = tmp_path / "audit_log.jsonl"

    def fake_assess_text_with_groq(text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": "likely_human",
            "ai_likelihood": 0.15,
            "confidence": 0.85,
            "reasoning": "Mocked human-like writing.",
            "evidence": ["Personal tone", "Vivid description"],
        }

    def fake_assess_text_with_stylometric_heuristics(text):
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": 0.10,
            "confidence": 0.90,
            "reasoning": "Mocked style result.",
            "evidence": ["Moderate variation"],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(text):
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": 0.05,
            "confidence": 0.95,
            "reasoning": "Mocked repetition result.",
            "evidence": ["Very little repetition"],
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
                "text": "The sun dipped below the horizon, painting the sky in hues of amber and rose.",
                "creator_id": "test-user-1",
            },
        )

    assert response.status_code == 201
    payload = response.get_json()

    assert payload["message"] == "Submission received and assessed."
    assert isinstance(payload["content_id"], str)
    assert payload["content_id"].startswith("cnt_")
    assert payload["combined_attribution"]["verdict"] == "likely_human"
    assert payload["combined_attribution"]["combined_score"] == pytest.approx(0.1125, rel=1e-3)
    expected_label = "Likely human-written. This post appears to have been written by a person. Confidence: 89%"
    assert payload["combined_attribution"]["label"] == expected_label
    assert payload["stylometric_signal"]["signal_name"] == "stylometric_heuristics"
    assert payload["repetition_signal"]["signal_name"] == "repetition_redundancy"
    assert payload["confidence"] == pytest.approx(0.8875, rel=1e-3)
    assert payload["label"] == expected_label

    submission = payload["submission"]
    assert submission["content_id"] == payload["content_id"]
    assert submission["creator_id"] == "test-user-1"
    assert submission["text"].startswith("The sun dipped below the horizon")
    assert submission["status"] == "classified"
    assert submission["attribution"]["signal_name"] == "groq_llm_classification"
    assert submission["stylometric_signal"]["signal_name"] == "stylometric_heuristics"
    assert submission["repetition_signal"]["signal_name"] == "repetition_redundancy"
    assert submission["combined_attribution"]["combined_score"] == pytest.approx(0.1125, rel=1e-3)

    assert payload["content_id"] in SUBMISSIONS
    stored_submission = SUBMISSIONS[payload["content_id"]]
    assert stored_submission["creator_id"] == "test-user-1"
    assert stored_submission["label"] == expected_label
    assert stored_submission["status"] == "classified"

    assert len(AUDIT_LOG) == 1
    audit_entry = AUDIT_LOG[0]
    assert audit_entry["event_type"] == "submission_created"
    assert audit_entry["content_id"] == payload["content_id"]
    assert audit_entry["creator_id"] == "test-user-1"
    assert audit_entry["attribution"] == "likely_human"
    assert audit_entry["combined_score"] == pytest.approx(0.1125, rel=1e-3)
    assert audit_entry["confidence"] == pytest.approx(0.8875, rel=1e-3)
    assert audit_entry["label"] == expected_label
    assert audit_entry["llm_score"] == 0.15
    assert 0.0 <= audit_entry["stylometric_score"] <= 1.0
    assert 0.0 <= audit_entry["repetition_score"] <= 1.0
    assert audit_entry["status"] == "classified"
    assert audit_entry["appeal_filed"] is False

    assert temp_audit_path.exists()
    file_lines = temp_audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(file_lines) == 1
    file_entry = json.loads(file_lines[0])
    assert file_entry["content_id"] == payload["content_id"]
    assert file_entry["attribution"] == "likely_human"
    assert file_entry["combined_score"] == pytest.approx(0.1125, rel=1e-3)
    assert file_entry["llm_score"] == 0.15
    assert 0.0 <= file_entry["stylometric_score"] <= 1.0
    assert 0.0 <= file_entry["repetition_score"] <= 1.0
    assert file_entry["status"] == "classified"
    assert file_entry["appeal_filed"] is False


@pytest.mark.parametrize(
    "llm_score,stylometric_score,repetition_score,expected_verdict,expected_label",
    [
        (
            0.10,
            0.10,
            0.10,
            "likely_human",
            "Likely human-written. This post appears to have been written by a person. Confidence: 90%",
        ),
        (
            0.50,
            0.50,
            0.50,
            "uncertain",
            "Uncertain. We cannot tell with confidence whether this post was written by a person or by AI. Confidence: 50%",
        ),
        (
            0.90,
            0.90,
            0.90,
            "likely_ai",
            "Likely AI-generated. This post appears to have been created with AI tools. Confidence: 90%",
        ),
    ],
)
def test_submit_endpoint_can_return_all_three_label_variants(
    monkeypatch,
    tmp_path,
    llm_score,
    stylometric_score,
    repetition_score,
    expected_verdict,
    expected_label,
):
    temp_audit_path = tmp_path / "audit_log.jsonl"

    def fake_assess_text_with_groq(text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": expected_verdict,
            "ai_likelihood": llm_score,
            "confidence": max(llm_score, 1 - llm_score),
            "reasoning": "Mocked route variant test.",
            "evidence": ["Mocked LLM score."],
        }

    def fake_assess_text_with_stylometric_heuristics(text):
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": stylometric_score,
            "confidence": max(stylometric_score, 1 - stylometric_score),
            "reasoning": "Mocked style score.",
            "evidence": ["Mocked stylometric score."],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(text):
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": repetition_score,
            "confidence": max(repetition_score, 1 - repetition_score),
            "reasoning": "Mocked repetition score.",
            "evidence": ["Mocked repetition score."],
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
                "text": "Variant reachability test input.",
                "creator_id": "variant-user",
            },
        )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["combined_attribution"]["verdict"] == expected_verdict
    assert payload["combined_attribution"]["label"] == expected_label
    assert payload["label"] == expected_label
    assert AUDIT_LOG[-1]["label"] == expected_label


def test_submit_endpoint_is_rate_limited(monkeypatch, tmp_path):
    temp_audit_path = tmp_path / "audit_log.jsonl"

    def fake_assess_text_with_groq(text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": "likely_human",
            "ai_likelihood": 0.10,
            "confidence": 0.90,
            "reasoning": "Mocked human-like writing.",
            "evidence": ["Mocked LLM score."],
        }

    def fake_assess_text_with_stylometric_heuristics(text):
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": 0.10,
            "confidence": 0.90,
            "reasoning": "Mocked style score.",
            "evidence": ["Mocked stylometric score."],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(text):
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": 0.10,
            "confidence": 0.90,
            "reasoning": "Mocked repetition score.",
            "evidence": ["Mocked repetition score."],
            "metrics": {},
        }

    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", temp_audit_path)
    monkeypatch.setattr("services.assess_text_with_groq", fake_assess_text_with_groq)
    monkeypatch.setattr("services.assess_text_with_stylometric_heuristics", fake_assess_text_with_stylometric_heuristics)
    monkeypatch.setattr("services.assess_text_with_repetition_redundancy", fake_assess_text_with_repetition_redundancy)

    app.config["RATELIMIT_ENABLED"] = True
    limiter.reset()

    with app.test_client() as client:
        for index in range(10):
            response = client.post(
                "/submit",
                json={
                    "text": f"Rate limit test submission {index}.",
                    "creator_id": "rate-limit-user",
                },
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            assert response.status_code == 201

        limited_response = client.post(
            "/submit",
            json={
                "text": "This request should exceed the rate limit.",
                "creator_id": "rate-limit-user",
            },
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

    assert limited_response.status_code == 429
    assert limited_response.get_json()["error"] == "Rate limit exceeded."
