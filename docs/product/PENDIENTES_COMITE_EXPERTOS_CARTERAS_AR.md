# Pendientes — Comité Expertos Carteras AR (inventario maestro)

**Versión:** 1.34 · **Fecha de referencia:** 2026-04-10  
**Skill:** `.cursor/skills/comite-expertos-carteras-ar/SKILL.md`  
**Backlog cerrado histórico:** [`BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md`](./BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md) (P0–P2 allí marcados como entregados)

Este documento consolida **todo lo que quedó pendiente** después de ese cierre: seguridad multi-rol, datos RF/BYMA, observabilidad, UX industrial, excelencia tipo “Abbaco-lite”, y deuda técnica explícita. Sirve como **norte de producto** alineado al comité (capital primero, claridad, trazabilidad, honestidad operativa).

---

## 1. Propósito

- Una sola fuente para **planificar**, **priorizar** y **aceptar** trabajo sin perder el hilo entre chats, planes Cursor y código.
- Cada ítem debe poder evaluarse con el **checklist del comité** (protección de capital, riesgo, UX mínima, trazabilidad, tests, degradación honesta).

---

## 2. Principios de gobierno (recordatorio operativo)

| # | Principio | Implicancia para pendientes |
|---|-----------|------------------------------|
| 1 | Capital primero | Nada que opaque pérdidas, unidades mal definidas o PnL “inflado”. |
| 2 | Riesgo antes que retorno | Métricas de riesgo y escenarios malos visibles antes que promesas de retorno. |
| 3 | Claridad radical | Unidades, fuente de precio y supuestos explícitos en UI y reportes. |
| 4 | Minimalismo funcional | No clonar terminales profesionales completas; entregar **fichas** y **decisiones** acotadas. |
| 5 | Trazabilidad | Scoring, rebalanceo, imports y precios auditables (quién, cuándo, con qué fuente). |
| 6 | Honestidad operativa | Degradar y avisar si falta dato, BYMA caído, o normalización heurística aplicada. |

**Tipografía producto:** Barlow Regular / Semibold / Semi Condensed Extrabold (ver design system).

---

## 3. Estado respecto del backlog canónico

El archivo [`BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md`](./BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md) tiene **P0–P2 completados** (contratos unidad, VaR/CVaR, SSOT, fingerprint imports, auditoría sim/ejec, fuente precio UI, RBAC sensible, logging estructurado, integración roles, UX/tokens, validador docs).

**Lo que sigue** es una **ola posterior**: roles Estudio/Asesor/Admin, RF end-to-end, observabilidad en tabs calientes, diseño industrial M41–M539, y enlaces datos BYMA/BD/prospecto.

---

## 4. Inventario por prioridad (P0 → P3)

### P0 — Seguridad, tenant y control de escritura

| ID | Pendiente | Objetivo | Evidencia / criterio de aceptación |
|----|-----------|----------|-------------------------------------|
| P0-RBAC-01 | Cerrar **todas** las mutaciones en `ui/tab_estudio.py` y `ui/tab_admin.py` con `can_action(ctx, …)` (no solo lectura implícita). | Nadie escribe fuera de política. | **Cerrado:** inventario §4a; Estudio — `_render_wizard_onboarding` y rama sin clientes exigen `can_action(ctx, "write")`; resto ya gateado (confirmar cliente, notas, email, invalidar caché torre). Admin — `_require_panel_admin_write` en Primera Cartera, usuarios BD, Telegram, demo, favoritos (`tab_admin.py`). Tests: `tests/test_rbac_p0_policy.py`. |
| P0-RBAC-02 | Tests de **deny write por rol** (estudio/viewer/asesor según política acordada). | Regresión imposible sin test rojo. | **`tests/test_rbac_p0_policy.py`**: matriz parametrizada desde `ACTION_POLICY` + docstring con tabla; casos explícitos viewer/estudio/asesor y `panel_admin_write`. |
| P0-RBAC-03 | Checklist de aceptación **P0 Done** publicado (una página): “sin bypass RBAC, sin brechas tenant, auth degradada fail-closed”. | Cierre formal de ola seguridad. | **[`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md)** — criterios 1.x–3.x; tenant exhaustivo pendiente **P0-TNT-01**. |
| P0-TNT-01 | Revisión puntual de **tenant_id** en cualquier API/DB que aún no pase por `db_manager` endurecido. | IDOR y cruces de tenant imposibles. | **`core/db_manager.py`**: `_cliente_pertenece_tenant`, SQL fallback con filtro tenant, `actualizar_cliente`/`delete_app_usuario` endurecidos; UI/sync; **`tests/test_tenant_p0_tnt01.py`**. Checklist v1.1 en [`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md). |

*Nota:* Parte de tenant en notas/usuarios ya se endureció en código; P0 es **cierre exhaustivo** y **pruebas de negación**.

**P0-RBAC-01 — Estado:** **cerrado** (2026-04-10): cierre wizard sin permiso + revisión inventario §4a.

**P0-RBAC-02 — Estado:** evidencia en CI vía `tests/test_rbac_p0_policy.py` (32 tests); matriz ASCII en docstring del módulo.

