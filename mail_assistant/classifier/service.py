from time import perf_counter
from ..imap.client import MailClient
from ..rules.engine import RuleEngine
from ..llm.base import LLMProvider, LLMUnavailableError
from ..imap.models import EmailHeader
from ..rules.base import Category
from ..utils.progress import ScanReporter

EXPLICACION_REGLAS_LOCALES = "Clasificado por reglas locales."
EXPLICACION_LLM_NO_DISPONIBLE = "No se pudo consultar el LLM (servicio no disponible); clasificado provisionalmente como DUDOSO."


class ClassifierService:
    def __init__(
        self,
        mail_client: MailClient,
        rule_engine: RuleEngine,
        llm_provider: LLMProvider | None,
        reporter: ScanReporter | None = None,
    ):
        self.mail_client = mail_client
        self.rule_engine = rule_engine
        self.llm_provider = llm_provider
        self.reporter = reporter or ScanReporter()

    def process_unread(self, limit: int, use_llm: bool, force_llm: bool = False):
        results = []
        self.reporter.fetch_start()

        with self.mail_client.session():
            emails = self.mail_client.get_unread_emails(
                limit=limit,
                on_progress=self.reporter.fetch_progress,
            )
            total = len(emails)
            self.reporter.fetch_done(total)

            for index, email in enumerate(emails, start=1):
                msg_id = email.headers.get("message-id", "")
                if isinstance(msg_id, (list, tuple)):
                    msg_id = msg_id[0] if msg_id else ""
                else:
                    msg_id = str(msg_id)

                header = EmailHeader(
                    uid=email.uid,
                    from_=email.from_,
                    subject=email.subject,
                    date=email.date,
                    message_id=msg_id,
                    headers=dict(email.headers),
                    flags=set(email.flags),
                )

                self.reporter.email_start(index, total, header.subject, header.from_)

                category, score, forced = self.rule_engine.classify(header)

                if (category == Category.DUDOSO or force_llm) and use_llm and self.llm_provider:
                    self.reporter.llm_request(score, forced=forced)
                    try:
                        body_preview = self.mail_client.get_email_body_preview(header.uid)
                        t0 = perf_counter()
                        llm_result = self.llm_provider.classify_email(
                            header,
                            {"score": score},
                            body_preview,
                        )
                        duration = perf_counter() - t0
                        category = llm_result.category
                        explanation = llm_result.explanation
                        self.reporter.llm_response(category, duration=duration)
                    except LLMUnavailableError as exc:
                        category = Category.DUDOSO
                        explanation = EXPLICACION_LLM_NO_DISPONIBLE
                        self.reporter.llm_failed(str(exc))
                    except Exception as exc:
                        category = Category.DUDOSO
                        explanation = EXPLICACION_LLM_NO_DISPONIBLE
                        self.reporter.llm_failed(f"Error inesperado al consultar el LLM: {exc}")
                else:
                    explanation = EXPLICACION_REGLAS_LOCALES
                    self.reporter.classified_by_rules(category, score)

                results.append({"header": header, "category": category, "explanation": explanation})
        return results
