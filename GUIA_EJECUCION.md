# Guia de ejecucion del simulador DSAR

## Requisitos

- Windows 10/11 con PowerShell, o Linux/macOS con bash.
- Python 3.10 o superior (`python` en Windows, `python3` en Linux/macOS).

El motor, el RAG y el simulador de consola usan solamente la biblioteca estandar de Python. La interfaz web necesita las dependencias de `requirements.txt` (FastAPI, Uvicorn, Jinja2 y python-multipart). No hace falta base de datos: los casos se guardan en archivos JSON. Sin clave de API todo funciona sin internet; con una clave de Gemini se activa el asistente de IA y, si Claude Code esta instalado, el agente Claude (ver "Inteligencia artificial en la web" y las secciones 6 y 7).

El proyecto incorpora un RAG vectorial local basico. Genera embeddings TF-IDF de unigramas y bigramas, los conserva en `rag/vector_store.json`, recupera por similitud coseno y registra los fragmentos con su procedencia y huella SHA-256.

## Componentes principales

| Ruta | Proposito |
|---|---|
| `skills/dsar-rights/` | Definicion, referencias, plantillas y scripts del skill. |
| `rag/dsar_rag.py` | Generacion de embeddings, indice y recuperacion vectorial. |
| `rag/vector_store.json` | Vectores, vocabulario, IDF, metadatos y fragmentos indexados. |
| `demo/dsar_simulator.py` | Simulador interactivo y escenarios preparados. |
| `skills/dsar-rights/scripts/case_lifecycle.py` | Ciclo de vida con aprobacion humana: identidad, aprobar/rechazar, ejecucion simulada, respuesta y cierre. |
| `agents/` | Orquestador del Flujo 3, Agente de Inventario y Agente de Evidencia simulados, y almacen JSON de casos. |
| `app/` | Interfaz web (FastAPI + HTML): bandeja, formulario, panel HITL, evidencia y API REST. |
| `data/` | Inventario, registros de PII y politicas ficticios. `data/runtime/` guarda los casos y la evidencia generados. |
| `llm/dsar_llm.py` | Asistente de IA opcional (Gemini u OpenRouter) para triaje y redaccion. |
| `llm/claude_agent.py` | Agente Claude: ejecuta Claude Code en modo de solo lectura para analizar un caso y redactar. |
| `.claude/skills/dsar-rights/` | Adaptador del skill para usar el agente dentro de Claude Code. |
| `tests/` | Pruebas del motor DSAR, del ciclo de vida, del orquestador, de la web, del RAG, de la IA y de la ejecucion completa. |
| `evidencias/` | Expedientes de muestra para la entrega academica. |

No es necesario incluir `.venv`, `simulaciones/`, `data/runtime/` ni carpetas `__pycache__` en el archivo comprimido.

## Interfaz web (inicio rapido)

Linux/macOS:

```bash
./scripts/setup.sh      # crea .venv, instala dependencias y ejecuta las pruebas
./scripts/run_app.sh    # http://127.0.0.1:8000
```

Windows:

```powershell
.\scripts\setup.ps1
.\scripts\run_app.ps1
```

Tambien puede iniciarse directamente con `uvicorn app.main:app --reload` desde la raiz del proyecto.

| Pagina | Uso |
|---|---|
| `/` | Bandeja de casos con estado, fecha limite y dias restantes. |
| `/solicitudes/nueva` | Formulario para registrar una solicitud ficticia del titular. |
| `/casos/<id>` | Panel HITL: motivos, datos localizados, RAG, borrador, decisiones firmadas, coordinacion de agentes y auditoria. |
| `/pruebas` | Casos de prueba: 13 escenarios con resultado esperado; se ejecutan todos o uno a uno y muestran cada comprobacion. |
| `/inventario` | Sistemas con PII que consulta el Agente de Inventario. |
| `/evidencia` | Cadena de evidencia con verificacion de integridad. |
| `/docs` | Documentacion interactiva de la API REST (`/api/...`). |

### Recorrido del ciclo completo

