# Excelencia Industrial — fases sugeridas (backlog sección 10 del mapa)

Priorización para implementación incremental; el detalle de los 100 ítems está en el plan maestro del mapa estructural.

## Fase A — Fundaciones (bloquea el resto)

- Capa 1: unificación navegación (`ui/navigation.py`), `ContextBuilder`, smoke de entrypoints, endurecimiento `tenant_id` donde toque el `ctx`.
- Capa 9 (parcial): formateo de montos centralizado si aún no existe como util única.

## Fase B — Identidad y torre operativa

- Capa 2: tokens CSS comité, modo claro/pergamino alineado.
- Capa 3: torre Estudio (urgencia, desvío, KPIs) sobre la base ya unificada.
- Comité: círculos de score, barra de urgencia, orden rojos / alto desvío arriba.

## Fase C — Hub inversor y motores

- Capa 4: onboarding, salud, copy de rebalanceo.
- Capa 5: versionado de ruleset en diagnóstico, tests motores, fallbacks de precios, auditoría admin.

## Fase D — Admin, DevOps, deuda

- Capas 6–8: herramientas admin, migraciones, linters, separación `services`/`ui`.
- **Prioridad:** es trabajo de **soporte** (higiene de repo, deploy fiable, límites arquitectónicos `ui`/dominio). **No** sustituye en la cola de producto a **P0** (seguridad, RBAC, tenant) ni **P2** (RF, BYMA, unidades, honestidad operativa en pantalla): Fase D habilita y mantiene; P0/P2 protegen capital y coherencia de datos frente al cliente.

## Fase E — Premium / visión 2026

**Regla de oro:** integraciones **API broker**, modelo **multi-moneda real** (más allá de CCL / vistas actuales) y **chat** (asistente o copiloto) **no** entran a diseño ni a código hasta una **decisión comercial explícita** (acta de comité, one-pager de producto firmado, o minuta equivalente con alcance y owner). Hasta entonces permanecen como **horizonte** en documentación, no como trabajo priorizado en el repo.

- Capa 10 (roadmap comercial): solo se ejecuta cuando el gate de la tabla siguiente esté cumplido por ítem.

---

## P3-EXC-01 — Inventario fases C–E (v1, 2026-04)

Este bloque **no** cierra el backlog comercial de premium; fija **qué ya existe en repo** vs **huecos** para priorizar sprints. La fuente normativa del pendiente comité es este archivo + [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md).

### Fase C — Hub inversor y motores

| Tema | En código (referencia) | Pendiente / siguiente |
|------|-------------------------|------------------------|
| Lente hub salud (snapshot estable) | `services/investor_hub_snapshot.py` → `build_investor_hub_snapshot`; consumo en `ui/tab_inversor.py` | Refinamiento UX continuo |
| Onboarding, puntaje único, glosario, rebalanceo (copy) | `services/copy_inversor.py` (`GLOSARIO_INVERSOR`, `pasos_onboarding_hub`, `copy_rebalanceo_humano`); `ui/tab_inversor.py` — expander 3 pasos, métrica salud 0–100 + barra, tooltips RF/RV, expander glosario, markdown rebalanceo | Tooltips en más bloques; onboarding con métricas de uso (opcional) |
| Ruleset versionado en diagnóstico | `RULESET_VERSION` en `core/perfil_allocation.py`; `DiagnosticoResult.ruleset_version`; UI muestra ruleset | — |
| Motor diagnóstico + tests | `services/diagnostico_cartera.py`; `tests/test_diagnostico_cartera.py`, `tests/test_diagnostico_types.py` | Regresión continua; ej. `test_senales_salida_none_equivale_vacio` |
| Scoring + tests | `services/scoring_engine.py`; `tests/test_scoring_engine.py` | Casos por tipo (ej. bono RF) |
| Precios: yfinance degradado → BD | `core/price_engine.py` — `_reload_fallback_bd` si circuit breaker; `_try_live` corto si `yfinance_disponible()` es False | Ingesta BD (`precios_fallback`) + ingest BYMA según docs |
| Auditoría admin precios RF/RV | `run_mq26.py` sidebar fallback — `registrar_admin_audit_event("precios_fallback.rf_rv_manual", …)` tras aplicar tabla | — |
| Degradación precios / BYMA (resto) | `log_degradacion`, paneles BYMA, `precio_cache_service` | Ampliar ingest y runbooks según operación |