**P0-RBAC-03 — Estado:** checklist publicado en [`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md) (RBAC, auth y tenant §2).

**P0-TNT-01 — Estado:** cerrado en código + tests; checklist seguridad **v1.1** (§2 tenant).

#### Inventario mutaciones P0-RBAC-01 (tab Estudio / Admin)

| Área | Archivo | Acción / botón | Gate |
|------|---------|----------------|------|
| Estudio | `ui/tab_estudio.py` | Confirmar y crear cliente (wizard) | `can_action(ctx, "write")` |
| Estudio | `ui/tab_estudio.py` | Nuevo cliente (inicia wizard) | `can_action(ctx, "write")` |
| Estudio | `ui/tab_estudio.py` | Guardar notas asesor | `can_action(ctx, "write")` |
| Estudio | `ui/tab_estudio.py` | Enviar informe por email | `can_action(ctx, "write")` |
| Estudio | `ui/tab_estudio.py` | Invalidar caché torre | `can_action(ctx, "write")` |
| Admin | `ui/tab_admin.py` | Primera Cartera: generar / re-guardar / persistir BD | `_require_panel_admin_write` → `panel_admin_write` |
| Admin | `ui/tab_admin.py` | Usuarios BD: crear / eliminar / guardar vínculos | idem |
| Admin | `ui/tab_admin.py` | Telegram prueba, regenerar demo, guardar favoritos mes | idem |

Política en `ui/rbac.py`: acción **`write`** incluye roles `estudio`, `asesor`, `admin`, `super_admin`; acción **`panel_admin_write`** solo `super_admin` (panel ya restringido por rol en UI).

---

### P1 — Estabilidad, navegación única, observabilidad, admin auditable

| ID | Pendiente | Objetivo | Evidencia / criterio de aceptación |
|----|-----------|----------|-------------------------------------|
| P1-NAV-01 | **Navegación SSOT** en entrypoints (`run_mq26.py`, `app_main.py`): misma fuente de tabs/rutas que `ui/navigation.py` donde corresponda. | Una sola verdad de navegación. | **`run_mq26.py`:** `render_main_tabs(ctx, app_kind="mq26", role=_mq26_role)`; **`app_main.py`:** `render_main_tabs` con `app_kind="app"`. Tests: `tests/test_entrypoints_roles_integration.py` (`test_run_mq26_usa_render_main_tabs_ssot_p1_nav01`). Doc: [`docs/MAP_MQ26_ENTRYPOINTS.md`](../MAP_MQ26_ENTRYPOINTS.md) §Implicación. |
| P1-OBS-01 | Sustituir silencios críticos por `log_degradacion` / warning estructurado en: `ui/tab_optimizacion.py`, `ui/tab_riesgo.py`, `ui/tab_universo.py`, `run_mq26.py` (puntos acordados). | Incidentes diagnosticables. | **`core/structured_logging.log_degradacion`** en Lab Quant (modelos / BL / snapshots), riesgo (CCL proxy VaR, exposición factorial), universo (S&P panel, ON USD, historial MOD-23, CAFCI→fallback), `run_mq26` (universo_service, tokens reporte, clientes cache, circuit breaker, log context, alertas precio manual, monitor alertas sidebar, CCL hist sidebar, objetivos, PriceEngine, vencimientos/MOD-23 en FlowManager). Tests: **`tests/test_observabilidad.py`** (`test_p1_obs01_archivos_tienen_eventos_log_degradacion`, `test_log_degradacion_no_lanza`). |
| P1-OBS-02 | Test dedicado observabilidad (`tests/test_observabilidad.py` o similar) donde tenga sentido (mock de fallos). | No regresar a `except: pass`. | **`tests/test_observabilidad.py`:** clases `TestP1Obs02LogDegradacionMocks` (`get_logger` mockeado → `exc_info` / payload) y `TestP1Obs02BuildCclSeriesMock` (callback que lanza → `log_degradacion`; casos sin excepción → sin log). CI verde con suite. |
| P1-ADM-01 | Admin **auditable**: confirmaciones en acciones sensibles, auditoría de cambios (quién/qué/cuándo), **no** secretos en claro en UI/session logs. | Confianza institucional. | **`core/db_manager.py`:** `registrar_admin_audit_event` + `_sanitizar_detalle_auditoria_admin` (claves con password/token/hash/… → `[REDACTED]`); filtro `list_global_param_audit(..., param_prefix=ADMIN.)`. **`ui/tab_admin.py`:** checkbox de confirmación antes de alta usuario BD, guardar vínculos, persistir Primera Cartera en BD, eliminar usuario, regenerar demo, Telegram prueba, favoritos del mes; auditoría tras éxito (crear/borrar/vínculos usuario, primera cartera preview/nota/persist, demo, Telegram longitud mensaje, growth favoritos); copy Telegram sin nombrar secretos en claro. Tests: **`tests/test_db_manager.py`** (`test_p1_adm01_*`). |

---

### P2 — Renta fija, BYMA, unidades en toda la salida operativa

| ID | Pendiente | Objetivo | Evidencia / criterio de aceptación |
|----|-----------|----------|-------------------------------------|
| P2-RF-01 | **Ficha RF mínima unificada** por ticker (TIR ref/actual con fuente, paridad, vencimiento, cupón, unidad “ARS por 1 VN”, disclaimer). | Misma decisión que Abbaco “General” pero minimalista. | **Cerrado:** código (PR 1–5) + documentación **§10** en [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) (TIR ref. vs TIR al precio; PR 6). |
| P2-RF-02 | **Cashflow ilustrativo** (base 100 VN, moneda emisión) desde metadatos + calendario aproximado; **no** presentarlo como calendario legal sin prospecto. | Educar sin false precisión. | **Cerrado — alcance acotado:** entrega **solo** cashflow ilustrativo + **copy legal** (disclaimers); **no** sustituye la ficha RF completa (**P2-RF-01**). **`core/renta_fija_ar.py`:** `DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF`, `fecha_vencimiento_desde_meta`, `cashflow_ilustrativo_por_100_vn`. **`ui/monitor_on_usd.py`:** bloque selector ON USD + tabla. Tests: **`tests/test_renta_fija_ar.py`** (`TestCashflowIlustrativoP2Rf02`). |
| P2-RF-03 | **Coherencia unidades RF** en ejecución, reportes y exports: etiqueta explícita de unidad operativa; **guardrail** antes de confirmar órdenes si unidad inconsistente. | Cero “manzanas con peras”. | **Cerrado:** `core/unit_contracts.py` (heurística 100× vs `PPC_ARS` alineada a cartera); `ui/tab_ejecucion.py` (inyección y rebalanceo bloquean órdenes RF USD inconsistentes; export broker con **Unidad operativa** y mapeo `nominales`→Cantidad); tests `tests/test_unit_contracts_rf_ejecucion.py`. |
| P2-RF-04 | **Trazabilidad en UI** cuando se aplica normalización heurística (BYMA ×100 o ajuste ÷100 vs PPC en posición RF USD). | Honestidad operativa. | **Go comité (2026-04-10). Cerrado v1:** `escala_div100` en `enriquecer_on_desde_byma` → columna **Ajuste ×100 BYMA** en `monitor_on_usd_panel_df` + banner en `ui/monitor_on_usd.py`; columna **ESCALA_PRECIO_RF** + banner en `ui/tab_cartera.py`; `_normalizar_lastprice_on_byma_meta` en `byma_market_data`. Tests: `test_monitor_df_marca_ajuste_x100_*`, `test_normaliza_meta_indica_div100`, assert en `test_calcular_posicion_neta_on_usd_normaliza_precio_100x_con_hist`. |
| P2-BYMA-01 | Documentar y, si aplica, alinear con **documentación comercial BYMA** (ej. enlaces tipo `byma.com.ar/download/...`) **campos y escalas** vs Open Data. | Contrato de datos firmado con proveedor. | **Cerrado:** [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) — tablas campo JSON ↔ UI/MQ26, endpoints Open Data, heurísticas ON (÷100), REST `MQ26_BYMA_API_URL`, enlaces oficiales BYMA/BYMADATA/API portal; referencias en ADR-002 y `SOURCES.md`. |
| P2-BYMA-02 | Pipeline opcional: precios desde **BD propia** (`DATABASE_URL`) con reglas de escala **idénticas** a brokers (÷100 cuando corresponda). | Una sola verdad operativa en prod. | **Cerrado:** [`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md); `services/precios_mercado_ingest.py`; `normalizar_precio_ars_on_usd_desde_feed_o_broker` en `byma_market_data`; tests `tests/test_precios_mercado_ingest.py`; §8 en [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md). |
| P2-RF-05 | Enriquecer catálogo `INSTRUMENTOS_RF` con **ISIN**, **denominación mínima**, **forma amortización** cuando exista fuente estable (manual o ETL). | Mejor ficha y menos errores de lámina. | **Cerrado:** `core/renta_fija_ar.py` — `isin` / `lamina_min` / `denominacion_min` / `forma_amortizacion`; helpers `ficha_rf_*`; merge `_EXTRAS_CATALOGO_P2_RF5` (ISIN público AL30/GD30; textos prospecto); consumo vía **P2-RF-01** (`ficha_rf_minima_bundle` / `render_ficha_rf_minima`); tests `TestP2Rf05FichaCatalogo` en `tests/test_renta_fija_ar.py`. |

