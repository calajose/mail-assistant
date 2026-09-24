# Mail Assistant

Asistente de correo local y modular que clasifica correos electrónicos usando reglas y LLMs de forma eficiente.

## Características

- Clasificación basada en reglas locales (minimiza las llamadas al LLM)
- Gestión segura de credenciales mediante el llavero del sistema (keyring)
- Arquitectura extensible de proveedores LLM
- Generación de reportes detallados en Markdown
- Listado de carpetas del servidor y resolución de nombres de carpeta con sugerencias si no existen

## Instalación

Se recomienda usar un entorno virtual para evitar conflictos de dependencias:

```bash
# 1. Crear el entorno virtual
python -m venv venv

# 2. Activar el entorno virtual (según tu shell):
# Para Bash/Zsh:
source venv/bin/activate
# Para Fish:
source venv/bin/activate.fish
# Para Csh/Tcsh:
source venv/bin/activate.csh
# Para PowerShell:
source venv/bin/Activate.ps1

# 3. Instalar el paquete
pip install .
```

### Desarrollo (instalación editable)

Si vas a modificar el código, instala el proyecto en modo editable:

```bash
pip install -e .
```

Así los cambios en los archivos `.py` se reflejan de inmediato sin reinstalar el paquete.

Solo necesitas volver a ejecutar `pip install -e .` si cambias `pyproject.toml` en aspectos de empaquetado, por ejemplo:

- dependencias
- script de entrada (`mail-assistant`)
- versión o metadatos
- configuración de build

### Instalación en antiX 23 (32-bit)

Dado que antiX 23 (basado en Debian 12) utiliza Python 3.11 y no distribuye wheels de `cryptography` para 32-bit (i686), es necesario usar los paquetes del sistema para algunas dependencias:

```bash
# 1. Instalar dependencias del sistema
sudo apt install python3-cryptography python3-yaml python3-keyring \
                 python3-requests python3-httpx python3-venv \
                 build-essential python3-dev libssl-dev

# 2. Crear entorno virtual con acceso a los paquetes del sistema
python3 -m venv venv --system-site-packages
source venv/bin/activate

# 3. Instalar el paquete y dependencias restantes
pip install -e .
pip install pydantic imap-tools google-genai
```

Una vez instalado, puedes ejecutar los siguientes comandos:

```bash
mail-assistant configure
mail-assistant folders
mail-assistant scan
mail-assistant clean
mail-assistant report
```

Si prefieres no activar el entorno virtual manualmente en cada sesion, usa el script `run` incluido en el proyecto:

```bash
./run configure
./run folders
./run scan
./run clean
./run report
```

### Solucion de problemas: `command not found`

Si al ejecutar `mail-assistant ...` ves `command not found`, normalmente significa que el entorno virtual no esta activo y `venv/bin` no esta en el `PATH`.

Opciones para solucionarlo:

```bash
# Opcion recomendada para desarrollo: activar el venv
source venv/bin/activate
mail-assistant configure

# O sin activar el venv: usar el script helper
./run configure

# O sin helper: usar la ruta absoluta del ejecutable
./venv/bin/mail-assistant configure
```

### Configuración

El asistente **no utiliza** directamente el archivo `config.yaml.example`. Este archivo es únicamente una **plantilla de referencia** para saber qué estructura tiene la configuración.

Cuando ejecutas `mail-assistant configure`:
1. El CLI te pedirá los datos de tu cuenta (nombre, servidor IMAP, puerto, etc.).
2. Te pedirá de forma segura la contraseña del correo (IMAP).
3. Elegirás el proveedor LLM: **Gemini** (Google) u **Ollama** (local).
4. Según el proveedor, se listarán los modelos disponibles (desde Google GenAI o desde tu instancia local de Ollama vía `/api/tags`) y podrás seleccionar uno mediante un menú interactivo. Si eliges Gemini, te pedirá la API Key de Gemini.
5. Generará automáticamente tu archivo de configuración real en `~/.config/mail-assistant/config.yaml`.
6. Guardará de forma segura tu contraseña de correo (y tu API Key de Gemini, si elegiste ese proveedor) en el **llavero del sistema** (`keyring`), garantizando que no queden expuestas en texto plano.

**Ajuste rápido del LLM**:
Si solo deseas cambiar el proveedor o el modelo sin alterar el resto de la configuración de tu cuenta ni volver a ingresar tus credenciales, puedes usar el flag `--model-only`:
```bash
mail-assistant configure --model-only
```
Esto te permitirá cambiar entre Gemini y Ollama, actualizar la URL base (para Ollama) o la API Key (para Gemini), y seleccionar un nuevo modelo.

