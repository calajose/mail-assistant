from email.utils import parseaddr

from .base import Rule
from ..imap.models import EmailHeader


def _extract_sender_parts(from_header: str) -> tuple[str, str]:
    """Devuelve (direccion real, dominio) en minusculas a partir de la cabecera From.

    La direccion real es la que va tras la ultima arroba; el nombre visible se
    descarta para que no pueda suplantarse un dominio (A-04, decisiones P2+P28).
    """
    _, address = parseaddr(from_header or "")
    address = (address or "").strip().lower()
    if "@" not in address:
        return address, ""
    _, domain = address.rsplit("@", 1)
    return address, domain


def _entry_matches(entry: str, address: str, domain: str) -> bool:
    """Compara una entrada de lista contra un remitente (A-04, decision P28).

    - Entrada con "@": coincidencia exacta de direccion completa.
    - Entrada sin "@": dominio estricto tras la ultima arroba.
    Ambas en minusculas (A-02, decision P1).
    """
    normalized = (entry or "").strip().lower()
    if not normalized:
        return False
    if "@" in normalized:
        return bool(address) and normalized == address
    return bool(domain) and normalized == domain


class WhitelistRule(Rule):
    def __init__(self, domains: list[str]):
        self.domains = domains

    def evaluate(self, email: EmailHeader) -> int:
        address, domain = _extract_sender_parts(email.from_)
        for entry in self.domains:
            if _entry_matches(entry, address, domain):
                return 100
        return 0


class BlacklistRule(Rule):
    def __init__(self, domains: list[str]):
        self.domains = domains

    def evaluate(self, email: EmailHeader) -> int:
        address, domain = _extract_sender_parts(email.from_)
        for entry in self.domains:
            if _entry_matches(entry, address, domain):
                return -100
        return 0


class ForceLLMRule(Rule):
    def __init__(self, senders: list[str]):
        self.senders = senders

    def evaluate(self, email: EmailHeader) -> int:
        return 0

    def forces_llm(self, email: EmailHeader) -> bool:
        address, domain = _extract_sender_parts(email.from_)
        for sender in self.senders:
            if _entry_matches(sender, address, domain):
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
        text = f"{email.subject} {email.from_}".lower()
        for word in self.positive:
            if word and word.lower() in text:
                score += 15
        for word in self.negative:
            if word and word.lower() in text:
                score -= 15
        return score