**Alcance P2 (recordatorio):** **P2-RF-02** cerró únicamente **cashflow ilustrativo + texto legal**. **P2-RF-01** está **implementada en código** (monitor, cartera, inversor); opcional **PR 6** documental. **P2-RF-04** (visibilidad ×100) **cerrado con Go comité**. **No** priorizar **parches de escala sueltos** fuera del marco de la ficha salvo **bug o regresión** demostrable.

#### P2-RF-01 — Plan de implementación (orden de PR)

Mismo criterio de salida que la fila **P2-RF-01** en la tabla §4: **un solo bloque** por ticker con TIR ref / TIR al precio (cuando aplique `tir_al_precio`), paridad, vencimiento, cupón, unidad **ARS por 1 VN** (o equivalente explícito), fuente de precio, traza de escala si aplica, disclaimers; **reutilizable** en pantallas; tests de unidades.

| PR | Alcance por archivo | Qué cerrar en el merge |
|----|---------------------|-------------------------|
| **1** | **`core/renta_fija_ar.py`** — API estable de dominio: p. ej. `ficha_rf_minima_bundle(ticker, meta, *, precio_mercado_ars, paridad_pct, fuente_precio, flags_escala, byma_row_meta)` → `dict`/`TypedDict` serializable a tests (campos: ISIN, denominación mín., forma amortización, vencimiento, frecuencia/cupón, `tir_ref`, `tir_al_precio` o `None` con motivo, unidad precio, línea texto para **ajuste ×100** / sin duplicar lógica de `byma_market_data`). Reutilizar **`ficha_rf_*`**, **`fecha_vencimiento_desde_meta`**, **`tir_al_precio`**, **`cashflow_ilustrativo_por_100_vn`** (solo referencia / resumen en el bundle, no reimplementar). **`tests/test_renta_fija_ar.py`** — `TestP2Rf01FichaMinima`: meta mínimo, con/sin precio, sin `tir_ref`, coherencia de strings. | Dominio + contrato listo para UI sin tocar Streamlit. |
| **2** | **`ui/components/ficha_rf_minima.py`** (nuevo) + **`ui/components/__init__.py`** — `render_ficha_rf_minima(bundle, *, mostrar_cashflow_expander: bool = True, key_prefix: str)` usando solo el bundle; cashflow ilustrativo **dentro** del mismo expander (contenido ya definido en P2-RF-02). Tipografía vía CSS existente (Barlow). | Un solo punto de render; sin lógica de negocio fuera de `core`. |
| **3** | **`ui/monitor_on_usd.py`** — Sustituir el bloque disperso (selectbox + 3 columnas ISIN/denominación/forma + tabla cashflow **separada** del panel §“Cashflow ilustrativo”) por **una** experiencia: selector de ticker alineado al panel BYMA + **`render_ficha_rf_minima`** alimentado con `byma_live` + fila del `monitor_on_usd_panel_df` para ese ticker (paridad, fuente, **Ajuste ×100 BYMA**). Mantener banner P2-RF-04 existente. **`tests/test_monitor_on_usd.py`** — ajustar o añadir aserciones si cambian keys/textos críticos. | Monitor ON USD = primera pantalla “canónica” de la ficha. |
| **4** | **`ui/tab_cartera.py`** — Para filas RF (o subconjunto ON USD si se acota v1): expander o panel lateral **`render_ficha_rf_minima`** con bundle construido desde posición + columnas **`ESCALA_PRECIO_RF`** / precio ya mostrados en tabla. Evitar duplicar copy de P2-RF-04: **referenciar** columna/banner ya presentes. | Ficha visible donde el asesor mira posiciones. |
| **5** | **`ui/tab_inversor.py`** — Reemplazar la tabla plana P2-RF-05 (solo ISIN / denom / forma) por la **misma** ficha unificada por ticker distinto en cartera (o tabla compacta + detalle expander por fila según UX); reutilizar `get_meta` + precios de agregado si existen en `df_ag`. | Inversor alineado al monitor/cartera sin tercer diseño. |
| **6** | **`docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`** — **§10** *Semántica ficha RF (P2-RF-01): TIR de referencia vs TIR al precio*; versión doc **1.1**. | **Entregado:** desambiguación TIR ref. / paridad ref. / TIR al precio (`tir_al_precio`) y orígenes por pantalla. |

