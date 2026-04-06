# MQ26 — Runbook MVP sólido (SQLite, sin Supabase obligatorio)

Este documento **centraliza** cómo trabajar en modo MVP: costo cero en base en la nube, entorno claro y camino a escalar después.

---

## Decisiones ya tomadas por el producto

| Tema | MVP recomendado |
|------|------------------|
| Base de datos | **SQLite** (`0_Data_Maestra/master_quant.db`) dejando `DATABASE_URL` y `DB_URL` **vacíos** en `.env` |
| Contraseña app | **`MQ26_PASSWORD`** en `.env` (mínimo 8 caracteres) |
| Postgres / Supabase | **Opcional** cuando haya deploy o necesidad real; no bloquea el MVP |
| Copia de seguridad | Script `scripts/backup_sqlite_mvp.py` antes de demos o cambios grandes |

---

## Paso 1 — Entorno

1. Copiá plantilla si hace falta: `.env.example` → `.env`
2. En `.env`:
   - `MQ26_PASSWORD=` contraseña fuerte (≥ 8 caracteres)
   - `DATABASE_URL=` y `DB_URL=` **vacíos** para MVP solo local
   - Opcional: `MQ26_VIEWER_PASSWORD`, `MQ26_INVESTOR_PASSWORD` con la misma regla de longitud
3. Ejecutá comprobaciones:

```bash
python scripts/mvp_preflight.py
```

Si más adelante configurás Postgres:

```bash
python scripts/mvp_preflight.py --try-postgres
```

---

## Paso 2 — Arranque local

```bash
python -m streamlit run run_mq26.py --server.port 8502
```

En el log debe aparecer **SQLite local** si no hay `DATABASE_URL` válida. Eso es correcto para el MVP.

---

## Paso 3 — Respaldo del SQLite (antes de demos o migraciones manuales)

```bash
python scripts/backup_sqlite_mvp.py
```

Los archivos quedan en `0_Data_Maestra/backups/` (carpeta ignorada por git si el maestro también lo está).

---

## Paso 4 — Definición corta de “MVP listo”

- [ ] `mvp_preflight.py` sin errores
- [ ] Camino feliz: login → carga/import de cartera → resumen legible y coherente
- [ ] Backup probado al menos una vez
- [ ] Schema: cambios de tablas pasan por **Alembic** cuando toques producción/seriamente

---

## Cuándo sumar PostgreSQL (Supabase u otro)

Cuando necesites varias instancias de app escribiendo a la vez, hosting en la nube con BD remota o backups gestionados del proveedor. La app ya usa `DATABASE_URL`; el runbook de conexión pooler está en comentarios de `.env.example`.

---

## Referencias

- Voz y tono UI: `docs/product/VOZ_Y_TONO_MQ26.md`
- UX carga cartera: `docs/product/UX_CARGA_CARTERA_INVERSOR_ARGENTINO.md`
- Variables de ejemplo: `.env.example`
