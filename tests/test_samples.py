import os
import json

import pytest

from app import app
from detectors import (
    assess_text_with_groq,
    assess_text_with_repetition_redundancy,
    assess_text_with_stylometric_heuristics,
)
from services import combine_signal_scores


HUMAN_SAMPLE_1 = """The Nightmare before Christmas (part 1 AND 2) I just love the whole silliness of it, Christmas, the boys meeting Santa, with Skully, and the movie is one of my faves too.

My other faves are Glorious Masquerade, Phantom bride, and Eternity Float. The outfits and songs in Glomas are *chef's kiss*. The Phantom bride was hilarious and like one of the only times we see anything remotely romantic-themed by the characters. Eternity Float bc I love Jade and his hometown is beautiful

All the events are lovely tho, another fave is tbh Lost in the Book with Stitch, it was cute and we got to see the boys wearing um, less 😳"""

HUMAN_SAMPLE_2 = """That is a hard question! I like all the ones I've played/watched so far.

My current top 3

Playful Land: I like how Kalim was one of the leading characters. I like how Kalim shows that kindness is a strength in the event. The event also kept me on the edge of my seat the whole time!

Firelit Sky: I might be biased since Kalim is my favorite character but I really enjoyed seeing where he grew up! I also liked seeing another side of Jamil and meeting his sister Najma! Overall a fun event

Halloween (Terror is Trending): I thought it was one of the funniest events! The plot was really unique! It was cool seeing the full cast work together to get back at the magicam monsters haha

Honorable Mention- Fairy Gala"""

HUMAN_SAMPLE_3 = (
    "An attention function can be described as mapping a query and a set of key-value pairs to an output, "
    "where the query, keys, values, and output are all vectors. The output is computed as a weighted sum "
    "of the values, where the weight assigned to each value is computed by a compatibility function of the "
    "query with the corresponding key."
)

AI_SAMPLE_1 = (
    "Artificial intelligence is transforming the way people create, communicate, and collaborate. "
    "In many cases, it can draft polished text quickly, organize information clearly, and maintain a "
    "consistent tone throughout a response. However, the best results often come from combining machine "
    "assistance with careful human review, because nuance, context, and lived experience still matter."
)

AI_SAMPLE_2 = (
    "In summary, the proposed framework provides a comprehensive, scalable, and efficient pathway for content analysis. "
    "By leveraging multiple layers of evaluation, the system can deliver robust outcomes, improve operational consistency, "
    "and enhance user trust. Future iterations may further optimize these capabilities through iterative refinement and "
    "continuous monitoring."
)

SAMPLES = [
    ("human_1", HUMAN_SAMPLE_1, "likely_human"),
    ("human_2", HUMAN_SAMPLE_2, "likely_human"),
    ("human_3", HUMAN_SAMPLE_3, "likely_human"),
    ("ai_1", AI_SAMPLE_1, "likely_ai"),
    ("ai_2", AI_SAMPLE_2, "likely_ai"),
]

CASUAL_IRREGULAR_SAMPLES = [
    (
        "casual_1",
        "I meant to leave early but then I could not find my keys, and somehow the cat was sitting on them. "
        "So yeah, I was late again. Not my finest moment, honestly.",
    ),
    (
        "casual_2",
        "The soup was weirdly good? Like, too much pepper at first, but then it settled down. "
        "I went back for more even though I said I would not.",
    ),
    (
        "casual_3",
        "I keep telling myself I will organize the desk tomorrow. There are receipts, two dead pens, "
        "a sock for some reason, and one very judgmental sticky note.",
    ),
    (
        "casual_4",
        "My brother said the movie was boring, but I liked the slow parts. They felt quiet in a good way. "
        "Maybe I was just tired, though.",
    ),
    (
        "casual_5",
        "Walked outside for five minutes and immediately forgot why I was mad. The air smelled like rain "
        "and someone's laundry. Tiny reset button.",
    ),
    (
        "casual_6",
        "I tried making bread again. It came out dense, kind of rude-looking, but warm enough that nobody complained.",
    ),
    (
        "casual_7",
        "There is a crack in the blue mug now, which is annoying because that is the good mug. "
        "I still used it. Probably a bad idea.",
    ),
    (
        "casual_8",
        "Not gonna lie, I clicked the wrong button three times before noticing. The screen was right there. "
        "My brain just fully walked away.",
    ),
    (
        "casual_9",
        "The meeting went fine, I guess. Too many slides, one useful comment, and then everyone pretended "
        "the last ten minutes did not exist.",
    ),
    (
        "casual_10",
        "I loved the ending, even if it made no sense. Sometimes a story can be messy and still hit exactly right.",
    ),
]