Si deseas ajustar manualmente otras reglas técnicas (como palabras clave positivas/negativas, umbrales de puntuación, forzado a LLM o reintentos del LLM), puedes editar directamente tu archivo `~/.config/mail-assistant/config.yaml` tomando `config.yaml.example` como guía.

Parámetros recomendados del LLM en `config.yaml`:

- `llm.max_retries`: número máximo de reintentos ante errores transitorios de Gemini (`503`/"Too busy", `429` o fallos de red). Default: `5`.
- `llm.user_context`: instrucciones de clasificación personalizadas que se añaden al prompt base del proveedor.
- `llm.ollama_format`: modo de salida para Ollama. Valores: `auto` (default), `schema`, `json`, `plain`.
  - `auto`: prueba `schema -> json -> plain`.
  - `plain`: recomendado si tu modelo local no respeta `format` y devuelve vacío o JSON inválido.
- `llm.body_preview_limit`: número de caracteres del cuerpo del correo que se envían al LLM para su clasificación. Default: `500`. Aumentarlo da más contexto pero consume más tokens y latencia.

Compatibilidad de salida con Ollama:

- El proveedor de Ollama intenta parsear la respuesta con tolerancia a variaciones del modelo: JSON directo, bloques markdown tipo ` ```json ... ``` `, o JSON embebido en texto libre.
- Para mejorar compatibilidad, la llamada a Ollama usa una cascada automática de formatos: `schema` -> `json` -> `plain`.
- Si tu modelo devuelve respuestas vacías en `schema`/`json` (por ejemplo algunos modelos locales), el asistente continúa automáticamente con `plain`.

Prompt por proveedor (externo y transparente):

Los prompts de cada proveedor ya no están embebidos en el código. La aplicación los gestiona automáticamente:

- En cada inicio se escriben (o sobrescriben) los archivos `gemini.default.txt` y `ollama.default.txt` en `~/.config/mail-assistant/prompts/`. Contienen el prompt oficial + una cabecera explicativa. **No edites estos archivos**, se regeneran en cada ejecución.

- Si deseas personalizar el prompt de un proveedor, crea `~/.config/mail-assistant/prompts/gemini.txt` o `~/.config/mail-assistant/prompts/ollama.txt` con el contenido que prefieras. El sistema lo usará automáticamente.

- Para **volver al prompt por defecto**, simplemente borra tu archivo `{provider}.txt`. El sistema usará el `.default.txt` automáticamente. Si también faltase ese, usará una constante en memoria como último recurso.

- Puedes incluir comentarios con `#` en tu prompt personalizado; serán filtrados automáticamente al cargarlo (no se envían al LLM, ahorrando tokens).

- Además, si defines `llm.user_context` en `config.yaml`, ese contexto se añade al final del prompt cargado.

### Reglas de clasificación

El motor local evalúa estas reglas en orden y suma puntuación:

| Regla | Qué evalúa | Puntuación | Efecto |
|------|------------|-----------:|--------|
| `whitelist_domains` | Si algún valor de la lista está contenido en `from_` | `+100` | Se clasifica como `IMPORTANTE` inmediatamente (sin LLM) |
| `blacklist_domains` | Si algún valor de la lista está contenido en `from_` | `-100` | Se clasifica como `DESCARTABLE` inmediatamente |
| `force_llm_senders` | Si algún valor de la lista está contenido en `from_` | `0` | Fuerza paso por LLM cuando el resultado local sería `DESCARTABLE` por umbral |
| Newsletter | Cabeceras como `list-unsubscribe` o `auto-submitted` | `-40` | Resta prioridad |
| `positive_keywords` / `negative_keywords` | Coincidencias en asunto + remitente | `+15` / `-15` por palabra | Ajuste incremental |

Si ninguna regla llega a `+100` o `-100`, se aplican los umbrales:

- `score >= important` → `IMPORTANTE`
- `score <= discard` → `DESCARTABLE`
- en medio → `DUDOSO` (y se consulta LLM si está habilitado)

Excepciones de prioridad:

- `blacklist_domains` y `whitelist_domains` ganan por cortocircuito (`-100` / `+100`) y no se envían al LLM.
- `force_llm_senders` aplica para evitar descartes por umbral y pasar esos correos al LLM.

#### Caso Amazon (novedades de libros)

Si quieres que correos de un remitente concreto no se descarten por reglas locales y pasen al LLM para decidir según contexto, usa `force_llm_senders` y `llm.user_context`:

```yaml
llm:
  user_context: |
    Los correos de novedades de libros de Amazon son IMPORTANTES para mi.
    Las novedades de otros productos no lo son.

classifier_rules:
  force_llm_senders:
    - novedades@amazon.es
```

#### Caso eBiblio (recomendado)

