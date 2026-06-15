# BYMA: campos, escalas y uso en MQ26 (P2-BYMA-01)

**Versión:** 1.1 · **Fecha:** 2026-04-10  
**Implementación de referencia:** `services/byma_market_data.py`, `services/byma_provider.py`

---

## 1. Propósito

Documentar **qué campos** consume MQ26 desde fuentes relacionadas con BYMA, **en qué unidad** quedan en el motor/UI y **dónde** puede haber heurísticas (÷100, paridad %, etc.). Sirve para auditoría, soporte y alineación futura con **documentación comercial BYMA** o contratos de Market Data.

**Importante:** MQ26 **no** replica el manual completo de ningún proveedor. Los nombres de campo JSON siguen lo observado en respuestas de **Open Data** (`open.bymadata.com.ar`) y pueden cambiar si BYMA actualiza el servicio. Antes de producción institucional, contrastar con la documentación vigente en el sitio oficial y el contrato licenciado.

### Enlaces útiles (verificar en origen; pueden moverse)

| Recurso | URL |
|--------|-----|
| Open BYMA Data (feed usado en listas tiempo real) | `https://open.bymadata.com.ar` |
| BYMADATA (portal informativo) | `https://www.bymadata.com.ar/` |
| Productos BYMA / APIs (comercial) | `https://www.byma.com.ar/byma-apis` (también versión EN en el sitio) |
| Portal de desarrolladores BYMA | `https://apiportal.byma.com.ar/` |

Las APIs **comerciales** (Market Data licenciado, clearing, etc.) tienen contrato y esquema distintos al endpoint **público** documentado abajo.

---

## 2. Resumen de fuentes BYMA en el código

| Fuente | Configuración | Módulo | Uso en MQ26 |
|--------|----------------|--------|-------------|
| **Open Data** (HTTP público) | Sin API key; URL fija en código | `services/byma_market_data.py` | Listas de instrumentos por tipo (acciones, CEDEARs, bonos, letras, ONs); enriquecimiento de **ONs** con paridad/precio |
| **REST genérico** (opcional) | `MQ26_BYMA_API_URL`, `MQ26_BYMA_API_KEY`, `MQ26_BYMA_AUTH_HEADER`, `MQ26_BYMA_TIMEOUT` | `services/byma_provider.py` | Lote de **precios ARS** vía `POST …/cotizaciones`; integrado en `core/price_engine.py` y relleno en `cartera_service` |
| Catálogo / maestro | Excel/CSV, `core/renta_fija_ar.py` | Varios | Metadatos RF cuando no hay live |

---

## 3. BYMA Open Data — endpoint implementado

### 3.1 Petición

- **Método:** `POST`
- **Base URL (código):** `https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free`
- **Ruta por tipo:** `/{endpoint}` donde `endpoint` ∈  
  `equities` · `cedears` · `government-bonds` · `lebac-notes` · `corporate-bonds`

**Cuerpo JSON (fijo en MQ26):**

```json
{
  "excludeZeroPxAndQty": true,
  "T2": true,
  "T1": false,
  "T0": false
}
```

Interpretación operativa: instrumentos con precio/cantidad no nulos; liquidación **T+2** habilitada en el filtro del cuerpo (según convención del feed).

**Cabeceras enviadas:** `Content-Type: application/json`, `Accept: application/json`, `User-Agent: MQ26Terminal/1.0`.

### 3.2 Respuesta

El código acepta:

- una **lista** JSON de objetos (uno por instrumento), o  
- un objeto con clave **`data`** que contiene esa lista.

Cada elemento se trata como diccionario de campos en **inglés** (según feed).

---

## 4. Campos JSON (Open Data) → MQ26

### 4.1 Tabla general (listas “Mercado BYMA” en UI)

Columnas mostradas tras `rename` en `_COLS_DISPLAY` de `byma_market_data.py`:

| Campo API (JSON) | Columna UI MQ26 | Significado en MQ26 | Notas de escala |
|------------------|-----------------|---------------------|-----------------|
| `symbol` | Ticker | Código de negociación | Fallback: `ticker` si no hay `symbol` |
| `description` | Descripción | Texto del instrumento | Fallback: `descripcion` |
| `lastPrice` | Último | Último operado / cotización mostrada por el feed | **ARS** en listas generales; ver §5 para ONs |
| `variationRate` | Var. % | Variación del día en % | Numérico; coloreado en UI |
| `openingPrice` | Apertura | Precio de apertura | ARS |
| `max` | Máximo | Máximo del día | ARS |
| `min` | Mínimo | Mínimo del día | ARS |
| `volumeAmount` | Vol. Nominal | Volumen nominal | Entero/número según feed |
| `quantityBuy` | Comp. | Cantidad compradora (si viene) | — |
| `quantitySell` | Venta | Cantidad vendedora (si viene) | — |
| `closingPrice` | Cierre ant. | Cierre anterior | ARS |
| `settlementType` | Plazo | Tipo de liquidación / plazo | Texto |

Campos ausentes en una respuesta concreta simplemente no aparecen en el DataFrame.

### 4.2 Uso interno ON (`corporate-bonds`) — `fetch_on_byma_live`

Para cada fila se guarda un subconjinto:

| Campo API | Uso en MQ26 |
|-----------|-------------|
| `symbol` / `ticker` | Clave del diccionario (ticker en mayúsculas) |
| `lastPrice` | Precio crudo antes de normalizar (§5) |
| `closingPrice` | Cierre para calcular variación si falta `variationRate` |
| `variationRate` | Variación % del día |
| `volumeAmount` | Copiado a salida enriquecida como volumen |
| `description` | `descripcion_byma` |
| `settlementType` | Conservado en crudo |

---

## 5. Escalas y heurísticas — ON USD (obligaciones negociables)

El motor de cartera y renta fija asume **ARS por 1 nominal USD** para coherencia con PPC y órgenes (ver `cartera_service`, `core/unit_contracts`, tests `tests/test_byma_market_data.py`).

### 5.1 `_normalizar_lastprice_on_byma(px_raw, ccl)`

- Si el precio en **paridad implícita** “completa” sería absurda (>500 % en cierto sentido) pero **px/100** da paridad típica ON (≈35–220 %), se interpreta que el feed trajo **escala ×100** respecto de ARS por 1 nominal y se usa **`px/100`**.

### 5.2 `_paridad_pct_desde_precio_on(px, ccl)`

- Valores muy bajos de `px` (< umbral `_PRECIO_UMBRAL_ARS`) se interpretan como **% de paridad directo**.
- En caso contrario se distingue si `px` representa ARS por **1** o por **100** nominales USD usando rangos de **px/CCL** y **px/CCL×100** frente a paridades habituales de ON.

**Salida de `enriquecer_on_desde_byma(ccl)`** (por ticker):

| Clave interna MQ26 | Significado |
|---------------------|-------------|
| `paridad_ref` | Paridad % sobre nominal USD (ej. 101,5 = 101,5 %) |
| `var_diaria_pct` | Variación diaria % (del feed o calculada vs cierre) |
| `precio_ars` | **ARS por 1 USD nominal** (tras normalización) |
| `volumen` | `volumeAmount` crudo |
| `descripcion_byma` | Texto del feed |
| `fecha_ref` | Marca de tiempo local de la consulta |
| `fuente` | Constante `BYMA_LIVE` |

Estas claves alimentan `core/renta_fija_ar` (enriquecimiento de panel), `ui/tab_inversor`, etc., siempre con el mismo contrato de unidad documentado en ADR de precios.

---

## 6. Proveedor REST opcional (`MQ26_BYMA_API_URL`)

**No** es Open Data: es un contrato **configurable** para un tercero o proxy interno.

| Aspecto | Valor en MQ26 |
|---------|----------------|
| Endpoint | `POST {MQ26_BYMA_API_URL}/cotizaciones` |
| Body | `{"tickers": ["GGAL", "AL30", …]}` |
| Respuesta esperada | Objeto con precios en `precios` **o** `prices` **o** `data` (dict ticker → número) |
| Unidad | **ARS por unidad negociada** en el mercado local (misma convención que el proveedor devuelva; MQ26 solo convierte a `float` por ticker) |

Si la URL no está definida o la llamada falla, se devuelve `{}` sin romper la app.

---

## 7. Alineación con documentación comercial BYMA

