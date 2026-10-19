import imaplib
import ssl
import time
from collections.abc import Callable
from contextlib import contextmanager

from imap_tools import A, MailBox, MailMessageFlags
from imap_tools.errors import MailboxFolderSelectError, MailboxLoginError

from ..config.models import AccountConfig
from ..utils.folders import resolve_folder

FETCH_CHUNK_SIZE = 25
RETRY_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)
TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError, ssl.SSLError, imaplib.IMAP4.abort)


class FolderNotFoundError(Exception):
    def __init__(self, folder: str, available: list[str]):
        self.folder = folder
        self.available = available
        super().__init__(f"Folder '{folder}' does not exist on the server")


class MailConnectionError(Exception):
    """Fallo de conexion con el servidor IMAP con mensaje y accion sugerida."""

    NETWORK = "network"
    CREDENTIALS = "credentials"

    def __init__(self, reason: str, detail: str = "", suggestion: str = "", subject: str = ""):
        self.reason = reason
        self.detail = detail
        self.suggestion = suggestion
        self.subject = subject
        lines = [self._headline()]
        if detail:
            lines.extend(["", f"Detalle: {detail}"])
        if suggestion:
            lines.extend(["", f"Acción sugerida: {suggestion}"])
        super().__init__("\n".join(lines))

    def _headline(self) -> str:
        if self.reason == self.CREDENTIALS:
            account = f" de la cuenta {self.subject}" if self.subject else ""
            return f"Error: el servidor IMAP ha rechazado las credenciales{account}."
        return "Error: no se ha podido conectar con el servidor IMAP."


