import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from storage import AUDIT_LOG


AUDIT_LOG_PATH = Path(__file__).with_name("audit_log.jsonl")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_audit_event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    entry = {
        "event_type": event_type,
        "timestamp": _utc_timestamp(),
        **payload,
    }
    AUDIT_LOG.append(entry)
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def get_log(limit: int = 50) -> list[Dict[str, Any]]:
    if AUDIT_LOG:
        return AUDIT_LOG[-limit:]

    if not AUDIT_LOG_PATH.exists():
        return []

    entries: list[Dict[str, Any]] = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[-limit:]
