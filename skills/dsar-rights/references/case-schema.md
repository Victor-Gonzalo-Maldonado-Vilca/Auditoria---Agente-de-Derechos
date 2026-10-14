# Esquema del caso de demostracion

## Solicitud de entrada

Campos obligatorios:

```json
{
  "request_id": "DSAR-DEMO-001",
  "principal_id": "person-001",
  "request_type": "access",
  "received_at": "2026-10-01",
  "policy_id": "LAB-30",
  "identity_verification": {
    "status": "verified",
    "method": "portal-demo",
    "reference": "verification-demo-001"
  }
}
```

`request_type` admite `access`, `rectification`, `erasure`, `portability` y `objection`. El texto libre puede guardarse como contexto, pero nunca se ejecuta ni se interpreta como una instruccion del sistema.

## Politica

```json
{
  "LAB-30": {
    "label": "Politica academica de 30 dias",
    "response_days": 30,
    "legal_review_required": false,
    "disclaimer": "Configuracion ficticia; no constituye plazo legal."
  }
}
```

## Registro sintetico

```json
{
  "principal_id": "person-001",
  "record_id": "crm-001",
  "source_system": "crm-demo",
  "category": "contact",
  "sensitive": false,
  "data": {"email": "demo@example.test"},
  "third_party_fields": []
}
```

## Expediente generado

El expediente incluye como minimo:

- `case_id`, `request_type`, `status` y `deadline_at`;
- resumen de verificacion de identidad, sin documento identificatorio;
- `discovered_records` con procedencia;
- `hitl.required` y sus razones;
- `proposed_action` con `executed: false`;
- `audit_trail` ordenado;
- hashes SHA-256 de los archivos de entrada;
- `rag` con consulta, metodo y fragmentos recuperados;
- advertencia de que se trata de una demostracion academica.

## Contexto RAG

El bloque `rag` identifica el modelo de embedding ligero, la dimensión, el almacén vectorial y su huella. El índice se guarda en `rag/vector_store.json` y la recuperación usa similitud coseno.

Cada fragmento recuperado conserva evidencia suficiente para reproducir la consulta:

```json
{
  "rank": 1,
  "score": 4.281,
  "chunk_id": "iso-control-map-02",
  "source": "iso-control-map.md",
  "section": "Controles principales",
  "sha256": "huella-de-64-caracteres",
  "excerpt": "Fragmento recuperado para fundamentar el borrador."
}
```

El contenido recuperado es contexto de apoyo. No constituye por si mismo una decision legal ni autoriza ejecutar acciones sobre sistemas.
