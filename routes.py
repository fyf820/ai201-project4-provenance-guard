from flask import Blueprint, jsonify, request

from analytics import build_analytics_dashboard
from audit import get_log
from rate_limit import limiter
from services import approve_human_verification, process_submission, request_human_verification, submit_appeal

api = Blueprint("api", __name__)


@api.post("/submit")
@limiter.limit("10 per minute;100 per day")
def submit():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify(
            {
                "error": "Request body must be valid JSON.",
            }
        ), 400

    text = payload.get("text")
    creator_id = payload.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return jsonify(
            {
                "error": "Field 'text' is required and must be a non-empty string.",
            }
        ), 400

    if creator_id is None or (not isinstance(creator_id, str) and not isinstance(creator_id, int)):
        return jsonify(
            {
                "error": "Field 'creator_id' is required and must be a string or integer.",
            }
        ), 400

    try:
        submission = process_submission(creator_id=creator_id, text=text)
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503 if isinstance(exc, RuntimeError) else 400
    except Exception:
        return jsonify({"error": "Unable to assess submission at this time."}), 502

    return jsonify(
        {
            "message": "Submission received and assessed.",
            "content_id": submission["content_id"],
            "attribution": submission["attribution"],
            "stylometric_signal": submission["stylometric_signal"],
            "repetition_signal": submission["repetition_signal"],
            "combined_attribution": submission["combined_attribution"],
            "confidence": submission["confidence"],
            "label": submission["label"],
            "submission": submission["submission"],
        }
    ), 201


@api.get("/log")
def log_entries():
    return jsonify({"entries": get_log()})


@api.get("/analytics")
def analytics_dashboard():
    return jsonify(build_analytics_dashboard(get_log()))


@api.post("/appeal")
def appeal():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    content_id = payload.get("content_id")
    creator_reasoning = payload.get("creator_reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "Field 'content_id' is required and must be a non-empty string."}), 400

    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return jsonify({"error": "Field 'creator_reasoning' is required and must be a non-empty string."}), 400

    try:
        result = submit_appeal(content_id=content_id.strip(), creator_reasoning=creator_reasoning.strip())
    except KeyError:
        return jsonify({"error": "Submission not found."}), 404

    return jsonify(result), 201


@api.post("/verify-human")
def verify_human():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    content_id = payload.get("content_id")
    creator_reasoning = payload.get("creator_reasoning")
    supporting_context = payload.get("supporting_context")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "Field 'content_id' is required and must be a non-empty string."}), 400

    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return jsonify({"error": "Field 'creator_reasoning' is required and must be a non-empty string."}), 400

    if supporting_context is not None and not isinstance(supporting_context, str):
        return jsonify({"error": "Field 'supporting_context' must be a string if provided."}), 400

    try:
        result = request_human_verification(
            content_id=content_id.strip(),
            creator_reasoning=creator_reasoning.strip(),
            supporting_context=supporting_context.strip() if isinstance(supporting_context, str) else None,
        )
    except KeyError:
        return jsonify({"error": "Submission not found."}), 404

    return jsonify(result), 201


@api.post("/verify-human/approve")
def approve_verify_human():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    content_id = payload.get("content_id")
    reviewer_id = payload.get("reviewer_id")
    reviewer_notes = payload.get("reviewer_notes")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "Field 'content_id' is required and must be a non-empty string."}), 400

    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        return jsonify({"error": "Field 'reviewer_id' is required and must be a non-empty string."}), 400

    if reviewer_notes is not None and not isinstance(reviewer_notes, str):
        return jsonify({"error": "Field 'reviewer_notes' must be a string if provided."}), 400

    try:
        result = approve_human_verification(
            content_id=content_id.strip(),
            reviewer_id=reviewer_id.strip(),
            reviewer_notes=reviewer_notes.strip() if isinstance(reviewer_notes, str) else None,
        )
    except KeyError:
        return jsonify({"error": "Submission not found."}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 200
