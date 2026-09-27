CONFIRM_ALL_ANSWERS = frozenset({"t", "todos", "all", "a"})


def is_confirm_all(answer: str) -> bool:
    """Interpretacion unica de la respuesta afirmativa de consola.

    Convencion de negocio D-04 (acta 26 sep 2026): "t", "todos", "all" y "a"
    significan "todos" en todos los comandos interactivos (A-07).
    """
    if answer is None:
        return False
    return answer.strip().lower() in CONFIRM_ALL_ANSWERS
