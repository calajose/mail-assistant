from pathlib import Path
from ..config.manager import ConfigManager
from ..imap.client import MailClient


def run_folders():
    config_path = Path.home() / ".config" / "mail-assistant" / "config.yaml"
    try:
        manager = ConfigManager(config_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return

    mail_client = MailClient(
        manager.config.account,
        manager.get_imap_password(manager.config.account.name),
    )

    try:
        folders = mail_client.list_folders()
    except Exception as exc:
        print(f"Error al conectar con el servidor IMAP: {exc}")
        return

    configured = manager.config.account.folder
    print(f"Carpetas disponibles en {manager.config.account.host}:")
    for name in folders:
        marker = " (configurada)" if name.lower() == configured.lower() else ""
        print(f"  - {name}{marker}")