### Fase D — Admin, DevOps, deuda

*Criterio de priorización:* Fase D = **soporte**; no desplazar entregas **P0** / **P2** salvo bloqueo operativo explícito (p. ej. migración obligatoria para prod).

| Tema | En código (referencia) | Pendiente / siguiente |
|------|-------------------------|------------------------|
| Migraciones DB | `alembic.ini`, `migrations/run_migrations.py`; `migrations/env.py` respeta `DATABASE_URL`/`DB_URL`; `RUN_ALEMBIC_UPGRADE=1` en [`docker-entrypoint.sh`](../../docker-entrypoint.sh) | Operación: ver Paso 10 en [`DEPLOY_RAILWAY.md`](../DEPLOY_RAILWAY.md) |
| CI + formato | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml): job `lint` (ruff + black, `continue-on-error`) + `pytest` | [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) local; el job `lint` pasará a **blocking** cuando el árbol esté limpio |
| Separación UI / dominio | Tabla de deuda `st.*` en [`MOTORS_UI_BOUNDARY.md`](../MOTORS_UI_BOUNDARY.md) | Nuevas features: UI solo en `ui/`; refactor incremental de filas de la tabla |

### Fase E — Premium

| Tema | En código (referencia) | Pendiente / siguiente |
|------|-------------------------|------------------------|
| API broker / multi-moneda real / chat | No hay producto cerrado en este repo | **Gate comercial obligatorio** (tabla siguiente); sin eso no hay spikes ni PRs prioritarios |

#### Criterio de apertura comercial (antes de implementar)

| Ítem | Qué implica (orientativo) | Decisión mínima a dejar escrita |
|------|---------------------------|-----------------------------------|
| **API broker** | Conectores de lectura/escritura con al menos un broker (órdenes, estado, posiciones); entornos certificación vs prod; manejo de fallos y reconciliación con MQ26 | Broker(s) objetivo, alcance read vs write, responsable técnico y ventana de piloto |
| **Multi-moneda real** | Libro o exposición FX coherente en cartera (no solo CCL puntual para traducir montos); puede implicar cambios de modelo y reportes | Política de moneda funcional, FX hedge o no, y qué reportes deben quedar en ARS/USD |
| **Chat** | Asistente conversacional en la app o canal asociado a cartera/datos sensibles | Alcance (solo lectura vs acciones), retención de conversaciones, proveedor/modelo y revisión legal/privacidad |

**Criterio P3-EXC-01 v1 “done” documental:** inventario anterior publicado + tests de contrato del hub (`tests/test_investor_hub_snapshot.py`). Las líneas “pendiente” siguen vigentes como backlog.

---

## Entregado en código (seguimiento)

