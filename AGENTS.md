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
tests/          # pytest (131 tests, unitarios con monkeypatch)
```

## Fase actual: mantenimiento y mejora

El proyecto esta en fase de MANTENIMIENTO en produccion (mejora continua),
gobernado por la Constitucion v3.0.0 (ratificada 2026-09-26, ultima enmienda
2026-09-27), depositada en el repo privado de especificaciones del proyecto
(ruta interna `.specify/memory/constitution.md`).

Dicho repo privado se clona aparte en `specs-privado/`, con symlinks `specs/` y
`.specify/` a el. Las tres rutas estan en `.gitignore`: las especificaciones son
privadas, jamas se commitean en este repo publico ni se nombra aqui su remoto
(la URL esta en la config local de `specs-privado`). Para trabajar con ellas,
`cd specs-privado` y commitear/pushear ahi; para sincronizar, `git pull` ahi.

La constitucion prevalece sobre cualquier practica informal:

- Nuevas funcionalidades, mejoras y correcciones permitidas sin decisión
  previa de negocio; su alcance se fija en la definición de cada intervención.
- Modificar el comportamiento observable existente en producción exige una
  entrada en el registro de decisiones de cambio (decisión, autor, fecha,
  justificación) y citar el ID de la decisión en el commit.
- Characterization tests (prefijo `"CONGELA comportamiento actual:"`) y golden
  master: son la red de regresión. Si pasan a rojo sin justificación, se
  revierte el cambio; nunca se ajusta el test para forzar el aprobado.
- Un solo módulo existente refactorizado a la vez (estrangulamiento), jamás
  reescritura integral; los módulos nuevos llevan sus propias pruebas.
- Dependencias externas: justificación motivada y aprobación previa; preferencia
  por la librería estándar (stdlib).
- Datos históricos persistidos (`results.json`, reportes): inmutables, cero
  cambios retroactivos.
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
  ~1s). `pyproject.toml` fija `testpaths = ["tests"]`.
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
