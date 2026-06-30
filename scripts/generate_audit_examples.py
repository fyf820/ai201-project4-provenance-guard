import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import audit
import services
from storage import AUDIT_LOG, SUBMISSIONS


SAMPLES = [
    {
        "creator_id": "audit-example-ai",
        "llm_score": 0.9,
        "llm_verdict": "likely_ai",
        "text": (
            "Artificial intelligence represents a transformative paradigm shift in modern society. "
            "It is important to note that while the benefits of AI are numerous, it is equally "
            "essential to consider the ethical implications. Furthermore, stakeholders across "
            "various sectors must collaborate to ensure responsible deployment."
        ),
    },
    {
        "creator_id": "audit-example-human",
        "llm_score": 0.1,
        "llm_verdict": "likely_human",
        "text": (
            "ok so i finally tried that new ramen place downtown and honestly? "
            "underwhelming. the broth was fine but they put WAY too much sodium in it and "
            "i was thirsty for like three hours after. my friend got the spicy version and "
            "said it was better. probably won't go back unless someone drags me there"
        ),
    },
    {
        "creator_id": "audit-example-formal-human",
        "llm_score": 0.45,
        "llm_verdict": "uncertain",
        "text": (
            "The relationship between monetary policy and asset price inflation has been "
            "extensively studied in the literature. Central banks face a fundamental tension "
            "between their mandate for price stability and the unintended consequences of "
            "prolonged low interest rates on equity and real estate valuations."
        ),
    },
    {
        "creator_id": "audit-example-edited-ai",
        "llm_score": 0.6,
        "llm_verdict": "uncertain",
        "text": (
            "I've been thinking a lot about remote work lately. There are genuine tradeoffs - "
            "flexibility and no commute on one side, isolation and blurred work-life boundaries "
            "on the other. Studies show productivity varies widely by individual and role type."
        ),
    },
]


def stub_llm_assessment(text):
    for sample in SAMPLES:
        if sample["text"] == text:
            return {
                "signal_name": "groq_llm_classification",
                "model": "stubbed-for-audit-example",
                "verdict": sample["llm_verdict"],
                "ai_likelihood": sample["llm_score"],
                "confidence": max(sample["llm_score"], 1 - sample["llm_score"]),
                "reasoning": "Deterministic score used to generate local audit-log evidence.",
                "evidence": ["Saved audit example generated without calling the live Groq API."],
            }
    raise ValueError("Unexpected sample text.")


def main():
    SUBMISSIONS.clear()
    AUDIT_LOG.clear()
    if audit.AUDIT_LOG_PATH.exists():
        audit.AUDIT_LOG_PATH.unlink()

    original_llm = services.assess_text_with_groq
    services.assess_text_with_groq = stub_llm_assessment
    try:
        submissions = [services.process_submission(sample["creator_id"], sample["text"]) for sample in SAMPLES]
        human_content_id = submissions[1]["content_id"]
        formal_human_content_id = submissions[2]["content_id"]
        services.request_human_verification(
            human_content_id,
            (
                "I wrote this ramen review myself from personal experience. The casual wording, "
                "specific food details, and personal reaction are part of my own writing style."
            ),
            supporting_context=(
                "I can provide draft notes, timestamped edits, or account history if a human "
                "reviewer needs more evidence."
            ),
        )
        services.submit_appeal(
            formal_human_content_id,
            (
                "I wrote this myself in a formal academic style. Please review the original "
                "classification because polished human writing can look AI-like."
            ),
        )
    finally:
        services.assess_text_with_groq = original_llm

    pretty_path = audit.AUDIT_LOG_PATH.with_name("audit_log_examples.json")
    pretty_path.write_text(json.dumps(AUDIT_LOG, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(AUDIT_LOG)} audit entries to {audit.AUDIT_LOG_PATH}")
    print(f"Wrote pretty JSON copy to {pretty_path}")


if __name__ == "__main__":
    main()
