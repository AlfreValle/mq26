---
name: diagnostico-degradaciones
description: Diagnostica degradaciones de runtime en MQ26 — precios en cero o viejos, yfinance/BYMA caídos, fichas incompletas, CCL raro. Usar cuando el usuario reporte "no carga precios", "sale todo en cero", "la app anda rara" o aparezcan logs degradacion_*.
---

# Diagnóstico de degradaciones MQ26

La app degrada por diseño (nunca explota), así que los síntomas son sutiles:
precios viejos, secciones de ficha en "—", labels FALLBACK. Diagnosticar por capa.

## Capa 1 — ¿De dónde salió el precio que se ve?

La cadena de fallbacks (core/price_engine.py): LIVE_YFINANCE → LIVE_BYMA →
FALLBACK_BD → FALLBACK_HARD → FALLBACK_PPC → FALLBACK_CATALOGO_RF → MISSING.

- En la UI: columna "Fuente px" (tab_cartera/tab_reporte) y tooltips de la
  tabla del inversor ya muestran fuente + ⚠STALE.
- Por consola:
```python
from core.price_engine import PriceEngine
pe = PriceEngine()
recs = pe.get_portfolio(["AAPL", "PN43O"], ccl=1450.0)
for t, r in recs.items(): print(t, r.source.value, r.stale, r.precio_cedear_ars)
```
- `scripts/debug_pricing_snapshot.py` existe para snapshots completos.

## Capa 2 — Proveedores

- **yfinance caído/limitado**: típico `JSONDecodeError` o histories vacíos.
  Verificar: `python -c "import yfinance as yf; print(len(yf.Ticker('SPY').history(period='5d')))"`.
  Si está caído, la app vive de fallbacks → precios ACEPTABLE/STALE según tipo.
- **BYMA**: `services/byma_provider.fetch_precios_ars_batch` — revisar si
  `BYMA_FIRST` está activo en core/data_providers.py.
- **CCL raro**: `obtener_ccl()` = GGAL.BA/GGAL × 10 con fallback hardcodeado.
  Si CCL ≈ CCL_FALLBACK de config.py, el cálculo live falló.

## Capa 3 — Logs de degradación

Los flujos loguean `degradacion_*` vía `_log_degradacion`/`log_degradacion`:
```bash
grep -rn "degradacion" *.log 2>/dev/null | tail -20
```
Cada evento tiene nombre propio (ej. `price_engine_portfolio_fallo`,
`pci_plan_objetivos_error`) — grep por el nombre lleva al sitio exacto.

## Capa 4 — Datos de referencia vencidos

Si todo "funciona" pero los números son viejos: revisar fechas de
CCL_HISTORICO, `fecha_ref` del catálogo RF y PRECIOS_FALLBACK_ARS
(skill actualizar-datos-referencia).

## Runbook oficial

Para incidentes de producción: `docs/RUNBOOK_INCIDENTES_DEGRADACIONES.md`.
