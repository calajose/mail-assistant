import pytest
from pydantic import ValidationError

from mail_assistant.config.models import EmailResult
from mail_assistant.llm.ollama import _CLASSIFICATION_SCHEMA
from mail_assistant.rules.base import Category


def _gemini_prompt() -> str:
    from mail_assistant.config.defaults import DEFAULT_GEMINI_PROMPT

    return DEFAULT_GEMINI_PROMPT


def _ollama_prompt() -> str:
    from mail_assistant.config.defaults import DEFAULT_OLLAMA_PROMPT

    return DEFAULT_OLLAMA_PROMPT


def make_phishing_result(**overrides) -> dict:
    base = dict(
        uid="901",
        from_="seguridad@banco-ejemplo.com",
        subject="Verificacion urgente de tu cuenta",
        date="2026-10-04T09:00:00+00:00",
        category="PELIGROSO",
        explanation=(
            "Remitente suplantando al banco Ejemplo con dominio typo-squatting "
            "y solicitud urgente de credenciales bancarias."
        ),
    )
    base.update(overrides)
    return base


# --- RF-01 / CA-05: dominio, esquema y persistencia ---


def test_categoria_peligroso_existe_en_el_enum():
    assert Category.PELIGROSO.value == "PELIGROSO"


def test_email_result_admite_la_categoria_peligroso():
    resultado = EmailResult.model_validate(make_phishing_result())
    assert resultado.category == "PELIGROSO"
    assert "suplantando" in resultado.explanation


def test_email_result_sigue_rechazando_categorias_invalidas():
    with pytest.raises(ValidationError):
        EmailResult.model_validate(make_phishing_result(category="MALICIOSO"))


def test_esquema_de_ollama_incluye_peligroso_automaticamente():
    assert "PELIGROSO" in _CLASSIFICATION_SCHEMA["properties"]["category"]["enum"]


def test_esquema_de_ollama_conserva_las_tres_categorias_previas():
    enum = _CLASSIFICATION_SCHEMA["properties"]["category"]["enum"]
    for valor in ("IMPORTANTE", "DUDOSO", "DESCARTABLE"):
        assert valor in enum


def test_esquema_de_ollama_coincide_con_el_enum_de_categoria():
    enum = _CLASSIFICATION_SCHEMA["properties"]["category"]["enum"]
    assert enum == [c.value for c in Category]


def test_resultados_historicos_sin_peligroso_siguen_validos():
    historico = {
        "uid": "42",
        "from_": "avisos@ejemplo.com",
        "subject": "Prestamo renovado",
        "date": "2026-09-27T10:30:00+00:00",
        "category": "IMPORTANTE",
        "explanation": "Coincidencia de lista blanca.",
    }
    assert EmailResult.model_validate(historico).category == "IMPORTANTE"


def test_load_canonical_results_acepta_la_categoria_peligroso(tmp_path):
    import json

    from mail_assistant.utils.results_io import load_canonical_results

    (tmp_path / "results.json").write_text(
        json.dumps({"provider": "gemini", "model": "m", "results": [make_phishing_result()]}),
        encoding="utf-8",
    )
    datos = load_canonical_results(str(tmp_path / "results.json"))
    assert datos is not None
    assert datos["results"][0]["category"] == "PELIGROSO"


# --- RF-02 / CA-01: prompts LLM con la categoria PELIGROSO (US1) ---


@pytest.mark.parametrize(
    "prompt", [_gemini_prompt(), _ollama_prompt()], ids=["gemini", "ollama"]
)
def test_prompt_declara_la_categoria_peligroso(prompt):
    assert "PELIGROSO" in prompt


@pytest.mark.parametrize(
    "prompt", [_gemini_prompt(), _ollama_prompt()], ids=["gemini", "ollama"]
)
def test_prompt_exige_explicacion_detallada_de_indicios(prompt):
    bajo = prompt.lower()
    assert "peligroso" in bajo
    assert "detall" in bajo
    assert "indicio" in bajo


