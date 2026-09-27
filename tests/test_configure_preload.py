import getpass
from pathlib import Path

import yaml

from mail_assistant.cli import configure


EXISTING = {
    "account": {
        "name": "usuario@ejemplo.com",
        "host": "imap.ejemplo.com",
        "port": 1993,
        "folder": "INBOX",
        "timeout": 45,
    },
    "llm": {
        "provider": "gemini",
        "model": "gemini-2.5-pro",
        "max_retries": 12,
        "ollama_base_url": "http://localhost:11434",
        "ollama_format": "auto",
        "user_context": "Avisos de libros nuevos para mi",
        "body_preview_limit": 4096,
    },
    "classifier_rules": {
        "score_thresholds": {"important": 70, "discard": -45},
        "whitelist_domains": ["cantookstation.com"],
        "blacklist_domains": ["recommendations@discover.pinterest.com"],
        "force_llm_senders": ["novedades@amazon.es"],
        "positive_keywords": ["factura", "pedido"],
        "negative_keywords": ["descuento"],
    },
}

# Orden de las respuestas de `input()` en el asistente completo:
# 0 cuenta, 1 host, 2 puerto, 3 carpeta, 4 timeout, 5 proveedor, 6 modelo,
# 7 lista blanca, 8 lista negra, 9 force_llm, 10 positivas, 11 negativas,
# 12 umbral IMPORTANTE, 13 umbral DESCARTABLE, 14 limite de cuerpo.
IDX_WHITELIST = 7


def _no_network(**kwargs):
    raise RuntimeError("sin red en pruebas")


def setup_home(monkeypatch, tmp_path, existing=EXISTING):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr("keyring.get_password", lambda *a, **k: None)
    monkeypatch.setattr("keyring.set_password", lambda *a, **k: None)
    monkeypatch.setattr("google.genai.Client", _no_network)
    config_dir = tmp_path / ".config" / "mail-assistant"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    if existing is not None:
        with open(config_file, "w") as f:
            yaml.dump(existing, f)
    return config_file


def read_config(config_file) -> dict:
    with open(config_file) as f:
        return yaml.safe_load(f)


def feed(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))


# --- A-01: precarga de la configuracion existente (P16 + P17) ---


def test_full_configure_preserves_heuristic_lists(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    # Todas las respuestas vacias: el asistente debe conservar los valores actuales.
    feed(monkeypatch, *[""] * 18)

    configure.run_configure(model_only=False)

    saved = read_config(config_file)
    rules = saved["classifier_rules"]
    assert rules["whitelist_domains"] == ["cantookstation.com"]
    assert rules["blacklist_domains"] == ["recommendations@discover.pinterest.com"]
    assert rules["force_llm_senders"] == ["novedades@amazon.es"]
    assert rules["positive_keywords"] == ["factura", "pedido"]
    assert rules["negative_keywords"] == ["descuento"]


def test_full_configure_preserves_account_and_thresholds(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    feed(monkeypatch, *[""] * 18)

    configure.run_configure(model_only=False)

    saved = read_config(config_file)
    assert saved["account"]["name"] == "usuario@ejemplo.com"
    assert saved["account"]["host"] == "imap.ejemplo.com"
    assert saved["account"]["port"] == 1993
    assert saved["account"]["timeout"] == 45
    assert saved["classifier_rules"]["score_thresholds"] == {"important": 70, "discard": -45}
    assert saved["llm"]["max_retries"] == 12


def test_full_configure_can_still_edit_a_list(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    answers = [""] * 18
    answers[IDX_WHITELIST] = "cantookstation.com, ejemplo.org"
    feed(monkeypatch, *answers)

    configure.run_configure(model_only=False)

    saved = read_config(config_file)
    assert saved["classifier_rules"]["whitelist_domains"] == ["cantookstation.com", "ejemplo.org"]


def test_full_configure_first_run_builds_complete_config(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path, existing=None)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    answers = [""] * 18
    answers[0] = "nuevo@ejemplo.com"
    answers[1] = "imap.nuevo.es"
    feed(monkeypatch, *answers)

    configure.run_configure(model_only=False)

    saved = read_config(config_file)
    assert saved["account"]["name"] == "nuevo@ejemplo.com"
    assert saved["classifier_rules"]["score_thresholds"] == {"important": 60, "discard": -30}
    assert saved["classifier_rules"]["force_llm_senders"] == []


# --- A-09: --model-only no restablece max_retries (P17) ---


def test_model_only_keeps_max_retries(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    # Cambiar de proveedor = "n"; elegir modelo = Enter (se conserva el actual).
    feed(monkeypatch, "n", "")

    configure.run_configure(model_only=True)

    saved = read_config(config_file)
    assert saved["llm"]["max_retries"] == 12
    assert saved["llm"]["model"] == "gemini-2.5-pro"


def test_model_only_keeps_account_and_lists(monkeypatch, tmp_path):
    config_file = setup_home(monkeypatch, tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    feed(monkeypatch, "n", "")

    configure.run_configure(model_only=True)

    saved = read_config(config_file)
    assert saved["account"] == EXISTING["account"]
    assert saved["classifier_rules"] == EXISTING["classifier_rules"]
    assert saved["llm"]["user_context"] == "Avisos de libros nuevos para mi"


def test_full_configure_migrates_legacy_body_limit(monkeypatch, tmp_path):
    existing = dict(EXISTING, llm=dict(EXISTING["llm"], body_preview_limit=500))
    config_file = setup_home(monkeypatch, tmp_path, existing=existing)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secreto")
    feed(monkeypatch, *[""] * 18)

    configure.run_configure(model_only=False)

    saved = read_config(config_file)
    assert saved["llm"]["body_preview_limit"] == 4096
