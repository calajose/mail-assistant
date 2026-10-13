from time import perf_counter
from ..imap.client import MailClient
from ..rules.engine import RuleEngine
from ..llm.base import LLMProvider, LLMUnavailableError
from ..imap.models import EmailHeader
from ..rules.base import Category
from ..utils.progress import ScanReporter
from ..utils.security import extract_security_signals

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

    def process_unread(
        self,
        limit: int,
        use_llm: bool,
        force_llm: bool = False,
        on_result=None,
    ):
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

                signals = extract_security_signals(header.headers)
                category, score, forced, rule_or_stage = self.rule_engine.classify_with_audit(header, signals=signals)
                confidence = "high"

                if (category == Category.DUDOSO or force_llm) and use_llm and self.llm_provider:
                    self.reporter.llm_request(score, forced=forced)
                    try:
                        body_preview = self.mail_client.get_email_body_preview(header.uid)
                        signals = extract_security_signals(header.headers, body_text=body_preview)

                        t0 = perf_counter()
                        llm_result = self.llm_provider.classify_email(
                            header,
                            {
                                "score": score,
                                "security_prompt": signals.to_prompt_text(),
                                "security": signals.to_summary_dict(),
                            },
                            body_preview,
                        )
                        duration = perf_counter() - t0
                        category = llm_result.category
                        explanation = llm_result.explanation
                        rule_or_stage = f"llm:{getattr(self.llm_provider, 'model', 'unknown')}"
                        confidence = getattr(llm_result, "confidence", "medium") or "medium"
                        self.reporter.llm_response(category, duration=duration)

                        # Guardarraíl de segundo nivel (RF-3, RF-4)
                        if category == Category.PELIGROSO and not signals.has_objective_risk:
                            subj_lower = header.subject.lower()
                            expl_lower = explanation.lower()
                            important_keywords = [
                                "alerta", "factura", "recibo", "seguridad", "banco", "préstamo",
                                "prestamo", "pedido", "verificacion", "notificacion", "cuenta"
                            ]
                            if score >= 60 or any(k in subj_lower or k in expl_lower for k in important_keywords):
                                category = Category.IMPORTANTE
                            else:
                                category = Category.DESCARTABLE
                            explanation = f"{explanation} [Nota: Sin indicios tecnicos objetivos; reasignado a {category.value}]."
                            rule_or_stage = "guardrail:downgraded_no_evidence"
                            confidence = "high"

                    except LLMUnavailableError as exc:
                        category = Category.DUDOSO
                        explanation = EXPLICACION_LLM_NO_DISPONIBLE
                        rule_or_stage = "llm_error"
                        confidence = "low"
                        self.reporter.llm_failed(str(exc))
                    except Exception as exc:
                        category = Category.DUDOSO
                        explanation = EXPLICACION_LLM_NO_DISPONIBLE
                        rule_or_stage = "llm_error"
                        confidence = "low"
                        self.reporter.llm_failed(f"Error inesperado al consultar el LLM: {exc}")
                else:
                    explanation = EXPLICACION_REGLAS_LOCALES
                    self.reporter.classified_by_rules(category, score)

                record = {
                    "header": header,
                    "category": category,
                    "explanation": explanation,
                    "rule_or_stage": rule_or_stage,
                    "confidence": confidence,
                    "signals": signals,
                }
                results.append(record)
                if on_result:
                    on_result(record)
        return results
