# Guia de ejecucion del simulador DSAR

## Requisitos

- Windows 10 u 11.
- PowerShell.
- Python 3.10 o superior disponible mediante el comando `python`.

El simulador usa solamente la biblioteca estandar de Python. No necesita internet, base de datos ni credenciales.

El proyecto incorpora un RAG vectorial local basico. Genera embeddings TF-IDF de unigramas y bigramas, los conserva en `rag/vector_store.json`, recupera por similitud coseno y registra los fragmentos con su procedencia y huella SHA-256.

## Componentes principales

| Ruta | Proposito |
|---|---|
| `skills/dsar-rights/` | Definicion, referencias, plantillas y scripts del skill. |
| `rag/dsar_rag.py` | Generacion de embeddings, indice y recuperacion vectorial. |
| `rag/vector_store.json` | Vectores, vocabulario, IDF, metadatos y fragmentos indexados. |
| `demo/dsar_simulator.py` | Simulador interactivo y escenarios preparados. |
| `tests/` | Pruebas del motor DSAR, del RAG y de la ejecucion completa. |
| `evidencias/` | Expedientes de muestra para la entrega academica. |

No es necesario incluir `.venv`, `simulaciones/` ni carpetas `__pycache__` en el archivo comprimido.

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
- espacio vectorial de 996 dimensiones;
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
Ran 11 tests
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
