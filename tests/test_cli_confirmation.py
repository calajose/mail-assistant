import pytest

from mail_assistant.cli import clean as clean_cli
from mail_assistant.cli import scan as scan_cli
from mail_assistant.utils.cli import is_confirm_all


RESULTS = [
    {
        "uid": "10",
        "from_": "ruido@ejemplo.com",
        "subject": "Oferta",
        "date": "2026-09-27T12:00:00+00:00",
        "category": "DESCARTABLE",
        "explanation": "Clasificado por reglas locales.",
    },
    {
        "uid": "11",
        "from_": "otro@ejemplo.com",
        "subject": "Aviso",
        "date": "2026-09-27T12:30:00+00:00",
        "category": "IMPORTANTE",
        "explanation": "Lista blanca.",
    },
]

CONFIRM_ALIASES = ("a", "all", "t", "todos", "A", "ALL", "T", "TODOS", "  all  ")
REJECT_ANSWERS = ("d", "descartable", "n", "no", "solo", "", "q")


# --- A-07: vocabulario unico de confirmacion (P4) ---


@pytest.mark.parametrize("answer", CONFIRM_ALIASES)
def test_is_confirm_all_acepta_todas_las_variantes(answer):
    assert is_confirm_all(answer) is True


@pytest.mark.parametrize("answer", REJECT_ANSWERS)
def test_is_confirm_all_rechaza_el_resto(answer):
    assert is_confirm_all(answer) is False


def test_is_confirm_all_no_explota_con_none():
    assert is_confirm_all(None) is False


@pytest.mark.parametrize("answer", CONFIRM_ALIASES)
def test_resolve_scan_limit_acepta_las_mismas_variantes(monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda *a, **k: answer)
    assert scan_cli._resolve_scan_limit(total_unread=10, limit=5) == 10


@pytest.mark.parametrize("answer", ("", "d", "n"))
def test_resolve_scan_limit_conserva_el_limite_si_no_confirma(monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda *a, **k: answer)
    assert scan_cli._resolve_scan_limit(total_unread=10, limit=5) == 5


def test_resolve_scan_limit_cancela_en_entrada_cerrada(monkeypatch):
    def _raise(*a, **k):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    assert scan_cli._resolve_scan_limit(total_unread=10, limit=5) == 5


def _answer(monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda *a, **k: answer)


def _spy_mark(monkeypatch, calls):
    monkeypatch.setattr(
        clean_cli,
        "_mark_as_read",
        lambda uids, folder, mode, account: calls.append((list(uids), mode)),
    )


@pytest.mark.parametrize("answer", CONFIRM_ALIASES)
def test_clean_confirma_todos_con_las_mismas_variantes(monkeypatch, answer):
    calls = []
    _spy_mark(monkeypatch, calls)
    _answer(monkeypatch, answer)

    clean_cli._ask_and_execute(RESULTS, "INBOX", object())

    assert calls and calls[0][1] == "all"
    assert calls[0][0] == ["10", "11"]


@pytest.mark.parametrize("answer", ("", "d", "descartable", "n"))
def test_clean_por_defecto_solo_descartables(monkeypatch, answer):
    calls = []
    _spy_mark(monkeypatch, calls)
    _answer(monkeypatch, answer)

    clean_cli._ask_and_execute(RESULTS, "INBOX", object())

    assert calls and calls[0][1] == "descartable"
    assert calls[0][0] == ["10"]


def test_clean_cancela_si_no_hay_entrada(monkeypatch):
    calls = []
    _spy_mark(monkeypatch, calls)

    def _raise(*a, **k):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    clean_cli._ask_and_execute(RESULTS, "INBOX", object())

    assert calls == []
