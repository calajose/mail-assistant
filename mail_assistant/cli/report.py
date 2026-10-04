import json
from ..report.generator import ReportGenerator
from ..utils.results_io import load_canonical_results


_PREGUNTA = (
    "¿Qué deseas incluir en el reporte? [T]odos / [I]mportantes y Peligrosos / "
    "Solo [P]eligrosos / Solo I[m]portantes (Enter = Todos): "
)

_SCOPE_TODOS = {"important": True, "peligroso": True, "dudoso": True, "descartable": True}


def _resolve_scope(bruto: str) -> dict | None:
    if bruto in ("", "t", "todos"):
        return dict(_SCOPE_TODOS)
    if bruto in ("i", "importante", "importantes"):
        return {"important": True, "peligroso": True, "dudoso": False, "descartable": False}
    if bruto in ("p", "peligroso", "peligrosos"):
        return {"important": False, "peligroso": True, "dudoso": False, "descartable": False}
    if bruto in ("m",):
        return {"important": True, "peligroso": False, "dudoso": False, "descartable": False}
    return None


def ask_report_scope(respuesta: str | None = None) -> dict:
    if respuesta is not None:
        return _resolve_scope(respuesta.strip().lower()) or dict(_SCOPE_TODOS)

    while True:
        try:
            bruto = input(_PREGUNTA)
        except (EOFError, OSError):
            return dict(_SCOPE_TODOS)

        scope = _resolve_scope(bruto.strip().lower())
        if scope is not None:
            return scope
        print("Por favor responde con 't' (todos), 'i' (importantes y peligrosos), 'p' o 'm'.")


def ask_only_important() -> bool:
    return ask_report_scope() == {
        "important": True,
        "peligroso": False,
        "dudoso": False,
        "descartable": False,
    }


def run_report():
    data = load_canonical_results()
    if data is None:
        return

    results = data["results"]
    provider = data.get("provider", "desconocido")
    model = data.get("model", "desconocido")

    scope = ask_report_scope()

    generator = ReportGenerator()
    report = generator.generate(
        results,
        provider=provider,
        model=model,
        include_important=scope["important"],
        include_peligroso=scope["peligroso"],
        include_dudoso=scope["dudoso"],
        include_descartable=scope["descartable"],
    )

    with open("report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("\nReporte generado en report.md")
