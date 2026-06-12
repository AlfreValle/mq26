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

## Pilar 2 — estado

### Sprint 1 (2026-06-11) ✅ — commit `ab85ebe`

- `services/ficha_ticker.py`: ficha unificada que compone identidad
  (instrument_master), fundamentals (cache 24h), score multifactor
  (35/30/20/15 con cada dimensión explicada), DCF (margen de seguridad +
  supuestos) y comparables (vs mediana de industria).
- Hallazgo clave: `calcular_action_score` y `analizar_ticker` no tenían
  ningún consumidor en la UI — motores construidos que nadie veía.
- Degradación elegante por sección (cobertura "4/5"), resumen ejecutivo que
  cruza señales (multifactor COMPRAR + DCF SOBREVALUADA → aviso de entrada
  escalonada). RF deriva a ficha RF. 11 tests con dobles, sin red.

### Sprint 2 (2026-06-11) ✅ — commit `a927205`

- Sub-tab "📑 Ficha de ticker" en tab_universo para ambos roles, con buscador
  validado contra el maestro (sugerencias de typo antes de gastar red).
- Componente `ui/components/ficha_ticker_view.py`: recomendación semaforizada,
  score + cobertura, 4 dimensiones con pesos, secciones en expanders, velas
  opcionales, descarga HTML. Cache 15 min + persistencia del último ticker.
- `ficha_ticker_html()`: export standalone imprimible con contenido escapado.

### Sprint 3 (2026-06-12) ✅ — commit `b0369fd` — **PILAR 2 CERRADO**

- Sexta sección: consenso de analistas (`consenso_analistas()` liviano,
  cobertura X/6, integrado al resumen ejecutivo con disclaimer).
- Ficha accesible desde el detalle de cada perla (lazy, botón) y desde la
  tabla de posiciones del inversor (selector de activos RV).

## Pilar 3 — estado

### Sprint 1 (2026-06-12) ✅ — commit `e7a4592`

- `services/recomendador_explicable.py`: contrato PlanAccion →
  RecomendacionExplicada → Motivo. Unifica compras (recomendacion_capital)
  y ventas/revisiones (motor_salida) sin re-decidir.
- Confianza ALTA/MEDIA/BAJA por frescura del precio (Pilar 1);
  `tiene_ficha` enlaza al Pilar 2; `auditar_plan()` cablea el audit trail
  que estaba huérfano (payload completo con motivos).
- 19 tests con dobles, sin red.

### Sprint 2 (2026-06-12) ✅ — commit `8a4bf25`

- `ui/components/plan_accion_view.py`: render del plan — motivos atómicos,
  badge de confianza por frescura (🟢/🟡/🔴), link lazy a la ficha Pilar 2.
- Integrado en plata nueva ("🧭 Por qué estas sugerencias") y primera
  cartera ("🧭 Por qué esta cartera"); `auditar_plan()` cableado en ambos
  cálculos con payload completo. La auditoría nunca bloquea el flujo.

### Sprint 3 (2026-06-12) ✅ — commit `a4efef9` — **PILAR 3 CERRADO**

- Costos de operación (decision_engine revivido) en la trazabilidad de cada
  compra + advertencia de operación chica. Bug de truncado de unidades
  fraccionarias detectado por revisión quant y corregido pre-commit.
- Plan explicado en tab_cartera (asesor): señales del motor de salida como
  plan de vender/revisar con motivos.
- Auditoría visible en tab_admin: `listar_recomendaciones()` +
  `obtener_payload_recomendacion()` — el "por qué" de cualquier plan
  registrado, filtrable por evento.

## Siguiente → **Pilar 4: Admin SaaS completo**

Panel super admin: gestión de tenants/usuarios, feature flags por tenant
(A08), métricas de uso, monitor de salud de datos en vivo (qué proveedor
está caído, qué precios están viejos — apoyado en PriceSource/stale_policy
del Pilar 1 y la cobertura de la ficha del Pilar 2).

## Criterio de éxito del plan

- Toda recomendación trazable a: instrumento validado contra maestro +
  precio con fuente y frescura conocidas + FX de fecha correcta.
- Ficha de ticker que un asesor pueda mostrar a su cliente sin vergüenza.
- Cada sugerencia del recomendador con su "por qué" auditable.
- Panel admin que muestre salud de datos en vivo.
