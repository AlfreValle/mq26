# Regla de negocio — Recomendación de capital: RV local vs equity internacional

| Campo | Valor |
|-------|--------|
| **ID** | RB-MQ26-REC-001 |
| **Estado** | Vigente |
| **Ámbito** | Motor de recomendación de capital nuevo (S5), textos de **impacto en balance** y **justificaciones** tácticas en UI (inversor / primera cartera) |
| **Relación** | Complementa RB-MQ26-RV-001 (universo BYMA) y `tipo_regla_negocio` en `services/universo_service.py` |

---

## Enunciado (regla)

**Los mensajes de recomendación de compra no deben mezclar “renta variable genérica” con acción local argentina (Merval/Latam) ni con equity internacional (CEDEAR, ETF o subyacente exterior).**

- El usuario debe poder leer **si el aporte es diversificación en panel **local** o exposición **internacional** (incluido vía CEDEAR o instrumento listado en BYMA con subyacente no argentino).
- La **clasificación de producto** (`core/diagnostico_types.py` → `CLASIFICACION_ACTIVOS`, categoría `LATAM` vs resto) **prevalece** sobre el tipo crudo del feed BYMA cuando este último puede listar el mismo símbolo como “equity” sin distinguir el subyacente económico.
- Las **oportunidades tácticas** (prioridad baja, señal MOD / análisis técnico fuera del núcleo del plan) deben explicitar que son **exposición internacional / subyacente exterior**, no “panel local”, cuando corresponda.

---

## Criterios de copy (texto de impacto)

| Situación | Mensaje esperado (idea) |
|-----------|-------------------------|
| Ticker con categoría **LATAM** en `CLASIFICACION_ACTIVOS` | Renta variable **local** / diversificación |
| Tipo universo **CEDEAR** o **ETF**, o ticker en `RATIOS_CEDEAR` | Equity **internacional** (CEDEAR/ETF o subyacente exterior) |
| Categoría de modelo **no** LATAM ni OTRO (p. ej. cuasi-defensivo US) | Equity **internacional** — aunque BYMA marque `ACCION_LOCAL` en el listado |
| Resto | Renta variable genérica (fallback) |

---

## Implementación de referencia (código)

| Componente | Rol |
|------------|-----|
| `services/recomendacion_capital.py` → `_impacto_str()` | Arma texto de **impacto en balance** según regla |
| `services/recomendacion_capital.py` → `_build_justificacion_item()` | Ajusta redacción de **oportunidad táctica** (prioridad Baja + MOD) |
| `core/diagnostico_types.py` → `CLASIFICACION_ACTIVOS` | Mapa ticker → categoría (incl. `LATAM` vs subyacente US) |
| `services/universo_service.py` → `tipo_regla_negocio()` | Tipo efectivo por negocio (RF → universo BYMA → CSV) |

---

## Tests asociados

- `tests/test_recomendacion_capital.py` — cobertura de impacto en ADM (ejemplo internacional con universo `ACCION_LOCAL`).

---

## Referencias cruzadas

| Documento | Contenido |
|-----------|-----------|
| `REGLA_NEGOCIO_UNIVERSO_RV_BYMA.md` | RB-MQ26-RV-001 — fuente BYMA para listado RV |
| `COMITE_CEDEARS_CRITERIOS.md` | CEDEAR: ratio, CCL implícito |
| `COMITE_REGLAS_NEGOCIO_INSTRUMENTOS_AR.md` | Matriz producto |

---

# Regla de negocio — RV solo si el ticker está en BYMA (acciones + CEDEARs)

| Campo | Valor |
|-------|--------|
| **ID** | RB-MQ26-REC-002 |
| **Estado** | Vigente |
| **Ámbito** | Motor `recomendar()` — candidatos de **renta variable** (plan ideal, dilución de concentración, oportunidad táctica MOD) |
| **Relación** | Requiere universo cargado desde BYMA (RB-MQ26-RV-001); coherente con REC-001 (copy) |

## Enunciado (regla)

**No recomendar como renta variable ningún ticker que no figure en el listado BYMA Open Data de `cedears` + `equities` (universo RV del motor).**

- El **catálogo de renta fija** (`es_renta_fija` / `INSTRUMENTOS_RF`) **no** se filtra por este criterio: ON, bonos y letras siguen sus reglas propias.
- Si **no hay** `universo_df` o está vacío, **no** se proponen líneas RV nuevas (solo RF cuando aplique).

## Implementación de referencia (código)

| Componente | Rol |
|------------|-----|
| `services/recomendacion_capital.py` → `_permite_recomendar_rv_segun_universo_byma()` | Filtra dilución, `rest_keys` y filas tácticas MOD |
| `services/byma_market_data.py` → `fetch_universo_rv_byma()` | Fuente del conjunto de tickers válidos |

## Tests asociados

- `tests/test_recomendacion_capital.py` — `test_no_recomienda_rv_tactica_si_ticker_fuera_universo_byma`

---

## Historial de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-04-14 | Regla formalizada; alineación de copy recomendación vs equity local/internacional |
| 2026-04-14 | RB-MQ26-REC-002: RV solo con ticker en BYMA cedears/equities |
