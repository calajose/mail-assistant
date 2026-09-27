import yaml
import keyring
from pathlib import Path
from .models import MailAssistantConfig

_HEADER_COMMENT = (
    "# ==========================================================================\n"
    "# PROMPT POR DEFECTO DE MAIL-ASSISTANT\n"
    "# ==========================================================================\n"
    "# NO EDITES ESTE ARCHIVO DIRECTAMENTE.\n"
    "# Este archivo se sobrescribe automaticamente en cada inicio de la aplicacion.\n"
    "#\n"
    "# Si deseas personalizar el prompt, crea un archivo llamado '{provider}.txt'\n"
    "# en este mismo directorio y escribe alli tu prompt personalizado.\n"
    "#\n"
    "# Para volver a usar el prompt por defecto, simplemente borra '{provider}.txt'.\n"
    "# ==========================================================================\n\n"
)

class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
        self._initialize_prompts()

    def _load_config(self) -> MailAssistantConfig:
        if not self.config_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de configuración en {self.config_path}")
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
        return MailAssistantConfig(**data)

    def _initialize_prompts(self):
        from .defaults import DEFAULT_GEMINI_PROMPT, DEFAULT_OLLAMA_PROMPT
        prompts_dir = self.config_path.parent / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        for provider, content in [("gemini", DEFAULT_GEMINI_PROMPT), ("ollama", DEFAULT_OLLAMA_PROMPT)]:
            default_file = prompts_dir / f"{provider}.default.txt"
            header = _HEADER_COMMENT.replace("{provider}", provider)
            default_file.write_text(header + content, encoding="utf-8")

    def get_imap_password(self, account_name: str) -> str | None:
        return keyring.get_password("mail-assistant", f"imap_password:{account_name}")

    def set_imap_password(self, account_name: str, password: str):
        keyring.set_password("mail-assistant", f"imap_password:{account_name}", password)

    def get_gemini_api_key(self) -> str | None:
        return keyring.get_password("mail-assistant", "gemini_api_key")

    def set_gemini_api_key(self, api_key: str):
        keyring.set_password("mail-assistant", "gemini_api_key", api_key)

    def _fallback_prompt(self, provider: str) -> str:
        prompts_dir = self.config_path.parent / "prompts"
        default_prompt_file = prompts_dir / f"{provider}.default.txt"
        if default_prompt_file.exists() and default_prompt_file.is_file():
            content = default_prompt_file.read_text(encoding="utf-8")
            clean_lines = [
                line for line in content.splitlines() if not line.strip().startswith("#")
            ]
            cleaned = "\n".join(clean_lines).strip()
            if cleaned:
                return cleaned
        from .defaults import DEFAULT_GEMINI_PROMPT, DEFAULT_OLLAMA_PROMPT
        return DEFAULT_GEMINI_PROMPT if provider == "gemini" else DEFAULT_OLLAMA_PROMPT

    def get_prompt(self, provider: str) -> str:
        prompts_dir = self.config_path.parent / "prompts"
        user_prompt_file = prompts_dir / f"{provider}.txt"

        content = None
        if user_prompt_file.exists() and user_prompt_file.is_file():
            content = user_prompt_file.read_text(encoding="utf-8")

        if content is not None:
            clean_lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
            cleaned = "\n".join(clean_lines).strip()
            if cleaned:
                return cleaned
            print(
                f"El prompt personalizado de {provider} no contiene instrucciones; "
                "se usa el prompt maestro por defecto."
            )
            return self._fallback_prompt(provider)

        return self._fallback_prompt(provider)
