# ADR 003: Convención de precios por instrumento y lineage mínimo

## Estado

**Propuesta** — pendiente validación de negocio y refactor incremental en motores de precio.

## Contexto

MQ26 mezcla **acciones locales, CEDEARs, bonos/letras, FCI y efectivo**, con fuentes heterogéneas (Yahoo, maestro, BD, CAFCI). Sin reglas explícitas:

- Los **CEDEARs** pueden mostrarse por error con lógica del **subyacente en USD** en lugar de la **cotización local en ARS** en BYMA, rompiendo barras de progreso (compra → actual → target).
- Los **bonos** cotizan como precio por cada **100 o 1.000** de nominal; el valor económico depende de **`LAMINA_VN`** (u homólogo en maestro) además del precio de mercado.
- Los usuarios y la competencia esperan **transparencia**: de dónde sale cada número y si está **retrasado u obsoleto**.

Este ADR acota **qué debe significar “precio”** en cada tipo y **qué metadatos mínimos** acompañan cada cotización mostrada.

## Decisiones propuestas

### 1. Unidad de precio por clase de activo (para UI y P&L coherente)

| Clase | Moneda de cotización mostrada | Regla |
| --- | --- | --- |
| Acción local BYMA | ARS | Precio último disponible de la fuente configurada; **1 título = 1 unidad** salvo ajustes corporativos explícitos. |
| CEDEAR | **ARS** | **Siempre** la cotización del CEDEAR en mercado local (típicamente ticker `.BA`), no el precio del subyacente en USD como “precio actual” de la posición. El subyacente puede mostrarse como **referencia** en otra columna o tooltip. |
| Bono / letra (renta fija) | Según maestro (ARS/USD…) | Precio de mercado en la **convención del maestro**; valor nominal económico = función de **cantidad × precio × factor lámina** (`LAMINA_VN` o default documentado). |
| FCI | ARS (cuotaparte) | Precio/cuotaparte según CAFCI o maestro; clase de fondo alineada a catálogo. |
| Efectivo / moneda | ARS / USD explícito | Sin mezclar columnas sin etiqueta de moneda. |

### 2. Lineage mínimo por cotización (contrato lógico)

Todo valor presentado como “precio de mercado” o “último” debería poder resolverse a un struct conceptual:

```text
valor_numérico
moneda_iso          # ARS | USD | ...
fuente_codigo       # YFIN | MAESTRO | BD_FALLBACK | CAFCI | MANUAL | ...
obtenido_en_utc     # timestamp de la lectura
validez             # OK | STALE | ERROR | PEG
delay_minutos_estimado  # nullable; p.ej. 15 para delayed
nota_corta          # opcional; p.ej. ticker_no_encontrado
```

Esto **no obliga** una implementación en DB en el primer merge; puede vivir primero en memoria/DF y UI. La dirección es converber con **A02/A44** del [BACKLOG_MOSCOW.md](../BACKLOG_MOSCOW.md).

### 3. Degradación

- Si la fuente primaria falla: usar siguiente nivel según [ADR-001](001-fuentes-de-datos-mq26.md) y marcar `validez=STALE` o `PEG` según corresponda.
- Nunca combinar en la **misma barra de progreso** precios de **convenciones distintas** (ej. PPC en ARS vs “actual” en USD del subyacente).

## Consecuencias en código (cuando se implemente)

Áreas probables (sin orden estricto):

- [`core/price_engine.py`](../../core/price_engine.py) — selección de quote por instrumento y fuente.
- [`1_Scripts_Motor/data_engine.py`](../../1_Scripts_Motor/data_engine.py) — batch Yahoo; asegurar CEDEAR usa `.BA` local para “precio posición”.
- [`services/cartera_service.py`](../../services/cartera_service.py) — consolidación posición neta, PPC, targets y **columnas mostradas**.
- [`core/pricing_utils.py`](../../core/pricing_utils.py) — helpers tipo CEDEAR vs bono; validación lámina.
- [`core/db_manager.py`](../../core/db_manager.py) — si se persiste lineage: tabla o columnas en `precios_fallback` / snapshot (decisión pendiente).

## Decisiones abiertas

1. ¿Persistir lineage solo en **sesión** o en **BD** para auditoría?
2. ¿Unificar naming en salidas (`precio_actual_ars` vs `px_mercado`) en un **único contrato** exportable (ver A26 en backlog)?
3. ¿Tabla `instrument` maestra central (A01) o seguir extendiendo CSV transaccional?

## Referencias

- [ADR-001 — Fuentes de datos](001-fuentes-de-datos-mq26.md)
- [ADR-002 — Proveedores BYMA](002-proveedores-datos-byma.md)
- [Análisis producto y benchmark 2026](../PRODUCTO_ANALISIS_FUENTES_BACKLOG_2026.md)
- [BACKLOG_MOSCOW.md](../BACKLOG_MOSCOW.md) — A01, A02, A04, A13, A26, A44, D27, D45, D47, U16
