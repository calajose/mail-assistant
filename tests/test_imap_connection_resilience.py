import json
from types import SimpleNamespace

import pytest
from imap_tools.errors import MailboxFolderSelectError, MailboxLoginError

from mail_assistant.cli import clean as clean_cli
from mail_assistant.cli import scan as scan_cli
from mail_assistant.config.models import AccountConfig, ClassifierRules, Thresholds
from mail_assistant.imap import client as imap_client
from mail_assistant.imap.client import (
    FolderNotFoundError,
    MailClient,
    MailConnectionError,
    RETRY_DELAYS,
)

AVAILABLE = ["INBOX", "Bulk"]


class FakeIMAPClient:
    def __init__(self):
        self.shutdown_calls = 0
        self.shutdown_error = None

    def shutdown(self):
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error


class FakeFolderManager:
    def __init__(self, available=None, set_error=None):
        self.available = AVAILABLE if available is None else available
        self.set_error = set_error
        self.set_calls = []

    def list(self):
        return [SimpleNamespace(name=name) for name in self.available]

    def set(self, folder, readonly=False):
        self.set_calls.append((folder, readonly))
        if self.set_error is not None:
            raise self.set_error


class FakeMailBox:
    failures: list[Exception] = []
    instances: list["FakeMailBox"] = []

    def __init__(self, host="", port=993, timeout=None, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.folder = FakeFolderManager()
        self.client = FakeIMAPClient()
        self.broken = False
        self.logged_out = False
        self.logout_error = None
        self.initial_folder = "INBOX"
        self.flagged = []
        self.body = "cuerpo del correo"
        FakeMailBox.instances.append(self)

    @classmethod
    def reset(cls):
        cls.failures = []
        cls.instances = []

    def login(self, username, password, initial_folder="INBOX"):
        if FakeMailBox.failures:
            raise FakeMailBox.failures.pop(0)
        self.initial_folder = initial_folder
        return self

    def logout(self):
        self.logged_out = True
        if self.logout_error is not None:
            raise self.logout_error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.logout()

    def uids(self, criteria):
        return ["1", "2"]

    def numbers(self, criteria):
        return ["1", "2"]

    def fetch(self, criteria, **kwargs):
        if self.broken:
            raise ConnectionError("socket zombi")
        return iter([SimpleNamespace(text=self.body, flags=set())])

    def flag(self, uids, flag, value):
        self.flagged.append((list(uids), flag, value))
        return True


@pytest.fixture(autouse=True)
def fake_mailbox(monkeypatch):
    FakeMailBox.reset()
    monkeypatch.setattr(imap_client, "MailBox", FakeMailBox)
    slept = []
    monkeypatch.setattr(imap_client.time, "sleep", slept.append)
    return SimpleNamespace(box=FakeMailBox, slept=slept)


def make_client(folder: str = "INBOX", timeout: int = 30, password: str = "secreto") -> MailClient:
    config = AccountConfig(name="usuario@ejemplo.com", host="imap.ejemplo.com", folder=folder, timeout=timeout)
    return MailClient(config, password=password)


def login_error() -> MailboxLoginError:
    return MailboxLoginError(command_result=("NO", [b"credenciales rechazadas"]), expected="OK")


def select_error() -> MailboxFolderSelectError:
    return MailboxFolderSelectError(command_result=("NO", [b"no existe"]), expected="OK")


def network_error() -> MailConnectionError:
    return MailConnectionError(
        MailConnectionError.NETWORK,
        detail="tiempo de espera agotado",
        suggestion="comprueba la red y reintenta",
    )


class FakeManager:
    def __init__(self, path=None, folder="INBOX"):
        self.config = SimpleNamespace(
            account=AccountConfig(name="usuario@ejemplo.com", host="imap.ejemplo.com", folder=folder),
            llm=SimpleNamespace(provider="none", model="modelo", body_preview_limit=100),
            classifier_rules=ClassifierRules(
                score_thresholds=Thresholds(important=10, discard=0)
            ),
        )

    def get_imap_password(self, name):
        return "secreto"


class FakeScanClient:
    def __init__(self, *args, **kwargs):
        self.raises_on_count = kwargs.pop("raises_on_count", None)

    def count_unread(self):
        raise network_error()

    def get_email_body_preview(self, uid, limit=None):
        return ""


class FakeCleanClient:
    def __init__(self, *args, **kwargs):
        pass

    def mark_as_read(self, uids):
        raise network_error()


class FakeFoldersClient:
    def __init__(self, *args, **kwargs):
        pass

    def list_folders(self):
        raise network_error()


class FakeService:
    def __init__(self, *args, **kwargs):
        pass

    def process_unread(self, limit, use_llm, force_llm=False, on_result=None):
        header = SimpleNamespace(uid="1", from_="a@b.com", subject="asunto", date=None)
        on_result({"header": header, "category": "DUDOSO", "explanation": "sin cambios"})
        raise network_error()


# --- US1: reintentos ante fallos transitorios ---


def test_connect_reintenta_un_fallo_transitorio(fake_mailbox):
    FakeMailBox.failures = [TimeoutError("agotado")]
    with make_client()._connect(readonly=True):
        pass
    assert len(FakeMailBox.instances) == 2
    assert fake_mailbox.slept == [RETRY_DELAYS[0]]


def test_connect_reintenta_dos_fallos_transitorios(fake_mailbox):
    FakeMailBox.failures = [OSError("red"), ConnectionError("caida")]
    with make_client()._connect(readonly=True):
        pass
    assert len(FakeMailBox.instances) == 3
    assert fake_mailbox.slept == list(RETRY_DELAYS)


def test_connect_agota_intentos_y_lanza_mail_connection_error(fake_mailbox):
    FakeMailBox.failures = [TimeoutError("1"), OSError("2"), ConnectionError("3")]
    with pytest.raises(MailConnectionError) as excinfo:
        with make_client()._connect(readonly=True):
            pass
    assert excinfo.value.reason == MailConnectionError.NETWORK
    assert "no se ha podido conectar" in str(excinfo.value)
    assert "Acción sugerida" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ConnectionError)
    assert len(FakeMailBox.instances) == 3
    assert fake_mailbox.slept == list(RETRY_DELAYS)


