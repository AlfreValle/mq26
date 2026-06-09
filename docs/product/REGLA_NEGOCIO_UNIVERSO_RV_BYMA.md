# Regla de negocio — Universo RV (CEDEARs y acciones) desde BYMA

| Campo | Valor |
|-------|--------|
| **ID** | RB-MQ26-RV-001 |
| **Estado** | Vigente |
| **Ámbito** | Motor de datos, búsqueda de tickers, ratios y cualquier listado de **CEDEARs** y **acciones argentinas** (renta variable local) en MQ26 |
| **Fuente normativa** | BYMA Open Data (`open.bymadata.com.ar`) |

---

## Regla vinculada — RV comercializable en ARS (RB-MQ26-RV-002)

| Campo | Valor |
|-------|--------|
| **ID** | RB-MQ26-RV-002 |
| **Estado** | Vigente |
| **Enunciado** | Si el instrumento **no** puede incluirse en el universo como **negociable / cotizable en pesos argentinos (ARS)** según los metadatos del feed BYMA, **no** debe formar parte del universo de activos RV de MQ26. |
| **Implementación** | `services/byma_market_data.py` → `_fila_byma_comercializable_ars()` aplicado en `fetch_universo_rv_byma()` sobre cada fila de `cedears` y `equities`. |

**Criterio técnico:** en **equities**, se examinan campos de moneda habituales (`currency`, `currencyCode`, `tradeCurrency`, etc.). Si indican **explícitamente** moneda **solo** USD (u otra no ARS) **sin** señal de ARS/pesos, la fila se descarta. En **cedears**, no se aplica este filtro por moneda: el feed suele marcar USD por el nominal del subyacente, pero el instrumento cotiza en ARS en BYMA. Si no hay información de moneda en equities, se **conserva** la fila.

---

## Enunciado (regla)

**El universo de instrumentos de renta variable local —CEDEARs y acciones— debe construirse exclusivamente a partir de BYMA, sin excepción como fuente primaria de tickers.**

- Los **tickers** y la **existencia** del instrumento en el universo operativo de MQ26 provienen **solo** de los endpoints oficiales de listado BYMA (en la implementación actual: `cedears` y `equities`).
- **No** se utiliza como fuente primaria: listas fijas en código (`config.UNIVERSO_BASE`, `RATIOS_CEDEAR` como catálogo de tickers), ni el Excel `Universo_120_CEDEARs.xlsx`) para **añadir** símbolos que no estén en BYMA.

---

## Enriquecimiento permitido (no sustituye la regla)

- El archivo **`Universo_120_CEDEARs.xlsx`** (u homólogo) puede usarse **solo** para **metadatos** sobre tickers **ya** devueltos por BYMA: por ejemplo **ratio** CEDEAR, **sector** o **nombre** si faltan en el feed.
- **No** se incorporan tickers adicionales desde Excel ni desde configuración si no figuran en el listado BYMA del día.

---

## Comportamiento ante fallo de BYMA

- Si BYMA no devuelve datos (red, indisponibilidad del servicio), **no** se debe sustituir el universo por listas locales: el arranque del motor **debe fallar de forma explícita** hasta que haya un universo válido desde BYMA (o un procedimiento operativo acordado, p. ej. modo mantenimiento documentado aparte).

---

## Implementación de referencia (código)

| Componente | Rol |
|------------|-----|
| `core/byma_open_data_config.py` | Parámetros CRÍTICOS de recolección Open Data (RB-MQ26-OD-CRIT-001); ver `REGLA_CRITICA_BYMA_OPEN_DATA.md` |
| `services/byma_market_data.py` → `fetch_universo_rv_byma()` | Consolida CEDEARs + equities desde BYMA Open Data; filtra no-ARS (RB-MQ26-RV-002) |
| `services/byma_market_data.py` → `_fila_byma_comercializable_ars()` | Excluye filas con moneda explícita no ARS |
| `1_Scripts_Motor/data_engine.py` → `DataEngine._cargar_universo()` | Carga el universo obligando fuente BYMA; enriquece opcionalmente con Excel |
| `services/universo_service.py` | Consume el `DataFrame` registrado por el motor |

---

## Tests asociados

- `tests/test_byma_market_data.py` — consolidación de universo RV.
- `tests/test_data_engine_rf_units.py` — motor con universo BYMA stub en tests.

---

## Relación con otros documentos

- Criterios de **análisis** de CEDEAR (ratio, CCL implícito): `COMITE_CEDEARS_CRITERIOS.md`.
- Matriz de producto y tipos: `COMITE_REGLAS_NEGOCIO_INSTRUMENTOS_AR.md`.
- ADR proveedores / datos: `docs/adr/002-proveedores-datos-byma.md`.

---

## Historial de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-04-14 | Regla formalizada; implementación alineada a BYMA como única fuente de tickers RV |
| 2026-04-14 | RB-MQ26-RV-002: exclusión universo RV si feed indica no comercializable en ARS |
| 2026-04-14 | Referencia RB-MQ26-OD-CRIT-001: parámetros Open Data centralizados en `core/byma_open_data_config.py` |
