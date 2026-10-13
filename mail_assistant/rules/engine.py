from ..imap.models import EmailHeader
from ..config.models import ClassifierRules
from .base import Category, Rule
from .implementations import WhitelistRule, BlacklistRule, ForceLLMRule, NewsletterRule, KeywordRule

class RuleEngine:
    def __init__(self, rules_config: ClassifierRules):
        self.config = rules_config

        # Sort whitelist and blacklist entries by specificity:
        # Full addresses (@) first, then longer domain patterns before shorter ones
        sorted_whitelist = sorted(
            rules_config.whitelist_domains,
            key=lambda x: (0 if "@" in (x or "") else 1, -len(x or ""))
        )
        sorted_blacklist = sorted(
            rules_config.blacklist_domains,
            key=lambda x: (0 if "@" in (x or "") else 1, -len(x or ""))
        )

        self.rules = [
            WhitelistRule(sorted_whitelist),
            BlacklistRule(sorted_blacklist),
            ForceLLMRule(rules_config.force_llm_senders),
            NewsletterRule(),
            KeywordRule(rules_config.positive_keywords, rules_config.negative_keywords)
        ]

    def classify_with_audit(self, email: EmailHeader, signals=None) -> tuple[Category, int, bool, str]:
        forced = any(rule.forces_llm(email) for rule in self.rules)
        score = 0

        for rule in self.rules:
            try:
                rule_score = rule.evaluate(email, signals=signals)
            except TypeError:
                rule_score = rule.evaluate(email)

            score += rule_score

            if rule_score >= 100:
                return Category.IMPORTANTE, score, False, "rule:whitelist"
            if rule_score <= -100:
                if forced:
                    return Category.DUDOSO, score, True, "rule:blacklist"
                return Category.DESCARTABLE, score, False, "rule:blacklist"

        if score >= self.config.score_thresholds.important:
            return Category.IMPORTANTE, score, forced, "rule:threshold_important"
        elif score <= self.config.score_thresholds.discard:
            if forced:
                return Category.DUDOSO, score, True, "rule:threshold_discard"
            return Category.DESCARTABLE, score, False, "rule:threshold_discard"
        else:
            return Category.DUDOSO, score, forced, "rule:dudoso"

    def classify(self, email: EmailHeader, signals=None) -> tuple[Category, int, bool]:
        cat, score, forced, _ = self.classify_with_audit(email, signals=signals)
        return cat, score, forced
