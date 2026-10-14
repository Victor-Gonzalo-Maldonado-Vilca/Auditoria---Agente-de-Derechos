# Sistema de Gestión de Privacidad de la Información (PIMS) Multiagente basado en ISO/IEC 27701:2025

## Índice

1. [Resumen ejecutivo](#resumen-ejecutivo)
2. [ISO/IEC 27701:2025: Fundamentos](#isoiec-277012025-fundamentos)
3. [Arquitectura de referencia PIMS Multiagente](#arquitectura-de-referencia-pims-multiagente)
4. [Los 8 agentes especializados](#los-8-agentes-especializados)
5. [Diseño del bus MCP](#diseño-del-bus-mcp)
6. [Arquitectura todo en la nube con herramientas gratuitas](#arquitectura-todo-en-la-nube-con-herramientas-gratuitas)
7. [Base de datos PII en PostgreSQL](#base-de-datos-pii-en-postgresql)
8. [Integración del toolkit PIMS](#integración-del-toolkit-pims)
9. [Flujos de trabajo multiagente](#flujos-de-trabajo-multiagente)
10. [Plan de implementación en 5 fases](#plan-de-implementación-en-5-fases)
11. [Consideraciones críticas de diseño](#consideraciones-críticas-de-diseño)
12. [Stack tecnológico recomendado](#stack-tecnológico-recomendado)
13. [Conclusión](#conclusión)
14. [Anexos](#anexos)

---

## Resumen ejecutivo

Este documento describe el diseño e implementación de un **Sistema de Gestión de Privacidad de la Información (PIMS) multiagente** basado en la norma **ISO/IEC 27701:2025**. El sistema automatiza los controles del Anexo A, la evaluación de riesgos, la gestión de derechos de los titulares, la respuesta a incidentes y la recopilación de evidencias para auditorías, todo ello sobre una arquitectura completamente en la nube con herramientas gratuitas y una base de datos PostgreSQL para la PII.

La solución combina:

- **8 agentes especializados** orquestados mediante LangGraph/CrewAI.
- **Bus de comunicación MCP** (Model Context Protocol) para conectar agentes con herramientas y datos.
- **PostgreSQL gratuito en Aiven** con enmascaramiento dinámico (PostgreSQL Anonymizer).
- **Toolkit PIMS de código abierto** para gap analysis, DPIA y SoA.
- **Hosting gratuito** en Streamlit Community Cloud, Railway/Render y GitHub Actions.
- **Puertas de aprobación humana (HITL)** en decisiones críticas.

El resultado es un PIMS auditable, trazable y escalable que reduce drásticamente el esfuerzo manual de cumplimiento.

---

## ISO/IEC 27701:2025: Fundamentos

### Cambio clave: de extensión a estándar independiente

La edición 2019 requería obligatoriamente ISO 27001 para certificarse. La versión 2025 es un **sistema de gestión autónomo y certificable por sí mismo**. Cualquier organización puede implementarlo sin necesidad de un SGSI previo.

### Estructura del sistema: Cláusulas 4 a 10

Sigue la Estructura Armonizada ISO y el ciclo PDCA:

| Cláusula | Título | Fase PDCA | Requisitos principales |
|---|---|---|---|
| 4 | Contexto de la organización | Plan | Cuestiones internas/externas, partes interesadas, rol (responsable/encargado), alcance, cambio climático. |
| 5 | Liderazgo | Plan | Compromiso de la alta dirección, política de privacidad, roles y responsabilidades. |
| 6 | Planificación | Plan | Riesgos y oportunidades, evaluación de riesgos de privacidad, tratamiento, objetivos, planificación de cambios. |
| 7 | Apoyo | Do | Recursos, competencia, concienciación, comunicación, información documentada. |
| 8 | Operación | Do | Planificación y control operacional, ejecución de evaluaciones y tratamientos. |
| 9 | Evaluación del desempeño | Check | Seguimiento, medición, auditoría interna, revisión por la dirección. |
| 10 | Mejora | Act | Mejora continua, no conformidades y acciones correctivas. |

### El corazón normativo: Anexo A (Controles)

Reestructurado en tres tablas según el rol:

| Tabla | Aplica a | Nº de Controles | Enfoque principal |
|---|---|---|---|
| A.1 | Responsables (Controllers) | 31 | Base jurídica, consentimiento, derechos, privacidad desde el diseño, transferencias. |
| A.2 | Encargados (Processors) | 18 | Acuerdos con clientes, propósitos, subcontratistas, notificación de brechas. |
| A.3 | Ambos roles | 29 | Políticas de seguridad, control de acceso, incidentes, criptografía, desarrollo seguro. |

Cada control tiene su guía de implementación en el **Anexo B** (normativo).

### Anexos informativos

- **Anexo C:** Mapeo con ISO/IEC 29100.
- **Anexo D:** Mapeo con el RGPD (artículos 5-35 y 44-49).
- **Anexo E:** Mapeo con ISO/IEC 27018 y ISO/IEC 29151.
- **Anexo F:** Correspondencia con ISO/IEC 27701:2019.

### Certificación

La certificación puede ser **independiente o combinada con ISO 27001**. El proceso típico incluye: análisis de brechas, planificación, implementación, auditoría interna y auditoría de certificación en dos etapas.

---

## Arquitectura de referencia PIMS Multiagente

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAPA DE GOBERNANZA                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Orquestador  │  │  Registro de │  │  Panel de Aprobación     │  │
│  │ (Supervisor) │  │  Decisiones  │  │  Humana (HITL)           │  │
│  └──────┬───────┘  └──────────────┘  └──────────────────────────┘  │
└─────────┼───────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────────┐
│                    BUS DE COMUNICACIÓN (MCP)                        │
│         Protocolo estandarizado para conectar agentes               │
│         con herramientas, datos y otros agentes                     │
└─────────┬───────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────────┐
│                      CAPA DE AGENTES ESPECIALIZADOS                 │
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │  Agente de  │ │  Agente de  │ │  Agente de  │ │  Agente de   │  │
│  │  Inventario │ │  Evaluación │ │  Controles  │ │  Evidencia   │  │
│  │  de Datos   │ │  de Riesgos │ │  y SoA      │ │  y Auditoría │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘  │
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │  Agente de  │ │  Agente de  │ │  Agente de  │ │  Agente de   │  │
│  │  Derechos   │ │  Incidentes │ │  Terceros   │ │  Formación   │  │
│  │  (DSAR)     │ │  y Brechas  │ │  (DPAs)     │ │  y Conciencia│  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘  │
└─────────┬───────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────────┐
│                      CAPA DE HERRAMIENTAS (MCP Servers)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  Bases   │ │  APIs de │ │  Sistemas│ │  Almacén │ │  Motores │ │
│  │  de Datos│ │  RRHH    │ │  de Tick │ │  Vectorial│ │  de LLM  │ │
│  │  (PII)   │ │  (HRIS)  │ │  (Jira)  │ │  (RAG)   │ │ (Ollama) │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Componentes clave

| Componente | Función | Tecnología sugerida |
|---|---|---|
| Orquestador | Descompone tareas, asigna agentes, supervisa el flujo | LangGraph, CrewAI o AutoGen |
| Bus MCP | Comunicación estandarizada entre agentes y herramientas | Model Context Protocol |
| Agentes especializados | Ejecutan tareas específicas del PIMS | LLMs locales (Ollama + Qwen/Llama) |
| Memoria compartida | Almacena hallazgos, decisiones y evidencias | Redis + base vectorial (Chroma) |
| Panel HITL | Aprobación humana para acciones críticas | Interfaz web (FastAPI + Streamlit) |

---

## Los 8 agentes especializados

Cada agente se mapea a un conjunto de controles del Anexo A de ISO 27701:2025.

| Agente | Controles ISO 27701:2025 | Herramientas MCP | Entradas | Salidas | Puerta HITL |
|---|---|---|---|---|---|
| **1. Inventario de Datos** | A.1.2.2, A.1.2.9, A.1.5.4 | Escaneo de red, API de metadatos, lector de esquemas PostgreSQL, catálogo de proveedores | Consultas SQL a `information_schema`, logs de aplicaciones, configuraciones | Inventario de actividades de tratamiento (RoPA), mapa de flujos de PII, catálogo de propósitos | Aprobación del DPO para registrar nuevas actividades |
| **2. Evaluación de Riesgos** | A.1.2.6, Cláusula 6.1.2 | Calculadora DPIA (`dpia_risk_scorer.py`), RAG normativo, base de amenazas | Descripción de la actividad, categorías de PII, contexto organizacional | Informe DPIA con puntuación de riesgo, recomendaciones | Revisión y firma del DPO |
| **3. Controles y SoA** | Todos los del Anexo A, Cláusula 6.1.3 | Repositorio de políticas, motor de reglas, tracker SoA (`pims_soa_tracker.py`) | Resultados del DPIA, estado de controles, requisitos legales | Declaración de Aplicabilidad (SoA), plan de tratamiento | Aprobación del CISO/DPO |
| **4. Evidencia y Auditoría** | Cláusula 9.1, 9.2, A.3.14 | APIs de GRC, almacenamiento de evidencias, generador de informes, gap checker (`pims_gap_checker.py`) | Logs, capturas, registros de formación, auditorías previas | Paquete de evidencias por control, informe de brechas | Validación del auditor interno |
| **5. Derechos (DSAR)** | A.1.3.7, A.1.3.9, A.1.3.10 | MCP server DSAR, bases de datos PII, ticketing, generador de respuestas | Solicitudes entrantes, identidad del titular, bases a consultar | Respuesta al titular, registro de solicitud | Aprobación del DPO para datos sensibles |
| **6. Incidentes y Brechas** | A.3.11, A.3.12, A.2.5.5 | SIEM (Wazuh), alertas, canales de notificación, MCP server de incidentes | Alertas de seguridad, logs de acceso, informes de empleados | Clasificación de brecha, registro, notificaciones | Aprobación del DPO para notificar a la autoridad (72h RGPD) |
| **7. Terceros (DPAs)** | A.1.2.7, A.2.5.7, A.2.5.8 | Repositorio de contratos, APIs de proveedores, scoring de riesgo, MCP server de proveedores | Contratos, lista de proveedores, evaluaciones, cambios en subcontratistas | Registro de DPAs, alertas de renovación, evaluación de riesgo | Aprobación legal para nuevos DPAs |
| **8. Formación y Conciencia** | A.3.17, A.3.18 | LMS (Moodle), generador de cuestionarios, notificaciones, registro de asistencia | Plantilla de empleados, roles, resultados previos | Programas de formación, registros, informes | Aprobación del DPO para contenido |

### Descripción detallada

#### 1. Agente de Inventario de Datos
**Propósito:** Descubrir y catalogar todos los sistemas, bases de datos, endpoints y flujos donde se procesa PII, así como los propósitos y bases jurídicas asociadas.

**Herramientas MCP:**
- `query_information_schema`: consulta metadatos de PostgreSQL.
- `scan_network`: escaneo de endpoints (con permisos).
- `read_config`: lectura de archivos de configuración.
- `fetch_vendor_catalog`: API de proveedores.

**Salidas:** Tabla `processing_activities` actualizada, mapa de flujos, catálogo de propósitos.

**HITL:** El DPO debe aprobar la inclusión de nuevas actividades de tratamiento.

#### 2. Agente de Evaluación de Riesgos
**Propósito:** Ejecutar evaluaciones de impacto de privacidad (DPIA) y análisis de riesgos conforme a la Cláusula 6.1.2.

**Herramientas MCP:**
- `run_dpia`: invoca el script `dpia_risk_scorer.py` del toolkit.
- `score_risk`: calcula probabilidad e impacto.
- `suggest_mitigation`: propone controles del Anexo A.

**Salidas:** Informe DPIA con puntuación y recomendaciones, actualización de `processing_activities.dpia_completed`.

**HITL:** El DPO revisa y firma el DPIA antes de su aprobación.

#### 3. Agente de Controles y SoA
**Propósito:** Generar y mantener la Declaración de Aplicabilidad (SoA) y verificar la implementación de los controles del Anexo A.

**Herramientas MCP:**
- `update_soa`: actualiza la tabla `soa_controls`.
- `check_control_status`: consulta estado de implementación.
- `generate_soa_report`: produce informe en PDF/Markdown.

**Salidas:** SoA actualizada, plan de tratamiento de riesgos.

**HITL:** Aprobación del CISO/DPO para la versión final del SoA.

#### 4. Agente de Evidencia y Auditoría
**Propósito:** Recopilar y organizar evidencias de auditoría de forma automática, ejecutar gap analysis y preparar informes.

**Herramientas MCP:**
- `store_evidence`: sube archivos a S3/R2 y registra hash.
- `retrieve_evidence`: recupera evidencias por control.
- `run_gap_checker`: ejecuta `pims_gap_checker.py`.
- `generate_audit_report`: crea el paquete de auditoría.

**Salidas:** Evidencias organizadas por cláusula/control, informe de brechas de madurez.

**HITL:** Validación del auditor interno antes de la auditoría de certificación.

#### 5. Agente de Derechos (DSAR)
**Propósito:** Gestionar solicitudes de acceso, rectificación, supresión, portabilidad y oposición de los titulares de datos.

**Herramientas MCP:**
- `create_request`: registra la solicitud en `dsar_requests`.
- `verify_identity`: valida identidad del titular.
- `fulfill_request`: extrae datos de PostgreSQL (con enmascaramiento si es necesario).
- `track_status`: consulta estado de la solicitud.

**Salidas:** Respuesta al titular, registro completo de la solicitud.

**HITL:** Aprobación del DPO para respuestas con datos sensibles o disputas.

#### 6. Agente de Incidentes y Brechas
**Propósito:** Detectar, clasificar y notificar brechas de privacidad conforme a los controles A.3.11 y A.3.12.

**Herramientas MCP:**
- `classify_breach`: analiza severidad y alcance.
- `notify_authority`: envía notificación a la autoridad de control.
- `notify_principals`: comunica a los titulares afectados.
- `log_incident`: registra en la tabla `incidents`.

**Salidas:** Clasificación de la brecha, registro del incidente, notificaciones.

**HITL:** Aprobación del DPO para notificar a la autoridad (plazo 72h RGPD).

#### 7. Agente de Terceros (DPAs)
**Propósito:** Gestionar contratos con encargados del tratamiento (DPAs), subencargados y evaluaciones de proveedores.

**Herramientas MCP:**
- `list_processors`: lista encargados y subencargados.
- `check_dpa_status`: verifica vigencia y cláusulas.
- `evaluate_vendor`: scoring de riesgo de proveedores.
- `update_contract`: registra cambios contractuales.

**Salidas:** Registro de DPAs vigentes, alertas de renovación, evaluación de riesgo.

**HITL:** Aprobación legal para nuevos DPAs o cambios de subcontratistas.

#### 8. Agente de Formación y Conciencia
**Propósito:** Programar y verificar la concienciación y formación en privacidad (A.3.17) y gestionar acuerdos de confidencialidad (A.3.18).

**Herramientas MCP:**
- `assign_training`: asigna cursos en el LMS.
- `track_completion`: consulta finalización.
- `generate_awareness_report`: crea informes de concienciación.
- `manage_nda`: registra acuerdos de confidencialidad.

**Salidas:** Programas de formación personalizados, registros de finalización, informes.

**HITL:** Aprobación del DPO para el contenido de la formación en privacidad.

---

## Diseño del bus MCP

MCP (Model Context Protocol) es un protocolo abierto creado por Anthropic que estandariza la conexión entre aplicaciones de IA y herramientas/fuentes de datos. Sigue una arquitectura **cliente-host-servidor**.

### Arquitectura del bus MCP

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HOST (Orquestador del PIMS)                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  LangGraph / CrewAI / AutoGen                                          ││
│  │  - Crea y gestiona instancias de clientes MCP                          ││
│  │  - Controla permisos y ciclo de vida de conexiones                     ││
│  │  - Aplica políticas de seguridad y requisitos de consentimiento        ││
│  │  - Coordina la integración con el LLM (Ollama/OpenAI)                  ││
│  │  - Agrega contexto de múltiples servidores                              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│ Cliente MCP 1 │         │ Cliente MCP 2 │         │ Cliente MCP 3 │
│ (1:1 con      │         │ (1:1 con      │         │ (1:1 con      │
│  Server 1)    │         │  Server 2)    │         │  Server 3)    │
└───────┬───────┘         └───────┬───────┘         └───────┬───────┘
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│ Server MCP 1  │         │ Server MCP 2  │         │ Server MCP 3  │
│ PostgreSQL    │         │ DSAR Manager  │         │ Evidence Store│
│ (PII Database)│         │ (Derechos)    │         │ (Evidencias)  │
└───────────────┘         └───────────────┘         └───────────────┘
```

### Servidores MCP necesarios para el PIMS

| Servidor MCP | Propósito | Herramientas expuestas | Tecnología |
|---|---|---|---|
| **MCP PostgreSQL** | Acceso controlado a la base de datos de PII | `query_pii`, `anonymize_record`, `export_consent`, `audit_query` | Python + `psycopg2` + PostgreSQL Anonymizer |
| **MCP DSAR** | Gestión de solicitudes de derechos | `create_request`, `verify_identity`, `fulfill_request`, `track_status` | MCP server open-source para DSAR |
| **MCP Evidencias** | Almacenamiento y recuperación de evidencias | `store_evidence`, `retrieve_evidence`, `generate_audit_report` | S3-compatible + metadatos en PostgreSQL |
| **MCP Riesgos** | Evaluación de riesgos de privacidad | `run_dpia`, `score_risk`, `suggest_mitigation` | Scripts del toolkit + LLM |
| **MCP SoA** | Generación y seguimiento del SoA | `update_soa`, `check_control_status`, `generate_soa_report` | Tracker SoA + PostgreSQL |
| **MCP Terceros** | Gestión de DPAs y subencargados | `list_processors`, `check_dpa_status`, `evaluate_vendor` | APIs de proveedores + DB contratos |
| **MCP Formación** | Gestión de concienciación | `assign_training`, `track_completion`, `generate_awareness_report` | LMS API (Moodle) + PostgreSQL |
| **MCP Incidentes** | Respuesta a brechas de privacidad | `classify_breach`, `notify_authority`, `notify_principals`, `log_incident` | SIEM (Wazuh) + canales de notificación |

### Principios de diseño del bus MCP

1. **Aislamiento estricto**: cada servidor MCP opera de forma independiente y solo recibe el contexto necesario. No puede leer la conversación completa ni ver otros servidores.
2. **Composición modular**: los servidores son altamente componibles; el host puede combinarlos según el flujo.
3. **Negociación de capacidades**: clientes y servidores declaran capacidades soportadas en cada solicitud.
4. **Seguridad por diseño**: el host aplica políticas de seguridad y consentimiento.
5. **Protocolo JSON-RPC**: toda comunicación usa JSON-RPC 2.0 sobre stdio o HTTP streamable.

---

## Arquitectura todo en la nube con herramientas gratuitas

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE APLICACIÓN (GRATUITA)                        │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Streamlit Community Cloud (hosting gratuito de la UI del PIMS)       │  │
│  │  - Panel de control del DPO                                            │  │
│  │  - Visualización del SoA y brechas                                     │  │
│  │  - Aprobaciones HITL                                                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Railway / Render (free tier para el orquestador)                     │  │
│  │  - LangGraph / CrewAI ejecutando los 8 agentes                        │  │
│  │  - Servidores MCP como procesos locales o contenedores                │  │
│  │  - Ollama (LLM local en el servidor o vía API gratuita)               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  GitHub Actions (CI/CD gratuito)                                       │  │
│  │  - Ejecución programada del gap checker                                │  │
│  │  - Generación de informes de evidencia                                 │  │
│  │  - Notificaciones al DPO                                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE DATOS (GRATUITA)                             │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Aiven for PostgreSQL (free tier: 1 CPU, 1GB RAM, 1GB disco)         │  │
│  │  - Base de datos principal de PII                                     │  │
│  │  - PostgreSQL Anonymizer instalado para enmascaramiento dinámico      │  │
│  │  - Tablas: pii_records, consent_log, processing_activities,           │  │
│  │           dsar_requests, incidents, evidence_store, soa_controls      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  ChromaDB (embeddings locales) o Aiven OpenSearch free tier           │  │
│  │  - Base vectorial para RAG normativo (ISO 27701, RGPD, guías)        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  AWS S3 Free Tier (5GB) o Cloudflare R2 (10GB gratis)                │  │
│  │  - Almacenamiento de evidencias de auditoría                          │  │
│  │  - Documentos DPIA, SoA, informes                                     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Opciones gratuitas de PostgreSQL en la nube

| Proveedor | Recursos gratuitos | Ideal para |
|---|---|---|
| **Aiven** | 1 CPU, 1 GB RAM, 1 GB disco, backups diarios | Base de datos principal del PIMS (recomendado) |
| **AWS Aurora PostgreSQL Serverless** | Hasta 4 ACU, 1 GiB almacenamiento por clúster | Prototipos con escalabilidad automática |
| **Supabase** | 500 MB PostgreSQL | Proyectos pequeños con autenticación integrada |
| **Neon** | PostgreSQL serverless con ramificación | Desarrollo y pruebas con entornos efímeros |

---

## Base de datos PII en PostgreSQL

### Esquema completo

```sql
-- Tabla principal de PII (con enmascaramiento dinámico)
CREATE TABLE pii_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL,
    data_category TEXT NOT NULL,  -- 'identificadores', 'financiero', 'salud', etc.
    data_value TEXT,  -- valor real (enmascarado por PostgreSQL Anonymizer)
    purpose TEXT NOT NULL,
    lawful_basis TEXT NOT NULL,
    retention_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Registro de consentimiento
CREATE TABLE consent_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL,
    purpose TEXT NOT NULL,
    consent_given BOOLEAN NOT NULL,
    consent_date TIMESTAMPTZ DEFAULT NOW(),
    withdrawal_date TIMESTAMPTZ,
    mechanism TEXT  -- 'email', 'web', 'api'
);

-- Actividades de tratamiento (RoPA)
CREATE TABLE processing_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    pii_categories TEXT[],
    recipients TEXT[],
    transfers_countries TEXT[],
    dpia_required BOOLEAN DEFAULT FALSE,
    dpia_completed BOOLEAN DEFAULT FALSE,
    soa_controls TEXT[]  -- controles del Anexo A aplicables
);

-- Solicitudes DSAR
CREATE TABLE dsar_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL,
    request_type TEXT NOT NULL,  -- 'access', 'rectification', 'erasure', 'portability'
    status TEXT DEFAULT 'pending',
    received_at TIMESTAMPTZ DEFAULT NOW(),
    deadline_at TIMESTAMPTZ,  -- 30 días según RGPD
    completed_at TIMESTAMPTZ,
    response_data JSONB
);

-- Incidentes de privacidad
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    pii_affected TEXT[],
    principals_affected INTEGER,
    notified_authority BOOLEAN DEFAULT FALSE,
    notified_principals BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Evidencias de auditoría
CREATE TABLE evidence_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    control_ref TEXT NOT NULL,  -- 'A.1.2.2', 'Cláusula 6.1.2', etc.
    evidence_type TEXT NOT NULL,  -- 'policy', 'log', 'screenshot', 'record'
    file_path TEXT,
    hash_sha256 TEXT NOT NULL,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    collected_by TEXT
);

-- SoA (Declaración de Aplicabilidad)
CREATE TABLE soa_controls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    control_ref TEXT UNIQUE NOT NULL,
    control_title TEXT NOT NULL,
    applicable BOOLEAN NOT NULL,
    justification TEXT,
    implemented BOOLEAN DEFAULT FALSE,
    evidence_id UUID REFERENCES evidence_store(id)
);
```

### PostgreSQL Anonymizer

Para cumplir con la minimización y el enmascaramiento dinámico:

```sql
-- Instalar extensión
CREATE EXTENSION IF NOT EXISTS anon CASCADE;

-- Definir reglas de enmascaramiento
SECURITY LABEL FOR anon ON COLUMN pii_records.data_value
  IS 'MASKED WITH FUNCTION anon.fake_email()';

-- Consultas enmascaradas para agentes no privilegiados
SET ROLE agente_dsar;
SELECT * FROM pii_records WHERE principal_id = '...';
-- Los valores se muestran enmascarados automáticamente
```

---

## Integración del toolkit PIMS

El **ISO/IEC 27701:2025 PIMS Toolkit** de Ankit-Uniyal (GitHub) es un conjunto de scripts de automatización GRC de calidad production-ready, sin dependencias externas (solo Python 3.8+).

### Scripts principales

| Script | Función |
|---|---|
| `pims_gap_checker.py` | Evalúa el estado actual frente a los requisitos de ISO 27701:2025 y genera informe de brechas. |
| `dpia_risk_scorer.py` | Calcula la puntuación de riesgo de una DPIA según probabilidad e impacto. |
| `pims_soa_tracker.py` | Gestiona la Declaración de Aplicabilidad, controles aplicables y su implementación. |

### Ejemplo de integración con PostgreSQL

```python
import subprocess
import psycopg2
from datetime import datetime

def run_gap_checker_and_store():
    """Ejecuta el gap checker y almacena los resultados en PostgreSQL."""
    
    # 1. Ejecutar el script del toolkit
    result = subprocess.run(
        ["python3", "iso-27701-pims-toolkit/13-SCRIPTS/pims_gap_checker.py", 
         "--input", "gap_scores.csv", "--output", "gap_report.txt"],
        capture_output=True, text=True
    )
    
    # 2. Parsear el resultado y almacenar en PostgreSQL
    conn = psycopg2.connect(
        "postgresql://user:pass@aiven-postgres-pims:12345/pims_db"
    )
    cursor = conn.cursor()
    
    # Insertar puntuaciones de madurez por cláusula
    cursor.execute("""
        INSERT INTO gap_assessments (clause, score, assessed_at)
        VALUES (%s, %s, %s)
    """, ("6.1", 2, datetime.now()))
    
    # 3. Si el score es bajo, crear una tarea de remediación
    if score < 3:
        cursor.execute("""
            INSERT INTO remediation_tasks (control_ref, description, priority, created_at)
            VALUES (%s, %s, %s, %s)
        """, ("6.1.2", "Implementar evaluación de riesgos de privacidad", "high", datetime.now()))
    
    conn.commit()
    conn.close()
    
    # 4. Subir el informe a S3/R2
    # ...
```

### Flujo completo con PostgreSQL y el toolkit

1. **Agente de Inventario** consulta PostgreSQL vía MCP para descubrir tablas con PII y sus propósitos.
2. **Agente de Riesgos** ejecuta `dpia_risk_scorer.py` con los datos extraídos y almacena el resultado en `processing_activities.dpia_completed`.
3. **Agente de Controles** ejecuta `pims_soa_tracker.py` y actualiza la tabla `soa_controls`.
4. **Agente de Evidencia** ejecuta `pims_gap_checker.py` periódicamente vía GitHub Actions y almacena los informes en S3.
5. **Agente de DSAR** usa el MCP server de PostgreSQL con PostgreSQL Anonymizer para enmascarar datos sensibles antes de responder al titular.
6. **Agente de Incidentes** consulta `pii_records` para determinar qué titulares fueron afectados por una brecha.

---

## Flujos de trabajo multiagente

### Flujo 1: Evaluación de impacto de privacidad (DPIA) automatizada

```
Usuario solicita DPIA
       │
       ▼
┌──────────────┐
│ Orquestador  │ → Descompone la tarea
└──────┬───────┘
       │
       ├──▶ Agente de Inventario: identifica sistemas, PII y propósitos
       │
       ├──▶ Agente de Riesgos: analiza amenazas y vulnerabilidades
       │
       ├──▶ Agente de Controles: verifica controles existentes
       │
       ├──▶ Agente de Evidencia: recopila documentación de soporte
       │
       ▼
┌──────────────┐
│ Panel HITL   │ → DPO revisa y aprueba el DPIA
└──────┬───────┘
       │
       ▼
Informe DPIA firmado y archivado
```

### Flujo 2: Gestión de una brecha de privacidad

```
Alerta de SIEM (acceso no autorizado a PII)
       │
       ▼
┌──────────────┐
│ Orquestador  │ → Activa protocolo de incidentes
└──────┬───────┘
       │
       ├──▶ Agente de Incidentes: clasifica la brecha (gravedad, alcance)
       │
       ├──▶ Agente de Inventario: identifica PII afectada y titulares
       │
       ├──▶ Agente de Terceros: verifica si hay encargados implicados
       │
       ├──▶ Agente de Evidencia: documenta el incidente y las acciones
       │
       ▼
┌──────────────┐
│ Panel HITL   │ → DPO aprueba notificación a autoridad y afectados
└──────┬───────┘
       │
       ▼
Notificación enviada en plazo legal (72h RGPD)
```

### Flujo 3: Gestión de una solicitud DSAR

```
Titular envía solicitud (email/formulario)
       │
       ▼
┌──────────────┐
│ Orquestador  │ → Activa protocolo DSAR
└──────┬───────┘
       │
       ├──▶ Agente de Derechos: registra solicitud y verifica identidad
       │
       ├──▶ Agente de Inventario: localiza PII del titular
       │
       ├──▶ Agente de Derechos: extrae datos (con enmascaramiento si aplica)
       │
       ├──▶ Agente de Evidencia: registra la solicitud y la respuesta
       │
       ▼
┌──────────────┐
│ Panel HITL   │ → DPO aprueba respuesta (si hay datos sensibles)
└──────┬───────┘
       │
       ▼
Respuesta enviada al titular en plazo legal (30 días RGPD)
```

### Flujo 4: Auditoría interna automatizada

```
Inicio de ciclo de auditoría
       │
       ▼
┌──────────────┐
│ Orquestador  │ → Planifica auditoría
└──────┬───────┘
       │
       ├──▶ Agente de Evidencia: recopila evidencias de todos los controles
       │
       ├──▶ Agente de Controles: verifica implementación del SoA
       │
       ├──▶ Agente de Riesgos: revisa DPIA y tratamientos
       │
       ├──▶ Agente de Formación: verifica registros de concienciación
       │
       ▼
┌──────────────┐
│ Panel HITL   │ → Auditor interno revisa y valida el paquete
└──────┬───────┘
       │
       ▼
Informe de auditoría interna listo para certificación
```

---

## Plan de implementación en 5 fases

### Fase 1: Análisis de brechas y preparación (2-4 semanas)

- **Actividad**: Ejecutar el **Agente de Controles** para evaluar el estado actual frente a los requisitos de ISO 27701:2025.
- **Entregable**: Informe de brechas con priorización de acciones.
- **Herramienta**: Toolkit de PIMS con scripts de evaluación automatizada.

### Fase 2: Diseño de la arquitectura multiagente (2-3 semanas)

- **Actividad**: Definir roles de agentes, mapeo a controles y flujos de trabajo.
- **Entregable**: Documento de arquitectura + SoA preliminar.
- **Decisión clave**: ¿Usar un framework de agentes (LangGraph, CrewAI) o una plataforma de orquestación (n8n, Temporal)?

### Fase 3: Desarrollo e integración (2-4 meses)

- **Actividad**: Implementar agentes, conectar herramientas vía MCP y configurar la memoria compartida.
- **Entregable**: Sistema multiagente operativo en entorno de pruebas.
- **Consideración**: Priorizar agentes de alto impacto (Riesgos, Evidencia) y bajo riesgo de automatización.

### Fase 4: Pruebas y validación (1-2 meses)

- **Actividad**: Ejecutar escenarios de prueba (DPIA, DSAR, brecha) y validar con el DPO.
- **Entregable**: Informe de validación + ajustes de configuración.
- **Métrica**: Tasa de acierto en la clasificación de controles y generación de evidencias.

### Fase 5: Auditoría interna y certificación (2-4 semanas)

- **Actividad**: Realizar auditoría interna con el **Agente de Evidencia** y preparar la certificación.
- **Entregable**: Paquete de evidencias listo para el auditor externo.
- **Beneficio**: Reducción de hasta un 80-85% en el esfuerzo de preparación de auditorías.

---

## Consideraciones críticas de diseño

| Desafío | Estrategia de mitigación |
|---|---|
| **Autonomía excesiva** | Implementar puertas de aprobación humana (HITL) para acciones irreversibles: notificaciones de brechas, transferencias internacionales, modificaciones de DPAs. |
| **Propósito limitado** | Cada agente debe operar con un propósito declarado y registrado. Los valores de propósito deben ser evaluables por máquina y registrarse en cada solicitud. |
| **Eliminación de datos** | Definir procesos para localizar y eliminar datos en documentos originales, índices vectoriales, logs de prompts y datos de fine-tuning. |
| **Radio de acción** | Delimitar estrictamente los permisos de cada agente. Un agente con acceso amplio es una superficie de ataque. |
| **Deriva del modelo** | Monitorear el comportamiento de los agentes a lo largo del tiempo; el sistema puede comportarse diferente en el mes 3 que en el día 1. |
| **Trazabilidad** | Registrar cada decisión, herramienta usada y evidencia generada. Los logs deben ser inmutables y auditables. |

---

## Stack tecnológico recomendado

| Capa | Opción open-source | Opción comercial |
|---|---|---|
| **LLM local** | Ollama + Qwen/Llama | Azure OpenAI, AWS Bedrock |
| **Framework de agentes** | LangGraph, CrewAI, AutoGen | — |
| **Bus de comunicación** | MCP (Model Context Protocol) | — |
| **Memoria** | Redis + Chroma/Qdrant | Pinecone, Weaviate |
| **Base de conocimiento (RAG)** | LlamaIndex + documentos normativos | — |
| **Orquestación de flujos** | n8n, Temporal | Zapier, Make |
| **GRC / Evidencias** | Toolkit PIMS (GitHub) | Vanta, Scrut, OneTrust |
| **Panel HITL** | FastAPI + Streamlit | Retool, Appsmith |
| **Base de datos PII** | PostgreSQL (Aiven free tier) + Anonymizer | AWS RDS, Azure Database |
| **Almacenamiento de evidencias** | AWS S3 Free Tier / Cloudflare R2 | Google Cloud Storage |
| **Hosting de agentes** | Railway / Render free tier | AWS ECS, Google Cloud Run |
| **UI del DPO** | Streamlit Community Cloud | Retool, Appsmith |
| **CI/CD** | GitHub Actions | GitLab CI, CircleCI |

---

## Conclusión

Un PIMS multiagente basado en ISO/IEC 27701:2025 combina lo mejor de tres mundos: la **seguridad de ISO 27001**, la **privacidad de ISO 27701** y la **gobernanza de IA de ISO 42001**. La clave del éxito está en:

1. **Mapear cada agente a controles específicos** del Anexo A de la norma.
2. **Mantener el control humano** en decisiones críticas (HITL).
3. **Automatizar la evidencia** para reducir el esfuerzo de auditoría.
4. **Diseñar para la trazabilidad** desde el primer día.
5. **Empezar simple** y escalar según madurez.

La arquitectura propuesta es completamente funcional con herramientas gratuitas, escalable según crezca la organización, y cumple con los requisitos de ISO 27701:2025 al mantener trazabilidad, puertas de aprobación humana y evidencia auditable en cada paso.

---

## Anexos

### Glosario

- **PIMS**: Privacy Information Management System.
- **PII**: Personally Identifiable Information.
- **DPIA**: Data Protection Impact Assessment.
- **DSAR**: Data Subject Access Request.
- **SoA**: Statement of Applicability.
- **MCP**: Model Context Protocol.
- **HITL**: Human-in-the-Loop.
- **RoPA**: Record of Processing Activities.
- **DPA**: Data Processing Agreement.

### Referencias

- ISO/IEC 27701:2025 – Privacy information management systems – Requirements and guidance.
- ISO/IEC 27001 – Information security management systems – Requirements.
- ISO/IEC 27002 – Information security controls.
- ISO/IEC 29100 – Privacy framework.
- ISO/IEC 29134 – Guidelines for privacy impact assessment.
- ISO/IEC 42001 – Information technology – Artificial intelligence – Management system.
- Reglamento General de Protección de Datos (RGPD) – Reglamento (UE) 2016/679.
- Model Context Protocol (MCP) – Especificación oficial de Anthropic.
- ISO/IEC 27701:2025 PIMS Toolkit – Ankit-Uniyal, GitHub.

---

*Documento generado el 1 de octubre de 2026.*