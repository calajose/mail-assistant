from ..imap.models import EmailHeader
from ..config.models import ClassifierRules
from .base import Category, Rule
from .implementations import WhitelistRule, BlacklistRule, ForceLLMRule, NewsletterRule, KeywordRule

class RuleEngine:
    def __init__(self, rules_config: ClassifierRules):
        self.config = rules_config
        self.rules = [
            WhitelistRule(rules_config.whitelist_domains),
            BlacklistRule(rules_config.blacklist_domains),
            ForceLLMRule(rules_config.force_llm_senders),
            NewsletterRule(),
            KeywordRule(rules_config.positive_keywords, rules_config.negative_keywords)
        ]
        
    def classify(self, email: EmailHeader) -> tuple[Category, int, bool]:
        forced = any(rule.forces_llm(email) for rule in self.rules)
        score = 0
        for rule in self.rules:
            score += rule.evaluate(email)
            
            # Short-circuit
            if score >= 100:
                return Category.IMPORTANTE, score, False
            if score <= -100:
                return Category.DESCARTABLE, score, False
                
        if score >= self.config.score_thresholds.important:
            return Category.IMPORTANTE, score, forced
        elif score <= self.config.score_thresholds.discard:
            if forced:
                return Category.DUDOSO, score, True
            return Category.DESCARTABLE, score, False
        else:
            return Category.DUDOSO, score, forced
