from types import SimpleNamespace

from pii_shield.llm import guarded_complete


class FakeClient:
    """Stands in for anthropic.Anthropic(); records what it was sent."""

    def __init__(self, reply):
        self.reply = reply
        self.sent = None
        self.messages = self

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


TEXT = "Ana Diaz, (555) 201-3344, ana@example.com, SSN 457-55-5462"


def test_model_never_sees_raw_pii():
    client = FakeClient("ok")
    guarded_complete(TEXT, "Summarize.", client=client)
    prompt = client.sent["messages"][0]["content"]
    for secret in ("(555) 201-3344", "ana@example.com", "457-55-5462"):
        assert secret not in prompt
    assert "[PHONE_1]" in prompt and "[EMAIL_1]" in prompt and "[SSN_1]" in prompt


def test_reply_is_restored():
    client = FakeClient("Reach Ana at [PHONE_1] or [EMAIL_1].")
    result = guarded_complete(TEXT, "Summarize.", client=client)
    assert result.model_reply == "Reach Ana at [PHONE_1] or [EMAIL_1]."
    assert result.reply == "Reach Ana at (555) 201-3344 or ana@example.com."
    assert result.unknown_placeholders == []


def test_invented_placeholders_are_reported_not_filled():
    client = FakeClient("Call [PHONE_2].")
    result = guarded_complete(TEXT, "Summarize.", client=client)
    assert result.reply == "Call [PHONE_2]."
    assert result.unknown_placeholders == ["[PHONE_2]"]


def test_dry_run_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = guarded_complete(TEXT, "Summarize.")
    assert result.dry_run and result.reply is None
    assert "(555) 201-3344" not in result.prompt


def test_model_and_tokens_are_passed(monkeypatch):
    client = FakeClient("ok")
    guarded_complete("hi", "Say hi.", client=client, model="test-model", max_tokens=50)
    assert client.sent["model"] == "test-model" and client.sent["max_tokens"] == 50
