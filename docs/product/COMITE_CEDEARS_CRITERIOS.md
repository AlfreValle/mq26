# Comité de expertos — CEDEARs: criterios, ratio, CCL implícito y límites

**Objetivo:** que modelos de IA y analistas traten el CEDEAR como **réplica sintética** del activo subyacente (principalmente EE. UU.), no como una acción aislada en pesos. Coherente en espíritu con `COMITE_ON_USD_CRITERIOS_LIMITES.md` (unidades y fuentes) y con la lógica de renta fija (flujos y convenciones explícitas).

---

## 1. Triple variable (siempre junta)

| Variable | Qué es |
|----------|--------|
| **Subyacente** | Ticker y mercado de origen (p. ej. NYSE/NASDAQ). |
| **Ratio de conversión** | Cuántos CEDEAR equivalen a **1 acción** del subyacente (definición **oficial** del emisor/agente). |
| **Tipo de cambio implícito** | Cómo el precio local en ARS y el precio en USD del subyacente implican un **CCL** (Contado con Liquidación). |

Sin las tres, el análisis de “caro/barato” suele ser **inválido**.

---

## 2. Ratio de conversión (regla de oro)

- **N CEDEARs = 1 acción** es la convención habitual en Argentina (ej. 20:1 en AAPL).
- **Antes** de comparar precios o arbitrar, obtener el **ratio oficial** (tabla del emisor de CEDEARs, p. ej. agente de custodia).
- Si la fuente expresa el ratio en forma inversa (acciones por CEDEAR), **adaptar** la fórmula; no asumir.

**Equivalente en ARS de una acción:**

`Precio_CEDEAR_ARS × N` (con N = CEDEARs por acción).

---

## 3. CCL implícito

**Fórmula (cuando el ratio es “CEDEARs por acción”):**

`CCL_implícito = (Precio_CEDEAR_ARS × ratio) / Precio_subyacente_USD`

- Comparar con el **CCL de mercado** del mismo día/ventana (misma referencia que uses para FX).
- Un CCL implícito **muy por debajo** del mercado puede indicar CEDEAR **barato en pesos** (u otros factores: última operación, spread, horario NY vs. BA).

**Caveats:** no mezclar **última operación** con **cierre**; horarios cruzados generan ruido; **spread** y **pocas operaciones** distorsionan el implícito.

---

## 4. El subyacente manda

- Priorizar **noticias, fundamentos y técnico** del activo en **mercado de origen**.
- El CEDEAR local puede tener **poco volumen** en momentos puntuales; el precio **tiende** a alinear subyacente × ratio × FX, con fricción local.

---

## 5. Dividendos

- Si el subyacente paga dividendos, el tenedor del CEDEAR puede recibir flujos según **regimen del agente** y **tipo de cuenta** (no universalizar “siempre en cable” sin verificar).
- En análisis de precio: tener en cuenta **fecha ex-dividend** (el precio de mercado suele reflejar el evento).

---

## 6. Liquidez y spread

- Antes de sugerir operación: revisar **volumen** y **bid-ask**.
- Heurística orientativa: **spread alto** o **volumen bajo** → advertir **costo de ejecución y salida** (el umbral fijo en % es discrecional; documentar la fuente).

---

## 7. Límites típicos en sistemas (MQ26 / datos)

- Ratios y CCL implícito pueden **no** estar en el motor; si el producto no los carga, el modelo debe **pedir fuente** o **no** afirmar arbitrage sin datos.
- No confundir **CEDEAR** con la **acción en USD** sin **ajustar ratio**.

---

## Prompt sugerido (agentes / Cursor)

Tratá los CEDEARs como instrumentos derivados sintéticos del subyacente. Para cada ticker local: (1) identificá ticker y mercado del subyacente; (2) obtené el **ratio oficial** (CEDEARs por acción) de la entidad emisora; (3) calculá **CCL implícito = (P_CEDEAR_ARS × ratio) / P_subyacente_USD** y comparalo con CCL de mercado; (4) fundamentá con noticias y datos del **activo base**; (5) mencioná **ex-dividend** si aplica; (6) antes de inferir operación, revisá **volumen y spread**. No confundas CEDEAR con la acción cotizada en USD sin ajustar ratio.

---

## Referencias internas (cuando existan en el repo)

- Scoring / universo: `services/scoring_engine.py` (tipos CEDEAR, series Yahoo).
- Conectores de mercado: `services/market_connector.py` (CCL), según configuración del entorno.