Si tus correos de eBiblio llegan desde `no-reply@cantookstation.com` y quieres que siempre sean importantes, añade el dominio a la whitelist:

```yaml
classifier_rules:
  whitelist_domains:
    - cantookstation.com
```

Con eso, cualquier correo cuyo remitente contenga `cantookstation.com` se marca como `IMPORTANTE` por reglas locales (sin depender de la IA).

Nota: las keywords locales no analizan el cuerpo del correo; solo asunto y remitente. Por eso, en este caso, whitelist por dominio es la opción más fiable.

### Comando folders

Lista las carpetas IMAP reales disponibles en el servidor, marcando cuál es la configurada en `config.yaml`. Útil para averiguar el nombre exacto a usar con `--folder`, ya que cada proveedor usa su propia nomenclatura (por ejemplo, Yahoo no tiene `Spam`: su carpeta de correo basura se llama `Bulk`).

```bash
mail-assistant folders
```

No acepta flags. Ejemplo de salida:

```
Carpetas disponibles en imap.mail.yahoo.com:
  - Archive
  - Bulk
  - Inbox (configurada)
  - Sent
  - Trash
```

### Comando scan

Escanea los correos no leídos de la carpeta configurada y los clasifica usando reglas locales y, opcionalmente, un LLM.

```bash
mail-assistant scan [--limit N] [--no-llm] [--folder CARPETA] [--all] [--force-llm]
```

| Flag | Descripción |
|------|-------------|
| `--limit N` | Número máximo de correos a procesar (default: 20). Usa un valor alto como `99999` para procesar todos los no leídos |
| `--no-llm` | Deshabilita el uso del LLM; clasifica únicamente con reglas locales (whitelist, blacklist, keywords) |
| `--folder CARPETA` | Carpeta IMAP a escanear para esta ejecución. Si no se indica, usa la carpeta guardada en la configuración. El nombre se resuelve sin distinguir mayúsculas (`inbox` = `Inbox`); usa `mail-assistant folders` para ver las carpetas reales |
| `--all` | Procesa todos los correos no leídos sin preguntar, ignorando el límite |
| `--force-llm` | Fuerza que todos los correos pasen por el LLM, ignorando la clasificación local y anulando el cortocircuito de whitelist/blacklist |

Al inicio del escaneo se muestra cuántos correos no leídos hay en el buzón. Si el total supera el límite, el comando preguntará si deseas analizar todos o solo hasta el límite. Pulsar Enter usa por defecto el límite.

Durante el escaneo se muestra progreso detallado por correo, por ejemplo:

- `[3/120] Procesando 'Asunto...' de remitente@dominio.com`
- `Correo clasificado por reglas locales: IMPORTANTE`
- `Correo dudoso ... Enviado al LLM`
- `Respuesta recibida del LLM: DESCARTABLE en 5.03s.`
- `Reintento LLM 2/5 ... Esperando 4.3s`

El tiempo de respuesta del LLM se muestra en segundos con dos decimales, permitiendo comparar el rendimiento entre proveedores cloud (Gemini: ~1-3s) y locales (Ollama: variable según modelo y hardware). En Ollama, si el modelo no soporta bien salida estructurada, parte del tiempo puede incluir intentos previos de compatibilidad (`schema`/`json`) antes de usar `plain`.

La descarga de cabeceras se hace en lotes y muestra progreso incremental (`Descargando cabeceras... n/total`) para evitar periodos largos sin feedback cuando hay muchos correos.

Al finalizar, el comando imprime un resumen con duración total, número de correos clasificados por reglas locales, correos enviados al LLM, fallos del LLM, reintentos y desglose por categoría (`IMPORTANTE`, `DUDOSO`, `DESCARTABLE`).

El resultado se guarda en `results.json`.

Si el proveedor Gemini falla temporalmente (por ejemplo, `Too busy`, rate limit o problemas de conexión), el comando reintenta según `llm.max_retries` con espera progresiva y mostrando cada reintento en consola. Si aun así no hay respuesta, el correo se mantiene como `DUDOSO`, se registra una explicación de "LLM no disponible" y el escaneo continúa sin abortar.

### Troubleshooting Ollama

Si usas Ollama y ves respuestas vacías o errores de parseo, revisa estos casos:

- **Síntoma**: `Respuesta vacia del LLM en modo 'schema' ... done_reason='stop'`.
  - **Causa probable**: el modelo no soporta salida estructurada con `format`.
  - **Acción**: fija `llm.ollama_format: "plain"` en `~/.config/mail-assistant/config.yaml`.

- **Síntoma**: `No se pudo parsear respuesta del LLM en modo 'json'`.
  - **Causa probable**: el modelo mezcla texto libre y JSON incompleto.
  - **Acción**: usa `llm.ollama_format: "plain"` para evitar modo JSON forzado.

