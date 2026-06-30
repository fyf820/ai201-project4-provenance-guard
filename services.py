import uuid
from typing import Any, Dict

from audit import write_audit_event
from detectors import (
    assess_text_with_groq,
    assess_text_with_repetition_redundancy,
    assess_text_with_stylometric_heuristics,
)
from storage import save_submission
from storage import get_submission


ENSEMBLE_WEIGHTS = {
    "llm_score": 0.50,
    "stylometric_score": 0.25,
    "repetition_score": 0.25,
}


def generate_transparency_label(verdict: str, confidence: float) -> str:
    confidence_percent = round(confidence * 100)

    if verdict == "likely_ai":
        return (
            "Likely AI-generated. This post appears to have been created with AI tools. "
            f"Confidence: {confidence_percent}%"
        )

    if verdict == "likely_human":
        return (
            "Likely human-written. This post appears to have been written by a person. "
            f"Confidence: {confidence_percent}%"
        )

    return (
        "Uncertain. We cannot tell with confidence whether this post was written by a person or by AI. "
        f"Confidence: {confidence_percent}%"
    )


def combine_signal_scores(
    llm_score: float,
    stylometric_score: float,
    repetition_score: float,
) -> Dict[str, Any]:
    combined_score = (
        ENSEMBLE_WEIGHTS["llm_score"] * llm_score
        + ENSEMBLE_WEIGHTS["stylometric_score"] * stylometric_score
        + ENSEMBLE_WEIGHTS["repetition_score"] * repetition_score
    )
    combined_score = max(0.0, min(1.0, combined_score))
    confidence = max(combined_score, 1 - combined_score)

    if combined_score < 0.35:
        verdict = "likely_human"
    elif combined_score <= 0.65:
        verdict = "uncertain"
    else:
        verdict = "likely_ai"

    label = generate_transparency_label(verdict, confidence)

    return {
        "verdict": verdict,
        "combined_score": round(combined_score, 4),
        "confidence": round(confidence, 4),
        "label": label,
    }


def process_submission(creator_id: Any, text: str) -> Dict[str, Any]:
    signal_assessment = assess_text_with_groq(text)
    stylometric_assessment = assess_text_with_stylometric_heuristics(text)
    repetition_assessment = assess_text_with_repetition_redundancy(text)
    content_id = f"cnt_{uuid.uuid4().hex[:12]}"

    llm_score = signal_assessment.get("ai_likelihood", 0.5) if isinstance(signal_assessment, dict) else 0.5
    stylometric_score = (
        stylometric_assessment.get("ai_likelihood", 0.5) if isinstance(stylometric_assessment, dict) else 0.5
    )
    repetition_score = (
        repetition_assessment.get("ai_likelihood", 0.5) if isinstance(repetition_assessment, dict) else 0.5
    )
    ensemble_assessment = combine_signal_scores(
        llm_score=llm_score,
        stylometric_score=stylometric_score,
        repetition_score=repetition_score,
    )

    submission = {
        "content_id": content_id,
        "creator_id": creator_id,
        "text": text,
        "status": "classified",
        "attribution": signal_assessment,
        "stylometric_signal": stylometric_assessment,
        "repetition_signal": repetition_assessment,
        "combined_attribution": ensemble_assessment,
        "confidence": ensemble_assessment["confidence"],
        "label": ensemble_assessment["label"],
    }

    save_submission(submission)
    write_audit_event(
        "submission_created",
        {
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": ensemble_assessment["verdict"],
            "combined_score": ensemble_assessment["combined_score"],
            "confidence": ensemble_assessment["confidence"],
            "label": ensemble_assessment["label"],
            "llm_score": llm_score,
            "stylometric_score": stylometric_score,
            "repetition_score": repetition_score,
            "status": "classified",
            "appeal_filed": False,
        },
    )

    return {
        "content_id": content_id,
        "attribution": signal_assessment,
        "stylometric_signal": stylometric_assessment,
        "repetition_signal": repetition_assessment,
        "combined_attribution": ensemble_assessment,
        "confidence": ensemble_assessment["confidence"],
        "label": ensemble_assessment["label"],
        "submission": submission,
    }


def get_original_decision_snapshot(submission: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "attribution": submission["combined_attribution"]["verdict"],
        "combined_score": submission["combined_attribution"]["combined_score"],
        "confidence": submission["confidence"],
        "label": submission["label"],
        "llm_score": submission["attribution"].get("ai_likelihood"),
        "stylometric_score": submission["stylometric_signal"].get("ai_likelihood"),
        "repetition_score": submission["repetition_signal"].get("ai_likelihood"),
    }


