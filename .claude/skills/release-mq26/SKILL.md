---
name: release-mq26
description: Checklist de pre-release/deploy de MQ26 — verifica las 5 puertas de CI localmente, smoke de la app headless y estado del árbol antes de pushear. Usar cuando el usuario pida "deploy", "release", "pushear a main" o "preparar para producción".
---

# Pre-release MQ26

CI tiene 5 puertas (ruff bloqueante, cobertura ≥60, mypy-strict H06, mypy
informativo, smoke streamlit). Reproducirlas localmente ANTES de pushear
evita el ciclo push-rojo-fix.

## 1. Árbol limpio y rama correcta

```bash
git status --short   # nada sin commitear que deba entrar
git log --oneline -5 # los commits son atómicos y con mensaje claro
```
Deploy a Railway solo dispara en push a `main`. PRs corren todas las puertas.

## 2. Las 5 puertas, localmente

```bash
python -m ruff check . --exclude .claude                       # puerta 1
python -m pytest tests/ -q -m "not integration and not slow" -n 4   # puerta 2 (CON cobertura: gate 60%)
mypy core/hrp_weights.py core/deflated_sharpe.py core/corporate_actions_proxy.py core/after_tax.py core/hypothesis_metrics.py --follow-imports=silent   # puerta 3 (bloqueante)
mypy core services 2>&1 | tail -1                              # puerta 4 (informativa, ~149 errores conocidos)
```

## 3. Smoke streamlit headless (puerta 5)

```bash
streamlit run run_mq26.py --server.port 8502 --server.headless true --browser.gatherUsageStats false &
# esperar y verificar:
curl -sf http://127.0.0.1:8502/_stcore/health && echo OK
python scripts/smoke_produccion.py --base-url http://127.0.0.1:8502
# matar el proceso al terminar
```
En Windows: lanzar con `run_in_background` y matar por PID.

## 4. Datos de referencia al día

- ¿CCL_HISTORICO tiene el mes corriente? (skill actualizar-datos-referencia)
- ¿`fecha_ref` del catálogo RF no está vencida hace meses?
- ¿PRECIOS_FALLBACK_ARS tiene fecha razonable en el comentario?

## 5. Post-push

- Verificar CI verde en GitHub (`gh run list --limit 3`).
- Si deploy a main: smoke post-deploy corre solo (RAILWAY_URL); verificar el job.

## Reglas

- **Nunca** `--no-verify` ni saltear hooks.
- Si una puerta local pasa y CI falla: comparar versiones de herramienta
  (caso conocido: rev de ruff en pre-commit vs local).
