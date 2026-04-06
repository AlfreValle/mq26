# MQ26 — Operaciones: backup y monitoreo

## Backup SQLite (local y Railway)

### Local — antes de cada demo o migración

```bash
python scripts/backup_sqlite_mvp.py
```

Suele crear copias bajo `0_Data_Maestra/backups/` (ver docstring del script para la ruta exacta según tu `config`).

### Railway — opciones

**Opción 1: Railway Cron (recomendado si tenés cron habilitado)**

Ejemplo (ajustar ruta de trabajo al del contenedor):

```text
0 3 * * *   cd /app && python scripts/backup_sqlite_mvp.py
```

El archivo queda en el filesystem del contenedor. Para persistencia seria: **volumen Railway** montado en la carpeta de la BD o subida a S3/Backblaze desde el script.

**Opción 2: Export manual periódico**

Desde Railway → Service → Shell:

```bash
python scripts/export_portability_bundle.py
```

(descarga o empaqueta según cómo esté implementado el script en tu rama).

## Monitoreo de uptime

**UptimeRobot (gratuito)**

1. Cuenta en [uptimerobot.com](https://uptimerobot.com)
2. New Monitor → HTTP(s)
3. URL: `https://TU_URL/_stcore/health`
4. Intervalo: 5 minutos
5. Alerta: email o Telegram

**Alternativa:** Better Stack (u otro) con la misma URL de health.

## Variables de entorno críticas en producción

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `MQ26_PASSWORD` | Sí | Contraseña admin (≥ 8 caracteres). |
| `PYTHONUNBUFFERED` | Recomendado | `1` — logs en tiempo real. |
| `DATABASE_URL` / `DB_URL` | No (MVP) | Vacío → SQLite local según `db_manager`. |
| `DEMO_MODE` | No | `true` = datos demo precargados. |
| `SENTRY_DSN` | No | Errores en producción. |

## Healthcheck

- Docker / Railway: ideal chequear `/_stcore/health` (ver `docs/SMOKE_PRODUCCION.md`).
- Smoke automatizado: `python scripts/smoke_produccion.py --base-url TU_URL`.

## CI (GitHub Actions)

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml): tests con `MQ26_PASSWORD=test_password_123`.
- Deploy y smoke post-deploy: en GitHub → Settings → Secrets → Actions, definir `RAILWAY_TOKEN` (CLI) y `RAILWAY_URL` (URL pública HTTPS del servicio, ej. `https://….up.railway.app`). Sin secretos el job sigue sin bloquear el pipeline (`continue-on-error` en el workflow).

## Checklist pre-deploy

- [ ] `python scripts/mvp_preflight.py` sin errores bloqueantes.
- [ ] `pytest tests/ -q` → 0 failed.
- [ ] `.env.example` sin contraseñas ni emails reales.
- [ ] Si alguna vez se subieron secretos al historial: rotar credenciales y valorar limpieza de historial (`git filter-repo` o repo nuevo).
- [ ] Backup o export antes de cambios riesgosos en BD.
- [ ] `git status` sin archivos sensibles trackeados por error.

## Checklist post-deploy

- [ ] `python scripts/smoke_produccion.py --base-url TU_URL` → OK.
- [ ] Login admin funciona.
- [ ] Cliente demo → cartera → informe (flujo mínimo).
- [ ] Landing con CTA real: copiar `commercial/landing/site.config.example.js` → `site.config.js` y completar (guía [`docs/commercial/DEPLOY_LANDING.md`](commercial/DEPLOY_LANDING.md)); no commitear `site.config.js` si contiene datos privados.
- [ ] Monitor externo (UptimeRobot u otro) con primer ping OK.
