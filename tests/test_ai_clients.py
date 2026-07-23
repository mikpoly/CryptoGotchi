from cryptogotchi.ai_clients import NarrativeAI
from cryptogotchi.config import default_config


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_ollama_adapter_uses_chat_endpoint():
    cfg = default_config()
    cfg["ai"].update({"mode": "external", "provider": "ollama", "endpoint": "http://ollama:11434", "model": "tiny"})
    session = FakeSession({"message": {"content": "BTC is moving calmly."}})
    result = NarrativeAI(session).generate(cfg, {"state": "calm"}, "Local draft", "en")
    assert result.ok is True
    assert result.provider == "ollama"
    assert session.calls[0][0] == "http://ollama:11434/api/chat"
    assert session.calls[0][1]["json"]["stream"] is False


def test_openai_responses_adapter_and_local_mode():
    cfg = default_config()
    local = NarrativeAI(FakeSession({})).generate(cfg, {}, "Local brain message", "en")
    assert local.ok and local.provider == "local"
    cfg["ai"].update({"mode": "external", "provider": "openai", "endpoint": "https://api.openai.com", "model": "gpt-test", "api_key": "secret"})
    session = FakeSession({"output_text": "A compact market observation."})
    result = NarrativeAI(session).generate(cfg, {"state": "curious"}, "Local", "en")
    assert result.ok
    assert session.calls[0][0] == "https://api.openai.com/v1/responses"
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_external_failure_keeps_safe_local_text():
    cfg = default_config()
    cfg["ai"].update({"mode": "external", "provider": "ollama", "endpoint": "bad", "model": "tiny"})
    result = NarrativeAI().generate(cfg, {}, "Safe local message", "en")
    assert result.ok is False
    assert result.text == "Safe local message"
