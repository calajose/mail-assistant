import json
import httpx
import logging
import random
import re
import time
from collections.abc import Callable
from .base import LLMProvider, LLMClassificationResult, LLMUnavailableError
from ..imap.models import EmailHeader
from ..rules.base import Category

logger = logging.getLogger(__name__)

_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [c.value for c in Category]
        },
        "explanation": {
            "type": "string"
        }
    },
    "required": ["category", "explanation"]
}


class _TransientError(Exception):
    """Fallo transitorio de red o de servicio que admite reintento."""


def _retryable_status(exc: httpx.HTTPStatusError) -> bool:
    code = exc.response.status_code
    return code == 429 or code >= 500


def _first_json_object(text: str) -> str | None:
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for idx, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : idx + 1]

    return None


def _extract_json(text: str) -> dict:
    candidates: list[str] = [text]
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    first_object = _first_json_object(text)
    if first_object:
        candidates.append(first_object)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("La respuesta no es un objeto JSON.")
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("No se encontro JSON valido en la respuesta.")


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        prompt: str,
        timeout: int = 180,
        user_context: str | None = None,
        format_mode: str = "auto",
        body_preview_limit: int = 4096,
        max_retries: int = 5,
        on_retry: Callable[[int, int, str, float], None] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.prompt_intro = prompt.strip()
        self.user_context = user_context.strip() if user_context else None
        self.format_mode = format_mode.strip().lower()
        self.body_preview_limit = body_preview_limit
        self.max_retries = max(1, max_retries)
        self.on_retry = on_retry
        self.client = httpx.Client(timeout=timeout)

    def _sleep_before_retry(self, attempt: int, reason: str) -> None:
        wait_seconds = min(2 ** attempt, 30) + random.uniform(0, 1)
        if self.on_retry:
            self.on_retry(attempt, self.max_retries, reason, wait_seconds)
        time.sleep(wait_seconds)

    def _payload_variants(self, prompt: str) -> list[tuple[str, dict]]:
        all_payload_variants: list[tuple[str, dict]] = [
            (
                "schema",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": _CLASSIFICATION_SCHEMA,
                    "keep_alive": "10m",
                    "num_predict": 256,
                    "think": False,
                },
            ),
            (
                "json",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "10m",
                    "num_predict": 256,
                },
            ),
            (
                "plain",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "10m",
                    "num_predict": 256,
                },
            ),
        ]

        if self.format_mode == "auto":
            return all_payload_variants

        payload_variants = [
            (mode, payload) for mode, payload in all_payload_variants if mode == self.format_mode
        ]
        if not payload_variants:
            raise LLMUnavailableError(
                "Formato Ollama invalido. Usa: auto, schema, json o plain."
            )
        return payload_variants

    def _run_variants(self, payload_variants: list[tuple[str, dict]]) -> LLMClassificationResult:
        last_error: Exception | None = None

        for index, (mode, payload) in enumerate(payload_variants, start=1):
            try:
                response = self.client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if _retryable_status(exc):
                    raise _TransientError(
                        f"Ollama respondio {exc.response.status_code} en modo '{mode}'."
                    ) from exc
                logger.warning(
                    "Llamada Ollama fallo en modo '%s' (%s/%s): %s",
                    mode,
                    index,
                    len(payload_variants),
                    exc,
                )
                last_error = exc
                continue
            except httpx.TransportError as exc:
                raise _TransientError(f"Fallo de red con Ollama: {exc}") from exc
            except httpx.HTTPError as exc:
                raise _TransientError(f"Error HTTP con Ollama: {exc}") from exc

            data = response.json()
            raw_content = data.get("response", "")
            logger.debug("Respuesta raw del LLM (%s): %r", mode, raw_content)

            if not raw_content.strip():
                ollama_error = data.get("error")
                if ollama_error:
                    last_error = ValueError(f"Ollama devolvio un error: {ollama_error}")
                else:
                    last_error = ValueError("El LLM devolvio una respuesta vacia.")
                logger.warning(
                    "Respuesta vacia del LLM en modo '%s' (%s/%s). done=%r, done_reason=%r, error=%r",
                    mode,
                    index,
                    len(payload_variants),
                    data.get("done"),
                    data.get("done_reason"),
                    data.get("error"),
                )
                time.sleep(0.1)
                continue

            content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            try:
                result_dict = _extract_json(content)
                return LLMClassificationResult(**result_dict)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "No se pudo parsear respuesta del LLM en modo '%s' (%s/%s). Raw: %r",
                    mode,
                    index,
                    len(payload_variants),
                    raw_content,
                )
                last_error = exc
                continue

        if last_error is None:
            raise LLMUnavailableError("No se pudo obtener una respuesta valida del LLM.")
        raise LLMUnavailableError(str(last_error)) from last_error

    def classify_email(self, email: EmailHeader, signals: dict, body_preview: str | None = None) -> LLMClassificationResult:
        body = (body_preview or "")[: self.body_preview_limit]
        prompt = (
            f"{self.prompt_intro}\n"
            f"Asunto: {email.subject}\n"
            f"Remitente: {email.from_}\n"
            f"Senales: {signals}\n"
        )
        if body:
            prompt += f"Cuerpo: {body}\n"
        if self.user_context:
            prompt += f"\nContexto del usuario:\n{self.user_context}\n"

        payload_variants = self._payload_variants(prompt)

        last_reason = "No se pudo obtener una respuesta valida del LLM."
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._run_variants(payload_variants)
            except _TransientError as exc:
                last_reason = str(exc)
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt, last_reason)
                    continue
                raise LLMUnavailableError(last_reason) from exc

        raise LLMUnavailableError(last_reason)
