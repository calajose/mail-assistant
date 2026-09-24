import difflib

SPAM_ALIASES = {"spam", "bulk", "junk", "junk e-mail", "junk email", "correo basura"}


def resolve_folder(folder: str, available: list[str]) -> str | None:
    for name in available:
        if name == folder:
            return name
    lowered = folder.lower()
    for name in available:
        if name.lower() == lowered:
            return name
    return None


def _alias_match(folder: str, available: list[str]) -> str | None:
    if folder.lower() not in SPAM_ALIASES:
        return None
    for name in available:
        if name.lower() in SPAM_ALIASES:
            return name
    return None


def suggest_folder(folder: str, available: list[str]) -> str | None:
    alias = _alias_match(folder, available)
    if alias:
        return alias
    matches = difflib.get_close_matches(folder, available, n=1, cutoff=0.5)
    if matches:
        return matches[0]
    by_lower = {name.lower(): name for name in available}
    matches = difflib.get_close_matches(folder.lower(), list(by_lower), n=1, cutoff=0.5)
    if not matches:
        return None
    return by_lower[matches[0]]


def folder_error_message(folder: str, available: list[str]) -> str:
    lines = [f"Error: la carpeta '{folder}' no existe en el servidor."]
    if available:
        lines.append("Carpetas disponibles: " + ", ".join(available))
    suggestion = suggest_folder(folder, available)
    if suggestion:
        lines.append(f"Sugerencia: ¿quisiste decir '{suggestion}'?")
    lines.append("Usa 'mail-assistant folders' para ver todas las carpetas.")
    return "\n".join(lines)