POLISHED_UNIFORM_AI_STYLE_SAMPLES = [
    (
        "polished_ai_1",
        "In summary, the proposed approach provides a comprehensive and scalable framework for improving user outcomes. "
        "By leveraging structured evaluation, the system enhances consistency, reduces operational friction, and supports "
        "continuous improvement across future iterations.",
    ),
    (
        "polished_ai_2",
        "This solution offers an efficient pathway for organizations seeking to optimize content workflows. "
        "Through careful implementation, teams can improve reliability, strengthen trust, and maintain robust outcomes "
        "across a variety of operational contexts.",
    ),
    (
        "polished_ai_3",
        "The framework is designed to support clear decision-making, scalable deployment, and measurable improvement. "
        "It combines flexible architecture with consistent evaluation practices to ensure dependable performance over time.",
    ),
    (
        "polished_ai_4",
        "By integrating multiple layers of analysis, the platform enables a more comprehensive assessment process. "
        "This method promotes transparency, enhances user confidence, and provides a foundation for iterative refinement.",
    ),
    (
        "polished_ai_5",
        "In today's digital environment, reliable systems must balance efficiency, transparency, and adaptability. "
        "A structured framework can help organizations deliver consistent results while supporting long-term scalability.",
    ),
    (
        "polished_ai_6",
        "The proposed model improves operational consistency by aligning evaluation criteria with clearly defined outcomes. "
        "This approach reduces ambiguity, supports informed review, and strengthens the overall user experience.",
    ),
    (
        "polished_ai_7",
        "A comprehensive analysis pipeline can enhance trust by making decisions easier to interpret. "
        "When combined with careful monitoring, it allows teams to identify patterns, refine processes, and improve performance.",
    ),
    (
        "polished_ai_8",
        "This methodology emphasizes scalable design, efficient processing, and transparent communication. "
        "As a result, stakeholders can better understand system behavior and make more informed decisions.",
    ),
    (
        "polished_ai_9",
        "Future iterations may further optimize the system through expanded metrics, improved calibration, and continuous monitoring. "
        "These enhancements can increase reliability while preserving flexibility across diverse use cases.",
    ),
    (
        "polished_ai_10",
        "Overall, the solution provides a robust foundation for content analysis and decision support. "
        "By leveraging consistent signals and structured review, it can enhance user trust and promote responsible implementation.",
    ),
]


def build_sample_score_report():
    rows = []

    for sample_name, text, expected_verdict in SAMPLES:
        stylometric = assess_text_with_stylometric_heuristics(text)
        repetition = assess_text_with_repetition_redundancy(text)
        llm_score = 0.15 if expected_verdict == "likely_human" else 0.85
        ensemble = combine_signal_scores(
            llm_score=llm_score,
            stylometric_score=stylometric["ai_likelihood"],
            repetition_score=repetition["ai_likelihood"],
        )

        rows.append(
            {
                "sample": sample_name,
                "llm_score": llm_score,
                "stylometric_score": stylometric["ai_likelihood"],
                "repetition_score": repetition["ai_likelihood"],
                "ensemble_ai_score": ensemble["combined_score"],
                "confidence": ensemble["confidence"],
                "verdict": ensemble["verdict"],
                "label": ensemble["label"],
            }
        )

    return rows


def build_detector_calibration_report():
    rows = []

    for sample_name, text in CASUAL_IRREGULAR_SAMPLES:
        stylometric = assess_text_with_stylometric_heuristics(text)
        repetition = assess_text_with_repetition_redundancy(text)
        rows.append(
            {
                "sample": sample_name,
                "group": "casual_irregular",
                "stylometric_score": stylometric["ai_likelihood"],
                "repetition_score": repetition["ai_likelihood"],
            }
        )

    for sample_name, text in POLISHED_UNIFORM_AI_STYLE_SAMPLES:
        stylometric = assess_text_with_stylometric_heuristics(text)
        repetition = assess_text_with_repetition_redundancy(text)
        rows.append(
            {
                "sample": sample_name,
                "group": "polished_uniform_ai_style",
                "stylometric_score": stylometric["ai_likelihood"],
                "repetition_score": repetition["ai_likelihood"],
            }
        )

    return rows


