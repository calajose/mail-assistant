from pydantic import BaseModel, Field

class AccountConfig(BaseModel):
    name: str
    host: str
    port: int = 993
    folder: str = "INBOX"

class LLMConfig(BaseModel):
    provider: str
    model: str
    max_retries: int = Field(default=5, ge=1)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_format: str = Field(default="auto")
    user_context: str | None = None
    body_preview_limit: int = Field(default=500, ge=1)

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
