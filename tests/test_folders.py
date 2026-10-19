import pytest

from mail_assistant.utils.folders import (
    folder_error_message,
    resolve_folder,
    suggest_folder,
)

AVAILABLE = ["Inbox", "Bulk", "Trash", "Archive", "Notas del curso"]


def test_resolve_exact_match():
    assert resolve_folder("Bulk", AVAILABLE) == "Bulk"


def test_resolve_case_insensitive():
    assert resolve_folder("inbox", AVAILABLE) == "Inbox"
    assert resolve_folder("ARCHIVE", AVAILABLE) == "Archive"


def test_resolve_not_found():
    assert resolve_folder("Spam", AVAILABLE) is None


def test_resolve_prefers_exact_match_over_case_variant():
    assert resolve_folder("Inbox", ["inbox", "Inbox"]) == "Inbox"


def test_suggest_close_match():
    assert suggest_folder("Trashh", AVAILABLE) == "Trash"


def test_suggest_case_insensitive_fallback():
    assert suggest_folder("trashh", AVAILABLE) == "Trash"


def test_suggest_no_match():
    assert suggest_folder("zzzzzzzz", AVAILABLE) is None


def test_suggest_spam_alias_maps_to_bulk():
    assert suggest_folder("Spam", AVAILABLE) == "Bulk"


def test_suggest_alias_case_insensitive():
    assert suggest_folder("spam", AVAILABLE) == "Bulk"


def test_suggest_alias_not_used_when_folder_exists():
    assert suggest_folder("Bulk", AVAILABLE) == "Bulk"


def test_alias_no_match_when_server_has_no_spam_folder():
    assert suggest_folder("Spam", ["Inbox", "Sent"]) is None


def test_error_message_includes_folder_and_suggestion():
    message = folder_error_message("Trashh", AVAILABLE)
    assert "'Trashh'" in message
    assert "Inbox, Bulk, Trash" in message
    assert "¿quisiste decir 'Trash'?" in message
    assert "mail-assistant folders" in message


def test_error_message_without_suggestion():
    message = folder_error_message("zzzzzzzz", AVAILABLE)
    assert "¿quisiste decir" not in message
    assert "Carpetas disponibles" in message


def test_error_message_without_available_folders():
    message = folder_error_message("Spam", [])
    assert "Carpetas disponibles" not in message
    assert "mail-assistant folders" in message


class _FakeFolderManager:
    def __init__(self, path=None):
        from mail_assistant.config.models import AccountConfig

        self.config = type(
            "Cfg",
            (),
            {"account": AccountConfig(name="u@e.com", host="imap.ejemplo.com", folder="INBOX")},
        )()

    def get_imap_password(self, name):
        return "secreto"


def test_folders_reutiliza_el_mensaje_y_sale_con_1(monkeypatch, capsys):
    from mail_assistant.cli import folders as folders_cli
    from mail_assistant.imap.client import MailConnectionError

    class FalloCliente:
        def __init__(self, *args, **kwargs):
            pass

        def list_folders(self):
            raise MailConnectionError(
                MailConnectionError.NETWORK,
                detail="tiempo de espera agotado",
                suggestion="comprueba tu conexión y reintenta",
            )

    monkeypatch.setattr(folders_cli, "ConfigManager", _FakeFolderManager)
    monkeypatch.setattr(folders_cli, "MailClient", FalloCliente)

    with pytest.raises(SystemExit) as excinfo:
        folders_cli.run_folders()

    salida = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "no se ha podido conectar con el servidor IMAP" in salida
    assert "Acción sugerida" in salida
    assert "Error al conectar con el servidor IMAP" not in salida
