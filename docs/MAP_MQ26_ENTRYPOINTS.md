# Entrypoints MQ26 — decisión y divergencias

## Decisión de producto

| Contexto | Entrypoint objetivo | Motivo |
|----------|---------------------|--------|
| **Producción multi-tenant (Railway)** | [`run_mq26.py`](../run_mq26.py) | `check_password("mq26", ...)`, rol `estudio` con torre de clientes, Sentry opcional, `tenant_id` desde configuración. |
| **Operación legacy / compatibilidad** | [`app_main.py`](../app_main.py) | `check_password("app", ...)`, alcance por tenant vía `MQ26_DB_TENANT_ID` y [`core/cliente_scope_ui.py`](../core/cliente_scope_ui.py). |

[`mq26_main.py`](../mq26_main.py) delega en `run_mq26.py`. Cualquier cambio de navegación debe mantenerse alineado vía [`ui/navigation.py`](../ui/navigation.py).

## Mapa rol → pestañas (divergencias explícitas)

### Modo `app` (`app_main.py`, `get_user_role("app")`)

| Rol | Pestañas (orden) | Notas |
|-----|------------------|--------|
| `inversor` | Cartera → Cómo va tu inversión → Mesa de ejecución → Reporte | Cuatro tabs; la cartera y el hub inversor están separados. |
| Otros (`asesor`, `admin`, `super_admin`, etc.) | Cartera & Libro Mayor → Universo → Optimización → Riesgo → Ejecución → Reporte | Seis tabs numerados; **no** existe tab `tab_estudio` en este entrypoint. |

### Modo `mq26` (`run_mq26.py`, `get_user_role("mq26")`)

| Rol | Pestañas (orden) | Notas |
|-----|------------------|--------|
| `inversor` | Solo «Mi Cartera» (`render_tab_inversor`) | Experiencia retail compacta; sin tab Cartera separada. |
| `estudio` | Mis Clientes → Cartera Activa → Informes → Señales de Mercado | Incluye [`ui/tab_estudio.py`](../ui/tab_estudio.py) (torre). |
| `asesor` | Cartera → Señales → Optimizar → Riesgo → Ejecutar → Informe | Seis tabs; banner opcional en [`ui/asesor_suite.py`](../ui/asesor_suite.py). |
| `admin` / `super_admin` | Igual asesor + **Admin** | Séptima pestaña [`ui/tab_admin.py`](../ui/tab_admin.py). |

## Implicación

La divergencia **inversor** (1 tab en `mq26` vs 4 en `app`) es contrato de producto intencional: no unificar cantidad de tabs sin decisión explícita. Sí unificar la **definición** en código (labels + orden + función render) en `ui/navigation.py` para evitar drift.

**Implementación:** `app_main.py` y `run_mq26.py` delegan el armado de pestañas en `render_main_tabs(...)` de `ui/navigation.py` (`app_kind` `app` | `mq26`). No duplicar listas `st.tabs([...])` por rol en esos entrypoints.
