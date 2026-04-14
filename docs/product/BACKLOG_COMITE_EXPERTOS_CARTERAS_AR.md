# Backlog Comité Expertos Carteras AR

Estado: activo  
Objetivo: cerrar riesgos de negocio, confianza y trazabilidad antes de release Go.

**Pendientes posteriores (inventario maestro P0–P3, por rol y por dominio):**  
[`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md)

## P0 (crítico)

- [x] P0-01: Contrato de unidad/moneda en motor de salida + quality flags (`services/motor_salida.py`)
- [x] P0-02: VaR/CVaR con FX integrado en flujos reales (paso de `ccl_series` desde callers)
- [x] P0-03: Persistencia BD SSOT fase 2 (repository + dual-write controlado)
- [x] P0-04: Idempotencia fuerte de imports broker/Gmail por fingerprint
- [x] P0-05: Auditoría explícita simulación vs ejecución en recomendaciones

## P1 (alto)

- [x] P1-01: Trazabilidad de fuente de precio por ticker en UI (LIVE/FALLBACK_BD/FALLBACK_HARD/FALLBACK_PPC)
- [x] P1-02: Endurecimiento completo deny-by-default para utilidades sensibles restantes
- [x] P1-03: Logging estructurado en tabs y servicios con `except` amplios
- [x] P1-04: Suite de integración por rol en entrypoints críticos

## P2 (medio)

- [x] P2-01: Cierre de migración UX inline→clases en tabs prioritarios
- [x] P2-02: Consolidación final de tipografías y tokens UI
- [x] P2-03: Validadores CI docs↔entrypoint↔runbook

## Orden de ejecución

1. P0-01
2. P0-02
3. P0-03
4. P0-04
5. P0-05
6. P1-01..P1-04
7. P2-01..P2-03

## Criterio de Go

- Cero pérdidas de trazabilidad en operaciones.
- Cálculo de riesgo y señales sin ambigüedad de unidad/moneda.
- Persistencia canónica en BD con reconciliación estable.
- Evidencia de tests críticos en verde.

## Lanzamiento al mercado (otros comités)

Cuando el corte de producto deba alinearse con **entrega técnica** y **comunicación**, usar el documento de convergencia y la skill de sala conjunta: [COMITE_CONVERGENCIA_Y_LANZAMIENTO.md](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) (skills `comite-implementacion-mq26`, `comite-marketing-mq26`, `comite-convergencia-lanzamiento-mq26` en `.cursor/skills/`). **Índice y avance de todos los comités:** [COMITES_MQ26_INDICE_Y_AVANCE.md](./COMITES_MQ26_INDICE_Y_AVANCE.md).
