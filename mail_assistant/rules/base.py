from abc import ABC, abstractmethod
from enum import Enum
from ..imap.models import EmailHeader

class Category(Enum):
    IMPORTANTE = "IMPORTANTE"
    PELIGROSO = "PELIGROSO"
    DUDOSO = "DUDOSO"
    DESCARTABLE = "DESCARTABLE"

class Rule(ABC):
    @abstractmethod
    def evaluate(self, email: EmailHeader) -> int:
        pass

    def forces_llm(self, email: EmailHeader) -> bool:
        return False
