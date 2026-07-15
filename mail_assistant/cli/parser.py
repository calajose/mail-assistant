import argparse

def get_parser():
    parser = argparse.ArgumentParser(description="Mail Assistant")
    subparsers = parser.add_subparsers(dest="command")

    # Configure
    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("--model-only", action="store_true", help="Configurar únicamente el proveedor y modelo del LLM.")

    # Scan
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--limit", type=int, default=20)
    scan_parser.add_argument("--no-llm", action="store_true")
    scan_parser.add_argument(
        "--folder",
        default=None,
        help="Carpeta IMAP a escanear. Si no se indica, usa la carpeta configurada.",
    )
    scan_parser.add_argument(
        "--all",
        action="store_true",
        dest="process_all",
        help="Procesar todos los no leidos sin preguntar",
    )
    scan_parser.add_argument(
        "--force-llm",
        action="store_true",
        help="Forzar que todos los correos pasen por el LLM, incluso si las reglas locales los clasifican directamente.",
    )

    # Report
    subparsers.add_parser("report")

    # Clean
    clean_parser = subparsers.add_parser("clean")
    clean_parser.add_argument(
        "--folder",
        default=None,
        help="Carpeta IMAP a limpiar. Si no se indica, usa la carpeta configurada.",
    )
    clean_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma automaticamente sin preguntar",
    )
    clean_parser.add_argument(
        "--all",
        action="store_true",
        dest="process_all",
        help="Marcar todos los correos como leidos (no solo descartables)",
    )

    return parser
