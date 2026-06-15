# MQ26 — Smoke de producción post-deploy

Verifica que Railway (u otro hosting) esté respondiendo correctamente después de un deploy.

## Uso rápido

```bash
# Contra Railway (reemplazar con tu URL real):
python scripts/smoke_produccion.py --base-url https://mq26-production.up.railway.app

# Contra local (Streamlit en 8502):
python scripts/smoke_produccion.py
```

## Qué verifica

- `GET /_stcore/health` → HTTP 200 (healthcheck de Streamlit).
- Timeout configurable (`--timeout`, default 30 s).

## Manual (flujo mínimo)

1. **Login**: usuario `admin` (o el configurado) + `MQ26_PASSWORD`.
2. **Cliente**: seleccionar uno existente o crear cliente de prueba.
3. **Cartera**: abrir pestaña Cartera; sin traceback.
4. **Demo**: con `DEMO_MODE=true`, clientes precargados según `generate_demo_data`.

## Integración en CI/CD

En `.github/workflows/ci.yml`, el job de deploy puede encadenar (con `continue-on-error` si aún no hay URL):

```yaml
- name: Smoke producción
  run: python scripts/smoke_produccion.py --base-url ${{ secrets.RAILWAY_URL }}
  if: github.ref == 'refs/heads/main'
```

## Interpretación

| Resultado | Significado |
|-----------|-------------|
| `OK: ... → HTTP 200` | Deploy exitoso, app respondiendo. |
| `FAIL: ... → HTTP 5xx` | App arrancó pero Streamlit falla internamente. |
| `FAIL: Connection refused` | App no arrancó (revisar logs en Railway). |
| `FAIL: Timeout` | App muy lenta o host sin recursos. |

## Variables útiles para demos

- `DEMO_MODE=true`
- `DEMO_DB_PATH` (opcional; ver `scripts/demo_launcher.py`)

## Si falla el healthcheck

- Railway: `railway.json` puede definir `healthcheckPath`: `/_stcore/health`.
- Revisar logs del contenedor y variables (`MQ26_PASSWORD`, `PYTHONUNBUFFERED=1`).
