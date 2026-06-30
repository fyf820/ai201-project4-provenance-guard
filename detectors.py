import json
import os
import re
import statistics
from collections import Counter
from typing import Any, Dict

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
WORD_PATTERN = re.compile(r"[A-Za-z']+")
SENTENCE_PATTERN = re.compile(r"[^.!?]+")
NGRAM_SIZE_RANGE = (2, 3)
AI_GENERIC_PHRASES = [
    "in summary",
    "it is important to note",
    "it is equally essential",
    "proposed framework",
    "comprehensive",
    "scalable",
    "efficient",
    "transformative paradigm shift",
    "modern society",
    "ethical implications",
    "stakeholders across various sectors",
    "responsible deployment",
    "robust outcomes",
    "operational consistency",
    "enhance user trust",
    "future iterations",
    "iterative refinement",
    "continuous monitoring",
    "leveraging",
    "machine assistance",
    "careful human review",
    "genuine tradeoffs",
    "productivity varies",
    "individual and role type",
    "nuance",
    "context",
    "lived experience",
    "content analysis",
]
FIRST_PERSON_PRONOUNS = {
    "i",
    "me",
    "my",
    "mine",
    "we",
    "us",
    "our",
    "ours",
    "im",
    "i'm",
    "ive",
    "i've",
}


