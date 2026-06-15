# Runbook de Incidentes por Degradación

Este runbook define el procedimiento operativo cuando MQ26 entra en modo degradado parcial (no caída total), para proteger capital del cliente y mantener trazabilidad.

## 1) Clasificación rápida

- `ALTA`: riesgo de decisiones con datos incompletos o autenticación degradada.
- `MEDIA`: degradación controlada con fallback disponible.
- `OK`: sin degradaciones activas detectadas.

## 2) Señales monitoreadas en el tablero

- `cobertura_precios_baja`
  - Trigger: cobertura de precios menor a 95% o tickers sin precio.
  - Impacto: valuación incompleta / sesgada.
- `circuit_breaker_yfinance_activo`
  - Trigger: 3+ fallos en 60s con cooldown activo.
  - Impacto: menor disponibilidad de precios live.
- `auth_bd_degradado`
  - Trigger: bandera `*_degraded_auth` activa.
  - Impacto: login BD degradado con fallback local.
- `tab_inversor_modo_degradado`
  - Trigger: `inv_degradado_ui=True`.
  - Impacto: cálculos auxiliares con fallback por excepciones no fatales.

## 3) Procedimiento de respuesta (15 minutos)

1. Confirmar severidad en `Admin -> Incidentes`.
2. Si hay `ALTA`, pausar confirmaciones masivas y operaciones no urgentes.
3. Revisar cobertura de precios y lista de tickers sin precio.
4. Verificar estado de yfinance (circuit breaker + cooldown).
5. Revisar logs estructurados (`degradacion:*`) para identificar evento raíz.
6. Aplicar mitigación:
   - precios: fallback BD/PPC + recálculo;
   - auth: validar DB de usuarios y conectividad;
   - UI: refrescar sesión y repetir cálculo.
7. Registrar en bitácora: hora, evento, acción, resultado.

## 4) Criterio de recuperación

Se considera recuperado cuando:

- no hay eventos `ALTA`,
- cobertura de precios >= 95%,
- circuit breaker inactivo,
- login BD y cálculos críticos operan sin nuevas banderas.

## 5) Postmortem mínimo (en el día)

- Evento raíz y módulo afectado.
- Tiempo total degradado.
- Decisiones operativas tomadas.
- Fix permanente propuesto (código/test/runbook).
