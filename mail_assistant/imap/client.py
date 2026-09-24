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
    def __init__(self, config: AccountConfig, password: str, body_preview_limit: int = 500):
        self.config = config
        self.password = password
        self.body_preview_limit = body_preview_limit
        self._mailbox_session = None

    @contextmanager
    def session(self):
        with MailBox(self.config.host, port=self.config.port).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=True)
            self._mailbox_session = mailbox
            try:
                yield mailbox
            finally:
                self._mailbox_session = None

    @contextmanager
    def _open_readonly_mailbox(self):
        if self._mailbox_session is not None:
            yield self._mailbox_session
            return

        with MailBox(self.config.host, port=self.config.port).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=True)
            yield mailbox

    def list_folders(self) -> list[str]:
        with MailBox(self.config.host, port=self.config.port).login(
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
        with MailBox(self.config.host, port=self.config.port).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=True)
            for msg in mailbox.fetch(A(uid=uid)):
                return msg.text[:limit]
        return ""

    def mark_as_read(self, uids: list[str]) -> int:
        cleaned_uids = [uid for uid in uids if uid]
        if not cleaned_uids:
            return 0

        with MailBox(self.config.host, port=self.config.port).login(
            self.config.name, self.password
        ) as mailbox:
            self._select_folder(mailbox, readonly=False)
            mailbox.flag(cleaned_uids, MailMessageFlags.SEEN, True)

        return len(cleaned_uids)