1. Registre una solicitud. Si marca la identidad como no verificada, el caso queda en `IDENTITY_PENDING` y el Agente de Inventario no se consulta.
2. En el panel del caso, confirme la identidad (metodo y referencia). Se ejecuta el descubrimiento y el caso pasa a `REVIEW` o `APPROVAL_REQUIRED`.
3. Apruebe o rechace con nombre, rol y comentario. La decision queda firmada con una huella SHA-256.
4. Si se aprobo, registre la ejecucion simulada (`FULFILLED`). Ningun sistema origen se modifica.
5. Envie la respuesta: queda congelada en una bandeja de salida simulada con su huella.
6. Cierre el caso (`CLOSED`). Revise `/evidencia` para comprobar que la cadena sigue integra.

### API REST

| Metodo y ruta | Accion |
|---|---|
| `POST /api/requests` | Registrar una solicitud (Flujo 3 completo). |
| `GET /api/cases`, `GET /api/cases/{id}` | Consultar casos; incluye `available_actions`. |
| `POST /api/cases/{id}/verify-identity` | Confirmar identidad (`actor`, `method`, `reference`). |
| `POST /api/cases/{id}/approve` y `/reject` | Decision humana (`approver`, `role`, `comment`). |
| `POST /api/cases/{id}/fulfill`, `/send`, `/close` | Ejecucion simulada, respuesta y cierre (`actor`). |
| `GET /api/cases/{id}/response.md` | Borrador o respuesta enviada en Markdown. |
| `GET /api/evidence`, `GET /api/evidence/verify` | Registro de evidencia y verificacion de la cadena. |
| `GET /api/scenarios`, `POST /api/scenarios/run` | Catalogo de casos de prueba y su ejecucion (todos o `?scenario_id=CP-01`). |

Las transiciones no permitidas devuelven `409` y las entradas invalidas `422`.

### Despliegue gratuito en Render

El archivo `render.yaml` define un Web Service gratuito:

1. Inicie sesion en <https://render.com> con la cuenta de GitHub.
2. Elija **New > Blueprint** y seleccione este repositorio. Render lee `render.yaml`, que apunta a la rama `VictorDev`.
3. Al terminar el despliegue, Render muestra la URL publica.

En el plan gratuito el disco es efimero: los casos de `data/runtime/` se pierden cuando el servicio se reinicia o se suspende por inactividad. Para la demostracion basta con volver a registrar las solicitudes.

### Inteligencia artificial en la web

La interfaz integra dos modelos. Ninguno decide el estado, la identidad, la redaccion de terceros ni la aprobacion humana: proponen y una persona confirma o elige.

| Modelo | Donde aparece | Que hace | Que recibe |
|---|---|---|---|
| **Gemini** (asistente) | Boton **Sugerir derecho con IA** en *Nueva solicitud* | Propone el derecho a partir del texto; usted lo confirma o lo corrige antes de registrar. | Solo el texto de la solicitud. |
| **Gemini** (asistente) | Boton **Redactar con Gemini** en el caso | Redacta un borrador citando los fragmentos del RAG. | Hechos minimizados, sin valores de PII. |
| **Claude** (agente) | Boton **Redactar con Claude (agente)** en el caso | Ejecuta Claude Code con herramientas de solo lectura: lee el expediente, el skill y las referencias ISO por su cuenta y redacta. | El expediente (datos ficticios). |

Al **enviar la respuesta**, el campo *Texto a enviar* permite elegir la plantilla del motor o uno de los borradores de IA. El texto elegido se congela con su huella SHA-256 y el validador comprueba que coincide con el borrador original.

El expediente registra todo: sugerencia de la IA, derecho confirmado y si se acepto o corrigio (`llm.classification`), cada borrador con proveedor, modelo, autor, estado en que se genero y huella (`ai_drafts`), y el borrador enviado (`outbox.source`). Cada borrador agrega ademas un evento al registro de auditoria y a la cadena de evidencia (`AI_DRAFT_GENERATED`).

Para activarlos, en la misma terminal antes de iniciar la aplicacion:

```powershell
$env:GEMINI_API_KEY = "su clave de Google AI Studio"
.\scripts\run_app.ps1
```

