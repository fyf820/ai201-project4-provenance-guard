import pytest

import audit
from analytics import build_analytics_dashboard
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


def sample_audit_entries():
    return [
        {
            "event_type": "submission_created",
            "content_id": "cnt_human",
            "attribution": "likely_human",
            "confidence": 0.91,
            "llm_score": 0.1,
            "stylometric_score": 0.15,
            "repetition_score": 0.0,
            "appeal_filed": False,
        },
        {
            "event_type": "submission_created",
            "content_id": "cnt_ai",
            "attribution": "likely_ai",
            "confidence": 0.78,
            "llm_score": 0.9,
            "stylometric_score": 0.55,
            "repetition_score": 0.75,
            "appeal_filed": False,
        },
        {
            "event_type": "submission_created",
            "content_id": "cnt_uncertain",
            "attribution": "uncertain",
            "confidence": 0.52,
            "llm_score": 0.5,
            "stylometric_score": 0.55,
            "repetition_score": 0.45,
            "appeal_filed": False,
        },
        {
            "event_type": "appeal_received",
            "content_id": "cnt_ai",
            "status": "under_review",
            "appeal_filed": True,
        },
        {
            "event_type": "human_verification_requested",
            "content_id": "cnt_human",
            "status": "under_review",
            "credential_status": "pending_review",
        },
    ]


def test_build_analytics_dashboard_counts_patterns_and_rates():
    dashboard = build_analytics_dashboard(sample_audit_entries())

    assert dashboard["summary"]["total_submissions"] == 3
    assert dashboard["summary"]["total_appeals"] == 1
    assert dashboard["summary"]["total_human_verification_requests"] == 1
    assert dashboard["summary"]["total_human_review_events"] == 2
    assert dashboard["detection_pattern_distribution"]["likely_human"] == {"count": 1, "rate": 0.3333}
    assert dashboard["detection_pattern_distribution"]["likely_ai"] == {"count": 1, "rate": 0.3333}
    assert dashboard["detection_pattern_distribution"]["uncertain"] == {"count": 1, "rate": 0.3333}
    assert dashboard["appeal_rate"] == 0.3333
    assert dashboard["appeal_overturn_rate"] == 0.0
    assert dashboard["human_review_rate"] == 0.6667


def test_build_analytics_dashboard_counts_appeal_overturns():
    entries = [
        *sample_audit_entries(),
        {
            "event_type": "appeal_resolved",
            "content_id": "cnt_ai",
            "appeal_outcome": "overturned",
            "decision_changed": True,
        },
    ]

    dashboard = build_analytics_dashboard(entries)

    assert dashboard["summary"]["total_appeal_resolutions"] == 1
    assert dashboard["summary"]["total_appeal_overturns"] == 1
    assert dashboard["appeal_overturn_rate"] == 1.0


def test_analytics_endpoint_returns_dashboard(monkeypatch, tmp_path):
    temp_audit_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", temp_audit_path)

    for entry in sample_audit_entries():
        audit.write_audit_event(entry["event_type"], {key: value for key, value in entry.items() if key != "event_type"})

    with app.test_client() as client:
        response = client.get("/analytics")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["summary"]["total_submissions"] == 3
    assert payload["summary"]["total_appeals"] == 1
    assert payload["detection_pattern_distribution"]["likely_ai"]["count"] == 1
    assert payload["appeal_rate"] == 0.3333
    assert payload["human_review_rate"] == 0.6667
