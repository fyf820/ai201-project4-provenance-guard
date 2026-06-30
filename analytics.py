from collections import Counter
from typing import Any, Dict, List


VERDICTS = ("likely_human", "uncertain", "likely_ai")


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def build_analytics_dashboard(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    submission_events = [entry for entry in entries if entry.get("event_type") == "submission_created"]
    appeal_events = [entry for entry in entries if entry.get("event_type") == "appeal_received"]
    verification_events = [
        entry for entry in entries if entry.get("event_type") == "human_verification_requested"
    ]
    appeal_resolution_events = [
        entry
        for entry in entries
        if entry.get("event_type") in {"appeal_resolved", "human_review_completed"}
    ]
    appeal_overturn_events = [
        entry
        for entry in appeal_resolution_events
        if entry.get("appeal_outcome") in {"overturned", "changed"}
        or entry.get("decision_changed") is True
    ]

    verdict_counts = Counter(entry.get("attribution") for entry in submission_events)
    total_submissions = len(submission_events)
    detection_pattern_distribution = {
        verdict: {
            "count": verdict_counts.get(verdict, 0),
            "rate": _rate(verdict_counts.get(verdict, 0), total_submissions),
        }
        for verdict in VERDICTS
    }

    human_review_events = appeal_events + verification_events + appeal_resolution_events

    return {
        "summary": {
            "total_submissions": total_submissions,
            "total_appeals": len(appeal_events),
            "total_human_verification_requests": len(verification_events),
            "total_human_review_events": len(human_review_events),
            "total_appeal_resolutions": len(appeal_resolution_events),
            "total_appeal_overturns": len(appeal_overturn_events),
        },
        "detection_pattern_distribution": detection_pattern_distribution,
        "appeal_rate": _rate(len(appeal_events), total_submissions),
        "appeal_overturn_rate": _rate(len(appeal_overturn_events), len(appeal_resolution_events)),
        "human_review_rate": _rate(len(human_review_events), total_submissions),
    }
