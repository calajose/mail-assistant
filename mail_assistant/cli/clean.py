import sys
from pathlib import Path
from ..config.manager import ConfigManager
from ..config.models import AccountConfig
from ..imap.client import MailClient, FolderNotFoundError
from ..utils.folders import folder_error_message
from ..utils.results_io import load_canonical_results
from ..utils.cli import is_confirm_all

CATEGORIA_PELIGROSO = "PELIGROSO"


def _peligrosos_de(results: list) -> list[dict]:
    return [r for r in results if r.get("category", "") == CATEGORIA_PELIGROSO]


def _advertir_peligrosos(conteo: int) -> None:
    print(
        f"⚠️  Atención: Hay {conteo} correo(s) clasificado(s) como PELIGROSO en el lote.",
        flush=True,
    )


def _confirmar_peligrosos() -> bool:
    try:
        respuesta = input(
            "¿Estás seguro de marcar también como leídos los correos PELIGROSO? [s/N]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return respuesta in ("s", "si", "sí", "y", "yes")


def _filter_uids(results: list, mode: str) -> list[str]:
    uids = []
    for r in results:
        category = r.get("category", "")
        if mode == "all" or category == "DESCARTABLE":
            uid = str(r.get("uid", "") or "")
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

    if is_confirm_all(answer):
        mode = "all"
    else:
        mode = "descartable"

    if mode == "all":
        peligrosos = _peligrosos_de(results)
        if peligrosos:
            _advertir_peligrosos(len(peligrosos))
            if not _confirmar_peligrosos():
                print(
                    "Limpieza cancelada: los correos PELIGROSO no se han marcado como leidos.",
                    flush=True,
                )
                return

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
    data = load_canonical_results()
    if data is None:
        return

    results = data["results"]
    peligrosos = _peligrosos_de(results)

    config_path = Path.home() / ".config" / "mail-assistant" / "config.yaml"
    manager = ConfigManager(config_path)
    if folder:
        manager.config.account.folder = folder
    selected_folder = manager.config.account.folder
    account = manager.config.account

    if yes and all_:
        if peligrosos:
            _advertir_peligrosos(len(peligrosos))
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
        if peligrosos:
            _advertir_peligrosos(len(peligrosos))
            if not _confirmar_peligrosos():
                print(
                    "Limpieza cancelada: los correos PELIGROSO no se han marcado como leidos.",
                    flush=True,
                )
                return
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
