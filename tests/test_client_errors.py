from imap_tools.errors import MailboxFolderSelectError

from mail_assistant.config.models import AccountConfig
from mail_assistant.imap.client import FolderNotFoundError, MailClient

AVAILABLE = ["Inbox", "Bulk", "Trash"]


def _client(folder: str) -> MailClient:
    config = AccountConfig(
        name="user@example.com",
        host="imap.example.com",
        port=993,
        folder=folder,
    )
    return MailClient(config, password="secret")


class FakeFolderManager:
    def __init__(self, available=None, set_error=None):
        self.available = available if available is not None else AVAILABLE
        self.set_error = set_error
        self.set_calls = []

    def list(self):
        return [type("FolderInfo", (), {"name": name}) for name in self.available]

    def set(self, folder, readonly=False):
        self.set_calls.append((folder, readonly))
        if self.set_error is not None:
            raise self.set_error


class FakeMailbox:
    def __init__(self, folder):
        self.folder = folder


def test_select_folder_resolves_case_insensitive():
    folder_manager = FakeFolderManager()
    client = _client("inbox")
    client._select_folder(FakeMailbox(folder_manager), readonly=True)
    assert folder_manager.set_calls == [("Inbox", True)]


def test_select_folder_missing_raises_with_available():
    folder_manager = FakeFolderManager()
    client = _client("Spam")
    try:
        client._select_folder(FakeMailbox(folder_manager), readonly=True)
    except FolderNotFoundError as exc:
        assert exc.folder == "Spam"
        assert exc.available == AVAILABLE
    else:
        raise AssertionError("FolderNotFoundError no fue lanzada")


def test_select_folder_wraps_select_error():
    select_error = MailboxFolderSelectError(command_result=("NO", [b"error"]), expected="OK")
    folder_manager = FakeFolderManager(set_error=select_error)
    client = _client("Bulk")
    try:
        client._select_folder(FakeMailbox(folder_manager), readonly=False)
    except FolderNotFoundError as exc:
        assert exc.folder == "Bulk"
        assert exc.available == AVAILABLE
        assert exc.__cause__ is select_error
    else:
        raise AssertionError("FolderNotFoundError no fue lanzada")


def test_select_folder_uses_readonly_flag():
    folder_manager = FakeFolderManager()
    client = _client("Bulk")
    client._select_folder(FakeMailbox(folder_manager), readonly=False)
    assert folder_manager.set_calls == [("Bulk", False)]
