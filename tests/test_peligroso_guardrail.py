from datetime import datetime, timezone
from mail_assistant.classifier.service import ClassifierService
from mail_assistant.config.models import ClassifierRules, Thresholds
from mail_assistant.imap.models import EmailHeader
from mail_assistant.llm.base import LLMClassificationResult, LLMProvider
from mail_assistant.rules.base import Category
from mail_assistant.rules.engine import RuleEngine


class MockMailClientSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockMailClient:
    def __init__(self, email_headers, body_preview=""):
        self._headers = email_headers
        self._body_preview = body_preview

    def session(self):
        return MockMailClientSession()

    def get_unread_emails(self, limit=100, on_progress=None):
        return self._headers

    def get_email_body_preview(self, uid):
        return self._body_preview


class MockLLMProvider(LLMProvider):
    def __init__(self, result_category=Category.PELIGROSO, result_explanation="Riesgo de phishing"):
        self.result_category = result_category
        self.result_explanation = result_explanation
        self.model = "mock_llm"

    def classify_email(self, email, signals, body_preview=None):
        return LLMClassificationResult(
            category=self.result_category,
            explanation=self.result_explanation
        )


def test_guardrail_downgrades_hallucinated_peligroso():
    # Email with valid SPF/DKIM (no objective risk)
    headers = {
        "from": '"Financiera El Corte Inglés" <noreply@mc.financieraelcorteingles.es>',
        "Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"
    }
    header = EmailHeader(
        uid="101",
        from_='"Financiera El Corte Inglés" <noreply@mc.financieraelcorteingles.es>',
        subject="Alerta de seguridad.",
        date=datetime.now(timezone.utc),
        message_id="<msg101>",
        headers=headers,
        flags=set()
    )

    rules_config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30)
    )
    rule_engine = RuleEngine(rules_config)
    mail_client = MockMailClient([header], body_preview="Visita https://mc.financieraelcorteingles.es")
    llm = MockLLMProvider(result_category=Category.PELIGROSO, result_explanation="Alucinación del LLM")

    service = ClassifierService(mail_client, rule_engine, llm)
    results = service.process_unread(limit=10, use_llm=True)

    assert len(results) == 1
    res = results[0]
    # PELIGROSO should be downgraded because signals.has_objective_risk is False
    assert res["category"] == Category.IMPORTANTE
    assert res["rule_or_stage"] == "guardrail:downgraded_no_evidence"
    assert "Sin indicios tecnicos objetivos" in res["explanation"]


def test_guardrail_preserves_genuine_peligroso():
    # Email with phishing link mismatch
    headers = {
        "from": '"Banco Falso" <info@bancofalso.ru>',
        "Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"
    }
    header = EmailHeader(
        uid="102",
        from_='"Banco Falso" <info@bancofalso.ru>',
        subject="Acceso bloqueado",
        date=datetime.now(timezone.utc),
        message_id="<msg102>",
        headers=headers,
        flags=set()
    )

    rules_config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30)
    )
    rule_engine = RuleEngine(rules_config)
    body = 'Inicia sesión aquí: <a href="http://evil-phishing.ru">https://banco.es/login</a>'
    mail_client = MockMailClient([header], body_preview=body)
    llm = MockLLMProvider(result_category=Category.PELIGROSO, result_explanation="Ataque de phishing detectado")

    service = ClassifierService(mail_client, rule_engine, llm)
    results = service.process_unread(limit=10, use_llm=True)

    assert len(results) == 1
    res = results[0]
    assert res["category"] == Category.PELIGROSO
    assert res["rule_or_stage"] == "llm:mock_llm"