Claude se detecta automaticamente si el comando `claude` (Claude Code) esta instalado y con sesion iniciada; usa la suscripcion de la persona, por lo que solo funciona en el equipo local, no en Render. Variables opcionales: `LLM_MODEL` (modelo de Gemini), `CLAUDE_MODEL` (modelo de Claude), `CLAUDE_CLI` (ruta del ejecutable) y `CLAUDE_AGENT=0` para desactivarlo. Sin clave ni Claude Code, la aplicacion funciona igual y los botones aparecen desactivados con la indicacion de que falta.

| Metodo y ruta | Accion |
|---|---|
| `GET /api/assist/status` | Modelos disponibles. |
| `POST /api/assist/classify` | Sugerencia de derecho (`request_text`); devuelve un `token` para enviar en `POST /api/requests` como `ai_suggestion_token`. |
| `POST /api/cases/{id}/drafts` | Borrador con IA (`provider`: `gemini` o `claude`, `actor`). |
| `POST /api/cases/{id}/send` | Acepta `draft_source`: `plantilla` o el `draft_id` de un borrador. |

## 1. Abrir el proyecto

```powershell
Set-Location "<ruta donde descomprimio o clono el proyecto>"
```

## 2. Preparar el entorno

Si PowerShell permite ejecutar scripts locales:

```powershell
.\scripts\setup.ps1
```

Si la politica de ejecucion bloquea el script, puede habilitarlo solo para este proceso:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

El script crea `.venv`, comprueba Python y ejecuta las pruebas automatizadas. No instala dependencias externas.

## 3. Ejecutar el menu interactivo

```powershell
.\scripts\run_demo.ps1
```

Tambien puede ejecutarse directamente:

```powershell
.\.venv\Scripts\python.exe .\demo\dsar_simulator.py
```

El menu permite:

- escribir la solicitud como la redactaria el titular (si el asistente de IA esta activo, sugiere el derecho y usted lo confirma o lo cambia);
- elegir acceso, rectificacion, supresion, portabilidad u oposicion;
- un titular ficticio;
- identidad verificada o pendiente;
- una politica temporal ficticia;
- una descripcion libre de la solicitud.

## 4. Ejecutar escenarios rapidos

### Acceso con datos sensibles y de terceros

```powershell
.\scripts\run_demo.ps1 -Scenario access
```

Resultado esperado: `APPROVAL_REQUIRED`, dos registros y campo de tercero retirado.

### Identidad pendiente

```powershell
.\scripts\run_demo.ps1 -Scenario pending
```

Resultado esperado: `IDENTITY_PENDING` y cero registros descubiertos.

### Solicitud de supresion

```powershell
.\scripts\run_demo.ps1 -Scenario erasure
```

Resultado esperado: `APPROVAL_REQUIRED` y accion de supresion marcada como no ejecutada.

## 5. Probar el RAG de forma independiente

Consulta legible:

```powershell
.\scripts\run_rag.ps1 -Query "solicitud de acceso y copia de datos personales"
```

Consulta con salida JSON:

```powershell
.\scripts\run_rag.ps1 -Query "identidad pendiente y bloqueo del descubrimiento" -TopK 3 -Json
```

Cada resultado contiene `source`, `section`, `score`, `chunk_id`, `excerpt` y `sha256`.

Resultado esperado:

- metodo `Busqueda vectorial TF-IDF con similitud coseno`;
- modelo `tfidf-word-ngram-1-2-v1`;
- almacen `rag/vector_store.json`;
- 3 documentos y 14 fragmentos indexados;
- espacio vectorial de 1119 dimensiones;
- resultados ordenados por similitud coseno.

Para reconstruir el indice vectorial despues de modificar las referencias:

```powershell
.\scripts\run_rag.ps1 -Query "gestion de derechos DSAR" -RebuildIndex
```

## 6. Asistente de IA con Gemini (opcional)

El simulador puede usar un modelo de lenguaje para dos tareas acotadas:

- **triaje:** sugiere el derecho a partir del texto libre; la decision final la confirma la persona usuaria;
- **redaccion:** genera `response-draft-ia.md`, un borrador en lenguaje natural que cita los fragmentos del RAG.

El modelo no decide el estado, la verificacion de identidad, la redaccion de terceros ni la aprobacion humana. Solo recibe hechos minimizados del expediente (categorias, nombres de campos, motivos HITL y fragmentos RAG), nunca los valores de los datos personales. El expediente registra proveedor, modelo y huellas SHA-256 de cada prompt y respuesta.

