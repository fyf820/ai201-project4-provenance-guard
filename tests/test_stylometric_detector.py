import detectors


def test_stylometric_detector_returns_structured_result():
    result = detectors.assess_text_with_stylometric_heuristics(
        "The lantern glowed softly. The night was calm and quiet. I watched the moon rise over the rooftops."
    )

    assert result["signal_name"] == "stylometric_heuristics"
    assert 0.0 <= result["ai_likelihood"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reasoning"], str)
    assert isinstance(result["evidence"], list)
    assert "metrics" in result
    assert result["metrics"]["sentence_count"] >= 1


def test_stylometric_detector_flags_repetitive_text_higher_than_varied_text():
    repetitive = detectors.assess_text_with_stylometric_heuristics(
        "Very simple. Very simple. Very simple. Very simple."
    )
    varied = detectors.assess_text_with_stylometric_heuristics(
        "A breeze moved through the trees. I paused by the window and listened to the rain."
    )

    assert repetitive["ai_likelihood"] > varied["ai_likelihood"]


def test_stylometric_detector_scores_ai_samples_higher_than_human_samples():
    human_1 = detectors.assess_text_with_stylometric_heuristics(
        "The Nightmare before Christmas (part 1 AND 2) I just love the whole silliness of it, Christmas, the boys meeting Santa, with Skully, and the movie is one of my faves too. "
        "My other faves are Glorious Masquerade, Phantom bride, and Eternity Float. The outfits and songs in Glomas are *chef's kiss*. "
        "The Phantom bride was hilarious and like one of the only times we see anything remotely romantic-themed by the characters. "
        "Eternity Float bc I love Jade and his hometown is beautiful."
    )
    human_2 = detectors.assess_text_with_stylometric_heuristics(
        "That’s a hard question! I like all the ones I’ve played/watched so far. My current top 3 "
        "Playful Land: I like how Kalim was one of the leading characters. I like how Kalim shows that kindness is a strength in the event. "
        "The event also kept me on the edge of my seat the whole time! Firelit Sky: I might be biased since Kalim is my favorite character "
        "but I really enjoyed seeing where he grew up! I also liked seeing another side of Jamil and meeting his sister Najma! "
        "Overall a fun event Halloween (Terror is Trending): I thought it was one of the funniest events! The plot was really unique! "
        "It was cool seeing the full cast work together to get back at the magicam monsters haha Honorable Mention- Fairy Gala"
    )
    ai_1 = detectors.assess_text_with_stylometric_heuristics(
        "Artificial intelligence is transforming the way people create, communicate, and collaborate. In many cases, it can draft polished text quickly, "
        "organize information clearly, and maintain a consistent tone throughout a response. However, the best results often come from combining machine "
        "assistance with careful human review, because nuance, context, and lived experience still matter."
    )
    ai_2 = detectors.assess_text_with_stylometric_heuristics(
        "In summary, the proposed framework provides a comprehensive, scalable, and efficient pathway for content analysis. By leveraging multiple layers of evaluation, "
        "the system can deliver robust outcomes, improve operational consistency, and enhance user trust. Future iterations may further optimize these capabilities through iterative refinement and continuous monitoring."
    )

    assert ai_1["ai_likelihood"] > human_1["ai_likelihood"]
    assert ai_2["ai_likelihood"] > human_2["ai_likelihood"]
