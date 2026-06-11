# Plan "Mejor optimizador de carteras AR" — roadmap por pilares

Visión (2026-06-11): llevar MQ26 a nivel best-in-class como optimizador de
carteras adaptado a Argentina (CEDEARs, ONs, bonos, FCIs), con tres roles:
inversor particular, estudio/asesor y super admin.

Decisión de producto: **evolucionar MQ26, no clonar** — la app ya cubre la
visión funcional (3 roles, optimizador HRP, estudios de tickers, catálogo RF,
2.149 tests). El camino al "mejor" es cerrar las brechas del backlog
competitivo ([BACKLOG_MOSCOW.md](BACKLOG_MOSCOW.md)) en este orden aprobado:

## Orden de ejecución (aprobado por Alfredo)

1. **Pilar 1 — Fundación de datos AR** (Musts A01/A02/A04/A13/A15/A45)
2. **Pilar 2 — Estudio de tickers nivel pro** (ficha unificada: fundamentals
   + técnico + DCF + comparables + score multifactor explicado)
3. **Pilar 3 — Recomendador explicable end-to-end** (unificar perlas +
   recomendación de capital + decision engine con justificación auditable)
4. **Pilar 4 — Admin SaaS completo** (tenants, feature flags, métricas de
   uso, monitor de salud de datos)

## Pilar 1 — estado

### Sprint 1 (2026-06-11) ✅ — commit `5183988`

- **A01** `core/instrument_master.py`: maestro único de instrumentos.
  Consolida catálogo RF + universo Excel + RATIOS_CEDEAR + SECTORES.
  API: `get_master()`, `validar_ticker()`. Taxonomía canónica `TIPOS_CANONICOS`.
  Corrige el bug de ONs reportadas "CEDEAR".
- **A15** `core/stale_policy.py`: umbrales de frescura por tipo de activo
  (RV: 15min/1h · RF: 4h/24h · FCI: 1d/2d) + `aplicar_politica_stale()`
  en price_engine. `Frescura.usable_para_recomendacion` para que los motores
  degraden con criterio.
- **A45** validación de tickers contra el maestro en `ui/carga_activos.py`
  con sugerencias por typo. `universo_service.obtener_tipo` delega al maestro.

### Sprint 2 (2026-06-11) ✅ — commit `f7e3c6f`

- **Maestro adoptado**: 10 sitios `RATIOS_CEDEAR.get()` migrados a
  `get_master().ratio()` (perlas, primera_cartera, scoring, timeline,
  multicuenta, cartera_service, tab_perlas, tab_reporte).
  `set_universo_df()` reconstruye el maestro al cargar universo.
- **Frescura en UI**: `aplicar_politica_stale()` en app_main +
  `label_fuente_con_frescura()` unifica los labels de tab_cartera/tab_reporte
  con sufijo ⚠STALE por umbral de tipo.
- **A04**: `precio_referencia_ars_desde_catalogo()` normaliza paridad→ARS/VN;
  resolver_precios, resolver_precios_con_origen y PriceEngine delegan al modelo.
- Fix operativo: rev de ruff en pre-commit alineado a local/CI (v0.15.12).

### Sprint 3 (2026-06-11) ✅ — commit `bb0ef9d`

- **A13** `core/fx.py`: FX por fecha de operación. `ccl_para_fecha()` (pasado
  → serie histórica sin look-ahead, futuro → spot), `ccl_series()` para
  VaR/CVaR (P0-02), `ars_a_usd`/`usd_a_ars` con `FXQuote` trazable.
  `calcular_posicion_neta` cumple por fin su docstring: con fecha de compra,
  el costo ARS usa el CCL de esa fecha, no el spot.
- **A02**: `PriceRecord.moneda` + `convencion` (ars_por_unidad | ars_por_vn)
  con defaults compatibles; el fallback RF declara ars_por_vn.
- **Frescura inversor**: `build_posiciones_broker_html` muestra fuente en
  tooltip y ⚠ en precios vencidos; `run_mq26` aplica la política stale a
  sus records (antes solo app_main).

### Pilar 1 — Musts cerrados: A01, A04, A13, A15, A45, A02 (parcial: convención
explícita; PriceQuote como contrato separado quedó innecesario). Restan del
backlog: A21 (secrets), A37 (PII), A44 (✓ previo), A50 (✓ runbook).

### Siguiente → **Pilar 2: ficha de ticker nivel pro**

Vista unificada por ticker: fundamentals + técnico + DCF + comparables del
sector + score multifactor con explicación humana de cada componente.
Piezas existentes a unificar: services/analizador_ticker.py,
services/empresa_ficha.py, services/dcf_simple.py,
services/comparador_instrumentos.py, services/scoring_multifactor.py.

## Criterio de éxito del plan

- Toda recomendación trazable a: instrumento validado contra maestro +
  precio con fuente y frescura conocidas + FX de fecha correcta.
- Ficha de ticker que un asesor pueda mostrar a su cliente sin vergüenza.
- Cada sugerencia del recomendador con su "por qué" auditable.
- Panel admin que muestre salud de datos en vivo.
