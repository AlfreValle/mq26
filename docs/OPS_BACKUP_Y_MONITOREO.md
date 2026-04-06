# Operaciones — backup SQLite y monitoreo

## Backup de la base (MVP SQLite)

- **Local / antes de demo importante:** ejecutar [`scripts/backup_sqlite_mvp.py`](../scripts/backup_sqlite_mvp.py) según su docstring (apunta a la ruta de BD configurada en tu entorno).
- **Railway (SQLite en volumen efímero):** el archivo vive en el filesystem del contenedor. Para persistencia seria, planificar migración a PostgreSQL (ver [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) paso 10) o export periódico vía tarea manual hasta tener Cron.

## Healthcheck

- **Docker:** el [`Dockerfile`](../Dockerfile) define `HEALTHCHECK` contra `http://127.0.0.1:$PORT/_stcore/health`.
- **Railway:** [`railway.json`](../railway.json) → `healthcheckPath`: `/_stcore/health`, `healthcheckTimeout`: 900 s (arranque lento).

## Uptime externo (recomendado)

- Registrar la URL pública en **UptimeRobot** (u similar) con chequeo HTTP cada 5 min a `/_stcore/health` o a la raíz `/`.
- Alerta por email si cae el servicio.

## CI (GitHub Actions)

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml): en cada push/PR corre `pytest` con `MQ26_PASSWORD=test_password_123`.
- El job **deploy** solo corre en `main` si existe el secret **`RAILWAY_TOKEN`**. Sin token, el pipeline sigue siendo válido (tests en verde).

## Sentry (opcional)

- Definir `SENTRY_DSN` en Railway o `.env` para capturar errores en producción ([`run_mq26.py`](../run_mq26.py) inicializa sentry-sdk si está la variable).