@pytest.mark.parametrize(
    "prompt", [_gemini_prompt(), _ollama_prompt()], ids=["gemini", "ollama"]
)
def test_prompt_cubre_los_criterios_de_amenaza(prompt):
    bajo = prompt.lower()
    for termino in ("phishing", "suplant", "ingenier", "malware"):
        assert termino in bajo


@pytest.mark.parametrize(
    "prompt", [_gemini_prompt(), _ollama_prompt()], ids=["gemini", "ollama"]
)
def test_prompt_situa_peligroso_antes_que_dudoso(prompt):
    assert prompt.find("PELIGROSO") < prompt.find("DUDOSO")


# --- RF-07 / CA-07: resumen del escaneo en consola (US1) ---


def _reporter():
    from mail_assistant.utils.progress import ConsoleScanReporter

    return ConsoleScanReporter()


def test_reporter_inicializa_el_contador_de_peligrosos():
    assert _reporter().category_counts[Category.PELIGROSO] == 0


def test_reporter_registra_la_respuesta_peligrosa_del_llm(capsys):
    reporter = _reporter()
    reporter.llm_response(Category.PELIGROSO, duration=0.5)
    salido = capsys.readouterr().out
    assert reporter.category_counts[Category.PELIGROSO] == 1
    assert "PELIGROSO" in salido


def test_resumen_final_incluye_el_contador_de_peligrosos(capsys):
    reporter = _reporter()
    reporter.llm_response(Category.PELIGROSO)
    reporter.print_summary(processed=1)
    salido = capsys.readouterr().out
    assert "PELIGROSO:" in salido
    assert reporter.category_counts[Category.PELIGROSO] == 1


# --- RF-005 / RF-006 / RF-007 / CA-02: informe con tabla de amenazas (US2) ---


@pytest.mark.parametrize(
    ("explicacion", "esperado"),
    [
        ("Remitente suplantando a banco X con dominio typo-squatting", "Phishing / Suplantación"),
        ("Phishing dirigido a clientes", "Phishing / Suplantación"),
        ("Falsa urgencia exigiendo contraseñas", "Ingeniería social"),
        ("Solicitud urgente de credenciales bancarias", "Ingeniería social"),
        ("Adjunto ejecutable con malware", "Malware / Adjunto sospechoso"),
        ("Enlace a acortador sospechoso", "Enlace fraudulento"),
        ("Indicios diversos no catalogados", "Amenaza sospechosa"),
        ("", "Amenaza sospechosa"),
    ],
)
def test_infer_threat_type_cataloga_la_amenaza(explicacion, esperado):
    from mail_assistant.report.generator import infer_threat_type

    assert infer_threat_type(explicacion) == esperado


def _results_con_peligroso() -> list[dict]:
    return [
        {
            "uid": "50",
            "from_": "seguridad@banco-ejemplo.com",
            "subject": "Verificacion urgente",
            "date": "2026-10-04T09:00:00+00:00",
            "category": "PELIGROSO",
            "explanation": "Remitente suplantando a banco X con dominio typo-squatting.",
        },
        {
            "uid": "51",
            "from_": "aviso@ejemplo.com",
            "subject": "Factura",
            "date": "2026-10-04T10:00:00+00:00",
            "category": "IMPORTANTE",
            "explanation": "Coincidencia de lista blanca.",
        },
        {
            "uid": "52",
            "from_": "ruido@ejemplo.com",
            "subject": "Oferta",
            "date": "2026-10-04T11:00:00+00:00",
            "category": "DUDOSO",
            "explanation": "Clasificado por reglas locales.",
        },
    ]


def test_informe_incluye_el_resumen_de_peligrosos():
    from mail_assistant.report.generator import ReportGenerator

    informe = ReportGenerator().generate(_results_con_peligroso())
    assert "Peligrosos: 1" in informe


def test_informe_coloca_peligroso_antes_que_dudoso():
    from mail_assistant.report.generator import ReportGenerator

    informe = ReportGenerator().generate(_results_con_peligroso())
    assert informe.find("## Correos PELIGROSO") != -1
    assert informe.find("## Correos PELIGROSO") < informe.find("## Correos DUDOSO")