@pytest.mark.parametrize("sample_name,text,expected_verdict", SAMPLES)
def test_submit_route_uses_mocked_first_signal(monkeypatch, sample_name, text, expected_verdict):
    def fake_assess_text_with_groq(sample_text):
        return {
            "signal_name": "groq_llm_classification",
            "model": "test-model",
            "verdict": expected_verdict,
            "ai_likelihood": 0.15 if expected_verdict == "likely_human" else 0.85,
            "confidence": 0.85 if expected_verdict == "likely_human" else 0.85,
            "reasoning": f"Mocked result for {sample_name}.",
            "evidence": [f"Matched {sample_name} sample."],
        }

    def fake_assess_text_with_stylometric_heuristics(sample_text):
        if expected_verdict == "likely_human":
            score = 0.10
        else:
            score = 0.85
        return {
            "signal_name": "stylometric_heuristics",
            "ai_likelihood": score,
            "confidence": 1 - abs(0.5 - score),
            "reasoning": f"Mocked stylometric result for {sample_name}.",
            "evidence": [f"Stylometric cues for {sample_name}"],
            "metrics": {},
        }

    def fake_assess_text_with_repetition_redundancy(sample_text):
        if expected_verdict == "likely_human":
            score = 0.05
        else:
            score = 0.90
        return {
            "signal_name": "repetition_redundancy",
            "ai_likelihood": score,
            "confidence": 1 - abs(0.5 - score),
            "reasoning": f"Mocked repetition result for {sample_name}.",
            "evidence": [f"Repetition cues for {sample_name}"],
            "metrics": {},
        }

    monkeypatch.setattr("services.assess_text_with_groq", fake_assess_text_with_groq)
    monkeypatch.setattr("services.assess_text_with_stylometric_heuristics", fake_assess_text_with_stylometric_heuristics)
    monkeypatch.setattr("services.assess_text_with_repetition_redundancy", fake_assess_text_with_repetition_redundancy)

    with app.test_client() as client:
        response = client.post("/submit", json={"text": text, "creator_id": "creator_1"})

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"] == "Submission received and assessed."
    assert payload["submission"]["creator_id"] == "creator_1"
    assert payload["submission"]["text"] == text
    assert payload["combined_attribution"]["verdict"] == expected_verdict
    assert payload["attribution"]["signal_name"] == "groq_llm_classification"
    assert payload["stylometric_signal"]["signal_name"] == "stylometric_heuristics"
    assert payload["repetition_signal"]["signal_name"] == "repetition_redundancy"
    assert payload["combined_attribution"]["label"] in {
        "Likely human-written. This post appears to have been written by a person. Confidence: 89%",
        "Likely AI-generated. This post appears to have been created with AI tools. Confidence: 86%",
    }
    assert 0.0 <= payload["combined_attribution"]["combined_score"] <= 1.0
    assert 0.0 <= payload["stylometric_signal"]["ai_likelihood"] <= 1.0
    assert 0.0 <= payload["repetition_signal"]["ai_likelihood"] <= 1.0


