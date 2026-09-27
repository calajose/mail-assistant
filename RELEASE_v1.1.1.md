# Release 1.1.1 — Corrección de Anomalías Solicitadas por Negocio

**Fecha**: 27 de septiembre de 2026  
**Rama**: `main` (merge de `012-fix-business-anomalies`)  
**Tag**: `v1.1.1`  
**Acta de negocio**: 26 de septiembre de 2026 (José Manuel Cala)  
**Especificación**: `specs/012-fix-business-anomalies/spec.md`

---

## Resumen

Esta release implementa la corrección de **19 anomalías** operativas, de seguridad y de experiencia de usuario formalmente autorizadas por negocio en el acta del 26 de septiembre de 2026. Todas las correcciones han sido validadas con **131 pruebas automáticas** (23 preexistentes + 108 nuevas) sin dependencias externas.

---

## Correcciones Implementadas

### A-01: Destrucción silenciosa de reglas heurísticas personalizadas
- **Problema**: `configure` sobrescribía y vaciaba todas las listas blancas, negras y palabras clave.
- **Solución**: Precarga de todos los valores existentes con opciones por defecto en los prompts interactivos. Las listas se conservan intactas salvo modificación expresa.
- **Módulo**: `mail_assistant/cli/configure.py`
- **Tests**: `tests/test_configure_preload.py`

### A-02: Falso negativo por sensibilidad a mayúsculas/minúsculas
- **Problema**: Las reglas ignoraban correos críticos si el asunto o remitente contenían mayúsculas.
- **Solución**: Normalización a `.lower()` en dominios, palabras clave y remitentes forzados.
- **Módulo**: `mail_assistant/rules/implementations.py`
- **Tests**: `tests/test_rules_normalization.py`

### A-03: Pérdida económica por interrupción del escaneo
- **Problema**: Si el escaneo se interrumpía antes de escribir en disco, se perdían todas las clasificaciones y el coste de las llamadas a IA.
- **Solución**: Persistencia incremental y atómica tras cada correo clasificado (`.results.json.tmp` → `os.replace`).
- **Módulo**: `mail_assistant/cli/scan.py`, `mail_assistant/classifier/service.py`
- **Tests**: `tests/test_imap_and_persistence.py`

### A-04: Vulnerabilidad de suplantación por subcadena abierta
- **Problema**: Un remitente como `"Soporte cantookstation.com" <malicioso@evil.ru>` podía puntuar en lista blanca.
- **Solución**: Extracción rigurosa de la dirección real con `email.utils.parseaddr`. Entradas con `@` coinciden solo con dirección exacta; entradas sin `@` coinciden solo con dominio estricto tras la última `@`.
- **Módulo**: `mail_assistant/rules/implementations.py`
- **Tests**: `tests/test_rules_normalization.py`

### A-06: Cortocircuito destruía la marca de supervisión forzada a IA
- **Problema**: Un correo de `force_llm_senders` con puntuación ≤ −100 se descartaba sin consultar a la IA.
- **Solución**: El cortocircuito inferior preserva `forced=True` y clasifica como `DUDOSO` hacia la IA ("el rescate manda").
- **Módulo**: `mail_assistant/rules/engine.py`
- **Tests**: `tests/test_engine_rescue.py`

### A-07: Divergencia semántica en confirmación interactiva
- **Problema**: `scan` aceptaba `"a"` pero `clean` no.
- **Solución**: Unificación mediante `is_confirm_all()` en `mail_assistant/utils/cli.py`. Ambas herramientas aceptan `{"t", "todos", "all", "a"}` indistintamente.
- **Módulo**: `mail_assistant/cli/scan.py`, `mail_assistant/cli/clean.py`, `mail_assistant/utils/cli.py`
- **Tests**: `tests/test_cli_confirmation.py`

