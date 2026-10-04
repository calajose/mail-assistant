# Release 1.2.0 — Categoría PELIGROSO para Detección de Phishing y Suplantación

**Fecha**: 4 de octubre de 2026  
**Rama**: `main` (merge de `013-categoria-peligroso`)  
**Tag**: `v1.2.0` (anotado, `22fd192` → `3defd2d`)  
**Especificación**: `specs/013-categoria-peligroso` (repo privado [`calajose/mail-assistant-specs`](https://github.com/calajose/mail-assistant-specs))  

---

## Resumen

Esta release incorpora **PELIGROSO**, la cuarta categoría de clasificación de Mail Assistant, dedicada a la detección y aislamiento de correos con indicios de:

- **Phishing** y suplantación de identidad bancaria, gubernamental o de servicios conocidos
- **Spoofing** de dominio o remitente (incluidos dominios typosquatting)
- **Ingeniería social**: urgencia falsa, amenazas de bloqueo, solicitudes de credenciales o códigos 2FA
- **Malware** y adjuntos sospechosos
- **Enlaces fraudulentos**: acortadores sospechosos y dominios de suplantación

El LLM (Gemini u Ollama) actúa como **detector principal** mediante los prompts oficiales actualizados; el motor de reglas locales queda preparado para futuras reglas heurísticas (SPF/DKIM/DMARC, listas de amenaza) sin bloquear esta entrega.

**Validación**: **178 pruebas automáticas** (131 preexistentes intactas + 47 nuevas) en menos de 2 segundos, con **0 dependencias externas nuevas**.

---

## Funcionalidad Nueva

### FR-001: Dominio — nueva categoría `PELIGROSO`

- **Cambio**: `PELIGROSO = "PELIGROSO"` en el enum `Category` y `"PELIGROSO"` añadido a `CategoryLiteral`.
- **Compatibilidad**: aditivo y no destructivo; los `results.json` históricos siguen validando sin migración (Constitución, Principio V).
- **Módulo**: `mail_assistant/rules/base.py`, `mail_assistant/config/models.py`
- **Tests**: `tests/test_category_peligroso.py`

### FR-002 / FR-003 / FR-004: Prompts LLM con explicación obligatoria de indicios

- **Cambio**: los prompts maestros declaran la categoría con sus criterios y sitúan `PELIGROSO` antes que `DUDOSO` en el orden de gravedad (`IMPORTANTE → PELIGROSO → DESCARTABLE → DUDOSO`), con directiva explícita de que toda clasificación como `PELIGROSO` **debe detallar concretamente los indicios observados** (ej.: «Remitente suplantando a banco X con dominio typo-squatting»).
- **Esquema**: el schema JSON de Ollama incorpora `PELIGROSO` automáticamente por derivación del enum.
- **Idioma**: toda respuesta en español estándar de España (Constitución, Principio VI).
- **Módulo**: `mail_assistant/config/defaults.py` (`DEFAULT_GEMINI_PROMPT`, `DEFAULT_OLLAMA_PROMPT`)
- **Tests**: prompts de ambos proveedores, orden de categorías y esquema dinámico.

### FR-005 / FR-006 / FR-007 / FR-012: Reporte con tabla de amenazas y filtrado interactivo

- **Cambio**: nueva sección `## Correos PELIGROSO` situada **antes** de `## Correos DUDOSO`, con columnas `De | Asunto | Fecha | Tipo de amenaza | Explicación` y contador `Peligrosos:` en el resumen superior.
- **Tipo de amenaza**: inferido léxicamente de la explicación con `infer_threat_type()` → `Phishing / Suplantación`, `Ingeniería social`, `Malware / Adjunto sospechoso`, `Enlace fraudulento` o `Amenaza sospechosa` (normalización de acentos con la stdlib `unicodedata`, sin dependencias).
- **Diálogo de `report`**: selección en cuatro vías — `[T]odos` / `[I]mportantes y Peligrosos` / `Solo [P]eligrosos` / `Solo I[m]portantes`.
- **Módulo**: `mail_assistant/report/generator.py`, `mail_assistant/cli/report.py`
- **Tests**: inferencia de amenazas, orden de secciones, filtros interactivos.

### FR-008 / FR-009: Salvaguardas de limpieza contra borrado accidental

- **Cambio**: los correos `PELIGROSO` **jamás** se marcan como leídos por defecto:
  - `clean` y `clean --yes`: solo tocan `DESCARTABLE`.
  - `clean --all` interactivo: muestra el aviso `⚠️ Hay N correo(s) clasificado(s) como PELIGROSO en el lote` y exige confirmación adicional `[s/N]`; sin confirmación, la limpieza se cancela sin marcar nada.
  - `clean --yes --all`: emite la advertencia en consola y procesa el lote completo.
- **Módulo**: `mail_assistant/cli/clean.py`
- **Tests**: filtrado por modo, cancelación, confirmación y ejecución desatendida.

### FR-010: Resumen de escaneo con contador `PELIGROSO`

- **Cambio**: el resumen final de `scan` muestra `IMPORTANTE: X | PELIGROSO: Y | DUDOSO: Z | DESCARTABLE: W`.
- **Módulo**: `mail_assistant/utils/progress.py`
- **Tests**: inicialización, registro y salida en consola.

### FR-011: Persistencia compatible con `results.json`

- **Cambio**: `results.json` admite la nueva categoría sin romper lecturas históricas.
- **Hallazgo de implementación**: `utils/results_io.py` mantenía un segundo conjunto hardcodeado de categorías que habría rechazado `PELIGROSO` en la lectura; se corrigió derivándolo del enum (`{c.value for c in Category}`), eliminando la divergencia futura entre validador y dominio.
- **Módulo**: `mail_assistant/utils/results_io.py`
- **Tests**: carga de resultados con `PELIGROSO` y compatibilidad retroactiva.

---

## También incluido desde v1.1.1

- Reorganización de repositorios: las especificaciones residen ahora en el repo privado [`calajose/mail-assistant-specs`](https://github.com/calajose/mail-assistant-specs); el repo público distribuye solo código bajo licencia MIT.
- `AGENTS.md` alineado con la **Constitución v3.0.0** (fase de mantenimiento), sin referencias a Spec Kit.
- Sección de licencia en `README.md` y comentario muerto eliminado de `models.py`.

---

## Validación

```bash
source venv/bin/activate
python -m pytest -q        # 178 passed en <2s
```

Guía de verificación: `specs/013-categoria-peligroso/quickstart.md` (repo privado) — **5/5 escenarios** en verde:

1. Dominio y modelos (`EmailResult`, esquema Ollama, `load_canonical_results`)
2. Prompts LLM y resumen de consola
3. Reporte con tabla de amenazas
4. Salvaguardas de `clean`
5. Regresión integral (131 tests originales intactos)

**Nota de validación end-to-end**: la clasificación en sí depende de la respuesta de un LLM real; el contrato (directivas de prompt + esquema de respuesta) está cubierto por la suite. La prueba CA-01 con un correo de phishing simulado ante el proveedor configurado es una verificación manual que requiere credenciales y red.

---

## Impacto y Beneficios

- **Seguridad**: detección temprana de fraude con explicación **auditable e obligatoria** de los indicios detectados — no basta con la etiqueta.
- **Sin roturas**: retrocompatible con datos históricos; los 131 characterization tests permanecen intactos (red de regresión del Principio II).
- **Operativa protegida**: ninguna limpieza puede archivar un incidente de seguridad sin acción explícita del usuario.
- **Coste añadido cero**: 0 dependencias nuevas; la detección reutiliza la llamada ya existente al LLM.
- **Mantenibilidad**: categorías con fuente única (enum) en dominio, esquema, validación y resumen.

---

## Documentación Relacionada

> Todo el material vive en el repo privado [`calajose/mail-assistant-specs`](https://github.com/calajose/mail-assistant-specs) (`specs-privado/` localmente; sin submódulo en el repo público).

- Especificación: `specs/013-categoria-peligroso/spec.md` (12 FR, 5 SC, checklist 16/16)
- Plan de implementación: `specs/013-categoria-peligroso/plan.md` (verificación constitucional I–VI)
- Investigación, modelo de datos y contratos: `research.md`, `data-model.md`, `contracts/`
- Tareas: `specs/013-categoria-peligroso/tasks.md` (20/20 completadas)
- Puesta en marcha: `specs/013-categoria-peligroso/quickstart.md`
- Constitución: `.specify/memory/constitution.md` (v3.0.0)
- `README.md` del repo público actualizado (características, prompts, reglas, `scan`, `clean`, `report`)

---

## Commits Incluidos

- `87beaa1` — feat: añadir categoría PELIGROSO con detección de phishing y salvaguardas de limpieza
- `3defd2d` — Merge: 013-categoria-peligroso -> main (release 1.2.0)
- `01035a2` — docs: añadir seccion de licencia (MIT para codigo, specs privadas)
- `1c56c51` — chore: extraer especificaciones del repo publico (invisibilidad total)
- `752d693` — Migrar specs a submódulo privado (repo privado de specs)
- `8fcd62d` — chore: eliminar comentario con referencia muerta a specs/ en models.py
- `2fcd237` — docs: AGENTS.md en fase de mantenimiento (constitucion v3.0.0), sin referencias a Spec Kit
- `22fd192` — tag anotado `v1.2.0` (apunta a `3defd2d`)

---

**Estado**: ✅ Cerrada y fusionada en `main`  
**Tag**: `v1.2.0`  
**Fecha**: 4 de octubre de 2026
