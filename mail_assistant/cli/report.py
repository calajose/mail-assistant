import json
from ..report.generator import ReportGenerator

def ask_only_important() -> bool:
    while True:
        try:
            ans = input("¿Qué deseas incluir en el reporte? [T]odos / solo [I]mportantes (Enter = Todos): ").strip().lower()
        except EOFError:
            return False

        if ans in ('', 't', 'todos'):
            return False
        if ans in ('i', 'importante', 'importantes'):
            return True
        print("Por favor responde con 't' (todos) o 'i' (solo importantes).")

def run_report():
    try:
        with open("results.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No se encontraron resultados de escaneo. Ejecuta 'scan' primero.")
        return

    results = data["results"]
    provider = data.get("provider", "desconocido")
    model = data.get("model", "desconocido")

    solo_importantes = ask_only_important()

    include_important = True
    include_dudoso = not solo_importantes
    include_descartable = not solo_importantes

    generator = ReportGenerator()
    report = generator.generate(
        results,
        provider=provider,
        model=model,
        include_important=include_important,
        include_dudoso=include_dudoso,
        include_descartable=include_descartable
    )
    
    with open("report.md", "w") as f:
        f.write(report)
        
    print("\nReporte generado en report.md")