def assess_text_with_groq(text: str) -> Dict[str, Any]:
    """Send text to Groq and return a structured first-signal assessment."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    api_key = os.getenv("ROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing Groq API key. Set ROQ_API_KEY or GROQ_API_KEY in the environment.")

    client = Groq(api_key=api_key)

    prompt = (
        "You are scoring a creative writing submission for whether it appears human-written or AI-generated.\n"
        "Return ONLY valid JSON with this exact shape:\n"
        "{\n"
        '  "verdict": "likely_human" | "uncertain" | "likely_ai",\n'
        '  "ai_likelihood": number between 0 and 1,\n'
        '  "confidence": number between 0 and 1,\n'
        '  "reasoning": string,\n'
        '  "evidence": [string, ...]\n'
        "}\n"
        "Guidance:\n"
        "- ai_likelihood should reflect how AI-like the text appears.\n"
        "- confidence should reflect how sure you are in that verdict.\n"
        "- reasoning should be concise and plain-language.\n"
        "- evidence should contain short bullet-like observations, not a long essay.\n"
        "Do not include markdown fences or extra text."
    )

    completion = client.chat.completions.create(
        model=DEFAULT_GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a careful attribution assistant that returns strict JSON only.",
            },
            {
                "role": "user",
                "content": f"Assess this text:\n\n{text}",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    response_text = completion.choices[0].message.content or ""
    parsed = _parse_json_response(response_text)

    verdict = parsed.get("verdict", "uncertain")
    ai_likelihood = _coerce_probability(parsed.get("ai_likelihood"), default=0.5)
    confidence = _coerce_probability(parsed.get("confidence"), default=max(ai_likelihood, 1 - ai_likelihood))
    reasoning = str(parsed.get("reasoning", "")).strip()
    evidence = parsed.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]

    return {
        "signal_name": "groq_llm_classification",
        "model": DEFAULT_GROQ_MODEL,
        "verdict": verdict,
        "ai_likelihood": ai_likelihood,
        "confidence": confidence,
        "reasoning": reasoning,
        "evidence": [str(item).strip() for item in evidence if str(item).strip()],
    }


def assess_text_with_stylometric_heuristics(text: str) -> Dict[str, Any]:
    """Score text using lightweight stylometric heuristics."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    words = WORD_PATTERN.findall(text.lower())
    if not words:
        raise ValueError("text must contain at least one word")

    sentences = [segment.strip() for segment in SENTENCE_PATTERN.findall(text) if segment.strip()]
    if not sentences:
        sentences = [text.strip()]

    sentence_lengths = [len(WORD_PATTERN.findall(sentence.lower())) for sentence in sentences if WORD_PATTERN.findall(sentence.lower())]
    if not sentence_lengths:
        sentence_lengths = [len(words)]

    avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
    sentence_variance = statistics.pvariance(sentence_lengths) if len(sentence_lengths) > 1 else 0.0

    word_counts = Counter(words)
    unique_word_ratio = len(word_counts) / len(words)
    repeated_word_ratio = 1.0 - unique_word_ratio

    punctuation_count = sum(1 for char in text if char in ".,;:!?")
    punctuation_density = punctuation_count / max(1, len(text))

    lower_text = text.lower()
    generic_phrase_hits = sum(lower_text.count(phrase) for phrase in AI_GENERIC_PHRASES)
    first_person_count = sum(1 for word in words if word in FIRST_PERSON_PRONOUNS)
    first_person_ratio = first_person_count / len(words)

    regularity_score = 1.0 / (1.0 + sentence_variance)
    polished_formality_score = 0.0
    if avg_sentence_length >= 12 and first_person_ratio == 0:
        polished_formality_score += 0.35
    if unique_word_ratio >= 0.84 and repeated_word_ratio <= 0.18:
        polished_formality_score += 0.25
    if punctuation_density <= 0.02:
        polished_formality_score += 0.20
    polished_formality_score = min(1.0, polished_formality_score)
    diversity_score = 1.0 - unique_word_ratio
    repetition_score = min(1.0, max(0.0, repeated_word_ratio * 1.5))
    punctuation_score = min(1.0, punctuation_density * 8.0)
    generic_phrase_score = min(1.0, generic_phrase_hits / max(1, len(sentences)))
    first_person_inverse = max(0.0, 1.0 - min(1.0, first_person_ratio * 6.0))

    ai_likelihood = (
        0.18 * regularity_score
        + 0.15 * diversity_score
        + 0.12 * repetition_score
        + 0.08 * punctuation_score
        + 0.27 * generic_phrase_score
        + 0.10 * first_person_inverse
        + 0.10 * polished_formality_score
    )
    confidence = max(ai_likelihood, 1 - ai_likelihood)

    evidence = [
        f"Average sentence length: {avg_sentence_length:.1f} words",
        f"Sentence length variance: {sentence_variance:.2f}",
        f"Type-token ratio: {unique_word_ratio:.2f}",
        f"Punctuation density: {punctuation_density:.3f}",
        f"Repeated-word ratio: {repeated_word_ratio:.2f}",
        f"Generic phrase hits: {generic_phrase_hits}",
        f"First-person pronoun ratio: {first_person_ratio:.2f}",
        f"Polished formality score: {polished_formality_score:.2f}",
    ]

    if ai_likelihood >= 0.65:
        reasoning = "The text uses formal, generic phrasing and limited personal voice, which can look machine-generated."
    elif ai_likelihood <= 0.35:
        reasoning = "The text uses personal language and varied phrasing, which looks more naturally written."
    else:
        reasoning = "The text has a mixed stylistic profile, with some formal phrasing but also enough personal variation to remain uncertain."

    return {
        "signal_name": "stylometric_heuristics",
        "ai_likelihood": round(ai_likelihood, 4),
        "confidence": round(confidence, 4),
        "reasoning": reasoning,
        "evidence": evidence,
        "metrics": {
            "sentence_count": len(sentence_lengths),
            "avg_sentence_length": round(avg_sentence_length, 4),
            "sentence_length_variance": round(sentence_variance, 4),
            "type_token_ratio": round(unique_word_ratio, 4),
            "punctuation_density": round(punctuation_density, 4),
            "repeated_word_ratio": round(repeated_word_ratio, 4),
            "generic_phrase_hits": generic_phrase_hits,
            "first_person_ratio": round(first_person_ratio, 4),
            "polished_formality_score": round(polished_formality_score, 4),
        },
    }


