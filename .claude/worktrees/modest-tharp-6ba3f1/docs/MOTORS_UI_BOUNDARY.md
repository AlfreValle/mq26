# Límite motores (dominio) vs UI

## Regla

- **Motores y reglas de negocio:** [`services/`](../services/) (p. ej. `diagnostico_cartera`, `scoring_engine`, `recomendacion_capital`, `motor_salida`) y [`core/`](../core/) (tipos, `perfil_allocation`, `renta_fija_ar`, etc.).
- **Streamlit y presentación:** [`ui/`](../ui/) únicamente.

No añadir `st.*` ni HTML de producto dentro de servicios nuevos. Si un servicio histórico mezcla UI (deuda técnica), al refactorizar extraer la parte pura a funciones sin Streamlit y dejar el render en `ui/`.

## Deuda técnica: `st.*` residual en `services/` (2026-04)

Pantallas que aún viven bajo `services/` y deberían migrarse a `ui/` (o a funciones puras + render en `ui/`):

| Módulo | Notas |
|--------|--------|
| [`services/backtester_real.py`](../services/backtester_real.py) | Vista backtesting |
| [`services/correlaciones.py`](../services/correlaciones.py) | Mapa correlaciones |
| [`services/byma_market_data.py`](../services/byma_market_data.py) | Tabla BYMA |
| [`services/risk_var.py`](../services/risk_var.py) | Panel VaR / CVaR |
| [`services/multicuenta.py`](../services/multicuenta.py) | Multi-broker |
| [`services/tab_recomendador.py`](../services/tab_recomendador.py) | Recomendador semanal |
| [`services/timeline_posiciones.py`](../services/timeline_posiciones.py) | Línea de tiempo |
| [`services/dashboard_ejecutivo.py`](../services/dashboard_ejecutivo.py) | Dashboard ejecutivo |
| [`services/motor_salida.py`](../services/motor_salida.py) | `render_motor_salida` (import local de `st`; dominio `evaluar_salida` sin UI) |

## Referencia de motores públicos

| Área | Entrada principal | Módulo |
|------|-------------------|--------|
| Scoring | `calcular_score_total` | [`services/scoring_engine.py`](../services/scoring_engine.py) |
| Diagnóstico | `diagnosticar` | [`services/diagnostico_cartera.py`](../services/diagnostico_cartera.py) |
| Capital | `recomendar` | [`services/recomendacion_capital.py`](../services/recomendacion_capital.py) |
| Salida | `evaluar_salida` / `render_motor_salida` | [`services/motor_salida.py`](../services/motor_salida.py) |