def test_connect_reintenta_ssl_error(fake_mailbox):
    import ssl

    FakeMailBox.failures = [ssl.SSLError("tls")]
    with make_client()._connect(readonly=True):
        pass
    assert len(FakeMailBox.instances) == 2


def test_connect_reintenta_abort_de_imap(fake_mailbox):
    import imaplib

    FakeMailBox.failures = [imaplib.IMAP4.abort("cerrado por el servidor")]
    with make_client()._connect(readonly=True):
        pass
    assert len(FakeMailBox.instances) == 2


def test_connect_no_reintenta_credenciales_invalidas(fake_mailbox):
    FakeMailBox.failures = [login_error()]
    with pytest.raises(MailConnectionError) as excinfo:
        with make_client()._connect(readonly=True):
            pass
    assert excinfo.value.reason == MailConnectionError.CREDENTIALS
    assert "credenciales" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, MailboxLoginError)
    assert len(FakeMailBox.instances) == 1
    assert fake_mailbox.slept == []


def test_connect_no_reintenta_carpeta_inexistente(fake_mailbox):
    client = make_client(folder="Spam")
    with pytest.raises(FolderNotFoundError) as excinfo:
        with client._connect(readonly=True):
            pass
    assert excinfo.value.folder == "Spam"
    assert len(FakeMailBox.instances) == 1
    assert fake_mailbox.slept == []


def test_connect_no_reintenta_error_inesperado(fake_mailbox):
    FakeMailBox.failures = [ValueError("fallo de programacion")]
    with pytest.raises(ValueError):
        with make_client()._connect(readonly=True):
            pass
    assert len(FakeMailBox.instances) == 1
    assert fake_mailbox.slept == []


def test_connect_espera_interrumpible(monkeypatch):
    FakeMailBox.failures = [TimeoutError("agotado")]

    def _interrumpir(_segundos):
        raise KeyboardInterrupt

    monkeypatch.setattr(imap_client.time, "sleep", _interrumpir)
    with pytest.raises(KeyboardInterrupt):
        with make_client()._connect(readonly=True):
            pass
    assert len(FakeMailBox.instances) == 1


def test_escaneo_recupera_cuerpos_tras_corte_a_mitad(fake_mailbox):
    client = make_client()
    with client.session() as original:
        original.broken = True
        FakeMailBox.failures = [OSError("corte")]
        assert client.get_email_body_preview("1") == "cuerpo del correo"
        assert client._mailbox_session is not original
        assert client._mailbox_session.broken is False


# --- US2: mensajes claros en la CLI ---


def test_scan_muestra_mensaje_y_sale_con_1_al_contar(monkeypatch, capsys):
    monkeypatch.setattr(scan_cli, "ConfigManager", FakeManager)
    monkeypatch.setattr(scan_cli, "MailClient", FakeScanClient)

    with pytest.raises(SystemExit) as excinfo:
        scan_cli.run_scan(limit=20, no_llm=True, folder=None)

    salida = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "no se ha podido conectar" in salida
    assert "Acción sugerida" in salida
    assert "Traceback" not in salida


