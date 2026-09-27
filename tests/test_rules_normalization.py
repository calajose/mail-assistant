from datetime import datetime

from mail_assistant.imap.models import EmailHeader
from mail_assistant.rules.implementations import (
    BlacklistRule,
    ForceLLMRule,
    KeywordRule,
    WhitelistRule,
)


def make_header(
    from_: str,
    subject: str = "Mensaje de prueba",
    headers: dict | None = None,
    uid: str = "1",
) -> EmailHeader:
    return EmailHeader(
        uid=uid,
        from_=from_,
        subject=subject,
        date=datetime(2026, 9, 27, 10, 0, 0),
        message_id="<id@prueba>",
        headers=headers or {},
        flags=set(),
    )


# --- A-02: normalizacion a minusculas en dominios (P1) ---


def test_whitelist_matches_domain_case_insensitive():
    rule = WhitelistRule(["cantookstation.com"])
    assert rule.evaluate(make_header("notificaciones@CANTOOKSTATION.COM")) == 100


def test_blacklist_matches_domain_case_insensitive():
    rule = BlacklistRule(["CANTOOKSTATION.COM"])
    assert rule.evaluate(make_header("avisos@cantookstation.com")) == -100


def test_whitelist_case_variant_does_not_depend_on_list_case():
    rule = WhitelistRule(["CantoOkStation.com"])
    assert rule.evaluate(make_header("aviso@cantookstation.com")) == 100


def test_force_llm_sender_case_insensitive():
    rule = ForceLLMRule(["novedades@amazon.es"])
    assert rule.forces_llm(make_header("NOVEDADES@AMAZON.ES")) is True


def test_keyword_positive_matches_uppercase_subject():
    rule = KeywordRule(positive=["factura"], negative=[])
    assert rule.evaluate(make_header("a@b.com", subject="Confirmacion de Factura urgente")) == 15


def test_keyword_negative_matches_uppercase_subject():
    rule = KeywordRule(positive=[], negative=["descuento"])
    assert rule.evaluate(make_header("a@b.com", subject="Solo Descuento")) == -15


# --- A-04: dominio estricto tras la arroba (P2) ---


def test_whitelist_rejects_spoofed_display_name():
    rule = WhitelistRule(["cantookstation.com"])
    spoofed = make_header('Soporte cantookstation.com <malicioso@evil.ru>')
    assert rule.evaluate(spoofed) == 0


def test_whitelist_rejects_other_domain_containing_entry_as_substring():
    rule = WhitelistRule(["cantookstation.com"])
    assert rule.evaluate(make_header("user@evil-cantookstation.com.evil.ru")) == 0


def test_whitelist_does_not_match_subdomain_of_listed_domain():
    rule = WhitelistRule(["cantookstation.com"])
    assert rule.evaluate(make_header("avisos@sub.cantookstation.com")) == 0


def test_whitelist_entry_with_arroba_matches_only_exact_address():
    rule = WhitelistRule(["novedades@amazon.es"])
    assert rule.evaluate(make_header("novedades@amazon.es")) == 100
    assert rule.evaluate(make_header("promociones@amazon.es")) == 0


def test_blacklist_entry_with_arroba_matches_only_exact_address():
    rule = BlacklistRule(["recommendations@discover.pinterest.com"])
    assert rule.evaluate(make_header("recommendations@discover.pinterest.com")) == -100
    assert rule.evaluate(make_header("otra@discover.pinterest.com")) == 0


def test_force_llm_entry_without_arroba_matches_whole_domain():
    rule = ForceLLMRule(["amazon.es"])
    assert rule.forces_llm(make_header("novedades@amazon.es")) is True
    assert rule.forces_llm(make_header("novedades@otro.es")) is False


def test_rules_do_not_raise_on_malformed_sender():
    assert WhitelistRule(["cantookstation.com"]).evaluate(make_header("cantookstation.com")) == 0
    assert WhitelistRule(["cantookstation.com"]).evaluate(make_header("")) == 0
    assert ForceLLMRule(["novedades@amazon.es"]).forces_llm(make_header("   ")) is False


def test_display_name_that_looks_like_address_is_ignored():
    rule = WhitelistRule(["ejemplo.com"])
    header = make_header('"pedro@ejemplo.com" <otro@dominioajeno.com>')
    assert rule.evaluate(header) == 0
