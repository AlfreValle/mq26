---
name: actualizar-datos-referencia
description: Actualiza los datos de referencia mantenidos a mano de MQ26 (serie CCL histórico, catálogo de renta fija, precios fallback, sectores). Usar cuando llegue el resumen mensual, cambien paridades de ONs, o el usuario pida actualizar CCL/catálogo/fallbacks.
---

# Datos de referencia MQ26 — mantenimiento manual

Estos cuatro datasets se actualizan A MANO y son críticos para la calidad de
las recomendaciones. Cada uno tiene su lugar y su verificación.

## 1. Serie CCL histórico (mensual)

- **Dónde**: `core/pricing_utils.py` → dict `CCL_HISTORICO` (clave "AAAA-MM").
- Agregar el mes nuevo al final (fuente: rava/ámbito/BCRA, o resumen Balanz).
- **No extrapolar meses futuros** — `core/fx.py` usa el último conocido o el spot.
- Verificar: `python -m pytest tests/test_fx.py tests/test_pricing_utils* -q --no-cov`

## 2. Catálogo de renta fija (ante cambios de mercado)

- **Dónde**: `core/renta_fija_ar.py` → `INSTRUMENTOS_RF`.
- Actualizar por instrumento: `paridad_ref`, `tir_ref`, `fecha_ref`, `activo` (False si dejó de cotizar), `ccl_ref` / `precio_ars_ref` si se recalculan.
- La conversión paridad→ARS es automática vía `precio_referencia_ars_desde_catalogo()` — NO hardcodear precios derivados.
- Verificar: `python -m pytest tests/test_renta_fija_ar.py tests/test_on_pricing.py -q --no-cov`

## 3. Precios fallback hard (cuando se renueven)

- **Dónde**: `services/cartera_service.py` → `PRECIOS_FALLBACK_ARS`.
- Actualizar el comentario con la fecha/fuente ("Balanz DD/MM/AAAA").
- Para ONs el valor es ARS por 1 VN (paridad% × CCL / 100) — mantener coherente con el catálogo RF.

## 4. Sectores (al agregar tickers al universo)

- **Dónde**: `data/sectores.csv` (editable sin deploy; config.py lo carga con fallback).
- Ratio CEDEAR nuevo: `config.py` → `RATIOS_CEDEAR` + idealmente el Excel de universo.
- El InstrumentMaster consolida todo — verificar con:
  `python -c "from core.instrument_master import get_master; print(get_master().get('TICKER'))"`

## Cierre

Tras cualquier actualización: suite rápida de los módulos tocados + commit
`chore(datos): actualizar <qué> a <fecha/fuente>`.
