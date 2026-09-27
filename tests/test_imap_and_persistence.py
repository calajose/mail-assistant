from types import SimpleNamespace

import pytest

from mail_assistant.classifier.service import ClassifierService
from mail_assistant.cli import scan as scan_cli
from mail_assistant.config.models import AccountConfig, ClassifierRules, Thresholds
from mail_assistant.imap import client as imap_client
from mail_assistant.imap.client import MailClient
from mail_assistant.rules.engine import RuleEngine
from mail_assistant.utils.progress import ScanReporter


class FakeFolder:
    def __init__(self):
        self.set_calls = []

    def list(self):
        return [SimpleNamespace(name="INBOX"), SimpleNamespace(name="Bulk")]

    def set(self, name, readonly=False):
        self.set_calls.append((name, readonly))


class FakeMailBox:
    created: list["FakeMailBox"] = []

    def __init__(self, host="", port=993, timeout=None, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.folder = FakeFolder()
        self.broken = False
        self.logged_out = False
        self.fetch_calls = 0
        FakeMailBox.created.append(self)

    @classmethod
    def reset(cls):
        cls.created = []

    def login(self, username, password, initial_folder="INBOX"):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.logout()
        return None

    def logout(self):
        self.logged_out = True

    def uids(self, criteria):
        return ["1", "2"]

    def numbers(self, criteria):
        return ["1", "2"]

    def fetch(self, criteria, **kwargs):
        self.fetch_calls += 1
        if self.broken:
            raise ConnectionError("socket zombi")
        return iter([SimpleNamespace(text="cuerpo del correo", flags=set())])

    def flag(self, uids, flag, value):
        return True


@pytest.fixture(autouse=True)
def fake_mailbox(monkeypatch):
    FakeMailBox.reset()
    monkeypatch.setattr(imap_client, "MailBox", FakeMailBox)
    return FakeMailBox


def make_client(timeout: int = 45) -> MailClient:
    return MailClient(
        AccountConfig(name="usuario", host="correo.ejemplo.com", folder="INBOX", timeout=timeout),
        "secreto",
    )


# --- A-12: tiempo limite en todas las conexiones IMAP ---


def test_session_utiliza_el_timeout_de_la_cuenta(fake_mailbox):
    with make_client(timeout=77).session():
        assert fake_mailbox.created[0].timeout == 77


def test_list_folders_utiliza_el_timeout(fake_mailbox):
    make_client(timeout=11).list_folders()
    assert fake_mailbox.created[0].timeout == 11


def test_mark_as_read_utiliza_el_timeout(fake_mailbox):
    make_client(timeout=13).mark_as_read(["1", "2"])
    assert fake_mailbox.created[0].timeout == 13


def test_conexion_fresca_utiliza_el_timeout(fake_mailbox):
    client = make_client(timeout=19)

    with client.session():
        client._mailbox_session.broken = True
        assert client.get_email_body_preview("1") == "cuerpo del correo"

    assert [box.timeout for box in fake_mailbox.created if box.timeout] == [19, 19]


def test_timeout_por_defecto_es_30_segundos():
    client = MailClient(AccountConfig(name="u", host="h"), "pw")
    assert client.config.timeout == 30


# --- A-11: la sesion activa se restablece tras una reconexion ---


def test_reconexion_reemplaza_la_sesion_activa(fake_mailbox):
    client = make_client()

    with client.session():
        original = client._mailbox_session
        original.broken = True

        assert client.get_email_body_preview("1") == "cuerpo del correo"

        replacement = client._mailbox_session
        assert replacement is not original

        # Los correos siguientes reutilizan la sesion ya restablecida.
        creados = len(fake_mailbox.created)
        assert client.get_email_body_preview("2") == "cuerpo del correo"
        assert len(fake_mailbox.created) == creados
        assert client._mailbox_session is replacement


def test_sin_sesion_activa_no_intent_reconexion(fake_mailbox):
    client = make_client()
    client._mailbox_session = None

    assert client.get_email_body_preview("1") == "cuerpo del correo"
    assert client._mailbox_session is None


def test_session_cierra_las_conexiones_sustituidas(fake_mailbox):
    client = make_client()

    with client.session():
        original = client._mailbox_session
        original.broken = True
        client.get_email_body_preview("1")
        replacement = client._mailbox_session

    assert original.logged_out is True
    assert replacement.logged_out is True
    assert client._mailbox_session is None


# --- A-03: guardado incremental y atomico ---


def test_write_results_es_atomico_y_no_deja_temporales(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    payload = {
        "provider": "none",
        "model": None,
        "updated_at": "2026-09-27T10:30:00+00:00",
        "results": [
            {
                "uid": "1",
                "from_": "a@b.com",
                "subject": "s",
                "date": "2026-09-27T10:30:00+00:00",
                "category": "DUDOSO",
                "explanation": "x",
            }
        ],
    }

    scan_cli._write_results(payload)

    assert (tmp_path / "results.json").exists()
    assert not (tmp_path / ".results.json.tmp").exists()

    import json

    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["results"][0]["uid"] == "1"
    assert data["updated_at"] == "2026-09-27T10:30:00+00:00"


def test_write_results_sobrescribe_el_archivo_anterior(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    empty = {"provider": "none", "model": None, "updated_at": None, "results": []}
    scan_cli._write_results(empty)
    assert (tmp_path / "results.json").read_text(encoding="utf-8")

    full = dict(empty, results=[{"uid": "9"}])
    scan_cli._write_results(full)

    import json

    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["results"] == [
        {"uid": "9"}
    ]
    assert not (tmp_path / ".results.json.tmp").exists()


class FakeMailClient:
    def __init__(self, headers):
        self._headers = headers

    def session(self):
        from contextlib import contextmanager

        @contextmanager
        def _session():
            yield self

        return _session()

    def get_unread_emails(self, limit, on_progress=None):
        return self._headers[:limit]

    def get_email_body_preview(self, uid):
        return "cuerpo"


class RecordingReporter(ScanReporter):
    def __init__(self, events):
        self.events = events

    def email_start(self, index, total, subject, sender):
        self.events.append(f"email{index}")

    def classified_by_rules(self, category, score):
        self.events.append("reglas")


def make_email(uid: str):
    from datetime import datetime

    from mail_assistant.imap.models import EmailHeader

    return EmailHeader(
        uid=uid,
        from_="alguien@ejemplo.com",
        subject=f"Asunto {uid}",
        date=datetime(2026, 9, 27, 10, 0, 0),
        message_id=f"<{uid}@prueba>",
        headers={},
        flags=set(),
    )


def make_engine() -> RuleEngine:
    return RuleEngine(
        ClassifierRules(score_thresholds=Thresholds(important=60, discard=-30))
    )


def test_on_result_se_invoca_tras_cada_correo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events: list[str] = []
    calls: list[int] = []

    headers = [make_email("1"), make_email("2"), make_email("3")]
    service = ClassifierService(
        FakeMailClient(headers),
        make_engine(),
        None,
        reporter=RecordingReporter(events),
    )

    def on_result(record):
        calls.append(int(record["header"].uid))
        events.append("guardado")

    service.process_unread(limit=3, use_llm=False, on_result=on_result)

    assert calls == [1, 2, 3]
    assert events == [
        "email1",
        "reglas",
        "guardado",
        "email2",
        "reglas",
        "guardado",
        "email3",
        "reglas",
        "guardado",
    ]


def test_results_incrementales_se_escriben_en_el_archivo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    headers = [make_email("1"), make_email("2")]
    service = ClassifierService(FakeMailClient(headers), make_engine(), None)

    serialized = []
    output = {"provider": "none", "model": None, "updated_at": None, "results": serialized}

    def on_result(record):
        from datetime import datetime, timezone

        serialized.append(scan_cli._serialize_result(record))
        output["results"] = serialized
        output["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        scan_cli._write_results(output)

    service.process_unread(limit=2, use_llm=False, on_result=on_result)

    import json

    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert [r["uid"] for r in data["results"]] == ["1", "2"]
    assert all(set(r) == {"uid", "from_", "subject", "date", "category", "explanation"} for r in data["results"])
    assert not (tmp_path / ".results.json.tmp").exists()