**Estado PR 1:** **entregado en código** — `ficha_rf_minima_bundle` en `core/renta_fija_ar.py`; tests `TestP2Rf01FichaMinima` en `tests/test_renta_fija_ar.py`.

**Estado PR 2:** **entregado en código** — `render_ficha_rf_minima` en `ui/components/ficha_rf_minima.py`; export en `ui/components/__init__.py`.

**Estado PR 3:** **entregado en código** — `ui/monitor_on_usd.py`: selector alineado a `monitor_on_usd_panel_df` + `ficha_rf_minima_bundle` + `render_ficha_rf_minima` (reemplaza bloque disperso cashflow/ISIN). Tests `tests/test_monitor_on_usd.py` en verde.

**Estado PR 4:** **entregado en código** — `ui/tab_cartera.py`: expander **Ficha RF** con filas RF (`es_fila_renta_fija_ar`), `_paridad_implicita_pct_on_usd_desde_fila` (ON/BONO USD), bundle + `render_ficha_rf_minima`; tests `tests/test_tab_cartera_ficha_rf.py`.

**Estado PR 5:** **entregado en código** — `ui/tab_inversor.py` (`_render_panel_rf_kpis`): tabla plana P2-RF-05 sustituida por selector + `ficha_rf_minima_bundle` (BYMA `cached_on_byma` + fila `df_ag` + `_paridad_implicita_pct_on_usd_desde_fila`).

**Estado PR 6:** **entregado** — [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) **v1.1**, §10 semántica TIR ficha. **P2-RF-01** cerrado en código y documentación de producto vinculada a BYMA.

**Reglas de secuencia (obligatorias)**

| Regla | Detalle |
|--------|---------|
| **Orden** | PR **1 → 2 → 3 → 4 → 5 → 6**. No adelantar merges a `main` saltando números salvo excepción acordada y riesgo explícito. |
| **Gate PR 1 → UI** | **No** abrir PR que toque **`ui/`** (PR **2** en adelante) sin **tests verdes** del dominio del PR 1: como mínimo `pytest tests/test_renta_fija_ar.py` pasando (incl. clase **`TestP2Rf01FichaMinima`** cuando exista) sobre la base donde ya esté mergeado **`ficha_rf_minima_bundle`** (o nombre final equivalente). |
| **Criterio de merge por PR** | Cumplir la columna **«Qué cerrar en el merge»** de la tabla anterior; CI / pytest del repo en verde para archivos tocados en ese PR. |

