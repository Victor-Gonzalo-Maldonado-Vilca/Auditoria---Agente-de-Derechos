# Guia de ejecucion del simulador DSAR

## Requisitos

- Windows 10 u 11.
- PowerShell.
- Python 3.10 o superior disponible mediante el comando `python`.

El simulador usa solamente la biblioteca estandar de Python. No necesita base de datos. Sin clave de API funciona sin internet ni credenciales; con una clave de Gemini u OpenRouter activa el asistente de IA opcional (seccion 6).

El proyecto incorpora un RAG vectorial local basico. Genera embeddings TF-IDF de unigramas y bigramas, los conserva en `rag/vector_store.json`, recupera por similitud coseno y registra los fragmentos con su procedencia y huella SHA-256.

## Componentes principales

| Ruta | Proposito |
|---|---|
| `skills/dsar-rights/` | Definicion, referencias, plantillas y scripts del skill. |
| `rag/dsar_rag.py` | Generacion de embeddings, indice y recuperacion vectorial. |
| `rag/vector_store.json` | Vectores, vocabulario, IDF, metadatos y fragmentos indexados. |
| `demo/dsar_simulator.py` | Simulador interactivo y escenarios preparados. |
| `llm/dsar_llm.py` | Asistente de IA opcional (Gemini u OpenRouter) para triaje y redaccion. |
| `.claude/skills/dsar-rights/` | Adaptador del skill para usar el agente dentro de Claude Code. |
| `tests/` | Pruebas del motor DSAR, del RAG y de la ejecucion completa. |
| `evidencias/` | Expedientes de muestra para la entrega academica. |

No es necesario incluir `.venv`, `simulaciones/` ni carpetas `__pycache__` en el archivo comprimido.

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
- espacio vectorial de 996 dimensiones;
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
Ran 19 tests
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
