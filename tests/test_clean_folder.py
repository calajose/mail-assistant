from mail_assistant.cli import clean
from mail_assistant.config.models import AccountConfig


class FakeManager:
    def __init__(self, path):
        self.config = type(
            "Cfg",
            (),
            {"account": AccountConfig(name="user@example.com", host="h", folder="INBOX")},
        )()

    def get_imap_password(self, name):
        return "secret"


class FakeClient:
    calls = []

    def __init__(self, account, password):
        self.account = account
        FakeClient.calls.append(account.folder)

    def mark_as_read(self, uids):
        return len(uids)


def test_mark_as_read_uses_requested_folder(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(clean, "ConfigManager", FakeManager)
    monkeypatch.setattr(clean, "MailClient", FakeClient)

    clean._mark_as_read(["1", "2"], "Bulk", "all", AccountConfig(name="u", host="h"))

    assert FakeClient.calls == ["Bulk"]


def test_mark_as_read_does_not_mutate_configured_account(monkeypatch):
    monkeypatch.setattr(clean, "ConfigManager", FakeManager)
    monkeypatch.setattr(clean, "MailClient", FakeClient)

    account = AccountConfig(name="u", host="h", folder="INBOX")
    clean._mark_as_read(["1"], "Bulk", "all", account)

    assert account.folder == "INBOX"
