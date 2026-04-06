# ADR 001: Fuentes de datos MQ26 (operación y cumplimiento)

## Estado

Aceptado — documento operativo vivo; actualizar cuando cambie un conector.

## Contexto

MQ26 agrega precios, cartera y FCI desde varias fuentes no oficiales BYMA. Hace falta una referencia única para soporte, auditoría y decisiones de proveedor.

## Fuentes activas (código)

| Fuente | Qué aporta | Latencia típica | Fallback |
|--------|------------|-----------------|----------|
| Yahoo Finance (`yfinance`) | Cierre `.BA`, subyacentes US, GGAL/GGAL.BA para CCL | Minutos a días (según ticker) | `PRECIOS_FALLBACK_ARS`, BD `precios_fallback` |
| Maestro CSV/XLSX | Posiciones, PPC, tipo, fechas | Local instantáneo | — |
| SQLite/Postgres | Fallback precios, config, clientes | Local | — |
| API CAFCI (`api.cafci.org.ar`) | Catálogo FCI, cuotapartes vía ficha | Red ~1–15 s por fondo | Heurística score |
| Gmail + parsers | Boletos Balanz/Bull Market | Manual / batch | — |
| Tabla `CCL_HISTORICO` en código | CCL por mes para costo histórico | Estática (requiere mantenimiento manual) | CCL actual / `CCL_FALLBACK` |

## Limitaciones legales y de uso

- **Yahoo Finance**: datos de terceros; términos de Yahoo aplican; no es feed oficial BYMA. Uso en producción implica disclaimer al usuario sobre posible peg, errores y retraso.
- **CAFCI**: API pública documentada en cafci.org.ar; respetar `User-Agent` identificable y no saturar (el código usa pausas en escaneos masivos).
- **BYMA**: no hay integración licenciada con catálogo oficial de negociación en este repositorio; cualquier cotización “tipo mercado” fuera de Yahoo/BD es responsabilidad del operador.
- **Scraping** de portales de noticias/brokers no está implementado de forma genérica; si se agrega, debe revisarse TOS del sitio.

## Observabilidad recomendada

- Registrar **fuente y timestamp** por precio mostrado (lineage) — roadmap.
- Circuit breaker `yfinance` ya expone estado en UI (sidebar).

## Consecuencias

- La **cobertura** de instrumentos es la unión de: tickers que Yahoo lista + overrides manuales + FCI mapeados a CAFCI.
- No se garantiza cobertura del **universo completo BYMA** sin un proveedor adicional (ver ADR 002).

## Referencias en código

- `1_Scripts_Motor/data_engine.py` — `obtener_precios_cartera`, `cargar_transaccional`
- `core/price_engine.py` — jerarquía de precios
- `services/cartera_service.py` — `PRECIOS_FALLBACK_ARS`, `resolver_precios`
- `services/cafci_connector.py` — CAFCI
- `services/market_connector.py` — CCL MEP
- `gmail_reader.py` — import broker

## Ver también

- [Backlog priorizado (MoSCoW)](../BACKLOG_MOSCOW.md) — mejoras de datos, diseño y UX enlazables a issues.
- [Análisis de fuentes y backlog competitivo 2026](../PRODUCTO_ANALISIS_FUENTES_BACKLOG_2026.md) — narrativa mercado AR, benchmark producto y crosswalk al MoSCoW.
- [ADR-003 — Convención de precios y lineage](003-convencion-precios-y-lineage.md) — reglas CEDEAR/bonos y lineage mínimo propuesto.
