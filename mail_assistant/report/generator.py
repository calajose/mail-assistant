from ..classifier.service import Category, EXPLICACION_REGLAS_LOCALES, EXPLICACION_LLM_NO_DISPONIBLE

def escape_md(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

class ReportGenerator:
    def generate(self, results: list, provider: str = "", model: str = "", include_important: bool = True, include_dudoso: bool = True, include_descartable: bool = True) -> str:
        report = "# Reporte de Escaneo de Correos\n\n"
        if provider and model:
            report += f"**Proveedor LLM:** {provider} | **Modelo:** {model}\n\n"
        elif provider:
            report += f"**Proveedor LLM:** {provider}\n\n"

        important = [r for r in results if r["category"] == Category.IMPORTANTE.value]
        dudoso = [r for r in results if r["category"] == Category.DUDOSO.value]
        descartable = [r for r in results if r["category"] == Category.DESCARTABLE.value]
        
        report += f"Total: {len(results)}\n"
        report += f"Importantes: {len(important)}\n"
        report += f"Dudosos: {len(dudoso)}\n"
        report += f"Descartables: {len(descartable)}\n\n"
        
        if include_important and important:
            report += "## Correos IMPORTANTE\n\n"
            report += "| De | Asunto | Fecha | Explicación |\n"
            report += "| --- | --- | --- | --- |\n"
            for r in important:
                header = r["header"]
                report += f"| {escape_md(header['from_'])} | {escape_md(header['subject'])} | {escape_md(header['date'])} | {escape_md(r['explanation'])} |\n"
            report += "\n"

        if include_dudoso and dudoso:
            report += "## Correos DUDOSO\n\n"
            report += "| De | Asunto | Fecha | Origen de la Duda | Detalle / Explicación |\n"
            report += "| --- | --- | --- | --- | --- |\n"
            for r in dudoso:
                header = r["header"]
                if r["explanation"] == EXPLICACION_REGLAS_LOCALES:
                    origen = "Reglas Locales (sin LLM)"
                    detalle = "La puntuación obtenida por las reglas locales determinó que el correo es DUDOSO y el LLM no fue ejecutado (o está desactivado)."
                elif r["explanation"] == EXPLICACION_LLM_NO_DISPONIBLE:
                    origen = "LLM no disponible (error)"
                    detalle = "Se intentó consultar el LLM, pero no respondió correctamente tras varios reintentos; el correo queda como DUDOSO provisionalmente."
                else:
                    origen = "Confirmado por LLM"
                    detalle = r["explanation"]
                report += f"| {escape_md(header['from_'])} | {escape_md(header['subject'])} | {escape_md(header['date'])} | {escape_md(origen)} | {escape_md(detalle)} |\n"
            report += "\n"

        if include_descartable and descartable:
            report += "## Correos DESCARTABLE\n\n"
            report += "| De | Asunto | Fecha | Explicación |\n"
            report += "| --- | --- | --- | --- |\n"
            for r in descartable:
                header = r["header"]
                report += f"| {escape_md(header['from_'])} | {escape_md(header['subject'])} | {escape_md(header['date'])} | {escape_md(r['explanation'])} |\n"
            report += "\n"
        
        return report
