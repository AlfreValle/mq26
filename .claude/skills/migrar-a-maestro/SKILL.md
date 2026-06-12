---
name: migrar-a-maestro
description: Migra código de MQ26 a los patrones de la fundación de datos del Pilar 1 (InstrumentMaster, política stale, FX por fecha). Usar al encontrar RATIOS_CEDEAR.get() a mano, lecturas crudas de universo_df, CCL spot para costos históricos, o precios sin trazabilidad.
---

# Migración a la fundación de datos (Pilar 1)

Patrones legacy → patrón canónico. Detectar con grep, migrar, verificar.

## Ratio CEDEAR

```bash
grep -rn "RATIOS_CEDEAR" --include="*.py" core/ services/ ui/ scripts/
```
- Legacy: `float(RATIOS_CEDEAR.get(ticker, 1.0))`
- Canónico: `from core.instrument_master import get_master` → `get_master().ratio(ticker)`
- Beneficio: respeta el override del universo Excel y la clasificación RF del catálogo.
- Excepciones permitidas: `config.py` (la fuente), `instrument_master.py`,
  `universo_service.py`, `price_engine.py` (cachea internamente).

## Tipo de instrumento

- Legacy: leer columna `Tipo` de universo_df a mano / asumir "CEDEAR".
- Canónico: `get_master().tipo(ticker)` (devuelve canónico de TIPOS_CANONICOS;
  el catálogo RF manda — una ON nunca se reporta CEDEAR).

## Validación de tickers

- Canónico: `get_master().validar(ticker, tipo_declarado)` → `ValidacionTicker`
  con `sugerencias` por typo. El caller decide warn/block.

## Frescura de precios

- Todo dict de `PriceRecord` que llegue a UI/motor debe pasar por
  `core.price_engine.aplicar_politica_stale(records)`.
- Label para UI: `label_fuente_con_frescura(record)` (agrega ⚠STALE).
- Motores de recomendación: respetar `Frescura.usable_para_recomendacion`.

## FX por fecha (costos históricos)

- Legacy: `monto_usd * ccl` (spot) para operaciones con fecha pasada.
- Canónico: `from core.fx import ccl_para_fecha` →
  `ccl_para_fecha(fecha_compra, spot=ccl).valor` (histórico sin look-ahead).
- Series para riesgo: `ccl_series(fechas, spot=ccl)`.

## Precio de referencia RF

- Legacy: `(paridad/100)*ccl` inline.
- Canónico: `core.renta_fija_ar.precio_referencia_ars_desde_catalogo(ticker, ccl, vn=...)`.

## Verificación

Suite completa `-n 4` (los consumidores migrados se usan desde flujos lejanos)
+ ruff. Commit `refactor(data): migrar <módulo> al maestro/fx/stale`.