**Inspiración Abbaco (sin clonar):** sensibilidad bp (precio↔TIR) **solo rol asesor/estudio**, plan pago, disclaimers fuertes — ver decisión comité previa.

---

### P3 — Excelencia industrial UX / diseño / premium

| ID | Pendiente | Objetivo | Referencia en repo |
|----|-----------|----------|---------------------|
| P3-UX-01 | Cierre **responsive homogéneo** (`dataframe_auto_height`, sin alturas fijas innecesarias) en tabs pendientes: `tab_riesgo`, `tab_optimizacion`, `tab_admin`. | Lectura notebook + desktop. | **Cerrado:** `ui/mq26_ux.py` (`dataframe_auto_height`, soporte Styler); `height=` en `st.dataframe` de `ui/tab_riesgo.py`, `ui/tab_optimizacion.py`, `ui/tab_admin.py`; tests `tests/test_mq26_ux_dataframe_height.py`. |
| P3-UX-02 | **Design system M41–M539** (cierre **v1**): tokens `:root` + breakpoints + paridad tipografía tema claro; componentes CSS para semáforo/hero/defensivo; `plotly_chart_layout_base` con Barlow y color de eje según `mq_light_mode`; métricas HTML con `var(--text-xs)` en labels. | Coherencia visual institucional; el listado M41–M539 sigue **incremental** por sprint (sin mega-PR). | **Cerrado v1:** `assets/style.css`, `assets/style_retail_light.css`, `ui/mq26_ux.py`; tests `tests/test_mq26_ux_design_system.py`. Seguimiento P3: § **P3 incremental** en [`COMITE_UX_DESIGN_SYSTEM_M41_M539.md`](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md) + anexo [`COMITE_UX_MEJORAS_LISTADO_M41_M539.md`](./COMITE_UX_MEJORAS_LISTADO_M41_M539.md). |
| P3-EXC-01 | Fases **C–E** de excelencia industrial (hub inversor, motores, DevOps, premium). | Roadmap trazado y **parcialmente cubierto** en código; **Fase E (premium)** solo tras gate comercial. | **Cerrado v1:** inventario § P3-EXC-01 en [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md); tests `tests/test_investor_hub_snapshot.py`. **Fase E:** API broker, multi-moneda real y chat — ver sección *Fase E* y tabla *Criterio de apertura comercial* en el mismo doc; sin decisión explícita no se prioriza ingeniería. |
| P3-QA-01 | **Pytest completo** + revisión visual oscuro/claro antes de release mayor. | Regresión controlada. | **Cerrado v1:** [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md); CI documentada (paso nombrado en `.github/workflows/ci.yml`); `pytest>=7.4.0` explícito en `requirements.txt`. |

---

## 5. Pendientes por rol

### Estudio
- Gates de escritura en todas las acciones de clientes/notas/importaciones que correspondan.
- Torre operativa: mantener KPIs sin filtrar riesgo (concentración, RF mal valuada degradada).

### Asesor
- Flujos de cartera con **fuente de precio** visible y RF con unidad explícita.
- (Opcional P2) mini sensibilidad RF con disclaimers.

### Admin
- Tablero incidentes ya iniciado: extender con señales de **normalización de precio** y **BYMA caído**.
- Auditoría de acciones administrativas (P1-ADM-01).

### Inversor
- Copy simple: qué es paridad, qué es nominal, qué significa “último operado”.
- Sin sensibilidad avanzada salvo producto explícito “educativo”.

---

## 6. Pendientes por dominio técnico

| Dominio | Qué falta típicamente |
|---------|------------------------|
| **Auth/RBAC** | Matriz completa rol × acción; tests deny. |
| **Multi-tenant** | Barrido final de lecturas/escrituras fuera de `db_manager`. |
| **Precios** | Unificar semántica: Open Data, REST `MQ26_BYMA_API_URL`, catálogo, transaccional; flags en UI. |
| **Motor RF** | **P2-RF-01/02/03 cerrados** (ficha unificada, cashflow ilustrativo, guardrail órdenes). Seguimiento: nuevos puntos de precio/imports con misma trazabilidad; §8 riesgos residuales escala. |
| **Observabilidad** | Silencios críticos → logs estructurados; tests. |
| **CI/CD** | Cobertura mínima en módulos tocados; evitar `--no-cov` como hábito en release. |
| **Documentación** | BYMA campo↔MQ26: [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md); ingesta BD: [`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md); runbook “precio RF raro”. |

---

## 7. Fuentes de datos (estado mental del comité)

| Fuente | Uso actual en código | Pendiente de gobierno |
|--------|----------------------|-------------------------|
| **BYMA Open Data** (`open.bymadata.com.ar`) | Listas mercado + ON live (`services/byma_market_data.py`) | Documento legal/técnico BYMA (ej. downloads del sitio) vs implementación; versionar cambios de API. |
| **REST BYMA/tercero** (`MQ26_BYMA_API_URL`) | Batch cotizaciones (`services/byma_provider.py`) | Contrato respuesta; mapeo RF igual que Open Data. |
| **Catálogo** `core/renta_fija_ar.py` | Fallback paridad / metadatos | ISIN, lámina, amortización, fechas ref actualizables. |
| **Transaccional / SSOT** | Costos, relleno precios | Reglas PPC paridad vs ARS documentadas para importadores. |

---

## 8. Deuda técnica y riesgos residuales (conocidos)

- **Heurísticas de escala** (BYMA ×100, corrección 100× posición RF): correctas para casos típicos; riesgo residual en tickers extremos → UI muestra ajuste cuando aplica (**P2-RF-04** cerrado) + logs.
- **Tests que dependen de red** (ej. advisory ON): pueden colgar CI; aislar con `monkeypatch` o marcar `network`.
- **Backlog histórico** marcaba P2 UX “consolidado”; el **design system M41–M539** sigue siendo trabajo sustantivo si se persigue excelencia visual completa.

---

## 9. Criterios de Done (ola actual)

**P0 Done**
- [x] Ninguna acción de escritura en Estudio/Admin sin `can_action` acorde (ver inventario §4a).
- [x] Tests deny por rol en verde (`tests/test_rbac_p0_policy.py`).
- [x] Checklist seguridad publicado: [`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md) (incluye cierre tenant P0-TNT-01 en §2).

