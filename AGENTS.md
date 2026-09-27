# Mail Assistant - Guia para Agentes de IA

## Arquitectura

Proyecto Python modular para clasificacion de correos electronicos usando reglas locales y LLMs.

```
mail_assistant/
  cli/          # Interfaz de linea de comandos (entrypoint: __main__.py:main)
  config/       # Gestion de configuracion y modelos Pydantic
  llm/          # Proveedores LLM (Gemini, Ollama)
  imap/         # Cliente y modelos IMAP
  rules/        # Motor de reglas de clasificacion
  classifier/   # Servicio de clasificacion
  report/       # Generacion de reportes
  utils/        # Utilidades
tests/          # pytest (23 tests, unitarios con monkeypatch)
```

## Fase actual (obligatoria)

El proyecto esta en fase de documentacion y proteccion, no de mejora. Ver
`.specify/memory/constitution.md`:

- El comportamiento observable actual es sagrado; nada se cambia sin decision
  por escrito del negocio, aunque parezca un bug.
- Todo hallazgo se registra (registro de anomalias), no se corrige aqui.
- Cero dependencias nuevas, cero refactors. No se anade ningun paquete ni se
  reorganiza codigo.
- Toda afirmacion requiere evidencia (fichero + lineas, dato real o testimonio
  con nombre y fecha). Lo no verificable se marca SUPOSICION y se pregunta.
- Todo el contenido nuevo en español de España.

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

- `./run` exige el entorno virtual `venv/` del propio repo; si no existe, falla
  con instrucciones de creacion. Ejecutar siempre desde la raiz del repo.
- Test: `source venv/bin/activate && python -m pytest` (sin red, sin credenciales,
  <1s). `pyproject.toml` fija `testpaths = ["tests"]`.
- No hay CI ni lint ejecutable: no se usa ningun linter en el proyecto.

## Rutas y artefactos

- Configuracion real en `~/.config/mail-assistant/config.yaml` (fuera del repo;
  el repo solo tiene `config.yaml.example`). Credenciales en el keyring del
  sistema: jamas imprimirlas en logs ni en la salida.
- `results.json` y `report.md` se leen/escriben con rutas relativas al CWD
  (`cli/scan.py`, `cli/report.py`, `cli/clean.py`): ejecutar desde la raiz del
  repo. Ambos estan en `.gitignore` y son artefactos regenerables.
- Si cambia `config.yaml` del repo o `pyproject.toml`, recuerda reinstalar con
  `pip install -e .`; cambios en `.py` se reflejan solos en modo editable.

## Flujo de trabajo

1. `configure` -> Configurar cuenta, credenciales y LLM
2. `folders` -> Listar carpetas IMAP disponibles (opcional)
3. `scan` -> Escanear y clasificar correos (escribe `results.json`)
4. `report` -> Generar reporte desde `results.json` (escribe `report.md`)
5. `clean` -> Marcar correos como leidos

## Convenciones

- **Extensibilidad**: Nuevos proveedores LLM heredan de `LLMProvider` en `llm/base.py`
- **Reglas**: Nuevas reglas heredan de `Rule` en `rules/base.py` y se registran en `RuleEngine`
- **Estilo**: Sin comentarios en codigo salvo docstrings necesarios
- **Testing**: Tests en carpeta `tests/` usando pytest; aislar red con `monkeypatch`

## Manejo de carpetas

- Las carpetas se resuelven contra el listado real del servidor; `--folder inbox` equivale a `Inbox`.
- Si la carpeta no existe, `scan` y `clean` terminan con codigo 1 y muestran las carpetas
  disponibles mas una sugerencia, en lugar de un traceback.
- `mail_assistant/utils/folders.py` contiene la logica pura de resolucion y sugerencia.

## Spec Kit

Comandos `/speckit.*` en `.opencode/commands/`; plantillas y scripts en `.specify/`.
