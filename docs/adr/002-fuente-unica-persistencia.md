# ADR 002 — Fuente única de persistencia (CSV/Excel/DB)

## Estado
Propuesto para implementación inmediata.

## Contexto
Hoy conviven tres mecanismos de persistencia:
- CSV transaccional (`Maestra_Transaccional.csv`)
- Excel operativo/histórico (`Maestra_Inversiones.xlsx`)
- Base de datos (`master_quant.db` o PostgreSQL)

Esta mezcla genera riesgo de:
- divergencia entre fuentes,
- sobreescritura accidental de histórico,
- auditoría incompleta,
- errores de trazabilidad en P&L y recomendaciones.

## Decisión
Adoptar **BD como única fuente de verdad** para operaciones, posiciones derivadas y metadata crítica.

Reglas:
- Escrituras: solo a BD.
- Lecturas de negocio: BD.
- CSV/Excel: solo como **import/export** y reportes, nunca como estado canónico.
- Todo cambio de operación debe quedar auditado con `who/when/what`.

## Modelo objetivo (alto nivel)
- `operaciones` (evento atómico):
  - id, tenant_id, cartera_id, ticker, tipo_operacion, cantidad, precio_unit_ars, precio_unit_usd, moneda_precio, fecha_operacion, fuente, metadata_json, created_at, created_by
- `clientes`, `carteras`, `usuarios`, `roles` (catálogo)
- `precios_cache` (fuente + timestamp + calidad)
- `audit_log` (acción, actor, entidad, before/after hash)

Invariantes:
- `precio_unit_ars` y `precio_unit_usd` siempre unitarios.
- `cantidad` firmada (compra positiva, venta negativa) o `tipo_operacion` + valor absoluto, pero no mixto.
- idempotencia por `operation_fingerprint` en imports.

## Plan de migración final

### Fase 1 — Hardening (1-2 días)
- Bloquear sobreescritura total de Excel/CSV en flujos UI (ya iniciado).
- En imports (broker/email), persistir por merge idempotente.
- Agregar logs estructurados de degradación y errores de persistencia.
- Agregar backups automáticos previos a migración masiva.

### Fase 2 — Dual-write controlado (3-5 días)
- Introducir capa `repository` única:
  - `save_operaciones()`, `load_operaciones()`, `merge_import()`.
- Escribir en BD y, temporalmente, exportar CSV/Excel como artefacto derivado.
- Validar consistencia diaria BD vs CSV exportado (checksum + conteo).

### Fase 3 — Cutover a BD (2-4 días)
- Cambiar lectura principal de `DataEngine` y tabs a BD.
- Mantener CSV/Excel solo para export.
- Activar feature flag: `MQ26_PERSISTENCE_MODE=db_only`.

### Fase 4 — Decomisión de legado (2-3 días)
- Desactivar paths de escritura directa a CSV/Excel.
- Mantener migradores de importación y scripts de compatibilidad.
- Publicar runbook de operación y recuperación.

## Criterios de aceptación
- 0 sobrescrituras de archivos canónicos en UI.
- 100% de operaciones nuevas persistidas en BD con trazabilidad.
- Reconciliación diaria sin diferencias (o diferencias explicadas) por 7 días.
- Tests de integración por rol y por flujo crítico en verde.

## Riesgos y mitigación
- Riesgo: regresión funcional en tabs legacy.
  - Mitigación: feature flags + smoke tests por tab.
- Riesgo: migración parcial de datos históricos.
  - Mitigación: script de backfill idempotente + reporte de filas rechazadas.
- Riesgo: performance en consultas.
  - Mitigación: índices por tenant/cartera/ticker/fecha.

## Impacto esperado
- Mayor confiabilidad operativa.
- Auditoría consistente para comité y compliance.
- Menor riesgo de errores que afecten dinero del cliente.
