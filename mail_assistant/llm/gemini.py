import random
import time
import httpx
from collections.abc import Callable
from google.genai import Client
from google.genai import errors as genai_errors
from google.genai import types
from .base import LLMProvider, LLMClassificationResult, LLMUnavailableError
from ..imap.models import EmailHeader


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        prompt: str,
        max_retries: int = 5,
        user_context: str | None = None,
        on_retry: Callable[[int, int, str, float], None] | None = None,
    ):
        self.client = Client(api_key=api_key)
        self.model = model
        self.prompt_intro = prompt.strip()
        self.max_retries = max(1, max_retries)
        self.user_context = user_context.strip() if user_context else None
        self.on_retry = on_retry

    def _sleep_before_retry(self, attempt: int, reason: str):
        base_delay = min(2 ** attempt, 30)
        jitter = random.uniform(0, 1)
        wait_seconds = base_delay + jitter
        if self.on_retry:
            self.on_retry(attempt, self.max_retries, reason, wait_seconds)
        time.sleep(wait_seconds)

    def classify_email(self, email: EmailHeader, signals: dict, body_preview: str | None = None) -> LLMClassificationResult:
        prompt = (
            f"{self.prompt_intro}\n"
            f"Asunto: {email.subject}\n"
            f"Remitente: {email.from_}\n"
            f"Senales de reglas locales: {signals}\n"
        )
        if body_preview:
            prompt += f"Vista previa del cuerpo: {body_preview}\n"
        if self.user_context:
            prompt += f"\nContexto del usuario:\n{self.user_context}\n"

        last_error_message = "No se pudo obtener respuesta del LLM."
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=LLMClassificationResult
                    )
                )
                if not response.text:
                    raise LLMUnavailableError("El LLM devolvio una respuesta vacia.")
                return LLMClassificationResult.model_validate_json(response.text)
            except genai_errors.ServerError as exc:
                last_error_message = f"Error temporal del servidor Gemini ({exc.code})."
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt, last_error_message)
                    continue
                raise LLMUnavailableError(last_error_message) from exc
            except genai_errors.ClientError as exc:
                if exc.code == 429:
                    last_error_message = "Gemini esta saturado o con limite temporal (429)."
                    if attempt < self.max_retries:
                        self._sleep_before_retry(attempt, last_error_message)
                        continue
                    raise LLMUnavailableError(last_error_message) from exc
                raise LLMUnavailableError(f"Error no recuperable del cliente Gemini ({exc.code}).") from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error_message = "Fallo de red al conectar con Gemini."
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt, last_error_message)
                    continue
                raise LLMUnavailableError(last_error_message) from exc
            except ValueError as exc:
                raise LLMUnavailableError("No se pudo interpretar la respuesta del LLM.") from exc
            except LLMUnavailableError as exc:
                raise LLMUnavailableError(str(exc)) from exc

        raise LLMUnavailableError(last_error_message)
