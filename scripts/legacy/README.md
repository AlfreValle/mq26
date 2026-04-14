# scripts/legacy/ — Herramientas históricas de Master Quant

## Movido a este directorio

### importar_reto2026.py

ETL manual para importar las compras históricas del «Reto 2026» de Alfredo Vallejos
al transaccional de MQ26. Fue ejecutado en enero 2026. No es parte del flujo
actual del producto — se conserva por auditoría y referencia.

Uso si algún día se necesita reimportar:

```bash
python scripts/legacy/importar_reto2026.py --preview
python scripts/legacy/importar_reto2026.py --forzar
```

---

## Archivos que permanecen en la raíz (activos del producto)

### libro_mayor.py (raíz/)

Módulo de libro mayor de operaciones. Importado por `run_mq26.py`, `app_main.py`
y usado en `ui/tab_cartera.py`. Es parte del flujo de importación de comprobantes de broker.

**PENDIENTE Sprint N+1:** mover a `services/libro_mayor.py` con imports corregidos.

### gmail_reader.py (raíz/)

Lector automático de emails de brokers (Balanz, Bull Market). Importado por
`run_mq26.py` y `app_main.py`. Activo en la UI del libro mayor.

**PENDIENTE Sprint N+1:** mover a `services/gmail_reader.py` con imports corregidos.

### migrar_gmail_a_sqlite.py (raíz/)

Script de migración única (ya ejecutada). Importa `gmail_reader.py`.
Mantener en raíz para evitar problemas de `sys.path` con `scripts/legacy/`.
Documentado aquí como referencia.