def test_tabla_de_peligrosos_muestra_tipo_de_amenaza_y_explicacion():
    from mail_assistant.report.generator import ReportGenerator

    informe = ReportGenerator().generate(_results_con_peligroso())
    cabecera = "| De | Asunto | Fecha | Tipo de amenaza | Explicación |"
    assert cabecera in informe
    assert "Phishing / Suplantación" in informe


def test_informe_sin_peligrosos_no_muestra_la_seccion():
    from mail_assistant.report.generator import ReportGenerator

    sin_peligrosos = [r for r in _results_con_peligroso() if r["category"] != "PELIGROSO"]
    informe = ReportGenerator().generate(sin_peligrosos)
    assert "Peligrosos: 0" in informe
    assert "## Correos PELIGROSO" not in informe


def test_informe_puede_excluir_peligrosos_por_parametro():
    from mail_assistant.report.generator import ReportGenerator

    informe = ReportGenerator().generate(_results_con_peligroso(), include_peligroso=False)
    assert "## Correos PELIGROSO" not in informe


# --- RF-012: dialogo interactivo de seleccion en report (US2) ---


def _scope(respuesta: str) -> dict:
    from mail_assistant.cli.report import ask_report_scope

    return ask_report_scope(respuesta=respuesta)


def test_dialogo_todos_incluye_las_cuatro_categorias():
    assert _scope("t") == {
        "important": True,
        "peligroso": True,
        "dudoso": True,
        "descartable": True,
    }


def test_dialogo_vacio_por_defecto_es_todos():
    assert all(_scope("").values())


def test_dialogo_importantes_y_peligrosos():
    assert _scope("i") == {
        "important": True,
        "peligroso": True,
        "dudoso": False,
        "descartable": False,
    }


def test_dialogo_solo_peligrosos():
    assert _scope("p") == {
        "important": False,
        "peligroso": True,
        "dudoso": False,
        "descartable": False,
    }


def test_dialogo_solo_importantes():
    assert _scope("m") == {
        "important": True,
        "peligroso": False,
        "dudoso": False,
        "descartable": False,
    }


def test_dialogo_sin_entrada_devuelve_todos():
    from mail_assistant.cli.report import ask_report_scope

    assert all(ask_report_scope().values())


# --- RF-008 / RF-009 / CA-03 / CA-04: salvaguardas en clean (US3) ---


def _results_con_peligroso_limpieza() -> list[dict]:
    return [
        {
            "uid": "60",
            "from_": "estafa@banco-falso.com",
            "subject": "Activa tu clave ahora",
            "date": "2026-10-04T09:00:00+00:00",
            "category": "PELIGROSO",
            "explanation": "Suplantación del banco con urgencia falsa.",
        },
        {
            "uid": "61",
            "from_": "ruido@ejemplo.com",
            "subject": "Oferta",
            "date": "2026-10-04T10:00:00+00:00",
            "category": "DESCARTABLE",
            "explanation": "Clasificado por reglas locales.",
        },
        {
            "uid": "62",
            "from_": "aviso@ejemplo.com",
            "subject": "Factura",
            "date": "2026-10-04T11:00:00+00:00",
            "category": "IMPORTANTE",
            "explanation": "Coincidencia de lista blanca.",
        },
    ]


def test_filter_uids_en_modo_descartable_excluye_peligrosos():
    from mail_assistant.cli import clean as clean_cli

    uids = clean_cli._filter_uids(_results_con_peligroso_limpieza(), "descartable")
    assert uids == ["61"]


def test_filter_uids_en_modo_all_conserva_la_totalidad():
    from mail_assistant.cli import clean as clean_cli

    uids = clean_cli._filter_uids(_results_con_peligroso_limpieza(), "all")
    assert uids == ["60", "61", "62"]


def _spy_mark(monkeypatch, calls):
    from mail_assistant.cli import clean as clean_cli

    monkeypatch.setattr(
        clean_cli,
        "_mark_as_read",
        lambda uids, folder, mode, account: calls.append((list(uids), mode)),
    )