| Tema | En MQ26 hoy | Recomendación si se licencia API oficial |
|------|-------------|------------------------------------------|
| Esquema JSON | Inferido del feed Open Data público | Mapear campo a campo contra manual del proveedor; versionar cambios |
| Escala de precios RF | Heurísticas ON documentadas en §5 | Sustituir o confirmar con documentación de “último” / “paridad” del producto contratado |
| Condiciones de uso | Tráfico anónimo al endpoint público | Revisar términos en `byma.com.ar`, portal de APIs y contrato |

---

## 8. Ingesta propia en BD (P2-BYMA-02)

Precios volcados por ETL/broker a `precios_fallback` deben usar la **misma** normalización ON USD que §5. Ver **[`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md)** y `services/precios_mercado_ingest.py` / `normalizar_precio_ars_on_usd_desde_feed_o_broker`.

---

## 9. Referencias en el repo

- [`docs/adr/001-fuentes-de-datos-mq26.md`](../adr/001-fuentes-de-datos-mq26.md)
- [`docs/adr/002-proveedores-datos-byma.md`](../adr/002-proveedores-datos-byma.md)
- [`docs/adr/003-convencion-precios-y-lineage.md`](../adr/003-convencion-precios-y-lineage.md)
- [`docs/SOURCES.md`](../SOURCES.md)
- [`BYMA_INGESTA_BD_P2_BYMA02.md`](./BYMA_INGESTA_BD_P2_BYMA02.md) — pipeline BD / ETL

---

## 10. Semántica ficha RF (P2-RF-01): TIR de referencia vs TIR al precio

La UI unificada (`ficha_rf_minima_bundle` + `render_ficha_rf_minima`) muestra dos conceptos distintos. Convención de **paridad %** sobre nominal USD: ver §5 y `core/renta_fija_ar.py` (`ON_USD_PARIDAD_BASE_VN`).

| Campo en bundle / pantalla | Origen | Qué es |
|----------------------------|--------|--------|
| **TIR ref. %** | Catálogo `INSTRUMENTOS_RF` → `tir_ref` | **Referencia educativa** fijada en el maestro interno (fecha / punto de anclaje del catálogo). No pretende ser la TIR de mercado “oficial” del día ni sustituye prospecto, custodio o calculadora de tesorería. |
| **Paridad ref. %** | Catálogo → `paridad_ref` | Paridad de referencia asociada a esa misma fila de catálogo (misma unidad que la paridad de mercado: % sobre nominal USD para ON/BONO USD). |
| **TIR al precio % (estim.)** | `tir_al_precio(ticker, paridad_compra)` en `core/renta_fija_ar.py` | Estimación **heurística** a partir de la **paridad de mercado** (o implícita desde precio/CCL en cartera) frente a `paridad_ref`: si la diferencia (en valor absoluto) entre ambas paridades es **menor que 0,1** puntos porcentuales, la TIR al precio coincide numéricamente con **TIR ref.**; si no, se aplica `TIR_est ≈ tir_ref − 0,08 × (paridad_mercado − paridad_ref)` y se acota a valores no negativos. Es una **regla simple** para coherencia visual entre precio y rendimiento esperado aproximado; **no** es duración-modificada ni precio limpio/sucio del bono. |

**Paridad “de mercado” en cada pantalla**

- **Monitor ON USD:** `paridad_ref` en el panel sale del enriquecimiento BYMA (`enriquecer_on_desde_byma`), ya normalizado según §5; columna **Ajuste ×100 BYMA** cuando aplicó heurística ÷100 (P2-RF-04).
- **Cartera / inversor:** prioridad a datos **live** del diccionario BYMA (`paridad_ref`, `precio_ars`, `escala_div100`); si faltan, paridad implícita ON/BONO USD con `PRECIO_ARS` y CCL, distinguiendo fila con **ESCALA_PRECIO_RF** (÷100 vs PPC) según `ui/tab_cartera.py` / fila agregada.

**Motivos de degradación** (`tir_a_precio_motivo` en el bundle): sin `tir_ref` en catálogo, sin paridad de mercado usable, etc.; la UI muestra texto en lugar de un número.

**Disclaimer:** contenido educativo y de transparencia operativa; no constituye recomendación personalizada ni promesa de resultado.

---

*Documento generado para cierre P2-BYMA-01 (tabla campo API → significado MQ26 + enlaces a documentación pública BYMA/BYMADATA). §8 P2-BYMA-02. §10 P2-RF-01 (semántica TIR ficha).*