- **Síntoma**: clasificación correcta pero lenta en Ollama.
  - **Causa probable**: en `auto`, el asistente puede agotar intentos `schema/json` antes de llegar a `plain`.
  - **Acción**: usa `plain` para ese modelo o cambia a uno con mejor soporte de salida estructurada.

- **Comprobación rápida de conectividad**:

```bash
curl http://localhost:11434/api/tags
```

Si falla, revisa `llm.ollama_base_url` y que Ollama esté en ejecución.

Ejemplo de configuración recomendada para modelos con problemas de formato:

```yaml
llm:
  provider: "ollama"
  model: "gpt-oss:20b"
  ollama_base_url: "http://localhost:11434"
  ollama_format: "plain"
```

### Comando clean

Marca como leídos los correos que aparecen en `results.json` (es decir, los correos realmente procesados en el último `scan`).

```bash
mail-assistant clean [--folder CARPETA] [--yes] [--all]
```

| Flag | Descripción |
|------|-------------|
| `--folder CARPETA` | Carpeta IMAP a limpiar para esta ejecución. Si no se indica, usa la carpeta guardada en la configuración. Igual que en `scan`, el nombre se resuelve sin distinguir mayúsculas |
| `--yes` | Marca solo DESCARTABLES sin preguntar nada |
| `--yes --all` | Marca todos los correos sin preguntar nada |

Comportamiento según flags:

- **Sin flags**: pregunta una sola vez `¿Marcar como leidos (t)odos o solo (d)escartables? [D]:`. Al responder, ejecuta directamente.
- `--all`: marca todos los correos sin preguntar modo.
- `--yes`: marca solo DESCARTABLES, sin preguntar nada (modo no interactivo).
- `--yes --all` = `--yes --all`: marca todos, sin preguntar nada.

Nota de comportamiento (caso borde): si ejecutaste `scan` con `--folder` para usar una carpeta distinta de la configurada, ejecuta `clean` con ese mismo `--folder` para marcar los correos correctos.

### Troubleshooting: carpeta inexistente

Si indicas una carpeta que no existe, el comando no lanza un traceback: termina con código 1 y muestra las carpetas reales del servidor junto con una sugerencia.

- **Síntoma**: `Error: la carpeta 'Spam' no existe en el servidor.`
- **Causa**: cada proveedor usa su propia nomenclatura y puede no existir esa carpeta.
- **Acción**: ejecuta `mail-assistant folders` para ver los nombres exactos y repite el comando con uno de ellos.

```bash
mail-assistant folders
mail-assistant scan --folder Bulk
```

### Generación de reportes

El comando `mail-assistant report` lee el archivo `results.json` generado por `mail-assistant scan` y compila un reporte detallado en `report.md`. No tiene flags de línea de comandos; usa una sola pregunta interactiva para elegir entre:

- `Todos` (default al pulsar Enter): incluye `IMPORTANTE`, `DUDOSO` y `DESCARTABLE`
- `Solo IMPORTANTES`: incluye únicamente `IMPORTANTE`

Si un correo quedó marcado como `DUDOSO`, el reporte identificará automáticamente si el origen de la duda proviene de las reglas locales, de un fallo de disponibilidad del LLM o si fue validado y confirmado por el LLM. En el modo `Solo IMPORTANTES`, las secciones `DUDOSO` y `DESCARTABLE` no se incluyen.

```bash
mail-assistant report
```

## Reglas de Uso

- **Seguridad**: Nunca modifiques el código para imprimir credenciales o claves API en logs. Utiliza siempre `keyring` para acceder a secretos.
- **Modo Read-Only**: `scan` y `report` trabajan en modo lectura (`readonly=True`). El comando `clean` es la única excepción y marca como leídos los correos procesados.
- **Eficiencia**: Antes de llamar al LLM, agota todas las reglas locales. Solo los correos `DUDOSO` deben ser enviados al LLM (a menos que se use `--force-llm`).
- **Configuración**: El archivo `config.yaml` es para parámetros técnicos; las credenciales van siempre al llavero del sistema.

## Reglas de Extensibilidad

- **Nuevos Proveedores LLM**: Implementa una nueva clase en `llm/` que herede de `LLMProvider` y regístrala en la factoría de `cli/scan.py`.
- **Nuevas Reglas**: Añade clases en `rules/implementations.py` heredando de `Rule`. Regístralas en `RuleEngine` para que sean consideradas.
- **Modificaciones de Estructura**: Mantén la separación de responsabilidades: si es lógica de negocio, va en `classifier/` o `rules/`; si es acceso a datos, va en `imap/`.
