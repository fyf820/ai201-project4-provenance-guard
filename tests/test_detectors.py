import pytest

import detectors


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs
        return _FakeCompletion(self.response_text)


class _FakeChat:
    def __init__(self, response_text):
        self.completions = _FakeCompletions(response_text)


class _FakeGroqClient:
    def __init__(self, api_key, response_text):
        self.api_key = api_key
        self.chat = _FakeChat(response_text)


def test_assess_text_with_groq_returns_structured_result(monkeypatch):
    monkeypatch.setenv("ROQ_API_KEY", "dummy-key")

    fake_response = (
        '{"verdict":"likely_human","ai_likelihood":0.18,"confidence":0.91,'
        '"reasoning":"Natural voice and specific details.","evidence":["Specific details","Personal tone"]}'
    )

    fake_client = _FakeGroqClient(api_key="dummy-key", response_text=fake_response)
    monkeypatch.setattr(detectors, "Groq", lambda api_key: fake_client)

    result = detectors.assess_text_with_groq("A short human-written sample.")

    assert result["signal_name"] == "groq_llm_classification"
    assert result["model"] == detectors.DEFAULT_GROQ_MODEL
    assert result["verdict"] == "likely_human"
    assert result["ai_likelihood"] == 0.18
    assert result["confidence"] == 0.91
    assert result["reasoning"] == "Natural voice and specific details."
    assert result["evidence"] == ["Specific details", "Personal tone"]

    request = fake_client.chat.completions.last_request
    assert request["model"] == detectors.DEFAULT_GROQ_MODEL
    assert request["temperature"] == 0.2
    assert request["messages"][1]["content"].startswith("Assess this text:\n\nA short human-written sample.")


def test_assess_text_with_groq_rejects_invalid_model_output(monkeypatch):
    monkeypatch.setenv("ROQ_API_KEY", "dummy-key")

    fake_client = _FakeGroqClient(api_key="dummy-key", response_text="not-json")
    monkeypatch.setattr(detectors, "Groq", lambda api_key: fake_client)

    with pytest.raises(ValueError, match="Groq response did not contain valid JSON"):
        detectors.assess_text_with_groq("A short sample.")
