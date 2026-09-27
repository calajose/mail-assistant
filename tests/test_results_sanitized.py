import json
from datetime import datetime, timezone

from mail_assistant.cli import clean as clean_cli
from mail_assistant.cli import report as report_cli
from mail_assistant.config.models import EmailResult
from mail_assistant.imap.models import EmailHeader
from mail_assistant.report.generator import ReportGenerator
from mail_assistant.rules.base import Category


def make_header(**overrides) -> EmailHeader:
    base = dict(
        uid="42",
        from_="avisos@cantookstation.com",
        subject="Prestamo renovado",
        date=datetime(2026, 9, 27, 10, 30, tzinfo=timezone.utc),
        message_id="<id@prueba>",
        headers={"x-originating-ip": "203.0.113.9", "received": "from mx1.ejemplo.com"},
        flags={"\\Seen", "\\Recent"},
    )
    base.update(overrides)
    return EmailHeader(**base)


def canonical_results() -> list[dict]:
    return [
        {
            "uid": "42",
            "from_": "avisos@cantookstation.com",
            "subject": "Prestamo renovado",
            "date": "2026-09-27T10:30:00+00:00",
            "category": "IMPORTANTE",
            "explanation": "Coincidencia de lista blanca.",
        },
        {
            "uid": "43",
            "from_": "promos@ejemplo.com",
            "subject": "Descuento",
            "date": "2026-09-27T11:00:00+00:00",
            "category": "DUDOSO",
            "explanation": "Clasificado por reglas locales.",
        },
        {
            "uid": "44",
            "from_": "ruido@ejemplo.com",
            "subject": "Oferta",
            "date": "2026-09-27T12:00:00+00:00",
            "category": "DESCARTABLE",
            "explanation": "Clasificado por reglas locales.",
        },
    ]


LEGACY_RESULTS = [
    {
        "header": {
            "uid": "42",
            "from_": "avisos@cantookstation.com",
            "subject": "Prestamo renovado",
            "date": "2026-09-27T10:30:00+00:00",
            "message_id": "<id@prueba>",
            "headers": {"x-originating-ip": "203.0.113.9"},
            "flags": ["\\Seen"],
        },
        "category": "IMPORTANTE",
        "explanation": "Coincidencia de lista blanca.",
    }
]


# --- A-16: saneado del registro persistido (P8) ---


def test_email_result_solo_expone_campos_canonicos():
    payload = EmailResult.from_classification(
        make_header(), Category.IMPORTANTE, "Coincidencia de lista blanca."
    ).model_dump()

    assert set(payload) == {"uid", "from_", "subject", "date", "category", "explanation"}
    assert payload["category"] == "IMPORTANTE"


def test_email_result_no_vuelca_ips_ni_cabeceras_tecnicas():
    payload = EmailResult.from_classification(
        make_header(), Category.DUDOSO, "sin datos"
    ).model_dump()
    serializado = json.dumps(payload, ensure_ascii=False)

    assert "203.0.113.9" not in serializado
    assert "x-originating-ip" not in serializado
    assert "received" not in serializado
    assert "headers" not in serializado
    assert "flags" not in serializado


def test_email_result_rechaza_campos_adicionales():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EmailResult(
            uid="1",
            from_="a@b.com",
            subject="s",
            date="2026-09-27T10:30:00+00:00",
            category="DUDOSO",
            explanation="x",
            headers={"x": "y"},
        )


# --- Generacion de reportes con el esquema plano (FR-011) ---


def test_generador_de_reporte_lee_campos_planos():
    report = ReportGenerator().generate(
        canonical_results(), provider="gemini", model="gemini-2.5-flash"
    )

    assert "avisos@cantookstation.com" in report
    assert "Prestamo renovado" in report
    assert "Total: 3" in report


def test_run_report_acepta_el_esquema_canonico(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text(
        json.dumps(
            {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "updated_at": "2026-09-27T10:30:00+00:00",
                "results": canonical_results(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(report_cli, "ask_only_important", lambda: False)

    report_cli.run_report()

    content = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Prestamo renovado" in content


def test_run_report_rechaza_el_esquema_heredado_sin_explotar(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text(
        json.dumps({"provider": "gemini", "model": "m", "results": LEGACY_RESULTS}),
        encoding="utf-8",
    )

    report_cli.run_report()

    out = capsys.readouterr().out
    assert "canónico" in out
    assert "scan" in out
    assert not (tmp_path / "report.md").exists()


def test_run_report_avisa_si_el_archivo_esta_danado(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text("{esto no es json", encoding="utf-8")

    report_cli.run_report()

    out = capsys.readouterr().out
    assert "dañado" in out
    assert not (tmp_path / "report.md").exists()


def test_run_report_avisa_si_no_hay_archivo(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    report_cli.run_report()

    assert "scan" in capsys.readouterr().out


# --- Limpieza con el esquema canonico (A-08) ---


def test_filter_uids_lee_el_campo_plano():
    uids = clean_cli._filter_uids(canonical_results(), "descartable")
    assert uids == ["44"]

    assert clean_cli._filter_uids(canonical_results(), "all") == ["42", "43", "44"]


def test_run_clean_rechaza_el_esquema_heredado_sin_explotar(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text(
        json.dumps({"provider": "gemini", "model": "m", "results": LEGACY_RESULTS}),
        encoding="utf-8",
    )

    clean_cli.run_clean(folder=None, yes=True, all_=True)

    out = capsys.readouterr().out
    assert "canónico" in out
    assert "scan" in out


def test_run_clean_acepta_el_esquema_canonico(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.json").write_text(
        json.dumps({"provider": "gemini", "model": "m", "results": canonical_results()}),
        encoding="utf-8",
    )

    captured = {}

    class FakeClient:
        def __init__(self, account, password):
            pass

        def mark_as_read(self, uids):
            captured["uids"] = uids
            return len(uids)

    class FakeManager:
        def __init__(self, path):
            from mail_assistant.config.models import AccountConfig

            self.config = type(
                "Cfg", (), {"account": AccountConfig(name="u", host="h", folder="INBOX")}
            )()

        def get_imap_password(self, name):
            return "x"

    monkeypatch.setattr(clean_cli, "ConfigManager", FakeManager)
    monkeypatch.setattr(clean_cli, "MailClient", FakeClient)

    clean_cli.run_clean(folder=None, yes=True, all_=True)

    assert captured["uids"] == ["42", "43", "44"]