1. Obtenga una clave gratuita en <https://aistudio.google.com> (menu **API keys**). No es necesario configurar facturacion.
2. Definala solo para la sesion de PowerShell; nunca la escriba en el codigo ni la suba a GitHub:

```powershell
$env:GEMINI_API_KEY = "AIza...su clave..."
# Opcional: otro modelo disponible en su cuenta
$env:LLM_MODEL = "gemini-3-flash-preview"
```

3. Ejecute el simulador como siempre:

```powershell
.\scripts\run_demo.ps1
```

Para comprobar solo la conexion:

```powershell
.\.venv\Scripts\python.exe .\llm\dsar_llm.py "quiero que borren todos mis datos"
```

Tambien admite OpenRouter con `$env:LLM_PROVIDER = "openrouter"` y `$env:OPENROUTER_API_KEY`. Si no hay clave, se agota la cuota o el modelo falla, el simulador continua con las reglas deterministas y registra el error en `case-package.json`. Para desactivarlo explicitamente use `.\scripts\run_demo.ps1 -NoAI`.

La capa gratuita de Gemini puede usar los prompts para mejorar sus productos. Por eso el proyecto trabaja solo con datos ficticios y aplica minimizacion antes de enviar cualquier contexto.

## 7. Agente en Claude Code

La carpeta `.claude/skills/dsar-rights/` permite que Claude Code actue como el Agente de Derechos DSAR usando el skill del proyecto. Abra Claude Code en la raiz del proyecto y escriba, por ejemplo:

```text
/dsar-rights Tramita esta solicitud: person-001, identidad verificada, politica LAB-30.
Texto del titular: "quiero saber que datos tienen de mi y para que los usan"
```

El agente clasifica el derecho, genera la solicitud, ejecuta el motor y el validador, consulta el RAG y redacta `response-draft-agente.md` en `simulaciones/<caso>/`. Respeta las mismas invariantes: si la identidad no esta verificada se detiene, y ninguna accion se marca como ejecutada.

Tambien puede tramitarse cualquier solicitud en JSON sin el agente:

```powershell
.\scripts\run_demo.ps1 -Request .\tests\fixtures\request-access.json
```

## 8. Revisar la salida

Cada ejecucion crea una carpeta en `simulaciones/` con:

| Archivo | Contenido |
|---|---|
| `request.json` | Solicitud usada por la simulacion. |
| `case-package.json` | Expediente completo, estados, HITL, contexto RAG, fuentes y auditoria. |
| `response-draft.md` | Borrador legible de respuesta al titular. |
| `response-draft-ia.md` | Borrador redactado por el asistente de IA (solo si esta activo). |

Ejemplo para abrir el ultimo borrador desde PowerShell:

```powershell
Get-ChildItem .\simulaciones -Recurse -Filter response-draft.md |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  ForEach-Object { Invoke-Item $_.FullName }
```

## 9. Ejecutar las pruebas manualmente

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s .\tests -v
```

Resultado esperado:

```text
Ran 59 tests
OK
```

Las pruebas cubren el motor DSAR, la recuperacion vectorial, la persistencia del indice, los escenarios completos y el asistente de IA. Las pruebas del asistente usan un modelo simulado: no consumen cuota ni necesitan clave.

## 10. Validar un expediente generado

Reemplace `<caso>` por el nombre de la carpeta creada:

```powershell
.\.venv\Scripts\python.exe `
  .\skills\dsar-rights\scripts\validate_case.py `
  .\simulaciones\<caso>\case-package.json
```

El resultado correcto es:

```text
VALID: expediente DSAR consistente
```

## 11. Preparar el proyecto para comprimir

Despues de probarlo pueden eliminarse manualmente:

- `.venv`;
- `simulaciones`;
- todas las carpetas `__pycache__`.

No elimine `rag/vector_store.json`, `evidencias`, `skills`, `tests` ni `informe`.

## Advertencia

Use unicamente los datos ficticios incluidos. El RAG recupera contexto documental, pero no determina obligaciones legales. El simulador no autentica personas, no consulta sistemas reales, no envia correos y no ejecuta rectificaciones, supresiones o restricciones. Las fechas configuradas son academicas y no constituyen asesoramiento legal.
