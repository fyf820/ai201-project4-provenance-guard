from typing import Any, Dict, List

SUBMISSIONS: Dict[str, Dict[str, Any]] = {}
AUDIT_LOG: List[Dict[str, Any]] = []


def save_submission(record: Dict[str, Any]) -> None:
    content_id = record["content_id"]
    SUBMISSIONS[content_id] = record


def get_submission(content_id: str) -> Dict[str, Any] | None:
    return SUBMISSIONS.get(content_id)


def list_submissions() -> List[Dict[str, Any]]:
    return list(SUBMISSIONS.values())
