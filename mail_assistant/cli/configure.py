import getpass
import yaml
from pathlib import Path
from ..config.manager import ConfigManager
from ..config.models import MailAssistantConfig, AccountConfig, LLMConfig, ClassifierRules, Thresholds

LEGACY_BODY_PREVIEW_LIMIT = 500
MODERN_BODY_PREVIEW_LIMIT = 4096


def _load_existing(config_file: Path) -> dict:
    if not config_file.exists():
        return {}
    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        print(f"Aviso: no se pudo leer {config_file}; se parte de una configuracion vacia.")
        return {}
    return data if isinstance(data, dict) else {}


def _prompt_text(label: str, current, default: str = "") -> str:
    shown = f" [{current}]" if current else ""
    raw = input(f"{label}{shown}: ").strip()
    return raw or (str(current) if current else default)


def _prompt_int(label: str, current: int) -> int:
    raw = input(f"{label} [{current}]: ").strip()
    if not raw:
        return current
    try:
        return int(raw)
    except ValueError:
        print(f"Valor no valido ('{raw}'); se conserva {current}.")
        return current


def _prompt_list(label: str, current: list[str]) -> list[str]:
    shown = ", ".join(current) if current else ""
    suffix = f" [{shown}]" if shown else ""
    raw = input(
        f"{label}{suffix} (Enter = conservar, valores separados por coma para cambiar): "
    ).strip()
    if not raw:
        return list(current)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_body_preview_limit(current) -> int:
    try:
        value = int(current)
    except (TypeError, ValueError):
        return MODERN_BODY_PREVIEW_LIMIT
    if value == LEGACY_BODY_PREVIEW_LIMIT:
        print(
            f"Limite de cuerpo actualizado de {LEGACY_BODY_PREVIEW_LIMIT} a "
            f"{MODERN_BODY_PREVIEW_LIMIT} caracteres (decision P5)."
        )
        return MODERN_BODY_PREVIEW_LIMIT
    return value


def _ask_models(models: list[str], current: str) -> str:
    print("\nModelos disponibles:")
    for idx, model_name in enumerate(models, 1):
        print(f"{idx}) {model_name}")
    print(f"{len(models) + 1}) Especificar otro modelo...")

    try:
        choice = input(f"Selecciona un modelo (1-{len(models) + 1}, Enter = actual [{current}]): ").strip()
        if not choice:
            return current
        choice_idx = int(choice)
        if 1 <= choice_idx <= len(models):
            return models[choice_idx - 1]
        if choice_idx == len(models) + 1:
            custom = input("Introduce el nombre del modelo personalizado: ").strip()
            return custom or current
        print(f"Seleccion no valida. Se usara: {current}")
    except ValueError:
        print(f"Entrada no valida. Se usara: {current}")
    return current


def _ask_provider(current: str) -> str:
    print("\nProveedores disponibles:")
    print("1) Gemini (Google)")
    print("2) Ollama (Local)")
    choice = input(f"Selecciona un proveedor (1-2, Enter = actual [{current}]): ").strip()
    if not choice:
        return current
    return "ollama" if choice == "2" else "gemini"


def _list_ollama_models(base_url: str) -> list[str]:
    print("Obteniendo modelos de Ollama...")
    try:
        import httpx
        response = httpx.get(f"{base_url}/api/tags")
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception as exc:
        print(f"No se pudieron obtener modelos de Ollama: {exc}")
        return ["llama3", "mistral"]


def _list_gemini_models(api_key: str) -> list[str]:
    known = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    if not api_key:
        return known
    try:
        print("\nConectando con Google GenAI para listar los modelos disponibles...")
        from google.genai import Client
        client = Client(api_key=api_key)
        names = [m.name for m in client.models.list() if "gemini" in m.name]
        if names:
            return sorted({name.replace("models/", "") for name in names})
    except Exception:
        print(
            "No se pudo conectar con Google GenAI para obtener la lista en tiempo real. "
            "Usando modelos conocidos por defecto."
        )
    return known


def run_configure(model_only: bool = False):
    config_dir = Path.home() / ".config" / "mail-assistant"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"

    if model_only:
        _run_model_only(config_file)
        return

    _run_full(config_file)


def _run_model_only(config_file: Path):
    if not config_file.exists():
        print(
            "Error: No se encontro ningun archivo de configuracion. "
            "Por favor, ejecuta 'mail-assistant configure' primero para configurar la cuenta por completo."
        )
        return

    print("Configurando proveedor y modelo del LLM...")

    manager = ConfigManager(config_file)
    # Precarga de la configuracion actual: solo se sobrescribe lo modificado (P17).
    config_data = manager.config.model_dump()
    llm_data = config_data.setdefault("llm", {})
    current_provider = llm_data.get("provider", "gemini")

    print(f"\nProveedor actual: {current_provider}")
    provider = _ask_provider(current_provider)

    ollama_base_url = llm_data.get("ollama_base_url", "http://localhost:11434")
    gemini_api_key = None

    if provider == "ollama":
        if provider != current_provider:
            raw = input(f"URL base de Ollama (por defecto {ollama_base_url}): ").strip()
            ollama_base_url = raw or ollama_base_url
        models = _list_ollama_models(ollama_base_url)
    else:
        gemini_api_key = manager.get_gemini_api_key()
        if not gemini_api_key or provider != current_provider:
            gemini_api_key = getpass.getpass("API Key de Gemini: ")
        models = _list_gemini_models(gemini_api_key)

    selected_model = _ask_models(models, llm_data.get("model", models[0]))

    llm_data["provider"] = provider
    llm_data["model"] = selected_model
    # A-09 / P17: no se restablece max_retries ni el resto de parametros LLM.
    if provider == "ollama":
        llm_data["ollama_base_url"] = ollama_base_url
    else:
        llm_data.pop("ollama_base_url", None)
        llm_data.pop("ollama_format", None)

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    if provider == "gemini" and gemini_api_key:
        manager.set_gemini_api_key(gemini_api_key)

    print(f"Proveedor y modelo actualizados correctamente en {config_file}")


