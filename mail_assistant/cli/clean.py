import json
import sys
from pathlib import Path
from ..config.manager import ConfigManager
from ..config.models import AccountConfig
from ..imap.client import MailClient, FolderNotFoundError
from ..utils.folders import folder_error_message


def _filter_uids(results: list, mode: str) -> list[str]:
    uids = []
    for r in results:
        category = r.get("category", "")
        if mode == "all" or category == "DESCARTABLE":
            uid = r.get("header", {}).get("uid", "")
            if uid:
                uids.append(uid)
    return uids


def _ask_and_execute(results: list, folder: str, account: AccountConfig):
    try:
        answer = input(
            "¿Marcar como leidos (t)odos o solo (d)escartables? [D]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nLimpieza cancelada.")
        return

    if answer in {"t", "todos", "all"}:
        mode = "all"
    else:
        mode = "descartable"

    uids = _filter_uids(results, mode)
    if not uids:
        label = "correos DESCARTABLES" if mode == "descartable" else "correos"
        print(f"No hay {label} para marcar como leidos.")
        return

    _mark_as_read(uids, folder, mode, account)


def _mark_as_read(uids: list[str], folder: str, mode: str, account: AccountConfig):
    config_path = Path.home() / ".config" / "mail-assistant" / "config.yaml"
    manager = ConfigManager(config_path)
    mail_client = MailClient(
        account.model_copy(update={"folder": folder}),
        manager.get_imap_password(account.name),
    )
    try:
        marked = mail_client.mark_as_read(uids)
    except FolderNotFoundError as exc:
        print(folder_error_message(exc.folder, exc.available))
        sys.exit(1)
    label = "DESCARTABLES" if mode == "descartable" else "correos"
    print(f"Limpieza completada. {marked} {label} marcados como leidos en '{folder}'.")


def run_clean(folder: str | None, yes: bool, all_: bool):
    try:
        with open("results.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No se encontraron resultados de escaneo. Ejecuta 'scan' primero.")
        return

    results = data if isinstance(data, list) else data.get("results", [])

    config_path = Path.home() / ".config" / "mail-assistant" / "config.yaml"
    manager = ConfigManager(config_path)
    if folder:
        manager.config.account.folder = folder
    selected_folder = manager.config.account.folder
    account = manager.config.account

    if yes and all_:
        uids = _filter_uids(results, "all")
        if not uids:
            print("No hay correos para marcar como leidos.")
            return
        _mark_as_read(uids, selected_folder, "all", account)
    elif yes:
        uids = _filter_uids(results, "descartable")
        if not uids:
            print("No hay correos DESCARTABLES para marcar como leidos.")
            return
        _mark_as_read(uids, selected_folder, "descartable", account)
    elif all_:
        uids = _filter_uids(results, "all")
        if not uids:
            print("No hay correos para marcar como leidos.")
            return
        print(f"Se marcaran como leidos {len(uids)} correos en '{selected_folder}'.")
        _mark_as_read(uids, selected_folder, "all", account)
    else:
        if not sys.stdin.isatty():
            print("Entorno no interactivo detectado. Usa --yes para confirmar automaticamente.")
            return
        _ask_and_execute(results, selected_folder, account)