**P1 Done**
- [x] Navegación SSOT verificada en smoke entrypoints (P1-NAV-01: `render_main_tabs` en `run_mq26` + test de fuente).
- [x] Tabs críticos sin silencios en puntos acordados; degradaciones vía `log_degradacion` (P1-OBS-01 + tests en `test_observabilidad.py`).
- [x] Observabilidad con **mocks de fallo** (P1-OBS-02: `TestP1Obs02*` en `test_observabilidad.py`).
- [x] Admin: confirmaciones + auditoría `ADMIN.*` + redacción de secretos en persistencia (P1-ADM-01).

**P2 Done**
- [x] **P2-RF-01** — Ficha RF mínima **unificada** (código + **§10** en [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md)).
- [x] **P2-RF-04** — Trazabilidad en UI cuando hay normalización heurística de precio/escala (monitor ON USD + tabla cartera).
- [x] **P2-RF-02** — Solo cashflow ilustrativo + copy legal (`cashflow_ilustrativo_por_100_vn` + monitor ON USD + tests); **no** cuenta como ficha completa.
- [x] **P2-RF-03** — Guardrail pre-orden RF + unidad explícita en exports de ejecución (`unit_contracts` + `tab_ejecucion`).
- [x] **P2-BYMA-01** — Documento campo BYMA ↔ MQ26 ([`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md)).
- [x] **P2-BYMA-02** — Ingesta `precios_fallback` con escala RF ([`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md), `precios_mercado_ingest.py`).
- [x] **P2-RF-05** — Catálogo RF: ISIN / denominación mínima / forma amortización (`ficha_rf_*`, UI monitor + inversor).

---

## 10. Orden de ejecución sugerido (checklist)

1. P0-RBAC-01 → P0-RBAC-02 → P0-RBAC-03  
2. P0-TNT-01 (barrido tenant)  
3. P1-NAV-01  
4. P1-OBS-01 → P1-OBS-02  
5. P1-ADM-01  
6. **P2-RF-04** — **cerrado + Go comité** (visibilidad normalizaciones); encaja con **P2-RF-01** (ficha unificada)  
7. **P2-RF-01** (ficha RF mínima unificada) — **siguiente foco RF**; **P2-RF-02** ya cerrado (solo cashflow + legal); **P2-RF-03** cerrado v1.11; sin nuevos parches de escala aislados fuera de este ítem salvo bug/regresión  
8. **P2-BYMA-01** y **P2-BYMA-02** cerrados (docs producto + ingest BD); pipeline ETL en prod según necesidad  
9. **P3-UX-01** y **P3-UX-02 v1** cerrados → refinamiento visual por bloques del listado M41–M539 (fuera del alcance de un solo ítem)  
10. **P3-EXC-01 v1** (inventario C–E + tests hub) cerrado; ejecutar filas “pendiente” de [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md) por sprint  
11. **P3-QA-01 v1** — seguir [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) antes de cada tag de release mayor

**Traducción a sprints y orden hacia convergencia de lanzamiento:** [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) (sección *Lista de sprints hacia el lanzamiento*: gate P0–P2, sprints de fundación condicionales, columna *Hacia mercado* 1–5 cuando §9 está verde). Mantener alineado con esta lista al cambiar prioridades globales.

---

## 11. Referencias cruzadas

| Documento | Uso |
|-----------|-----|
| [`BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md`](./BACKLOG_COMITE_EXPERTOS_CARTERAS_AR.md) | Histórico P0–P2 cerrado |
| [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md) | Fases C–E y mapa |
| [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) | QA release (pytest + visual claro/oscuro) |
| [`COMITE_UX_DESIGN_SYSTEM_M41_M539.md`](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md) | Tokens y UI |
| [`COMITE_UX_MEJORAS_LISTADO_M41_M539.md`](./COMITE_UX_MEJORAS_LISTADO_M41_M539.md) | Listado ejecutable UX |
| [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) | Open Data / REST BYMA: campos y escalas en MQ26 |
| [`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md) | Ingesta ETL → `precios_fallback` con escala ON USD |
| [`docs/MAP_MQ26_ENTRYPOINTS.md`](../MAP_MQ26_ENTRYPOINTS.md) | Entrypoints |
| [`docs/RUNBOOK_INCIDENTES_DEGRADACIONES.md`](../RUNBOOK_INCIDENTES_DEGRADACIONES.md) | Operación incidentes |
| [`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md) | Aceptación P0 RBAC / auth / tenant (parcial hasta TNT-01) |
| Skill comité | `.cursor/skills/comite-expertos-carteras-ar/SKILL.md` |

