# Guia de ejecucion del simulador DSAR

## Requisitos

- Windows 10/11 con PowerShell, o Linux/macOS con bash.
- Python 3.10 o superior (`python` en Windows, `python3` en Linux/macOS).

El motor, el RAG y el simulador de consola usan solamente la biblioteca estandar de Python. La interfaz web necesita las dependencias de `requirements.txt` (FastAPI, Uvicorn, Jinja2 y python-multipart). No hace falta base de datos ni credenciales: los casos se guardan en archivos JSON.

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
| `tests/` | Pruebas del motor DSAR, del ciclo de vida, del orquestador, de la web, del RAG y de la ejecucion completa. |
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

Las transiciones no permitidas devuelven `409` y las entradas invalidas `422`.

### Despliegue gratuito en Render

El archivo `render.yaml` define un Web Service gratuito:

1. Inicie sesion en <https://render.com> con la cuenta de GitHub.
2. Elija **New > Blueprint** y seleccione este repositorio. Render lee `render.yaml`, que apunta a la rama `VictorDev`.
3. Al terminar el despliegue, Render muestra la URL publica.

En el plan gratuito el disco es efimero: los casos de `data/runtime/` se pierden cuando el servicio se reinicia o se suspende por inactividad. Para la demostracion basta con volver a registrar las solicitudes.

### Integracion futura del LLM

El LLM se integra en una fase posterior. `Orchestrator` ya acepta dos puntos de extension opcionales:

- `classifier(texto) -> request_type`: se usa solo si la solicitud llega sin `request_type`.
- `drafter(expediente) -> markdown`: reemplaza la plantilla determinista al redactar o enviar la respuesta.

Lo que proponga el LLM sigue pasando por el validador y por la aprobacion humana; no puede ejecutar ni enviar nada por si mismo. Otra opcion es que el agente LLM consuma la API REST como cliente.

## 1. Abrir el proyecto

```powershell
Set-Location "C:\UNSA\8SEMESTRE\AUDITORIA\PROYECTO"
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

El menu permite elegir:

- acceso, rectificacion, supresion, portabilidad u oposicion;
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

## 6. Revisar la salida

Cada ejecucion crea una carpeta en `simulaciones/` con:

| Archivo | Contenido |
|---|---|
| `request.json` | Solicitud usada por la simulacion. |
| `case-package.json` | Expediente completo, estados, HITL, contexto RAG, fuentes y auditoria. |
| `response-draft.md` | Borrador legible de respuesta al titular. |

Ejemplo para abrir el ultimo borrador desde PowerShell:

```powershell
Get-ChildItem .\simulaciones -Recurse -Filter response-draft.md |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  ForEach-Object { Invoke-Item $_.FullName }
```

## 7. Ejecutar las pruebas manualmente

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s .\tests -v
```

Resultado esperado:

```text
Ran 33 tests
OK
```

Las pruebas cubren el motor DSAR, la recuperacion vectorial, la persistencia del indice y los escenarios completos.

## 8. Validar un expediente generado

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

## 9. Preparar el proyecto para comprimir

Despues de probarlo pueden eliminarse manualmente:

- `.venv`;
- `simulaciones`;
- todas las carpetas `__pycache__`.

No elimine `rag/vector_store.json`, `evidencias`, `skills`, `tests` ni `informe`.

## Advertencia

Use unicamente los datos ficticios incluidos. El RAG recupera contexto documental, pero no determina obligaciones legales. El simulador no autentica personas, no consulta sistemas reales, no envia correos y no ejecuta rectificaciones, supresiones o restricciones. Las fechas configuradas son academicas y no constituyen asesoramiento legal.
