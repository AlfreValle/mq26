---
name: optimizar-rendimiento-app
description: Diagnostica y mejora el rendimiento de la app MQ26 (tabs lentas, reruns excesivos, red innecesaria, cachés). Usar cuando el usuario diga "la app está lenta", "tarda en cargar", o antes de sumar features pesadas a una tab.
---

# Rendimiento de la app MQ26

Streamlit re-ejecuta TODO el script en cada interacción. El rendimiento se
gana evitando trabajo en el camino caliente, no optimizando microsegundos.

## Patrones del proyecto (ya probados — replicar)

1. **Lazy por pedido del usuario**: nada que gaste red corre sin click.
   Patrón botón → `st.session_state[flag] = True` → `st.rerun()` → render.
   (Ejemplos: ficha en perlas, velas en ficha_ticker_view.)
2. **Cache con TTL acorde al dato**:
   - `@st.cache_data(ttl=900)` ficha de ticker (15 min)
   - `@st.cache_data(ttl=1800)` series yfinance (30 min)
   - Fundamentales: cache BD 24 h (services/fundamentals_cache)
   - El cache de diagnóstico usa hash de contexto + TTL 300 s
     (`_get_diagnostico_cached` en ui/inversor/_helpers.py) — replicar para
     cálculos caros dependientes de cartera.
3. **Imports lazy en render**: los `import` pesados (plotly, yfinance,
   servicios) van DENTRO de la función de render, no a nivel módulo de la tab
   (navigation.py ya usa `_lazy_render`).
4. **Maestro/estructuras una vez**: `get_master()` es singleton con rebuild
   por fingerprint — no construir índices por fila ni por rerun.

## Diagnóstico de una tab lenta

1. ¿Cuántas llamadas de red hace en un render frío? Grep por `yf.`,
   `requests.`, `fetch_` en la tab y sus servicios.
2. ¿Hay loops `df.iterrows()` sobre DataFrames grandes que puedan
   vectorizarse o moverse a un servicio cacheado?
3. ¿Se recalcula algo idéntico en cada rerun? → cache con hash de inputs.
4. Medir en serio: envolver la sección sospechosa con `time.perf_counter()`
   y loguear; o correr la app y mirar logs de latencia
   (services/latency_metrics.py existe).

## Rendimiento del ciclo de desarrollo

- Tests SIEMPRE `-n 4` (3:20 → 1:35). CI usa `-n auto`.
- Tests nuevos con dobles, sin red — un test que descarga de yfinance hace
  lenta y flaky la suite para siempre.
- `--co -q` para verificar colección rápido sin correr nada.