def assess_text_with_repetition_redundancy(text: str) -> Dict[str, Any]:
    """Score text using repetition and redundancy heuristics."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    words = WORD_PATTERN.findall(text.lower())
    if not words:
        raise ValueError("text must contain at least one word")

    sentences = [segment.strip().lower() for segment in SENTENCE_PATTERN.findall(text) if segment.strip()]
    if not sentences:
        sentences = [text.strip().lower()]

    normalized_sentences = [_normalize_repetition_sentence(sentence) for sentence in sentences]
    unique_sentence_ratio = len(set(normalized_sentences)) / len(normalized_sentences)
    sentence_duplication_score = 1.0 - unique_sentence_ratio
    generic_phrase_hits = sum(text.lower().count(phrase) for phrase in AI_GENERIC_PHRASES)
    boilerplate_score = min(1.0, generic_phrase_hits / 3.0)

    ngram_scores = []
    evidence = []
    for n in range(NGRAM_SIZE_RANGE[0], NGRAM_SIZE_RANGE[1] + 1):
        ngrams = list(_build_ngrams(words, n))
        if not ngrams:
            ngram_scores.append(0.0)
            continue

        counts = Counter(ngrams)
        repeated = sum(count - 1 for count in counts.values() if count > 1)
        ratio = repeated / len(ngrams)
        ngram_scores.append(ratio)
        evidence.append(f"{n}-gram repetition ratio: {ratio:.3f}")

    repeated_ngram_score = sum(ngram_scores) / len(ngram_scores) if ngram_scores else 0.0
    immediate_repeat_ratio = _immediate_repeat_ratio(words)

    structural_redundancy_score = min(1.0, repeated_ngram_score * 1.35)
    ai_likelihood = max(
        sentence_duplication_score,
        structural_redundancy_score,
        boilerplate_score * 0.75,
        immediate_repeat_ratio,
    )
    confidence = max(ai_likelihood, 1 - ai_likelihood)

    if ai_likelihood >= 0.65:
        reasoning = "The text repeats boilerplate or short phrasing in a way that suggests redundancy."
    elif ai_likelihood <= 0.35:
        reasoning = "The text has little repeated phrasing or boilerplate, which looks less redundant and more human."
    else:
        reasoning = "The text shows some repeated phrasing or boilerplate, but not enough to be confidently classified either way."

    return {
        "signal_name": "repetition_redundancy",
        "ai_likelihood": round(ai_likelihood, 4),
        "confidence": round(confidence, 4),
        "reasoning": reasoning,
        "evidence": [
            f"Sentence duplication score: {sentence_duplication_score:.3f}",
            f"Repeated n-gram score: {repeated_ngram_score:.3f}",
            f"Structural redundancy score: {structural_redundancy_score:.3f}",
            f"Immediate repeat ratio: {immediate_repeat_ratio:.3f}",
            f"Generic boilerplate score: {boilerplate_score:.3f}",
            *evidence,
        ],
        "metrics": {
            "sentence_count": len(sentences),
            "unique_sentence_ratio": round(unique_sentence_ratio, 4),
            "sentence_duplication_score": round(sentence_duplication_score, 4),
            "repeated_ngram_score": round(repeated_ngram_score, 4),
            "structural_redundancy_score": round(structural_redundancy_score, 4),
            "immediate_repeat_ratio": round(immediate_repeat_ratio, 4),
            "generic_phrase_hits": generic_phrase_hits,
            "boilerplate_score": round(boilerplate_score, 4),
        },
    }


def _parse_json_response(response_text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("Groq response did not contain valid JSON.")


def _coerce_probability(value: Any, default: float) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        probability = float(default)

    return max(0.0, min(1.0, probability))


def _normalize_repetition_sentence(sentence: str) -> str:
    normalized = WORD_PATTERN.findall(sentence.lower())
    return " ".join(normalized)


def _build_ngrams(words: list[str], size: int):
    for index in range(len(words) - size + 1):
        yield tuple(words[index : index + size])


def _immediate_repeat_ratio(words: list[str]) -> float:
    if len(words) < 2:
        return 0.0

    repeated = sum(1 for index in range(1, len(words)) if words[index] == words[index - 1])
    return repeated / (len(words) - 1)
