from datetime import datetime, timezone
from mail_assistant.classifier.service import ClassifierService
from mail_assistant.config.models import ClassifierRules, Thresholds, EmailResult
from mail_assistant.imap.models import EmailHeader
from mail_assistant.rules.engine import RuleEngine


class MockClientSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockClient:
    def __init__(self, headers):
        self.headers = headers

    def session(self):
        return MockClientSession()

    def get_unread_emails(self, limit=100, on_progress=None):
        return self.headers

    def get_email_body_preview(self, uid):
        return ""


def test_classifier_record_audit_traceability():
    header = EmailHeader(
        uid="201",
        from_="test@example.com",
        subject="Test",
        date=datetime.now(timezone.utc),
        message_id="<msg201>",
        headers={},
        flags=set()
    )

    rules_config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30),
        whitelist_domains=["example.com"]
    )
    engine = RuleEngine(rules_config)
    client = MockClient([header])

    service = ClassifierService(client, engine, None)
    results = service.process_unread(limit=10, use_llm=False)

    assert len(results) == 1
    rec = results[0]
    assert rec["rule_or_stage"] == "rule:whitelist"
    assert rec["confidence"] == "high"
    assert rec["signals"] is not None


def test_email_result_canonical_serialization():
    header = EmailHeader(
        uid="202",
        from_="test@example.com",
        subject="Test",
        date=datetime.now(timezone.utc),
        message_id="<msg202>",
        headers={},
        flags=set()
    )

    res = EmailResult.from_classification(header, "IMPORTANTE", "Explicación")
    dump = res.model_dump()
    assert set(dump.keys()) == {"uid", "from_", "subject", "date", "category", "explanation"}