---

## 12. Mantenimiento de este documento

### 12.1 Versionado (semver ligero)

| Cambio | Cuándo subir | Ejemplo |
|--------|----------------|---------|
| **Micro** (opcional) | Solo typos, enlaces rotos o redacción sin cambiar alcance ni prioridades. Puede **no** bump: una línea extra bajo la misma versión en el changelog. Si querés trazabilidad fina, añadí tercer dígito (`1.1.1`). | Mismo `1.1` + nota en changelog, o `1.1` → `1.1.1` |
| **Minor** `1.x` | Cada **cierre de bloque** de trabajo comité: ítems marcados entregados, nuevos IDs, reorden de secciones, o nueva fila relevante en el changelog. | `1.0` → `1.1` |
| **Major** `2.0` | Cambia el **marco** del comité (principios, prioridades P0–P3 globales, o definición de “Done” de ola) o se **rebasan** históricos de forma que el lector ya no puede asumir continuidad con 1.x. | `1.9` → `2.0` |

Al subir versión: actualizar **Versión** y **Fecha de referencia** en el encabezado y añadir una línea en **12.3 Changelog**.

### 12.2 Owners e ítems activos

- No rellenar **owner** en toda la matriz desde el día uno: sobrecarga el doc.
- Añadir **Owner** (y opcionalmente **Estado**: `en_curso` / `bloqueado`) **solo** para IDs en ejecución; al cerrar el ítem, quitar owner o mover el ID a una subsección “Entregado reciente” y reflejarlo en el changelog.

### 12.3 Changelog

**Historial (más reciente arriba):**

