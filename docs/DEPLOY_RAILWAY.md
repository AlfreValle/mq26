# MQ26 — Deploy en Railway (10 pasos, ~2 horas la primera vez)

## Checklist rápido (operador, ~5 min)

1. Código en GitHub (`main` con `Dockerfile` y `railway.json` en la raíz).
2. Railway: New Project → Deploy from GitHub → elegir el repo.
3. Variables: `MQ26_PASSWORD` (mín. 8 caracteres), `PYTHONUNBUFFERED=1`; opcional `MQ26_VIEWER_PASSWORD`, `MQ26_INVESTOR_PASSWORD`, `MQ26_ADVISOR_PASSWORD`; demo pública: `DEMO_MODE=true`.
4. Settings → Generate Domain → abrir la URL.
5. Verificar `GET https://TU_DOMINIO/_stcore/health` → 200 (Streamlit).
6. Opcional CI: en GitHub → Settings → Secrets → `RAILWAY_TOKEN` (deploy) y `RAILWAY_URL` (URL pública del servicio, para el smoke post-deploy). Sin token el pipeline de tests sigue; el job de deploy no rompe el PR gracias a `continue-on-error` en el workflow.

## Requisitos previos

- Cuenta en GitHub (gratuita)
- Cuenta en Railway (gratuita, https://railway.app)
- El código subido a un repositorio GitHub (público o privado)

## Paso 1 — Subir el código a GitHub

Si todavía no tenés repositorio:

```bash
cd MQ26_V10
git init
git add .
git commit -m "feat: MQ26 V8 — MVP listo para deploy"
```

En GitHub.com: New repository → nombre "mq26" → Create.

Luego:

```bash
git remote add origin https://github.com/TU_USUARIO/mq26.git
git branch -M main
git push -u origin main
```

## Paso 2 — Crear proyecto en Railway

1. Entrar a https://railway.app → New Project
2. Elegir "Deploy from GitHub repo"
3. Conectar tu cuenta GitHub si no lo hiciste
4. Seleccionar el repositorio "mq26"
5. Railway detecta el `Dockerfile` automáticamente

## Paso 3 — Agregar variables de entorno en Railway

En el proyecto Railway → Variables → Agregar:

```
MQ26_PASSWORD         = [tu_password_seguro_minimo_8_chars]
MQ26_VIEWER_PASSWORD  = [password_para_estudio]
MQ26_INVESTOR_PASSWORD = [password_para_inversor]
PYTHONUNBUFFERED      = 1
```

**NO agregar** `DATABASE_URL` ni `DB_URL` → Railway usa SQLite local (correcto para MVP).

## Paso 4 — Generar dominio público

En Railway → Settings → Domains → Generate Domain.
Te da una URL del tipo `mq26-production.up.railway.app`.

## Paso 5 — Primer deploy

Railway hace el build automáticamente cuando recibe el push.
El primer build tarda 5-10 minutos (instala dependencias Python).
Los siguientes tardan 2-3 minutos.

## Paso 6 — Verificar que funciona

Abrir la URL generada en el paso 4.
Debería aparecer la pantalla de login de MQ26.
Ingresar con `MQ26_PASSWORD`.

## Paso 7 — Deploy automático en cada push

Cada vez que hacés `git push origin main`, Railway hace deploy automáticamente.
El CI de GitHub (`.github/workflows/ci.yml`) corre los tests antes del push.

## Paso 8 — Cargar los datos demo (opcional)

Para demos a prospects sin datos reales:
En Railway → Variables → agregar `DEMO_MODE=true`.
La app arranca con las 3 carteras de ejemplo.

## Paso 9 — Backup periódico

La BD SQLite vive dentro del container de Railway.
Antes de cada demo importante:

```bash
python scripts/backup_sqlite_mvp.py
```

(ejecutar local contra la BD exportada, o agregar como tarea programada).

## Paso 10 — Escalar a PostgreSQL cuando sea necesario

Cuando tengas 20+ clientes simultáneos o necesites acceso desde múltiples instancias:

1. Crear base en Supabase (plan gratuito hasta 500MB)
2. Agregar en Railway: `DATABASE_URL = postgresql://...` (o `DB_URL` con el mismo valor; la app y Alembic priorizan `DATABASE_URL`)
3. No hay cambios de código — la app detecta automáticamente la URL vía `core/db_manager.py`

### Migraciones Alembic en producción

- `migrations/env.py` usa la misma URL que la app cuando `DATABASE_URL` / `DB_URL` están definidas (evita aplicar migraciones contra el `sqlite://` del `alembic.ini` por error).
- **Opción A — al arrancar el contenedor:** en Variables de Railway agregar `RUN_ALEMBIC_UPGRADE=1`. El `docker-entrypoint.sh` ejecuta `python migrations/run_migrations.py` antes de levantar Streamlit. Si las migraciones fallan, el deploy no sirve tráfico (fail-fast).
- **Opción B — comando puntual:** `railway run python migrations/run_migrations.py` (o shell en el servicio) después de definir `DATABASE_URL`.
- Comprobar sin aplicar: `python migrations/run_migrations.py --check`

## Costo estimado

- Railway: USD 0/mes (plan gratuito) hasta USD 5/mes si superás las horas de uso gratuitas.
- Supabase: USD 0/mes (plan gratuito) para el MVP.
- Dominio .com.ar: USD 5/año (opcional pero recomendado).

## Troubleshooting

| Problema | Solución |
|----------|----------|
| Build falla en `pip install` | Verificar que `requirements.txt` esté actualizado |
| App arranca pero login no funciona | Verificar variables de entorno en Railway |
| "No clientes" al entrar | Entrar como admin y crear el primer cliente |
| Deploy muy lento | Normal en Railway gratuito — primer build siempre tarda más |