def _run_full(config_file: Path):
    existing = _load_existing(config_file)
    existing_account = existing.get("account") or {}
    existing_llm = existing.get("llm") or {}
    existing_rules = existing.get("classifier_rules") or {}
    existing_thresholds = existing_rules.get("score_thresholds") or {}

    print("Configurando Mail Assistant...")

    account_name = _prompt_text("Nombre de la cuenta", existing_account.get("name"))
    if not account_name:
        print("Error: el nombre de la cuenta es obligatorio.")
        return
    imap_host = _prompt_text("Host IMAP", existing_account.get("host"))
    if not imap_host:
        print("Error: el host IMAP es obligatorio.")
        return
    imap_port = _prompt_int("Puerto IMAP", existing_account.get("port") or 993)
    folder = _prompt_text("Carpeta", existing_account.get("folder") or "INBOX", "INBOX")
    timeout = _prompt_int("Timeout IMAP en segundos", existing_account.get("timeout") or 30)

    imap_password = getpass.getpass("Contrasena IMAP (Enter para conservar la actual): ")

    provider = _ask_provider(existing_llm.get("provider", "gemini"))

    ollama_base_url = existing_llm.get("ollama_base_url", "http://localhost:11434")
    gemini_api_key = None

    if provider == "ollama":
        raw = input(f"URL base de Ollama (por defecto {ollama_base_url}): ").strip()
        ollama_base_url = raw or ollama_base_url
        models = _list_ollama_models(ollama_base_url)
    else:
        gemini_api_key = _existing_gemini_key()
        if not gemini_api_key:
            gemini_api_key = getpass.getpass("API Key de Gemini: ")
        models = _list_gemini_models(gemini_api_key)

    current_model = existing_llm.get("model") or models[0]
    selected_model = _ask_models(models, current_model)

    print("\nReglas de clasificacion (Enter para conservar el valor actual):")
    whitelist = _prompt_list("Dominios de lista blanca", existing_rules.get("whitelist_domains") or [])
    blacklist = _prompt_list("Dominios de lista negra", existing_rules.get("blacklist_domains") or [])
    force_llm = _prompt_list(
        "Remitentes con supervision forzada a IA", existing_rules.get("force_llm_senders") or []
    )
    positive = _prompt_list("Palabras clave positivas", existing_rules.get("positive_keywords") or [])
    negative = _prompt_list("Palabras clave negativas", existing_rules.get("negative_keywords") or [])
    important = _prompt_int("Umbral IMPORTANTE", existing_thresholds.get("important") or 60)
    discard = _prompt_int("Umbral DESCARTABLE", existing_thresholds.get("discard") or -30)

    body_limit = _resolve_body_preview_limit(existing_llm.get("body_preview_limit"))
    body_limit = _prompt_int("Limite de caracteres del cuerpo hacia el LLM", body_limit)

    config = MailAssistantConfig(
        account=AccountConfig(
            name=account_name,
            host=imap_host,
            port=imap_port,
            folder=folder,
            timeout=timeout,
        ),
        llm=LLMConfig(
            provider=provider,
            model=selected_model,
            max_retries=existing_llm.get("max_retries", 5),
            ollama_base_url=ollama_base_url,
            ollama_format=existing_llm.get("ollama_format", "auto"),
            user_context=existing_llm.get("user_context"),
            body_preview_limit=body_limit,
        ),
        classifier_rules=ClassifierRules(
            score_thresholds=Thresholds(important=important, discard=discard),
            whitelist_domains=whitelist,
            blacklist_domains=blacklist,
            force_llm_senders=force_llm,
            positive_keywords=positive,
            negative_keywords=negative,
        ),
    )

    with open(config_file, "w") as f:
        yaml.dump(config.model_dump(), f)

    manager = ConfigManager(config_file)
    if imap_password:
        manager.set_imap_password(account_name, imap_password)
    elif not existing:
        print("Aviso: no se introdujo la contrasena IMAP y no hay una configuracion previa.")
    if provider == "gemini" and gemini_api_key:
        manager.set_gemini_api_key(gemini_api_key)

    print(f"Configuracion guardada en {config_file}")


def _existing_gemini_key() -> str | None:
    import keyring

    return keyring.get_password("mail-assistant", "gemini_api_key")
