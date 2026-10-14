# Avance RAG local para el agente DSAR

## Alcance

Este componente implementa un RAG vectorial local para la demostración académica. Recupera contexto desde las referencias mantenidas por el skill DSAR y adjunta los fragmentos seleccionados al expediente. El índice se guarda en `rag/vector_store.json` y no necesita Internet ni un modelo generativo externo.

## Flujo

1. Divide cada documento Markdown por encabezados.
2. Normaliza y tokeniza el contenido.
3. Genera embeddings TF-IDF normalizados de unigramas y bigramas.
4. Persiste los vectores dispersos, vocabulario y metadatos en un almacén JSON.
5. Vectoriza la consulta formada con el derecho y el texto de la solicitud.
6. Calcula similitud coseno y recupera los tres fragmentos más cercanos.
7. Registra fuente, sección, puntuación y SHA-256 de cada fragmento.
8. Inserta las referencias recuperadas en `case-package.json` y en el borrador.

## Corpus

El corpus se toma de `skills/dsar-rights/references/` e incluye el mapa de controles ISO/IEC 27701, el flujo y estados del expediente y el esquema de datos. Los resúmenes del estándar son material elaborado para el proyecto; la norma completa no se copia en el índice.

## Límites

- Los embeddings TF-IDF son ligeros y explicables, pero no capturan semántica profunda como un modelo neuronal.
- El texto recuperado fundamenta el borrador, pero no decide excepciones legales.
- Las referencias se versionan mediante huellas, pero este prototipo no ofrece almacenamiento inmutable.
- La generación permanece determinista y basada en plantilla; integrar un LLM es una evolución posterior.

## Ejecución

```powershell
.\scripts\run_rag.ps1 -Query "solicitud de acceso y copia de datos personales"
```

Para regenerar explícitamente el almacén vectorial:

```powershell
.\scripts\run_rag.ps1 -Query "solicitud de acceso" -RebuildIndex
```

También puede ejecutarse directamente:

```powershell
.\.venv\Scripts\python.exe .\rag\dsar_rag.py --query "identidad pendiente" --top-k 3 --json
```
