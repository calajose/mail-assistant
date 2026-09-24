# Mail Assistant - Guia para Agentes de IA

## Arquitectura

Proyecto Python modular para clasificacion de correos electronicos usando reglas locales y LLMs.

```
mail_assistant/
  cli/          # Interfaz de linea de comandos
  config/       # Gestion de configuracion y modelos Pydantic
  llm/          # Proveedores LLM (Gemini, Ollama)
  imap/         # Cliente y modelos IMAP
  rules/        # Motor de reglas de clasificacion
  classifier/   # Servicio de clasificacion
  report/       # Generacion de reportes
  utils/        # Utilidades
```

## Flujo de trabajo

1. `configure` -> Configurar cuenta, credenciales y LLM
2. `folders` -> Listar carpetas IMAP disponibles (opcional)
3. `scan` -> Escanear y clasificar correos
4. `report` -> Generar reporte desde results.json
5. `clean` -> Marcar correos como leidos

## Convenciones

- **Seguridad**: Usar `keyring` para credenciales, jamas imprimirlas en logs
- **Extensibilidad**: Nuevos proveedores LLM heredan de `LLMProvider` en `llm/base.py`
- **Reglas**: Nuevas reglas heredan de `Rule` en `rules/base.py` y se registran en `RuleEngine`
- **Estilo**: Sin comentarios en codigo salvo docstrings necesarios
- **Testing**: Tests en carpeta `tests/` usando pytest

## Comandos

```bash
./run configure        # Configuracion inicial
./run configure --model-only  # Cambiar solo LLM
./run folders          # Listar carpetas IMAP del servidor
./run scan --limit 20  # Escanear con limite
./run scan --no-llm    # Solo reglas locales
./run scan --folder X  # Escanear una carpeta concreta (nombre insensible a mayusculas)
./run scan --force-llm # Forzar LLM en todos
./run report           # Generar reporte
./run clean            # Limpiar correos procesados
```

## Manejo de carpetas

- Las carpetas se resuelven contra el listado real del servidor; `--folder inbox` equivale a `Inbox`.
- Si la carpeta no existe, `scan` y `clean` terminan con codigo 1 y muestran las carpetas
  disponibles mas una sugerencia, en lugar de un traceback.
- `mail_assistant/utils/folders.py` contiene la logica pura de resolucion y sugerencia.