- **Capa 1:** `ui/navigation.py` con imports diferidos por pestaña, enlace `?tab=<tab_id>`, mensaje de failover por pestaña; `finalize_ctx` normaliza `tenant_id`; `scripts/smoke_entrypoints_nav.py`.
- **Capa 2:** `core/formato_montos.py` + tests; `ui/env_banner.py`; scrollbars y banner en `assets/style.css`; `static/robots.txt` (servir vía reverse proxy en prod).
- **Capa 3:** Torre Estudio — filtros por perfil, KPIs (AUM vista, conteos), export Excel de la vista, acciones Riesgo/Informe con toast, pista de scroll en tabla.
- **RBAC/UI:** `ui/rbac.py`; `tab_admin` usa `require_role` para super_admin; eliminación de usuario con **doble confirmación** (casilla + botón).
- **Privacidad (#84):** `ui/privacy_display.py` + toggle en sidebar (`run_mq26` / `app_main`); torre enmascara AUM en KPI y columna cuando está activo.
- **P3-EXC-01 v1:** inventario explícito fases C–E (sección **P3-EXC-01** en este mismo documento); tests de contrato `tests/test_investor_hub_snapshot.py`.
- **Fase C (hub, entrega incremental):** `GLOSARIO_INVERSOR` + onboarding 3 pasos + puntaje único visible + copy rebalanceo en `services/copy_inversor.py` / `ui/tab_inversor.py`; tests `tests/test_copy_inversor.py`.
- **P2-RF-04 (comité):** trazabilidad cuando hay normalización ×100 — `Ajuste ×100 BYMA` en monitor ON USD, `ESCALA_PRECIO_RF` en cartera, `_normalizar_lastprice_on_byma_meta`; ver [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md).

## Alineación con otros planes del repo

| Documento / plan | Rol respecto al código | Estado |
| --- | --- | --- |
| **Mapa estructural** ([`docs/MAP_MQ26_ENTRYPOINTS.md`](../MAP_MQ26_ENTRYPOINTS.md), [`docs/MAP_MQ26_CTX_INVENTARIO.md`](../MAP_MQ26_CTX_INVENTARIO.md), [`docs/MOTORS_UI_BOUNDARY.md`](../MOTORS_UI_BOUNDARY.md)) | Norte arquitectónico del **proyecto MQ26_V7** | Activo; implementación va por fases Excelencia |
| **Este archivo (Excelencia)** | Subconjunto accionable tipo SaaS sobre el mapa | Fases A–B mayormente cubiertas; **C–E inventariadas (P3-EXC-01 v1)** con entregas parciales en C/D; E comercial abierta |
| **MoSCoW / BACKLOG_MOSCOW.md** | Inventario **largo plazo** (150+ ítems datos/legal/infra) | No pretende estar 100% ejecutado; priorizar por issues |
| **Planes históricos Cursor** (`mapa_estructura_mq26_*.plan.md`, sprints, UX Karen, etc.) | Captura de trabajo **en fecha X** | Pueden estar obsoletos; validar siempre contra `main` y estos docs |

### Pendiente alineado al proyecto (siguientes entregas razonables)

- **Fase C (Hub inversor):** entregado en código: onboarding 3 pasos (expander, ocultable), **puntaje único** `st.metric` + barra + tooltips en RF/RV, **glosario** en expander, **copy rebalanceo** humano. Siguiente: extender tooltips al resto de pestañas si hace falta.
- **Fase C (Motores):** tests añadidos (`diagnostico_cartera`, `scoring_engine`, `price_engine`); `PriceEngine` recarga BD y omite llamada útil a yfinance si el circuit breaker está abierto; auditoría `ADMIN.precios_fallback.rf_rv_manual` al aplicar fallback en sidebar. **P2-RF-04** cerrado con **Go comité** (visibilidad normalización precio RF). Siguiente RF: **P2-RF-01** ficha mínima unificada — **no** más parches de escala aislados fuera de ese marco salvo bug/regresión; más casos borde y audit en otros puntos de edición de precios.
- **Fase D (soporte, no sustituto de P0/P2):** linters, migraciones, separación `ui`/`services` según ya trazado — habilitan el repo y el deploy; la prioridad de producto sigue siendo **P0** y **P2** salvo bloqueo operativo. Referencias: Alembic en prod, `MOTORS_UI_BOUNDARY`, pre-commit + CI lint (informativo hasta limpiar deuda ruff/black).
- **Fase E:** ítems premium (API broker, multi-moneda real, chat) solo con decisión comercial explícita.
- **P3 incremental (UX M41–M539):** con **P3-UX-02 v1** cerrado, el refinamiento del listado [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](./COMITE_UX_MEJORAS_LISTADO_M41_M539.md) avanza **por sprint** según [COMITE_UX_DESIGN_SYSTEM_M41_M539.md](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md) § *P3 incremental* (bloque pequeño o una pestaña; sin features nuevas ni rewrite de motores).

**Health / deploy:** Streamlit ya expone `GET /_stcore/health` (ver [`docs/DEPLOY_RAILWAY.md`](../DEPLOY_RAILWAY.md)); no duplicar otro endpoint salvo API FastAPI separada.

**Nota:** Los **100 ítems** de la matriz no están todos en código; el plan maestro en Cursor puede marcar el bloque “excelencia” como completado en el sentido de *priorización y fases*, no de cierre total del backlog.