def submit_appeal(content_id: str, creator_reasoning: str) -> Dict[str, Any]:
    submission = get_submission(content_id)
    if submission is None:
        raise KeyError("Submission not found.")

    original_decision = get_original_decision_snapshot(submission)
    submission["status"] = "under_review"
    appeal = {
        "content_id": content_id,
        "creator_id": submission["creator_id"],
        "appeal_reasoning": creator_reasoning,
        "creator_reasoning": creator_reasoning,
        "status": "under_review",
        "original_decision": original_decision,
    }
    submission.setdefault("appeals", []).append(appeal)

    audit_entry = write_audit_event(
        "appeal_received",
        {
            **appeal,
            "appeal_count": len(submission["appeals"]),
            "appeal_filed": True,
        },
    )

    return {
        "message": "Appeal received and queued for human review.",
        "content_id": content_id,
        "status": "under_review",
        "appeal": appeal,
        "audit_entry": audit_entry,
    }


def request_human_verification(
    content_id: str,
    creator_reasoning: str,
    supporting_context: str | None = None,
) -> Dict[str, Any]:
    submission = get_submission(content_id)
    if submission is None:
        raise KeyError("Submission not found.")

    original_decision = get_original_decision_snapshot(submission)
    submission["status"] = "under_review"
    verification_request = {
        "content_id": content_id,
        "creator_id": submission["creator_id"],
        "creator_reasoning": creator_reasoning,
        "supporting_context": supporting_context,
        "status": "under_review",
        "credential_status": "pending_review",
        "badge_text": None,
        "display_badge": False,
        "original_decision": original_decision,
    }
    submission.setdefault("provenance_verification_requests", []).append(verification_request)
    submission["provenance_certificate"] = {
        "credential": "verified_human",
        "status": "pending_review",
        "badge_text": None,
        "display_badge": False,
    }

    audit_entry = write_audit_event(
        "human_verification_requested",
        {
            **verification_request,
            "verification_request_count": len(submission["provenance_verification_requests"]),
            "appeal_filed": bool(submission.get("appeals")),
        },
    )

    return {
        "message": "Verified-human request received and queued for human review.",
        "content_id": content_id,
        "status": "under_review",
        "credential_status": "pending_review",
        "badge_text": None,
        "display_badge": False,
        "verification_request": verification_request,
        "audit_entry": audit_entry,
    }


def approve_human_verification(content_id: str, reviewer_id: str, reviewer_notes: str | None = None) -> Dict[str, Any]:
    submission = get_submission(content_id)
    if submission is None:
        raise KeyError("Submission not found.")

    verification_requests = submission.get("provenance_verification_requests", [])
    if not verification_requests:
        raise ValueError("No pending verified-human request found.")

    latest_request = verification_requests[-1]
    latest_request["credential_status"] = "approved"
    latest_request["status"] = "approved"
    latest_request["badge_text"] = "Verified human"
    latest_request["display_badge"] = True
    latest_request["reviewer_id"] = reviewer_id
    latest_request["reviewer_notes"] = reviewer_notes

    submission["status"] = "classified"
    submission["provenance_certificate"] = {
        "credential": "verified_human",
        "status": "approved",
        "badge_text": "Verified human",
        "display_badge": True,
        "reviewer_id": reviewer_id,
        "reviewer_notes": reviewer_notes,
    }

    audit_entry = write_audit_event(
        "human_verification_approved",
        {
            "content_id": content_id,
            "creator_id": submission["creator_id"],
            "reviewer_id": reviewer_id,
            "reviewer_notes": reviewer_notes,
            "status": "classified",
            "credential_status": "approved",
            "badge_text": "Verified human",
            "display_badge": True,
            "standard_transparency_label": submission["label"],
            "original_decision": get_original_decision_snapshot(submission),
            "appeal_filed": bool(submission.get("appeals")),
        },
    )

    return {
        "message": "Verified-human credential approved.",
        "content_id": content_id,
        "status": "classified",
        "credential_status": "approved",
        "badge_text": "Verified human",
        "display_badge": True,
        "standard_transparency_label": submission["label"],
        "provenance_certificate": submission["provenance_certificate"],
        "audit_entry": audit_entry,
    }
