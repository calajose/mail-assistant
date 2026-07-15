import yaml
import getpass
from pathlib import Path
from ..config.manager import ConfigManager
from ..config.models import MailAssistantConfig, AccountConfig, LLMConfig, ClassifierRules, Thresholds

def run_configure(model_only: bool = False):
    config_dir = Path.home() / ".config" / "mail-assistant"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"

    if model_only:
        if not config_file.exists():
            print("Error: No se encontró ningún archivo de configuración. Por favor, ejecuta 'mail-assistant configure' primero para configurar la cuenta por completo.")
            return

        print("Configurando proveedor y modelo del LLM...")
        
        manager = ConfigManager(config_file)
        config_data = manager.config.model_dump()
        current_provider = config_data.get("llm", {}).get("provider", "gemini")

        # Provider selection
        print(f"\nProveedor actual: {current_provider}")
        change_provider = input("¿Cambiar de proveedor? (s/N): ").strip().lower()

        provider = current_provider
        gemini_api_key = None
        ollama_base_url = config_data.get("llm", {}).get("ollama_base_url", "http://localhost:11434")

        if change_provider in ("s", "si", "sí", "y", "yes"):
            print("\nProveedores disponibles:")
            print("1) Gemini (Google)")
            print("2) Ollama (Local)")
            provider_choice = input("Selecciona un proveedor (1-2): ").strip()
            provider = "ollama" if provider_choice == "2" else "gemini"

        # Provider-specific setup
        if provider == "ollama":
            ollama_base_url = input(f"URL base de Ollama (por defecto {ollama_base_url}): ").strip() or ollama_base_url
            print("Obteniendo modelos de Ollama...")
            try:
                import httpx
                response = httpx.get(f"{ollama_base_url}/api/tags")
                response.raise_for_status()
                models = [m["name"] for m in response.json().get("models", [])]
            except Exception as e:
                print(f"No se pudieron obtener modelos de Ollama: {e}")
                models = ["llama3", "mistral"]
        else:
            gemini_api_key = manager.get_gemini_api_key()
            if not gemini_api_key or change_provider in ("s", "si", "sí", "y", "yes"):
                gemini_api_key = getpass.getpass("API Key de Gemini: ")
            models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
            if gemini_api_key:
                try:
                    print("\nConectando con Google GenAI para listar los modelos disponibles...")
                    from google.genai import Client
                    client = Client(api_key=gemini_api_key)
                    api_models = []
                    for m in client.models.list():
                        name = m.name
                        if "gemini" in name:
                            clean_name = name.replace("models/", "")
                            api_models.append(clean_name)
                    if api_models:
                        models = sorted(list(set(api_models)))
                except Exception:
                    print("No se pudo conectar con Google GenAI para obtener la lista en tiempo real. Usando modelos conocidos por defecto.")

        # Model selection
        print("\nModelos disponibles:")
        for idx, model_name in enumerate(models, 1):
            print(f"{idx}) {model_name}")
        print(f"{len(models) + 1}) Especificar otro modelo...")
        
        selected_model = config_data.get("llm", {}).get("model", models[0])
        
        try:
            choice = input(f"Selecciona un modelo (1-{len(models) + 1}, por defecto 1): ").strip()
            if not choice:
                selected_model = models[0]
            else:
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(models):
                    selected_model = models[choice_idx - 1]
                elif choice_idx == len(models) + 1:
                    custom_model = input("Introduce el nombre del modelo personalizado: ").strip()
                    if custom_model:
                        selected_model = custom_model
                else:
                    print(f"Selección no válida. Se usará: {selected_model}")
        except ValueError:
            print(f"Entrada no válida. Se usará: {selected_model}")

        # Save LLM config
        if "llm" not in config_data:
            config_data["llm"] = {}
        config_data["llm"]["provider"] = provider
        config_data["llm"]["model"] = selected_model
        config_data["llm"]["max_retries"] = 5
        if provider == "ollama":
            config_data["llm"]["ollama_base_url"] = ollama_base_url
            config_data["llm"]["ollama_format"] = config_data.get("llm", {}).get("ollama_format", "auto")
        else:
            config_data["llm"].pop("ollama_base_url", None)
            config_data["llm"].pop("ollama_format", None)

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Save API key if Gemini
        if provider == "gemini" and gemini_api_key:
            manager.set_gemini_api_key(gemini_api_key)

        print(f"Proveedor y modelo actualizados correctamente en {config_file}")
        return

    print("Configurando Mail Assistant...")
    
    # 1. Ask for non-sensitive info
    account_name = input("Nombre de la cuenta: ")
    imap_host = input("Host IMAP: ")
    imap_port = int(input("Puerto IMAP (por defecto 993): ") or 993)
    folder = input("Carpeta (por defecto INBOX): ") or "INBOX"
    
    # 2. Ask for sensitive mail info
    imap_password = getpass.getpass("Contrasena IMAP: ")
    
    # 3. Provider selection
    print("\nProveedores disponibles:")
    print("1) Gemini (Google)")
    print("2) Ollama (Local)")
    
    provider_choice = input("Selecciona un proveedor (1-2, por defecto 1): ").strip()
    provider = "ollama" if provider_choice == "2" else "gemini"

    # 4. Ask for sensitive LLM info and model selection
    selected_model = "gemini-2.5-flash" if provider == "gemini" else "llama3"
    ollama_base_url = "http://localhost:11434"
    gemini_api_key = None
    
    if provider == "ollama":
        ollama_base_url = input(f"URL base de Ollama (por defecto {ollama_base_url}): ").strip() or ollama_base_url
        print("Obteniendo modelos de Ollama...")
        try:
            import httpx
            response = httpx.get(f"{ollama_base_url}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
        except Exception as e:
            print(f"No se pudieron obtener modelos de Ollama: {e}")
            models = ["llama3", "mistral"]
    else:
        gemini_api_key = getpass.getpass("API Key de Gemini: ")
        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
        if gemini_api_key:
            try:
                print("\nConectando con Google GenAI para listar los modelos disponibles...")
                from google.genai import Client
                client = Client(api_key=gemini_api_key)
                api_models = []
                for m in client.models.list():
                    name = m.name
                    if "gemini" in name:
                        clean_name = name.replace("models/", "")
                        api_models.append(clean_name)
                if api_models:
                    models = sorted(list(set(api_models)))
            except Exception:
                print("No se pudo conectar con Google GenAI para obtener la lista en tiempo real. Usando modelos conocidos por defecto.")
            
    print("\nModelos disponibles:")
    for idx, model_name in enumerate(models, 1):
        print(f"{idx}) {model_name}")
    print(f"{len(models) + 1}) Especificar otro modelo...")
    
    try:
        choice = input(f"Selecciona un modelo (1-{len(models) + 1}, por defecto 1): ").strip()
        if not choice:
            selected_model = models[0]
        else:
            choice_idx = int(choice)
            if 1 <= choice_idx <= len(models):
                selected_model = models[choice_idx - 1]
            elif choice_idx == len(models) + 1:
                custom_model = input("Introduce el nombre del modelo personalizado: ").strip()
                if custom_model:
                    selected_model = custom_model
            else:
                print(f"Selección no válida. Se usará: {selected_model}")
    except ValueError:
        print(f"Entrada no válida. Se usará: {selected_model}")

    # 4. Save YAML via Pydantic model (rellena valores por defecto automáticamente)
    config = MailAssistantConfig(
        account=AccountConfig(name=account_name, host=imap_host, port=imap_port, folder=folder),
        llm=LLMConfig(
            provider=provider,
            model=selected_model,
            max_retries=5,
            ollama_base_url=ollama_base_url if provider == "ollama" else "http://localhost:11434",
            ollama_format="auto" if provider == "ollama" else "auto",
        ),
        classifier_rules=ClassifierRules(
            score_thresholds=Thresholds(important=60, discard=-30),
            whitelist_domains=[],
            blacklist_domains=[],
            positive_keywords=[],
            negative_keywords=[],
        ),
    )

    with open(config_file, "w") as f:
        yaml.dump(config.model_dump(), f)
        
    # 5. Store sensitive info in keyring
    manager = ConfigManager(config_file)
    manager.set_imap_password(account_name, imap_password)
    if provider == "gemini":
        manager.set_gemini_api_key(gemini_api_key)
    
    print(f"Configuración guardada en {config_file}")
