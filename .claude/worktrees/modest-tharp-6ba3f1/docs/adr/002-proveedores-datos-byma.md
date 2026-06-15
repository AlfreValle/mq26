# ADR 002: Evaluación de proveedores de datos BYMA / mercado local

## Estado

Propuesta — decisión comercial/legal pendiente del titular del producto.

## Objetivo

Cerrar la brecha entre “lo que cotiza en BYMA” y “lo que MQ26 puede precificar hoy” (principalmente `yfinance` + manual).

## Opciones (alto nivel)

| Enfoque | Pros | Contras |
|---------|------|---------|
| **Mantener Yahoo + manual** | Costo cero, ya integrado | Cobertura incompleta, retrasos, bonos/FCI mal homogeneizados |
| **Proveedor de datos licenciado** (data vendor con cotizaciones locales) | Calidad institucional, metadatos ISIN/lámina | Costo recurrente, contrato |
| **Integración broker API** (donde el cliente tiene cuenta) | Posiciones y precios alineados al broker | Por cliente; permisos OAuth/API; heterogeneidad |
| **Feed BYMA vía acuerdo institucional** | Máxima alineación regulada | Trámite y costo alto; típico wholesale |

## Recomendación técnica (neutral)

1. **Corto plazo**: endurecer **maestro de instrumentos** (ticker, tipo, moneda, `LAMINA_VN`, ISIN si existe) + fallback y CAFCI ampliado (catálogo en caché).
2. **Medio plazo**: elegir **un** proveedor de referencia para panel BYMA o **API de broker** piloto (Balanz/IOL/etc.) según volumen de clientes.
3. **Largo plazo**: lineage completo y SLA de datos en contrato.

## Competencia (referencia de mercado)

Apps retail y wealth suelen combinar: feed licenciado o datos del propio broker + curación interna. MQ26 sin proveedor adicional no replica ese nivel de completitud.

## Consecuencias si no se adopta proveedor

- Seguirán existiendo tickers sin precio o con precio **teórico** derivado del subyacente (`p_teo` en `data_engine`).
- Renta fija requiere **convención explícita** de lámina en el maestro (ver validación en cartera).

## Referencias

- ADR 001 — inventario de fuentes actuales
- [ADR 003 — Convención de precios y lineage](003-convencion-precios-y-lineage.md) — alineación CEDEAR/bonos vs fuentes indirectas
- [`docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](../product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md) — mapeo campo API Open Data → significado MQ26, escalas ON y REST opcional (**P2-BYMA-01**)
- [`docs/product/BYMA_INGESTA_BD_P2_BYMA02.md`](../product/BYMA_INGESTA_BD_P2_BYMA02.md) — ingesta a `precios_fallback` con misma escala (**P2-BYMA-02**)
- `services/cafci_connector.py` — `obtener_catalogo_fondos_cacheado`
