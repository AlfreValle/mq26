# Regla de negocio **CRÍTICA** — BYMA Open Data (recolección unificada)

| Campo | Valor |
|-------|--------|
| **ID** | **RB-MQ26-OD-CRIT-001** |
| **Prioridad** | **Crítica** (incumplimiento: riesgo de datos inconsistentes, auditoría difícil o comportamiento distinto entre entornos) |
| **Estado** | Vigente |
| **Ámbito** | Cualquier llamada a la API pública **BYMA Open Data** (`open.bymadata.com.ar`, rutas `.../bymadata/free/<tipo>`): listados de mercado, **ONs corporativas** (`corporate-bonds`), **cedears**, **equities**, bonos, letras, etc. |
| **Fuente normativa** | Contrato documentado de BYMA Open Data; implementación MQ26 en `services/byma_market_data.py`. |

---

## Enunciado (regla crítica)

1. **Un solo núcleo de parámetros:** URL base, timeout HTTP, cuerpo JSON del POST (`excludeZeroPxAndQty`, `T2` / `T1` / `T0`), TTL de caché Streamlit aplicable a esas lecturas, `User-Agent`, y umbral heurístico de precio ON (`MQ26_BYMA_ON_PRECIO_UMBRAL_ARS`) **deben** definirse **únicamente** vía `core/byma_open_data_config.py`, leyendo variables de entorno con defaults documentados en **`.env.example`**.

2. **Sin duplicación dispersa:** **No** se introducen constantes duplicadas para la misma API en otros módulos (salvo reexportación explícita autorizada por arquitectura). El cliente HTTP de listados/ON en vivo **consume** ese núcleo.

3. **Timeouts alineados:** El proveedor REST opcional de cotizaciones por lote (`services/byma_provider.py`, `MQ26_BYMA_API_URL`) usa el mismo **orden de magnitud** de timeout por defecto que Open Data (`MQ26_BYMA_TIMEOUT` / `BYMA_HTTP_TIMEOUT_DEFAULT`), salvo necesidad operativa documentada.

4. **Trazabilidad:** Cambios en contrato BYMA o en política de plazos (T+2 vs otros) se reflejan en **un** lugar (`byma_open_data_config` + env), no en N copias.

---

## Implementación de referencia

| Componente | Rol |
|------------|-----|
| `core/byma_open_data_config.py` | Lectura unificada de env para Open Data y timeout HTTP por defecto compartido |
| `services/byma_market_data.py` | `_fetch_tipo`, caché `st.cache_data`, enriquecimiento ON |
| `.env.example` | Documentación de variables `MQ26_BYMA_OPEN_DATA_*` y relacionadas |
| `tests/test_byma_open_data_config.py` | Regresión de defaults y pisos mínimos |

---

## Relación con otras reglas

- **RB-MQ26-RV-001 / RV-002:** el universo RV se arma desde los mismos endpoints; esta regla **CRÍTICA** gobierna **cómo** se llama la API, no el filtro de negocio ARS.
- **ADR:** `docs/adr/002-proveedores-datos-byma.md`, `docs/adr/001-fuentes-de-datos-mq26.md`.

---

## Historial de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-04-14 | Regla **CRÍTICA** formalizada: centralización en `core/byma_open_data_config.py` |
