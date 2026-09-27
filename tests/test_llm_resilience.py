import json
from pathlib import Path

import httpx
import pytest
import yaml

from mail_assistant.config.manager import ConfigManager
from mail_assistant.imap.models import EmailHeader
from mail_assistant.llm.base import LLMUnavailableError
from mail_assistant.llm.gemini import GeminiProvider
from mail_assistant.llm.ollama import OllamaProvider
from datetime import datetime


def make_header(subject: str = "Asunto") -> EmailHeader:
    return EmailHeader(
        uid="1",
        from_="alguien@ejemplo.com",
        subject=subject,
        date=datetime(2026, 9, 27, 10, 0, 0),
        message_id="<id@prueba>",
        headers={},
        flags=set(),
    )


VALID_BODY = json.dumps({"category": "DUDOSO", "explanation": "ok"})


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class RecordingOllamaClient:
    """Sustituye a httpx.Client registrando los prompts y simulando errores."""

    def __init__(self, failures: int = 0, error: Exception | None = None):
        self.prompts: list[str] = []
        self.calls = 0
        self.failures = failures
        self.error = error or httpx.ConnectError("sin conexion")

    def post(self, url, json=None, **kwargs):
        self.calls += 1
        self.prompts.append(json.get("prompt", ""))
        if self.calls <= self.failures:
            raise self.error
        return FakeResponse({"response": VALID_BODY, "done": True})


# --- A-10: vista previa de 4.096 caracteres uniforme (P5) ---


def test_ollama_envia_hasta_4096_caracteres(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="Eres un clasificador.",
        body_preview_limit=4096,
    )
    client = RecordingOllamaClient()
    monkeypatch.setattr(provider, "client", client)

    provider.classify_email(make_header(), {"score": 0}, "x" * 6000)

    cuerpo = client.prompts[0].split("Cuerpo: ", 1)[1]
    assert len(cuerpo.split("\n")[0]) == 4096


def test_ollama_no_retrunca_a_500_caracteres(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="Eres un clasificador.",
        body_preview_limit=4096,
    )
    client = RecordingOllamaClient()
    monkeypatch.setattr(provider, "client", client)

    provider.classify_email(make_header(), {"score": 0}, "y" * 1500)

    cuerpo = client.prompts[0].split("Cuerpo: ", 1)[1].split("\n")[0]
    assert len(cuerpo) == 1500


def test_ollama_respeta_un_limite_inferior_configurado(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="Eres un clasificador.",
        body_preview_limit=100,
    )
    client = RecordingOllamaClient()
    monkeypatch.setattr(provider, "client", client)

    provider.classify_email(make_header(), {"score": 0}, "z" * 5000)

    cuerpo = client.prompts[0].split("Cuerpo: ", 1)[1].split("\n")[0]
    assert len(cuerpo) == 100


def test_gemini_aplica_el_limite_de_cuerpo(monkeypatch):
    provider = GeminiProvider(
        api_key="k",
        model="gemini-2.5-flash",
        prompt="Eres un clasificador.",
        body_preview_limit=100,
    )
    captured = {}

    class FakeModels:
        def generate_content(self, model=None, contents=None, config=None):
            captured["contents"] = contents
            return type("R", (), {"text": VALID_BODY})()

    monkeypatch.setattr(provider, "client", type("C", (), {"models": FakeModels()})())

    provider.classify_email(make_header(), {"score": 0}, "w" * 5000)

    vista = captured["contents"].split("Vista previa del cuerpo: ", 1)[1]
    assert len(vista.split("\n")[0]) == 100


# --- A-13: reintentos de Ollama analogos a Gemini (P6) ---


def test_ollama_reintenta_tras_una_desconexion_transitoria(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="Eres un clasificador.",
        max_retries=5,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("mail_assistant.llm.ollama.time.sleep", sleeps.append)
    client = RecordingOllamaClient(failures=2)
    monkeypatch.setattr(provider, "client", client)

    result = provider.classify_email(make_header(), {"score": 0}, "cuerpo")

    assert client.calls == 3
    assert result.category.value == "DUDOSO"
    assert len(sleeps) == 2


def test_ollama_reintenta_tras_un_timeout(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="p",
        max_retries=3,
    )
    monkeypatch.setattr("mail_assistant.llm.ollama.time.sleep", lambda s: None)
    client = RecordingOllamaClient(failures=1, error=httpx.TimeoutException("tardanza"))
    monkeypatch.setattr(provider, "client", client)

    provider.classify_email(make_header(), {"score": 0}, "cuerpo")

    assert client.calls == 2


def test_ollama_agota_reintentos_y_deja_el_correo_dudoso(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="p",
        max_retries=3,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("mail_assistant.llm.ollama.time.sleep", sleeps.append)
    client = RecordingOllamaClient(failures=99)
    monkeypatch.setattr(provider, "client", client)

    with pytest.raises(LLMUnavailableError):
        provider.classify_email(make_header(), {"score": 0}, "cuerpo")

    assert client.calls == 3
    assert len(sleeps) == 2


def test_ollama_reintenta_ante_error_500_del_servidor(monkeypatch):
    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen",
        prompt="p",
        max_retries=4,
    )
    monkeypatch.setattr("mail_assistant.llm.ollama.time.sleep", lambda s: None)

    def failing_post(url, json=None, **kwargs):
        request = httpx.Request("POST", url)
        raise httpx.HTTPStatusError(
            "500", request=request, response=httpx.Response(500, request=request)
        )

    client = RecordingOllamaClient()
    client.post = failing_post
    monkeypatch.setattr(provider, "client", client)

    with pytest.raises(LLMUnavailableError):
        provider.classify_email(make_header(), {"score": 0}, "cuerpo")


# --- A-17: prompt vacio -> prompt maestro por defecto ---


def _make_manager(tmp_path) -> ConfigManager:
    config_dir = tmp_path / ".config" / "mail-assistant"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(
            {
                "account": {"name": "u", "host": "h"},
                "llm": {"provider": "gemini", "model": "m"},
                "classifier_rules": {"score_thresholds": {"important": 60, "discard": -30}},
            },
            f,
        )
    return ConfigManager(config_file)


def test_prompt_solo_comentarios_recurre_al_maestro(tmp_path):
    manager = _make_manager(tmp_path)
    user_prompt = Path(manager.config_path).parent / "prompts" / "gemini.txt"
    user_prompt.write_text("# Todo comentado\n\n   \n# nada mas\n", encoding="utf-8")

    prompt = manager.get_prompt("gemini")

    assert prompt.strip()
    assert "Asunto" in prompt or len(prompt) > 50


def test_prompt_personalizado_se_conserva(tmp_path):
    manager = _make_manager(tmp_path)
    user_prompt = Path(manager.config_path).parent / "prompts" / "gemini.txt"
    user_prompt.write_text("# comentario\nInstruccion propia\n", encoding="utf-8")

    assert manager.get_prompt("gemini") == "Instruccion propia"


# --- A-10: valor por defecto unico de 4.096 en todos los motores ---


def test_ollama_usa_4096_por_defecto():
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen", prompt="p")
    assert provider.body_preview_limit == 4096


def test_mail_client_usa_4096_por_defecto():
    from mail_assistant.config.models import AccountConfig
    from mail_assistant.imap.client import MailClient

    client = MailClient(AccountConfig(name="u", host="h"), "clave")
    assert client.body_preview_limit == 4096


def test_config_llm_usa_4096_por_defecto():
    from mail_assistant.config.models import LLMConfig

    assert LLMConfig(provider="ollama", model="qwen").body_preview_limit == 4096
