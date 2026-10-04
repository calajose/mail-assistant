from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class AccountConfig(BaseModel):
    name: str
    host: str
    port: int = 993
    folder: str = "INBOX"
    timeout: int = Field(default=30, ge=1)

class LLMConfig(BaseModel):
    provider: str
    model: str
    max_retries: int = Field(default=5, ge=1)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_format: str = Field(default="auto")
    user_context: str | None = None
    body_preview_limit: int = Field(default=4096, ge=1)

class Thresholds(BaseModel):
    important: int
    discard: int

class ClassifierRules(BaseModel):
    score_thresholds: Thresholds
    whitelist_domains: list[str] = Field(default_factory=list)
    blacklist_domains: list[str] = Field(default_factory=list)
    force_llm_senders: list[str] = Field(default_factory=list)
    positive_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)

class MailAssistantConfig(BaseModel):
    account: AccountConfig
    llm: LLMConfig
    classifier_rules: ClassifierRules


CategoryLiteral = Literal["IMPORTANTE", "PELIGROSO", "DESCARTABLE", "DUDOSO"]

# Registro saneado de un correo procesado: solo datos de negocio.
class EmailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str
    from_: str
    subject: str
    date: str
    category: CategoryLiteral
    explanation: str

    @classmethod
    def from_classification(cls, header, category, explanation: str) -> "EmailResult":
        """Construye el registro saneado que se persiste en results.json.

        Descarta deliberadamente headers, flags, message_id y cualquier otra
        cabecera tecnica (A-16, decision P8).
        """
        date = getattr(header, "date", None)
        if hasattr(date, "isoformat"):
            date = date.isoformat()
        return cls(
            uid=str(getattr(header, "uid", "")),
            from_=str(getattr(header, "from_", "")),
            subject=str(getattr(header, "subject", "")),
            date=str(date if date is not None else ""),
            category=getattr(category, "value", str(category)),
            explanation=str(explanation),
        )


class ScanResultSet(BaseModel):
    provider: str
    model: str | None = None
    updated_at: str | None = None
    results: list[EmailResult] = Field(default_factory=list)