- **v1.34 (2026-04-10):** §10 — puntero actualizado a convergencia (gate P0–P2, columna *Hacia mercado* 1–5).
- **v1.33 (2026-04-10):** §10 — puntero a [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) (*Lista de sprints hacia el lanzamiento*).
- **v1.32 (2026-04-10):** **P2-RF-01 PR 6** — [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) **v1.1** §10 (TIR ref. vs TIR al precio); **P2-RF-01** cerrado documental; plan §4 PR 6 y §9.
- **v1.31 (2026-04-10):** **P2-RF-01 PR 5** — ficha unificada en `ui/tab_inversor.py`; fila §4, §9 P2 Done y alcance P2 alineados al cierre en código.
- **v1.30 (2026-04-10):** **P2-RF-01 PR 4** — ficha RF en `ui/tab_cartera.py` + `tests/test_tab_cartera_ficha_rf.py`; estado en plan §4 P2.
- **v1.29 (2026-04-10):** **P2-RF-01 PR 3** — ficha unificada cableada en `ui/monitor_on_usd.py`; estado en plan §4 P2.
- **v1.28 (2026-04-10):** **P2-RF-01 PR 2** — `render_ficha_rf_minima` + export en `ui/components`; estado en plan §4 P2.
- **v1.27 (2026-04-10):** **P2-RF-01 PR 1** — `ficha_rf_minima_bundle` + `TestP2Rf01FichaMinima`; estado en plan §4 P2.
- **v1.26 (2026-04-10):** **P2-RF-01** — tabla *Reglas de secuencia* (orden 1→6, gate PR1→UI, criterio de merge) junto al plan por PR (§4 P2).
- **v1.25 (2026-04-10):** **P2-RF-01** — plan de implementación por archivo y **orden de PR** (§4 P2, subsección *Plan de implementación*).
- **v1.24 (2026-04-10):** **P2-RF-04** — **Go comité**; siguiente paso RF = **P2-RF-01** (ficha unificada); explícito **no** a más parches de escala sueltos salvo bug/regresión (§4 P2 + §10).
- **v1.23 (2026-04-10):** **P3 incremental** — sección operativa en [`COMITE_UX_DESIGN_SYSTEM_M41_M539.md`](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md); puntero en anexo M41–M539; fila P3-UX-02 y Excelencia alineadas.
- **v1.22 (2026-04-10):** **P0-RBAC-01** cerrado — wizard Estudio y rama “sin clientes” con `can_action(ctx, "write")`; inventario §4a verificado.
- **v1.21 (2026-04-10):** **P2-RF-04** — trazabilidad normalización ×100: `Ajuste ×100 BYMA` / `ESCALA_PRECIO_RF`, banners en `monitor_on_usd` y `tab_cartera`; `_normalizar_lastprice_on_byma_meta`.
- **v1.19 (2026-04-10):** **P3-QA-01 v1** — [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md); CI con paso documentado; `pytest` explícito en `requirements.txt`.
- **v1.18 (2026-04-10):** **P3-EXC-01 v1** — sección inventario fases C–E en [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md); tests `tests/test_investor_hub_snapshot.py`.
- **v1.17 (2026-04-10):** **P3-UX-02 v1** — tokens `--bp-*`, paridad `--text-*` en tema claro; refactor `mq26_ux` (semáforo, hero, defensivo, Plotly); tests `tests/test_mq26_ux_design_system.py`.
- **v1.16 (2026-04-10):** **P3-UX-01** — `dataframe_auto_height` aplicado en `tab_riesgo`, `tab_optimizacion`, `tab_admin`; tests `tests/test_mq26_ux_dataframe_height.py`.
- **v1.15 (2026-04-10):** **P2-RF-05** — catálogo `INSTRUMENTOS_RF` + `ficha_rf_isin` / `ficha_rf_denominacion_min` / `ficha_rf_forma_amortizacion`; `monitor_on_usd` + `tab_inversor`; `TestP2Rf05FichaCatalogo`.
- **v1.14 (2026-04-10):** **P2-BYMA-02** — [`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md); `services/precios_mercado_ingest.py`; tests `tests/test_precios_mercado_ingest.py`; §8 en `BYMA_CAMPOS_Y_ESCALAS_MQ26.md`.
- **v1.13 (2026-04-10):** **P2-BYMA-01** — [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md); punteros en ADR-002, `SOURCES.md`, §11; test `tests/test_byma_docs_p2_byma01.py`.
- **v1.12 (2026-04-10):** Aclaración de alcance: **P2-RF-02** = solo cashflow ilustrativo + copy legal (cerrado); **P2-RF-01** (ficha RF unificada) y **P2-RF-04** (trazabilidad normalización) siguen pendientes; §9 P2 Done y checklist §10 alineados.
- **v1.11 (2026-04-10):** P2-RF-03 — coherencia unidades RF en ejecución/export (`core/unit_contracts.py`, `ui/tab_ejecucion.py`).
- **v1.10 (2026-04-11):** P2-RF-02 — cashflow ilustrativo base 100 VN en `renta_fija_ar` + UI `monitor_on_usd`; `TestCashflowIlustrativoP2Rf02`; checklist P2 Done (entrada cashflow).
- **v1.9 (2026-04-10):** P1-ADM-01 — `registrar_admin_audit_event` / redacción / confirmaciones en `tab_admin`; tests `test_p1_adm01_*` en `tests/test_db_manager.py`; checklist P1 Done (admin auditable).
- **v1.8 (2026-04-10):** P1-OBS-02 — tests con mocks (`TestP1Obs02LogDegradacionMocks`, `TestP1Obs02BuildCclSeriesMock`) en `tests/test_observabilidad.py`; checklist P1 Done (mocks de fallo).
- **v1.7 (2026-04-10):** P1-OBS-01 — `log_degradacion` en `tab_optimizacion`, `tab_riesgo`, `tab_universo` y `run_mq26` (puntos acordados); regresión en `tests/test_observabilidad.py`; checklist P1 Done (degradaciones logueadas).
- **v1.6 (2026-04-10):** P1-NAV-01 — `run_mq26.py` delega pestañas en `render_main_tabs` (SSOT con `app_main` vía `ui/navigation.py`); test `test_run_mq26_usa_render_main_tabs_ssot_p1_nav01`; §Implicación en `docs/MAP_MQ26_ENTRYPOINTS.md`; checklist P1 Done (navegación SSOT).
- **v1.5 (2026-04-10):** P0-TNT-01 — endurecimiento `db_manager` (tenant en SQL fallback, `actualizar_cliente`, `delete_app_usuario`); UI/sync/pantalla ingreso; tests `tests/test_tenant_p0_tnt01.py`; checklist seguridad v1.1.
- **v1.4 (2026-04-10):** P0-RBAC-03 — página [`CHECKLIST_P0_DONE_SEGURIDAD.md`](./CHECKLIST_P0_DONE_SEGURIDAD.md); §9 P0 Done actualizado; referencia cruzada §11.
- **v1.3 (2026-04-10):** P0-RBAC-02 matriz deny/allow parametrizada y docstring en `tests/test_rbac_p0_policy.py`; puntero en `ui/rbac.py`.
- **v1.2 (2026-04-10):** P0-RBAC-01 inventario mutaciones tab Estudio/Admin + owner en curso; gates `can_action` / `panel_admin_write` y tests `tests/test_rbac_p0_policy.py`.
- **v1.1 (2026-04-10):** sección 12 ampliada: reglas minor/major/micro, owners solo en ítems activos, plantilla de línea changelog.
- **v1.0 (2026-04-10):** inventario maestro P0–P3 inicial; enlaces a backlog cerrado y referencias cruzadas.

**Plantilla** para la próxima entrada (copiar y completar):

```text
- **v1.x (AAAA-MM-DD):** una frase; IDs cerrados o bloque (ej. P0 Done).
```

Reglas: una frase; IDs tocados si aplica; sin duplicar el detalle de las tablas de inventario.

### 12.4 Reglas operativas (resumen)

- Cualquier pendiente nuevo de conversación comité debe **entrar aquí** con ID y criterio de aceptación antes de codear.
- Al cerrar bloques: marcar ítems con `[x]` en sección Done, mover líneas a “Entregado” si se usa, y **subir minor** + changelog.

---

*Documento elaborado bajo el marco **comite-expertos-carteras-ar**: capital primero, riesgo antes que retorno, claridad, minimalismo, trazabilidad, honestidad operativa.*
