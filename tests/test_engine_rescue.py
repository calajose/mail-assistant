from datetime import datetime

from mail_assistant.config.models import ClassifierRules, Thresholds
from mail_assistant.imap.models import EmailHeader
from mail_assistant.rules.base import Category
from mail_assistant.rules.engine import RuleEngine


def make_header(from_: str, subject: str = "Mensaje", headers: dict | None = None) -> EmailHeader:
    return EmailHeader(
        uid="1",
        from_=from_,
        subject=subject,
        date=datetime(2026, 9, 27, 10, 0, 0),
        message_id="<id@prueba>",
        headers=headers or {},
        flags=set(),
    )


def build_engine(**overrides) -> RuleEngine:
    config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30),
        whitelist_domains=overrides.get("whitelist", []),
        blacklist_domains=overrides.get("blacklist", []),
        force_llm_senders=overrides.get("forced", []),
        positive_keywords=overrides.get("positive", []),
        negative_keywords=overrides.get("negative", []),
    )
    return RuleEngine(config)


# --- A-06: el rescate manda en el corte de -100 (P10) ---


def test_cortocircuito_menos100_con_forced_devuelve_dudoso_hacia_ia():
    engine = build_engine(
        blacklist=["amazon.es"],
        forced=["novedades@amazon.es"],
    )
    category, score, forced = engine.classify(make_header("novedades@amazon.es"))
    assert score == -100
    assert category is Category.DUDOSO
    assert forced is True


def test_cortocircuito_menos100_sin_forced_sigue_descartable():
    engine = build_engine(blacklist=["amazon.es"])
    category, score, forced = engine.classify(make_header("otro@amazon.es"))
    assert score == -100
    assert category is Category.DESCARTABLE
    assert forced is False


# --- A-05 protegida: el corte de +100 no consulta IA (P3) ---


def test_cortocircuito_mas100_con_forced_no_va_a_ia():
    engine = build_engine(whitelist=["amazon.es"], forced=["novedades@amazon.es"])
    category, score, forced = engine.classify(make_header("novedades@amazon.es"))
    assert score == 100
    assert category is Category.IMPORTANTE
    assert forced is False


def test_forced_con_puntuacion_importante_local_no_va_a_ia():
    engine = build_engine(
        forced=["novedades@amazon.es"],
        positive=["a", "b", "c", "d"],
    )
    category, score, forced = engine.classify(
        make_header("novedades@amazon.es", subject="a b c d")
    )
    assert score == 60
    assert category is Category.IMPORTANTE


# --- Conducta previa preservada fuera de los cortocircuitos ---


def test_forced_en_tramo_descartable_se_rescata_a_dudoso():
    engine = build_engine(forced=["novedades@amazon.es"])
    category, score, forced = engine.classify(
        make_header("novedades@amazon.es", headers={"list-unsubscribe": "<x>"})
    )
    assert score == -40
    assert category is Category.DUDOSO
    assert forced is True


def test_sin_forced_en_tramo_descartable_se_descarta():
    engine = build_engine()
    category, score, forced = engine.classify(
        make_header("otro@amazon.es", headers={"list-unsubscribe": "<x>"})
    )
    assert score == -40
    assert category is Category.DESCARTABLE
    assert forced is False


def test_tramo_intermedio_sigue_siendo_dudoso():
    engine = build_engine()
    category, score, forced = engine.classify(make_header("alguien@ejemplo.com"))
    assert score == 0
    assert category is Category.DUDOSO
    assert forced is False