def test_scan_muestra_mensaje_y_sale_con_1_al_procesar(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scan_cli, "ConfigManager", FakeManager)
    monkeypatch.setattr(scan_cli, "MailClient", lambda *a, **k: SimpleNamespace(count_unread=lambda: 0))
    monkeypatch.setattr(scan_cli, "ClassifierService", FakeService)

    with pytest.raises(SystemExit) as excinfo:
        scan_cli.run_scan(limit=20, no_llm=True, folder=None)

    salida = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "Acción sugerida" in salida
    assert "Traceback" not in salida
    persistidos = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert [r["uid"] for r in persistidos["results"]] == ["1"]


def test_clean_muestra_mensaje_y_sale_con_1(monkeypatch, capsys):
    monkeypatch.setattr(clean_cli, "ConfigManager", FakeManager)
    monkeypatch.setattr(clean_cli, "MailClient", FakeCleanClient)
    account = AccountConfig(name="usuario@ejemplo.com", host="imap.ejemplo.com")

    with pytest.raises(SystemExit) as excinfo:
        clean_cli._mark_as_read(["1"], "INBOX", "all", account)

    salida = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "no se ha podido conectar" in salida
    assert "Traceback" not in salida


def test_scan_mantiene_el_mensaje_de_carpeta_inexistente(monkeypatch, capsys):
    class MissingFolderClient:
        def __init__(self, *args, **kwargs):
            pass

        def count_unread(self):
            raise FolderNotFoundError("Spam", AVAILABLE)

    monkeypatch.setattr(scan_cli, "ConfigManager", FakeManager)
    monkeypatch.setattr(scan_cli, "MailClient", MissingFolderClient)

    with pytest.raises(SystemExit) as excinfo:
        scan_cli.run_scan(limit=20, no_llm=True, folder=None)

    salida = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "no existe en el servidor" in salida
    assert "Carpetas disponibles" in salida


# --- US3: cierre seguro ---


def test_close_cierra_socket_si_falla_la_despedida(fake_mailbox):
    client = make_client()
    box = FakeMailBox()
    box.logout_error = OSError("sin despedida")

    client._close(box)

    assert box.logged_out is True
    assert box.client.shutdown_calls == 1


def test_close_no_falla_si_el_socket_ya_esta_muerto(fake_mailbox):
    client = make_client()
    box = FakeMailBox()
    box.logout_error = OSError("muerto")
    box.client.shutdown_error = OSError("tambien muerto")

    client._close(box)

    assert box.client.shutdown_calls == 1


def test_close_no_enmascara_el_error_original(fake_mailbox):
    client = make_client()

    with pytest.raises(ValueError, match="original"):
        with client._connect(readonly=True) as box:
            box.logout_error = RuntimeError("fallo de despedida")
            raise ValueError("original")

    assert box.client.shutdown_calls == 1


def test_session_cierra_la_sesion_al_terminar(fake_mailbox):
    client = make_client()
    with client.session() as mailbox:
        assert client._mailbox_session is mailbox
    assert mailbox.logged_out is True
    assert client._mailbox_session is None


# --- US4: seleccion unica y modo solo lectura ---


def test_connect_usa_initial_folder_none(fake_mailbox):
    with make_client()._connect(readonly=True):
        pass
    assert [box.initial_folder for box in FakeMailBox.instances] == [None]


def test_connect_selecciona_una_sola_carpeta(fake_mailbox):
    with make_client()._connect(readonly=True) as box:
        pass
    assert box.folder.set_calls == [("INBOX", True)]


def test_connect_en_escritura_selecciona_en_modo_escritura(fake_mailbox):
    with make_client()._connect(readonly=False) as box:
        pass
    assert box.folder.set_calls == [("INBOX", False)]


def test_list_folders_no_selecciona_carpeta(fake_mailbox):
    carpetas = make_client().list_folders()
    assert carpetas == AVAILABLE
    assert FakeMailBox.instances[0].folder.set_calls == []
    assert FakeMailBox.instances[0].initial_folder is None


def test_mark_as_read_reintenta_sin_duplicar_efectos(fake_mailbox):
    FakeMailBox.failures = [OSError("red")]
    marked = make_client().mark_as_read(["1", "2"])

    assert marked == 2
    assert len(FakeMailBox.instances) == 2
    assert FakeMailBox.instances[-1].folder.set_calls == [("INBOX", False)]
    assert len(FakeMailBox.instances[-1].flagged) == 1
    assert fake_mailbox.slept == [RETRY_DELAYS[0]]


def test_escaneo_no_modifica_marcas_ni_selecciona_otra_carpeta(fake_mailbox):
    client = make_client()
    with client.session() as mailbox:
        client.get_unread_emails(limit=5)

    assert mailbox.flagged == []
    assert mailbox.folder.set_calls == [("INBOX", True)]
