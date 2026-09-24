import json
import sys
import time
from pathlib import Path
from ..config.manager import ConfigManager
from ..imap.client import MailClient, FolderNotFoundError
from ..rules.engine import RuleEngine
from ..llm.gemini import GeminiProvider
from ..llm.ollama import OllamaProvider
from ..classifier.service import ClassifierService
from ..utils.progress import ConsoleScanReporter
from ..utils.folders import folder_error_message


def _resolve_scan_limit(total_unread: int, limit: int) -> int:
    try:
        choice = input(
            f"Hay {total_unread} correos no leidos y el limite es {limit}. "
            "Analizar (t)odos o solo hasta el (l)imite? [t/L]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nEntrada cancelada. Se procesara solo hasta el limite.")
        return limit

    if choice in {"t", "todos", "all", "a"}:
        return total_unread
    return limit


def run_scan(limit: int, no_llm: bool, folder: str | None, process_all: bool = False, force_llm: bool = False):
    started = time.perf_counter()
    config_path = Path.home() / ".config" / "mail-assistant" / "config.yaml"
    manager = ConfigManager(config_path)

    if folder:
        manager.config.account.folder = folder

    selected_folder = manager.config.account.folder
    reporter = ConsoleScanReporter()

    mail_client = MailClient(
        manager.config.account,
        manager.get_imap_password(manager.config.account.name),
        body_preview_limit=manager.config.llm.body_preview_limit,
    )
    try:
        total_unread = mail_client.count_unread()
    except FolderNotFoundError as exc:
        print(folder_error_message(exc.folder, exc.available))
        sys.exit(1)
    print(f"Correos no leidos en '{selected_folder}': {total_unread}")
    if not no_llm:
        print(f"Proveedor LLM: {manager.config.llm.provider} | Modelo: {manager.config.llm.model}")
    else:
        print("Proveedor LLM: ninguno (solo reglas locales)")

    effective_limit = limit
    if total_unread > limit:
        if process_all:
            effective_limit = total_unread
            print(f"--all activado: se procesaran los {total_unread} correos no leidos.")
        elif not sys.stdin.isatty():
            print(
                "Entorno no interactivo detectado: se procesara solo hasta el limite. "
                "Usa --all para analizar todos."
            )
        else:
            effective_limit = _resolve_scan_limit(total_unread, limit)

    rule_engine = RuleEngine(manager.config.classifier_rules)
    
    llm = None
    if not no_llm:
        prompt = manager.get_prompt(manager.config.llm.provider)
        user_context = manager.config.llm.user_context
        if manager.config.llm.provider == "ollama":
            llm = OllamaProvider(
                base_url=manager.config.llm.ollama_base_url,
                model=manager.config.llm.model,
                prompt=prompt,
                user_context=user_context,
                format_mode=manager.config.llm.ollama_format,
                body_preview_limit=manager.config.llm.body_preview_limit,
            )
        elif manager.config.llm.provider == "gemini":
            api_key = manager.get_gemini_api_key()
            if not api_key:
                print("Error: No se encontró API key de Gemini. Configura la cuenta nuevamente.")
                sys.exit(1)
            llm = GeminiProvider(
                api_key,
                manager.config.llm.model,
                prompt=prompt,
                max_retries=manager.config.llm.max_retries,
                user_context=user_context,
                on_retry=reporter.llm_retry,
            )
        else:
            print(f"Error: Proveedor LLM desconocido: {manager.config.llm.provider}")
            sys.exit(1)

    service = ClassifierService(mail_client, rule_engine, llm, reporter=reporter)
    results = service.process_unread(effective_limit, not no_llm, force_llm=force_llm)
    
    serialized_results = []
    for r in results:
        serialized_results.append({
            "header": r["header"].model_dump(mode='json'),
            "category": r["category"].value,
            "explanation": r["explanation"]
        })

    output = {
        "provider": manager.config.llm.provider if not no_llm else "none",
        "model": manager.config.llm.model if not no_llm else None,
        "results": serialized_results,
    }
    with open("results.json", "w") as f:
        json.dump(output, f)

    elapsed = time.perf_counter() - started
    reporter.print_summary(len(results), elapsed)