class MailClient:
    def __init__(self, config: AccountConfig, password: str, body_preview_limit: int = 4096):
        self.config = config
        self.password = password
        self.body_preview_limit = body_preview_limit
        self._mailbox_session = None
        self._retired_sessions: list = []

    def _new_mailbox(self):
        return MailBox(self.config.host, port=self.config.port, timeout=self.config.timeout)

    @staticmethod
    def _detail(exc: Exception) -> str:
        text = str(exc).strip()
        return text or exc.__class__.__name__

    def _close(self, mailbox) -> None:
        """Cierra la sesion sin lanzar nunca y sin enmascarar el error original."""
        if mailbox is None:
            return
        try:
            mailbox.logout()
        except Exception:
            client = getattr(mailbox, "client", None)
            if client is not None:
                try:
                    client.shutdown()
                except Exception:
                    pass

    def _credentials_error(self, exc: Exception) -> MailConnectionError:
        return MailConnectionError(
            MailConnectionError.CREDENTIALS,
            detail=self._detail(exc),
            suggestion=(
                "revisa la contraseña y vuelve a ejecutar "
                "'mail-assistant configure' para actualizarla."
            ),
            subject=self.config.name,
        )

    def _network_error(self, exc: Exception) -> MailConnectionError:
        return MailConnectionError(
            MailConnectionError.NETWORK,
            detail=self._detail(exc),
            suggestion=(
                f"comprueba tu conexión a internet y que el servidor {self.config.host} "
                "esté disponible; vuelve a intentarlo más tarde."
            ),
        )

    def _open_mailbox(self, readonly: bool, select_folder: bool = True):
        last_error: Exception | None = None
        for attempt in range(RETRY_ATTEMPTS):
            if attempt:
                time.sleep(RETRY_DELAYS[attempt - 1])
            mailbox = None
            try:
                mailbox = self._new_mailbox()
                mailbox.login(self.config.name, self.password, initial_folder=None)
                if select_folder:
                    self._select_folder(mailbox, readonly=readonly)
                return mailbox
            except MailboxLoginError as exc:
                self._close(mailbox)
                raise self._credentials_error(exc) from exc
            except FolderNotFoundError:
                self._close(mailbox)
                raise
            except TRANSIENT_ERRORS as exc:
                self._close(mailbox)
                last_error = exc
            except Exception:
                self._close(mailbox)
                raise
        raise self._network_error(last_error) from last_error

    @contextmanager
    def _connect(self, readonly: bool = False, select_folder: bool = True):
        mailbox = self._open_mailbox(readonly, select_folder=select_folder)
        try:
            yield mailbox
        finally:
            self._close(mailbox)

    @contextmanager
    def session(self):
        with self._connect(readonly=True) as original:
            self._mailbox_session = original
            retired = []
            self._retired_sessions = retired
            try:
                yield original
            finally:
                current = self._mailbox_session
                self._mailbox_session = None
                self._retired_sessions = []
                for stale in retired:
                    if stale is not original:
                        self._close(stale)
                if current is not None and current is not original:
                    self._close(current)

    @contextmanager
    def _open_readonly_mailbox(self):
        if self._mailbox_session is not None:
            yield self._mailbox_session
            return

        with self._connect(readonly=True) as mailbox:
            yield mailbox

    def list_folders(self) -> list[str]:
        with self._connect(readonly=True, select_folder=False) as mailbox:
            return [folder.name for folder in mailbox.folder.list()]

    def _select_folder(self, mailbox, readonly: bool) -> None:
        available = [folder.name for folder in mailbox.folder.list()]
        resolved = resolve_folder(self.config.folder, available)
        if resolved is None:
            raise FolderNotFoundError(self.config.folder, available)
        try:
            mailbox.folder.set(resolved, readonly=readonly)
        except MailboxFolderSelectError as exc:
            raise FolderNotFoundError(self.config.folder, available) from exc

    def get_unread_emails(
        self,
        limit: int = 20,
        on_progress: Callable[[int, int], None] | None = None,
    ):
        unread_emails = []
        with self._open_readonly_mailbox() as mailbox:
            unread_uids = mailbox.uids(A(seen=False))
            total_target = min(len(unread_uids), limit)
            fetched = 0

            if on_progress:
                on_progress(0, total_target)

            for msg in mailbox.fetch(
                A(seen=False),
                limit=limit,
                mark_seen=False,
                headers_only=True,
                bulk=FETCH_CHUNK_SIZE,
            ):
                unread_emails.append(msg)
                fetched += 1
                if on_progress:
                    on_progress(fetched, total_target)
        return unread_emails

    def count_unread(self) -> int:
        with self._open_readonly_mailbox() as mailbox:
            return len(mailbox.numbers(A(seen=False)))

    def get_email_body_preview(self, uid: str, limit: int | None = None):
        effective_limit = limit if limit is not None else self.body_preview_limit
        try:
            return self._get_email_body_preview(uid, effective_limit)
        except Exception:
            if self._mailbox_session is None:
                raise
            return self._get_email_body_preview_with_fresh_connection(uid, effective_limit)

    def _get_email_body_preview(self, uid: str, limit: int) -> str:
        with self._open_readonly_mailbox() as mailbox:
            for msg in mailbox.fetch(A(uid=uid)):
                return msg.text[:limit]
        return ""

    def _get_email_body_preview_with_fresh_connection(self, uid: str, limit: int) -> str:
        replacement = self._open_mailbox(readonly=True)
        try:
            preview = ""
            for msg in replacement.fetch(A(uid=uid)):
                preview = msg.text[:limit]
                break
        except Exception:
            self._close(replacement)
            raise

        self._adopt_session(replacement)
        return preview

    def _adopt_session(self, replacement) -> None:
        """Retiene la sesion restablecida para los correos siguientes (A-11)."""
        stale = self._mailbox_session
        if stale is not None:
            self._retired_sessions.append(stale)
        self._mailbox_session = replacement

    def mark_as_read(self, uids: list[str]) -> int:
        cleaned_uids = [uid for uid in uids if uid]
        if not cleaned_uids:
            return 0

        with self._connect(readonly=False) as mailbox:
            mailbox.flag(cleaned_uids, MailMessageFlags.SEEN, True)

        return len(cleaned_uids)