### A-08: Quiebre fatal por `AttributeError` en `report.py`
- **Problema**: `report.py` y `clean.py` fallaban con traceback ante estructuras de lista o esquemas incompatibles.
- **Solución**: Validación estricta del esquema canónico de diccionario con mensajes descriptivos. Rechazo de archivos dañados, con campos faltantes/sobrantes o categorías desconocidas.
- **Módulo**: `mail_assistant/cli/report.py`, `mail_assistant/cli/clean.py`, `mail_assistant/utils/results_io.py`
- **Tests**: `tests/test_results_sanitized.py`

### A-09: Reseteo involuntario de `max_retries` en `--model-only`
- **Problema**: `configure --model-only` reseteaba `max_retries` a 5.
- **Solución**: Preservación de `max_retries`, `body_preview_limit` y configuración de cuenta al actualizar solo el modelo.
- **Módulo**: `mail_assistant/cli/configure.py`
- **Tests**: `tests/test_configure_preload.py`

### A-10: Truncamiento asimétrico de vista previa del cuerpo
- **Problema**: Ollama truncaba a 500 caracteres mientras Gemini usaba el límite configurado.
- **Solución**: Límite unificado a 4.096 caracteres configurable (`body_preview_limit`) en ambos proveedores. Migración transparente del valor legado 500 → 4096 con aviso.
- **Módulo**: `mail_assistant/llm/ollama.py`, `mail_assistant/llm/gemini.py`, `mail_assistant/config/models.py`
- **Tests**: `tests/test_llm_resilience.py`

### A-11: Desconexiones IMAP recurrentes por socket zombi
- **Problema**: Tras una reconexión, la sesión no se actualizaba y cada correo intentaba reconectar.
- **Solución**: Reasignación de `self._mailbox_session` tras reconexión exitosa. Las sesiones sustituidas se cierran correctamente al salir del contexto.
- **Módulo**: `mail_assistant/imap/client.py`
- **Tests**: `tests/test_imap_and_persistence.py`

### A-12: Inexistencia de timeouts en comunicación IMAP
- **Problema**: Sin timeout, una conexión lenta podía congelar el sistema indefinidamente.
- **Solución**: Parámetro `timeout` en `AccountConfig` (30 s por defecto, configurable). Aplicado a todas las inicializaciones de `MailBox`.
- **Módulo**: `mail_assistant/imap/client.py`, `mail_assistant/config/models.py`
- **Tests**: `tests/test_imap_and_persistence.py`

### A-13: Ausencia de reintentos en proveedor Ollama
- **Problema**: Errores transitorios de red o HTTP 429/5xx abortaban la clasificación.
- **Solución**: Bucle de reintentos con retroceso exponencial (`2**attempt + uniform(0, 1)`) hasta `max_retries`. Captura de `httpx.ConnectError`, `httpx.TimeoutException` y `httpx.HTTPStatusError` (429/5xx). Callback `on_retry` para feedback en consola.
- **Módulo**: `mail_assistant/llm/ollama.py`, `mail_assistant/cli/scan.py`
- **Tests**: `tests/test_llm_resilience.py`

### A-15: Dependencia no declarada de `httpx`
- **Problema**: `httpx` se usaba en tres módulos sin estar en `pyproject.toml`.
- **Solución**: Añadida formalmente a `dependencies`.
- **Módulo**: `pyproject.toml`

### A-16: Exposición de metadatos privados e IPs en `results.json`
- **Problema**: `results.json` contenía cabeceras técnicas con IPs en texto claro.
- **Solución**: Saneamiento con sustitución pasiva. El registro persistido contiene exclusivamente `uid`, `from_`, `subject`, `date`, `category`, `explanation`. Modelo Pydantic `EmailResult` con `extra="forbid"`.
- **Módulo**: `mail_assistant/config/models.py`, `mail_assistant/cli/scan.py`, `mail_assistant/report/generator.py`
- **Tests**: `tests/test_results_sanitized.py`

### A-17: Inyección de directivas vacías ante prompt en blanco
- **Problema**: Un fichero de prompt con solo comentarios o vacío producía un prompt vacío.
- **Solución**: Detección de texto limpio vacío con fallback al prompt maestro por defecto y advertencia al usuario.
- **Módulo**: `mail_assistant/config/manager.py`
- **Tests**: `tests/test_llm_resilience.py`

