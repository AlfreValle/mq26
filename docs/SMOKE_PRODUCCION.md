# Smoke test — producción (Railway u otro host)

Objetivo: comprobar en **5 minutos** que la URL pública sirve MQ26 y el flujo mínimo es usable.

## Automático (salud HTTP)

Con la app levantada (local o Railway):

```bash
python scripts/smoke_produccion.py --base-url https://TU-SERVICIO.up.railway.app
```

Sin `--base-url`, solo valida el contrato de health en localhost (`http://127.0.0.1:8502` por defecto).

## Manual (post-deploy)

1. **Login**: usuario `admin` (o el configurado) + `MQ26_PASSWORD`.
2. **Cliente**: seleccionar uno existente o crear cliente de prueba (rol con permiso de alta).
3. **Cartera**: abrir pestaña Cartera; verificar que carga sin traceback.
4. **Demo**: con `DEMO_MODE=true`, verificar clientes precargados (María / Carlos / Diego según `generate_demo_data`).
5. **Estudio** (rol adecuado): generar informe completo y descargar HTML.
6. **Inversor** (rol inversor): ver semáforo y barra defensiva sin error.

## Variables útiles para demos

- `DEMO_MODE=true`
- `DEMO_DB_PATH` (opcional; ver `scripts/demo_launcher.py`)

## Si falla el healthcheck

- Railway: `railway.json` usa `healthcheckPath`: `/_stcore/health` y timeout amplio por arranque lento.
- Revisar logs del contenedor: debe verse `[MQ26] listen port ...` desde `docker-entrypoint.sh`.
