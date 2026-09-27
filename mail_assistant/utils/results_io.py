import json

CANONICAL_FIELDS = ("uid", "from_", "subject", "date", "category", "explanation")
VALID_CATEGORIES = {"IMPORTANTE", "DUDOSO", "DESCARTABLE"}


def _formato_error(motivo: str) -> str:
    return (
        f"El archivo results.json {motivo} y no cumple el formato canónico "
        "de resultados saneados. Ejecuta 'scan' de nuevo para regenerarlo."
    )


def _validate_results(data: dict) -> str | None:
    results = data.get("results")
    if not isinstance(results, list):
        return _formato_error("no contiene la lista 'results'")

    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            return _formato_error(f"tiene un registro no válido en la posición {index}")

        missing = [field for field in CANONICAL_FIELDS if field not in item]
        if missing:
            return _formato_error(f"al registro {index} le faltan campos ({', '.join(missing)})")

        extra = [key for key in item if key not in CANONICAL_FIELDS]
        if extra:
            return _formato_error(
                f"al registro {index} le sobran campos no permitidos ({', '.join(extra)})"
            )

        if item["category"] not in VALID_CATEGORIES:
            return _formato_error(
                f"el registro {index} tiene una categoría desconocida ({item['category']!r})"
            )
    return None


def load_canonical_results(path: str = "results.json") -> dict | None:
    """Lee results.json exigiendo el esquema canónico (A-08, decision P12)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No se encontraron resultados de escaneo. Ejecuta 'scan' primero.")
        return None
    except json.JSONDecodeError:
        print(
            "El archivo results.json está dañado y no es legible. "
            "Ejecuta 'scan' de nuevo para regenerarlo."
        )
        return None

    if not isinstance(data, dict):
        print(_formato_error("no tiene la estructura de diccionario esperada"))
        return None

    error = _validate_results(data)
    if error:
        print(error)
        return None
    return data
