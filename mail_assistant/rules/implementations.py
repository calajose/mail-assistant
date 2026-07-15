from .base import Rule
from ..imap.models import EmailHeader
from ..config.models import ClassifierRules

class WhitelistRule(Rule):
    def __init__(self, domains: list[str]):
        self.domains = domains
        
    def evaluate(self, email: EmailHeader) -> int:
        for domain in self.domains:
            if domain in email.from_:
                return 100
        return 0

class BlacklistRule(Rule):
    def __init__(self, domains: list[str]):
        self.domains = domains
        
    def evaluate(self, email: EmailHeader) -> int:
        for domain in self.domains:
            if domain in email.from_:
                return -100
        return 0


class ForceLLMRule(Rule):
    def __init__(self, senders: list[str]):
        self.senders = senders

    def evaluate(self, email: EmailHeader) -> int:
        return 0

    def forces_llm(self, email: EmailHeader) -> bool:
        for sender in self.senders:
            if sender in email.from_:
                return True
        return False

class NewsletterRule(Rule):
    def evaluate(self, email: EmailHeader) -> int:
        if "list-unsubscribe" in email.headers or "auto-submitted" in email.headers:
            return -40
        return 0

class KeywordRule(Rule):
    def __init__(self, positive: list[str], negative: list[str]):
        self.positive = positive
        self.negative = negative
        
    def evaluate(self, email: EmailHeader) -> int:
        score = 0
        text = f"{email.subject} {email.from_}"
        for word in self.positive:
            if word in text:
                score += 15
        for word in self.negative:
            if word in text:
                score -= 15
        return score
