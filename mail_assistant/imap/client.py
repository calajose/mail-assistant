from imap_tools import MailBox, A, MailMessageFlags
from imap_tools.errors import MailboxFolderSelectError
from contextlib import contextmanager
from collections.abc import Callable
from ..config.models import AccountConfig
from ..utils.folders import resolve_folder

FETCH_CHUNK_SIZE = 25


class FolderNotFoundError(Exception):
    def __init__(self, folder: str, available: list[str]):
        self.folder = folder
        self.available = available
        super().__init__(f"Folder '{folder}' does not exist on the server")


class MailClient:
    def __init__(self, config: AccountConfig, password: str, body_preview_limit: int = 4096):
        self.config = config
        self.password = password
        self.body_preview_limit = body_preview_limit
        self._mailbox_session = None
        self._retired_sessions: list = []

    @staticmethod
    def _safe_close(mailbox) -> None:
        try:
            mailbox.__exit__(None, None, None)
        except Exception:
            pass

    @contextmanager
    def session(self):
        with MailBox(self.config.host, port=self.config.port, timeout=self.config.timeout).login(
            self.config.name, self.password
        ) as original:
            self._select_folder(original, readonly=True)
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
                        self._safe_close(stale)
                if current is not None and current is not original:
                    self._safe_close(current)

    @contextmanager
    def _open_readonly_mailbox(self):
        if self._mailbox_session is not None:
            yield self._mailbox_session
            return

        with MailBox(self.config.host, port=self.config.port, timeout=self.config.timeout).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=True)
            yield mailbox

    def list_folders(self) -> list[str]:
        with MailBox(self.config.host, port=self.config.port, timeout=self.config.timeout).login(
            self.config.name, self.password
        ) as mailbox:
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
        replacement = MailBox(
            self.config.host, port=self.config.port, timeout=self.config.timeout
        )
        try:
            replacement.login(self.config.name, self.password)
        except Exception:
            self._safe_close(replacement)
            raise

        try:
            self._select_folder(replacement, readonly=True)
            preview = ""
            for msg in replacement.fetch(A(uid=uid)):
                preview = msg.text[:limit]
                break
        except Exception:
            self._safe_close(replacement)
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

        with MailBox(self.config.host, port=self.config.port, timeout=self.config.timeout).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=False)
            mailbox.flag(cleaned_uids, MailMessageFlags.SEEN, True)

        return len(cleaned_uids)