### A-18: Importación huérfana de `ClassifierRules`
- **Problema**: Import no utilizado en `rules/implementations.py`.
- **Solución**: Eliminado.
- **Módulo**: `mail_assistant/rules/implementations.py`

### A-19: Configuración inactiva del linter Ruff
- **Problema**: `[tool.ruff]` en `pyproject.toml` y referencia en `AGENTS.md` sin linter instalado.
- **Solución**: Eliminada la sección `[tool.ruff]` y actualizada la referencia en `AGENTS.md`.
- **Módulo**: `pyproject.toml`, `AGENTS.md`

---

## Reglas Protegidas (Sin Cambios)

Las siguientes reglas fueron ratificadas como **INTENCIONAL** por negocio y permanecen inalteradas:

- **A-05**: Remitentes forzados no van a IA si puntuación es positiva (cortocircuito +100 protegido).
- **A-14**: Flags IMAP ni se usan ni se tocan.
- **A-20**: Discriminación contextual de novedades de libros frente a ofertas comerciales (Caso Amazon).
- **A-21**: Calificación inmediata de avisos bibliotecarios sin coste de IA (Caso eBiblio).
- **A-22**: Tolerancia a nomenclatura heterogénea de carpetas y alias de correo basura.
- **A-23**: Sobrescritura forzosa de directivas maestras predeterminadas en cada inicio.
- **A-24**: Blindaje y segregación criptográfica de credenciales en llavero del sistema.

---

## Verificación

### Suite de Pruebas

```bash
source venv/bin/activate && python -m pytest -v
```

**Resultado**: 131 tests en verde, 0 fallos, 0 regresiones.

### Escenarios de Validación Rápida

```bash
# Escenario 1: Normalización case-insensitive y dominios estrictos
pytest tests/test_rules_normalization.py -v

# Escenario 2: Prioridad de rescate a IA
pytest tests/test_engine_rescue.py -v

# Escenario 3: Integridad de configuración con precarga
pytest tests/test_configure_preload.py -v

# Escenario 4: Privacidad y estructura canónica en results.json
./run scan --limit 5 --no-llm
python -c "import json; data=json.load(open('results.json')); assert 'results' in data; print('Formato canónico OK')"
./run report

# Escenario 5: Unificación de confirmación interactiva "a"
pytest tests/test_cli_confirmation.py -v
```

**Resultado**: 5/5 escenarios verificados exitosamente.

---

## Impacto y Beneficios

- **Protección de inversión**: La persistencia incremental (A-03) protege el coste de las llamadas a IA ante interrupciones.
- **Seguridad**: Eliminación de exposición de IPs y cabeceras privadas (A-16). Blindaje anti-spoofing (A-04).
- **Fiabilidad**: Timeouts IMAP (A-12), reintentos exponenciales (A-13), reconexión sin socket zombi (A-11).
- **Experiencia de usuario**: Precarga de configuración (A-01, A-09), unificación de confirmación (A-07), mensajes de error claros (A-08).
- **Mantenibilidad**: Eliminación de código muerto (A-18, A-19), dependencias formalizadas (A-15).

---

## Documentación Relacionada

- Especificación funcional: `specs/012-fix-business-anomalies/spec.md`
- Plan de implementación: `specs/012-fix-business-anomalies/plan.md`
- Registro de anomalías: `specs/000-reconocimiento/registro-de-anomalias.md`
- Acta de negocio: `specs/000-reconocimiento/acta-entrevista-negocio.md`
- Constitución del proyecto: `.specify/memory/constitution.md`

---

## Commits Incluidos

- `47a7ebf` — [Spec Kit] Especificaciones, plan y tareas para 012-fix-business-anomalies
- `7d4400a` — feat: corrección de anomalías solicitadas por negocio (A-01 a A-19)
- `Merge: 012-fix-business-anomalies -> main (release 1.1.1)`

---

**Estado**: ✅ Cerrada y fusionada en `main`  
**Tag**: `v1.1.1`  
**Fecha**: 27 de septiembre de 2026
