# Inventario de claves `ctx` por pestaña

Fuentes: [`run_mq26.py`](../run_mq26.py) y [`app_main.py`](../app_main.py) arman el dict; cada `render_tab_*` consume un subconjunto.

## Campos frecuentes en entrypoints (referencia)

Cartera y mercado: `df_ag`, `tickers_cartera`, `precios_dict`, `ccl`, `cartera_activa`, `df_analisis`, `metricas`, `universo_df`, `price_coverage_pct`, `tickers_sin_precio`, `valoracion_audit`, `precio_records`.

Cliente: `cliente_id`, `cliente_nombre`, `cliente_perfil`, `horizonte_label`, `horizonte_dias`, `capital_nuevo`, `df_clientes`, `prop_nombre`, `ultimo_diagnostico`, `cliente_horizonte_label`, `cliente_capital_usd`.

Config: `RISK_FREE_RATE`, `PESO_MAX_CARTERA`, `N_SIM_DEFAULT`, `RUTA_ANALISIS`, `carteras_csv`.

Infra: `BASE_DIR`, `df_trans`, `engine_data`, `RiskEngine`, `cached_historico`, `df_historico`.

Servicios: `dbm`, `cs`, `m23svc`, `ejsvc`, `rpt`, `bt`, `ab`, `lm`, `bi`, `gr`, `mc`.

UI helpers: `_boton_exportar`, `asignar_sector`, `render_carga_activos_fn`.

Rol / flujo: `user_role`, `tenant_id`, `flow_resumen`.

---

## Por archivo de tab

### [`ui/tab_cartera.py`](../ui/tab_cartera.py)

**Requeridos (acceso directo `ctx["..."]`):** `tickers_cartera`, `precios_dict`, `ccl`, `cartera_activa`, `prop_nombre`, `df_clientes`, `df_analisis`, `PESO_MAX_CARTERA`, `dbm`, `cs`, `m23svc`, `ab`, `lm`, `bi`, `gr`, `engine_data`, `asignar_sector`, `_boton_exportar`, `BASE_DIR`.

**Opcionales frecuentes:** `df_ag`, `metricas`, `price_coverage_pct`, `tickers_sin_precio`, `valoracion_audit`, `ultimo_diagnostico`, `user_role`, `precio_records`, `df_trans`, `cliente_perfil`, `df_historico`, `cached_historico`, `carteras_csv`.

### [`ui/tab_inversor.py`](../ui/tab_inversor.py)

**Muchos opcionales:** `ccl`, `universo_df`, `df_analisis`, `engine_data`, `precios_dict`, `df_ag`, `cartera_activa`, `cliente_perfil`, `metricas`, `cliente_nombre`, `horizonte_label`, `cliente_horizonte_label`, `series_comparacion_informe`, `render_carga_activos_fn`, `dbm`, `cliente_id`, `capital_nuevo`, `cliente_capital_usd`.

### [`ui/tab_estudio.py`](../ui/tab_estudio.py)

**Principales:** `dbm`, `tenant_id`, `ccl`, `universo_df`, `df_ag`, `cliente_id`, `df_trans`, `engine_data`, `cs`, `metricas`, `precios_dict`.

### [`ui/tab_universo.py`](../ui/tab_universo.py)

**Requeridos:** `tickers_cartera`, `df_analisis`, `m23svc`, `mc`, `engine_data`, `RUTA_ANALISIS`.

**Opcionales:** `df_ag`, `dbm`, `cliente_id`, `horizonte_label`, `cliente_perfil`.

### [`ui/tab_optimizacion.py`](../ui/tab_optimizacion.py)

**Requeridos:** `tickers_cartera`, `RISK_FREE_RATE`, `capital_nuevo`, `engine_data`, `RiskEngine`, `cached_historico`, `_boton_exportar`.

**Opcionales:** `df_ag`, `prop_nombre`, `horizonte_label`, `cliente_perfil`, `user_role`, `cliente_id`, `horizonte_dias`, `cartera_activa`.

### [`ui/tab_riesgo.py`](../ui/tab_riesgo.py)

**Opcionales:** `df_ag`, `ccl`, `engine_data`, `cartera_activa`, `cached_historico`.

### [`ui/tab_ejecucion.py`](../ui/tab_ejecucion.py)

**Opcionales:** `df_ag`, `cliente_id`, `cliente_perfil`, `horizonte_label`, `user_role`.

### [`ui/tab_reporte.py`](../ui/tab_reporte.py)

**Opcionales:** `cliente_id`, `cartera_activa`, `metricas`, `cliente_nombre`, `horizonte_label`, `cliente_perfil`, `user_role`, `df_trans`, etc. (muchas ramas según tipo de reporte).

### [`ui/tab_admin.py`](../ui/tab_admin.py)

**Principales:** `ccl`, `user_role`, `metricas`, `dbm`, `tenant_id`, `df_clientes`, `universo_df`.

---

## Uso con `ContextBuilder`

Para nuevas pantallas, preferir completar el contexto con [`core/context_builder.py`](../core/context_builder.py) y evitar claves faltantes en runtime.
