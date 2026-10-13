from datetime import datetime, timezone
from mail_assistant.config.models import ClassifierRules, Thresholds
from mail_assistant.imap.models import EmailHeader
from mail_assistant.rules.base import Category
from mail_assistant.rules.engine import RuleEngine
from mail_assistant.rules.implementations import WhitelistRule, _entry_matches
from mail_assistant.utils.security import SecuritySignals


def _make_header(from_addr: str) -> EmailHeader:
    return EmailHeader(
        uid="1",
        from_=from_addr,
        subject="Asunto de prueba",
        date=datetime.now(timezone.utc),
        message_id="<msg1@test>",
        headers={},
        flags=set()
    )


def test_entry_matches_subdomains():
    # Exact full address
    assert _entry_matches("user@domain.com", "user@domain.com", "domain.com") is True
    assert _entry_matches("user@domain.com", "other@domain.com", "domain.com") is False

    # Subdomain matching
    assert _entry_matches("elcorteingles.es", "info@mc.elcorteingles.es", "mc.elcorteingles.es") is True
    assert _entry_matches("elcorteingles.es", "info@promociones.mc.elcorteingles.es", "promociones.mc.elcorteingles.es") is True
    assert _entry_matches("elcorteingles.es", "info@elcorteingles.es", "elcorteingles.es") is True

    # Reject partial match that is not a true subdomain
    assert _entry_matches("elcorteingles.es", "hacker@falsoelcorteingles.es", "falsoelcorteingles.es") is False


def test_whitelist_rule_inhibition_on_auth_failed():
    rule = WhitelistRule(["elcorteingles.es"])
    header = _make_header('"El Corte Ingles" <info@mc.elcorteingles.es>')

    # Valid auth -> score +100
    signals_pass = SecuritySignals(spf_status="pass", dkim_status="pass", dmarc_status="pass")
    assert rule.evaluate(header, signals=signals_pass) == 100

    # Failed auth -> inhibited (0)
    signals_fail = SecuritySignals(spf_status="fail", dkim_status="fail", dmarc_status="fail")
    assert rule.evaluate(header, signals=signals_fail) == 0


def test_rule_priority_order():
    config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30),
        whitelist_domains=["specific.domain.com", "vip@domain.com", "domain.com"],
        blacklist_domains=[],
        force_llm_senders=[],
        positive_keywords=[],
        negative_keywords=[]
    )
    engine = RuleEngine(config)

    # vip@domain.com should be evaluated before domain.com
    header = _make_header("vip@domain.com")
    cat, score, forced, rule_id = engine.classify_with_audit(header)
    assert cat == Category.IMPORTANTE
    assert score == 100
    assert rule_id == "rule:whitelist"
