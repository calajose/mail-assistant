from __future__ import annotations

import sys
from time import perf_counter
from ..rules.base import Category


def _shorten(text: str, max_len: int = 60) -> str:
    clean = (text or "").strip()
    if not clean:
        return "(sin asunto)"
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 3]}..."


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    minutes, rem = divmod(total, 60)
    hours, rem = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {rem}m"
    if minutes > 0:
        return f"{minutes}m {rem}s"
    return f"{max(total, 0)}s"


class ScanReporter:
    def fetch_start(self) -> None:
        pass

    def fetch_done(self, total: int) -> None:
        pass

    def fetch_progress(self, fetched: int, total: int) -> None:
        pass

    def email_start(self, index: int, total: int, subject: str, sender: str) -> None:
        pass

    def classified_by_rules(self, category: Category, score: int) -> None:
        pass

    def llm_request(self, score: int, forced: bool = False) -> None:
        pass

    def llm_response(self, category: Category, duration: float | None = None) -> None:
        pass

    def llm_retry(self, attempt: int, max_retries: int, reason: str, wait_seconds: float) -> None:
        pass

    def llm_failed(self, reason: str) -> None:
        pass

    def print_summary(self, processed: int, elapsed_seconds: float) -> None:
        pass


class ConsoleScanReporter(ScanReporter):
    def __init__(self):
        self._start = perf_counter()
        self.local_classified = 0
        self.llm_requested = 0
        self.llm_success = 0
        self.llm_failed_count = 0
        self.llm_retries = 0
        self.category_counts = {
            Category.IMPORTANTE: 0,
            Category.PELIGROSO: 0,
            Category.DUDOSO: 0,
            Category.DESCARTABLE: 0,
        }
        self._is_tty = sys.stdout.isatty()
        self._fetch_last_printed = -1
        self._fetch_line_active = False

    def fetch_start(self) -> None:
        print("Descargando cabeceras de correos no leidos...", flush=True)

    def fetch_done(self, total: int) -> None:
        if self._fetch_line_active:
            print("", flush=True)
            self._fetch_line_active = False
        print(f"Cabeceras descargadas: {total} correos listos para procesar.", flush=True)

    def fetch_progress(self, fetched: int, total: int) -> None:
        if total <= 0:
            return

        if self._is_tty:
            print(f"\rDescargando cabeceras... {fetched}/{total}", end="", flush=True)
            self._fetch_line_active = fetched < total
            return

        should_print = fetched == total or fetched == 0 or fetched - self._fetch_last_printed >= 20
        if should_print:
            print(f"Descargando cabeceras... {fetched}/{total}", flush=True)
            self._fetch_last_printed = fetched

    def email_start(self, index: int, total: int, subject: str, sender: str) -> None:
        short_subject = _shorten(subject)
        print(f"[{index}/{total}] Procesando '{short_subject}' de {sender}", flush=True)

    def classified_by_rules(self, category: Category, score: int) -> None:
        self.local_classified += 1
        self.category_counts[category] += 1
        print(
            f"  -> Correo clasificado por reglas locales: {category.value} (score {score}).",
            flush=True,
        )

    def llm_request(self, score: int, forced: bool = False) -> None:
        self.llm_requested += 1
        if forced:
            print(f"  -> Correo forzado al LLM por regla (score {score}).", flush=True)
            return
        print(f"  -> Correo dudoso (score {score}). Enviado al LLM.", flush=True)

    def llm_response(self, category: Category, duration: float | None = None) -> None:
        self.llm_success += 1
        self.category_counts[category] += 1
        duration_str = f" en {duration:.2f}s" if duration is not None else ""
        print(f"  -> Respuesta recibida del LLM: {category.value}{duration_str}.", flush=True)

    def llm_retry(self, attempt: int, max_retries: int, reason: str, wait_seconds: float) -> None:
        self.llm_retries += 1
        print(
            f"  -> Reintento LLM {attempt}/{max_retries} por '{reason}'. Esperando {wait_seconds:.1f}s...",
            flush=True,
        )

    def llm_failed(self, reason: str) -> None:
        self.llm_failed_count += 1
        self.category_counts[Category.DUDOSO] += 1
        print(f"  -> LLM no disponible: {reason}. Se mantiene como DUDOSO.", flush=True)

    def print_summary(self, processed: int, elapsed_seconds: float | None = None) -> None:
        if elapsed_seconds is None:
            elapsed_seconds = perf_counter() - self._start
        print(
            f"Escaneo completado en {_format_duration(elapsed_seconds)}. {processed} correos procesados:",
            flush=True,
        )
        print(
            "  - Por reglas locales: "
            f"{self.local_classified} | Consultados al LLM: {self.llm_requested} "
            f"({self.llm_success} ok, {self.llm_failed_count} fallidos)",
            flush=True,
        )
        print(f"  - Reintentos LLM: {self.llm_retries}", flush=True)
        print(
            "  - IMPORTANTE: "
            f"{self.category_counts[Category.IMPORTANTE]} | "
            "PELIGROSO: "
            f"{self.category_counts[Category.PELIGROSO]} | "
            "DUDOSO: "
            f"{self.category_counts[Category.DUDOSO]} | "
            "DESCARTABLE: "
            f"{self.category_counts[Category.DESCARTABLE]}",
            flush=True,
        )
