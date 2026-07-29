"""Tests for the summarize stage — uses a fake client, never the real API."""

from types import SimpleNamespace

import pytest

from loglens.digest import build_digest
from loglens.summarize import LLMUnavailable, summarize
from loglens.windowing import Anomaly


class FakeCompletions:
    """Records the call and returns a canned OpenAI-shaped response."""

    def __init__(self, content):
        self._content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        msg = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeClient:
    def __init__(self, content):
        self.completions = FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


def _digest():
    a = Anomaly(1, "NEW", 0, 25, 25, 75.8, ["FATAL disk failure"])
    return build_digest([a], source="app.log")


def test_summarize_parses_structured_response():
    client = FakeClient(
        '{"summary":"A new fatal error appeared.",'
        '"hypotheses":["disk full"],'
        '"suggested_actions":["check /data/3"]}'
    )
    exp = summarize(_digest(), client=client)
    assert exp.summary == "A new fatal error appeared."
    assert exp.hypotheses == ["disk full"]
    assert exp.suggested_actions == ["check /data/3"]


def test_summarize_requests_json_and_zero_temp():
    client = FakeClient('{"summary":"s","hypotheses":[],"suggested_actions":[]}')
    summarize(_digest(), client=client)
    kw = client.completions.kwargs
    # Anti-hallucination wiring: structured output + deterministic decoding,
    # and the digest is the user message.
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["temperature"] == 0
    assert kw["messages"][-1]["content"] == _digest().to_json()


def test_summarize_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        summarize(_digest())  # no client, no key -> graceful failure signal