def _respuestas(monkeypatch, *vals):
    iterable = iter(vals)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(iterable))


def test_clean_interactivo_todos_cancela_si_no_confirma_peligrosos(monkeypatch, capsys):
    from mail_assistant.cli import clean as clean_cli

    calls = []
    _spy_mark(monkeypatch, calls)
    _respuestas(monkeypatch, "t", "n")

    clean_cli._ask_and_execute(_results_con_peligroso_limpieza(), "INBOX", object())

    salido = capsys.readouterr().out
    assert "PELIGROSO" in salido
    assert "1 correo" in salido
    assert calls == []


def test_clean_interactivo_todos_marca_tras_confirmar_peligrosos(monkeypatch):
    from mail_assistant.cli import clean as clean_cli

    calls = []
    _spy_mark(monkeypatch, calls)
    _respuestas(monkeypatch, "t", "s")

    clean_cli._ask_and_execute(_results_con_peligroso_limpieza(), "INBOX", object())

    assert calls == [(["60", "61", "62"], "all")]


def test_clean_interactivo_descartables_no_toca_peligrosos(monkeypatch):
    from mail_assistant.cli import clean as clean_cli

    calls = []
    _spy_mark(monkeypatch, calls)
    _respuestas(monkeypatch, "d")

    clean_cli._ask_and_execute(_results_con_peligroso_limpieza(), "INBOX", object())

    assert calls == [(["61"], "descartable")]


class _FakeManager:
    def __init__(self, path):
        from mail_assistant.config.models import AccountConfig

        self.config = type(
            "Cfg", (), {"account": AccountConfig(name="u", host="h", folder="INBOX")}
        )()

    def get_imap_password(self, name):
        return "x"


class _FakeClient:
    captured: dict = {}

    def __init__(self, account, password):
        pass

    def mark_as_read(self, uids):
        _FakeClient.captured["uids"] = list(uids)
        return len(uids)


def _run_clean_con_resultados(monkeypatch, tmp_path, capsys, *, yes, all_):
    import json
    from pathlib import Path

    from mail_assistant.cli import clean as clean_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text(
        json.dumps(
            {
                "provider": "gemini",
                "model": "m",
                "results": _results_con_peligroso_limpieza(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(clean_cli, "ConfigManager", _FakeManager)
    monkeypatch.setattr(clean_cli, "MailClient", _FakeClient)
    _FakeClient.captured = {}

    clean_cli.run_clean(folder=None, yes=yes, all_=all_)
    return capsys.readouterr().out, _FakeClient.captured


def test_run_clean_yes_marca_solo_descartables(monkeypatch, tmp_path, capsys):
    salida, capturado = _run_clean_con_resultados(
        monkeypatch, tmp_path, capsys, yes=True, all_=False
    )
    assert capturado["uids"] == ["61"]
    assert "PELIGROSO" not in salida


def test_run_clean_yes_all_advise_sin_interrumpir(monkeypatch, tmp_path, capsys):
    salida, capturado = _run_clean_con_resultados(
        monkeypatch, tmp_path, capsys, yes=True, all_=True
    )
    assert "PELIGROSO" in salida
    assert capturado["uids"] == ["60", "61", "62"]


def test_run_clean_all_exige_confirmacion_extra(monkeypatch, tmp_path, capsys):
    _respuestas(monkeypatch, "no")
    salida, capturado = _run_clean_con_resultados(
        monkeypatch, tmp_path, capsys, yes=False, all_=True
    )
    assert "PELIGROSO" in salida
    assert "uids" not in capturado


def test_run_clean_all_confirma_y_marca(monkeypatch, tmp_path, capsys):
    _respuestas(monkeypatch, "si")
    salida, capturado = _run_clean_con_resultados(
        monkeypatch, tmp_path, capsys, yes=False, all_=True
    )
    assert "PELIGROSO" in salida
    assert capturado["uids"] == ["60", "61", "62"]
