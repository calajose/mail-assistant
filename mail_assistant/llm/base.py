from abc import ABC, abstractmethod
from pydantic import BaseModel
from ..imap.models import EmailHeader
from ..rules.base import Category

class LLMClassificationResult(BaseModel):
    category: Category
    explanation: str


class LLMUnavailableError(Exception):
    pass

class LLMProvider(ABC):
    @abstractmethod
    def classify_email(self, email: EmailHeader, signals: dict, body_preview: str | None = None) -> LLMClassificationResult:
        pass
