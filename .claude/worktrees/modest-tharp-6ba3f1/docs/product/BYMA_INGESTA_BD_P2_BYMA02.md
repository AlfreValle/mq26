# Ingesta de precios en BD — escala idéntica a brokers (P2-BYMA-02)

**Versión:** 1.0 · **Fecha:** 2026-04-10  
**Código:** `services/precios_mercado_ingest.py`, `services/byma_market_data.normalizar_precio_ars_on_usd_desde_feed_o_broker`

---

## 1. Objetivo

Cuando los precios llegan desde **jobs propios** (ETL nocturno, CSV de broker, tabla intermedia en PostgreSQL) y se persisten en la BD de MQ26, la **escala** de obligaciones **ON/bono USD** debe coincidir con la del feed Open Data y con `cartera_service` / `unit_contracts`: **ARS por 1 nominal USD** (con heurística **÷100** si el crudo viene en escala tipo “por 100 VN”).

Este pipeline **no** reemplaza Yahoo/BYMA en vivo: complementa `PriceEngine` en nivel **FALLBACK_BD** (`precios_fallback`).

---

## 2. Tabla de persistencia

| Tabla | Motor | Uso |
|-------|-------|-----|
| `precios_fallback` | SQLite local o PostgreSQL (`DATABASE_URL`) | Último precio ARS por ticker; leída por `obtener_precios_fallback()` y el `PriceEngine` |

Columnas relevantes: `ticker`, `precio_ars`, `fuente`, `fecha_actualizacion`.

---

## 3. API Python (recomendada)

```python
from services.precios_mercado_ingest import (
    precio_ars_canonico_para_persistencia,
    ingestar_precios_fallback_desde_dict,
)

ccl = 1500.0  # mismo CCL que usa la app al valorizar

# Dict crudo desde ETL (puede traer escala ×100 en ON USD)
crudos = {"TLCTO": 148_500.0, "GGAL": 5_200.0}

guardados = ingestar_precios_fallback_desde_dict(
    crudos,
    ccl=ccl,
    fuente="etl_nightly",
    tipos_por_ticker=None,  # opcional: {"TLCTO": "ON_USD"}
)
# guardados["TLCTO"] ≈ 1485.0 si aplica ÷100; GGAL sin cambio
```

- **`precio_ars_canonico_para_persistencia`**: un solo ticker; útil si insertás fila a fila.
- **`ingestar_precios_fallback_desde_dict`**: lote; llama internamente a `guardar_precio_fallback`.

La detección de “RF USD paridad” usa `core.unit_contracts.es_instrumento_rf_usd_paridad` (meta `renta_fija_ar` + tipos `ON_USD` / `BONO_USD`).

---

## 4. Regla de escala (resumen)

Delegada en `normalizar_precio_ars_on_usd_desde_feed_o_broker` → misma implementación que `_normalizar_lastprice_on_byma` en el feed. Ver [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md) §5.

---

## 5. Ingesta SQL directa (avanzado)

Si un job escribe **SQL** sin pasar por Python, el operador debe **pre-normalizar** los precios ON USD con la misma regla o ejecutar un paso posterior que actualice filas. **No** se aplica normalización automática al **leer** `precios_fallback`: la unidad correcta debe quedar guardada.

---

## 6. Tests

`tests/test_precios_mercado_ingest.py` — casos TLCTO ×100 vs GGAL, y persistencia en BD de test.

---

## 7. Referencias

- [`BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](./BYMA_CAMPOS_Y_ESCALAS_MQ26.md)  
- [`docs/adr/003-convencion-precios-y-lineage.md`](../adr/003-convencion-precios-y-lineage.md)  
- `core/price_engine.py` — `FALLBACK_BD`