@pytest.mark.parametrize("sample_name,text", [(sample_name, text) for sample_name, text, _ in SAMPLES])
def test_stylometric_signal_for_samples(sample_name, text):
    result = assess_text_with_stylometric_heuristics(text)

    assert result["signal_name"] == "stylometric_heuristics"
    assert 0.0 <= result["ai_likelihood"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reasoning"], str)
    assert isinstance(result["evidence"], list)
    assert result["evidence"], f"{sample_name} should produce evidence"


@pytest.mark.parametrize("sample_name,text", [(sample_name, text) for sample_name, text, _ in SAMPLES])
def test_repetition_signal_for_samples(sample_name, text):
    result = assess_text_with_repetition_redundancy(text)

    assert result["signal_name"] == "repetition_redundancy"
    assert 0.0 <= result["ai_likelihood"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reasoning"], str)
    assert isinstance(result["evidence"], list)
    assert result["evidence"], f"{sample_name} should produce evidence"


def test_stylometric_ai_samples_score_higher_than_human_samples():
    human_1 = assess_text_with_stylometric_heuristics(HUMAN_SAMPLE_1)
    human_2 = assess_text_with_stylometric_heuristics(HUMAN_SAMPLE_2)
    human_3 = assess_text_with_stylometric_heuristics(HUMAN_SAMPLE_3)
    ai_1 = assess_text_with_stylometric_heuristics(AI_SAMPLE_1)
    ai_2 = assess_text_with_stylometric_heuristics(AI_SAMPLE_2)

    human_average = (human_1["ai_likelihood"] + human_2["ai_likelihood"] + human_3["ai_likelihood"]) / 3
    ai_average = (ai_1["ai_likelihood"] + ai_2["ai_likelihood"]) / 2

    assert ai_average > human_average


def test_repetition_ai_samples_score_higher_than_human_samples():
    human_1 = assess_text_with_repetition_redundancy(HUMAN_SAMPLE_1)
    human_2 = assess_text_with_repetition_redundancy(HUMAN_SAMPLE_2)
    human_3 = assess_text_with_repetition_redundancy(HUMAN_SAMPLE_3)
    ai_1 = assess_text_with_repetition_redundancy(AI_SAMPLE_1)
    ai_2 = assess_text_with_repetition_redundancy(AI_SAMPLE_2)

    human_average = (human_1["ai_likelihood"] + human_2["ai_likelihood"] + human_3["ai_likelihood"]) / 3
    ai_average = (ai_1["ai_likelihood"] + ai_2["ai_likelihood"]) / 2

    assert ai_average > human_average


def test_combined_score_produces_three_label_categories():
    low = combine_signal_scores(0.10, 0.10, 0.10)
    lower_confidence_human = combine_signal_scores(0.30, 0.30, 0.30)
    mid = combine_signal_scores(0.50, 0.50, 0.50)
    high = combine_signal_scores(0.90, 0.90, 0.90)

    assert low["verdict"] == "likely_human"
    assert low["label"] == "Likely human-written. This post appears to have been written by a person. Confidence: 90%"
    assert lower_confidence_human["verdict"] == "likely_human"
    assert (
        lower_confidence_human["label"]
        == "Likely human-written. This post appears to have been written by a person. Confidence: 70%"
    )
    assert lower_confidence_human["label"] != low["label"]
    assert mid["verdict"] == "uncertain"
    assert (
        mid["label"]
        == "Uncertain. We cannot tell with confidence whether this post was written by a person or by AI. Confidence: 50%"
    )
    assert high["verdict"] == "likely_ai"
    assert high["label"] == "Likely AI-generated. This post appears to have been created with AI tools. Confidence: 90%"


def test_sample_score_report_contains_all_detector_outputs():
    report = build_sample_score_report()

    assert len(report) == len(SAMPLES)
    for row in report:
        assert set(row) == {
            "sample",
            "llm_score",
            "stylometric_score",
            "repetition_score",
            "ensemble_ai_score",
            "confidence",
            "verdict",
            "label",
        }
        assert 0.0 <= row["llm_score"] <= 1.0
        assert 0.0 <= row["stylometric_score"] <= 1.0
        assert 0.0 <= row["repetition_score"] <= 1.0
        assert 0.0 <= row["ensemble_ai_score"] <= 1.0
        assert 0.0 <= row["confidence"] <= 1.0


def test_detector_calibration_examples_score_polished_text_higher():
    report = build_detector_calibration_report()
    casual_rows = [row for row in report if row["group"] == "casual_irregular"]
    polished_rows = [row for row in report if row["group"] == "polished_uniform_ai_style"]

    casual_stylometric_average = sum(row["stylometric_score"] for row in casual_rows) / len(casual_rows)
    polished_stylometric_average = sum(row["stylometric_score"] for row in polished_rows) / len(polished_rows)
    casual_repetition_average = sum(row["repetition_score"] for row in casual_rows) / len(casual_rows)
    polished_repetition_average = sum(row["repetition_score"] for row in polished_rows) / len(polished_rows)

    assert polished_stylometric_average > casual_stylometric_average
    assert polished_repetition_average > casual_repetition_average


def test_print_sample_score_report():
    print(json.dumps(build_sample_score_report(), indent=2))


def test_print_detector_calibration_report():
    print(json.dumps(build_detector_calibration_report(), indent=2))


@pytest.mark.parametrize(
    "repetitive_text,varied_text",
    [
        (
            "Very simple. Very simple. Very simple. Very simple.",
            "A breeze moved through the trees. I paused by the window and listened to the rain.",
        ),
    ],
)
def test_repetition_signal_flags_redundant_text_higher(repetitive_text, varied_text):
    repetitive = assess_text_with_repetition_redundancy(repetitive_text)
    varied = assess_text_with_repetition_redundancy(varied_text)

    assert repetitive["signal_name"] == "repetition_redundancy"
    assert 0.0 <= repetitive["ai_likelihood"] <= 1.0
    assert 0.0 <= varied["ai_likelihood"] <= 1.0
    assert repetitive["ai_likelihood"] > varied["ai_likelihood"]


@pytest.mark.integration
@pytest.mark.parametrize("sample_name,text,expected_verdict", SAMPLES)
def test_live_groq_assessment_for_samples(sample_name, text, expected_verdict):
    if not os.getenv("RUN_GROQ_INTEGRATION_TESTS"):
        pytest.skip("Set RUN_GROQ_INTEGRATION_TESTS=1 to run live Groq tests.")

    result = assess_text_with_groq(text)

    assert result["signal_name"] == "groq_llm_classification"
    assert result["verdict"] in {"likely_human", "uncertain", "likely_ai"}
    assert 0.0 <= result["ai_likelihood"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reasoning"], str)
    assert isinstance(result["evidence"], list)
    assert result["evidence"], f"{sample_name} should produce at least one evidence item"

    if expected_verdict != "uncertain":
        assert result["verdict"] == expected_verdict
