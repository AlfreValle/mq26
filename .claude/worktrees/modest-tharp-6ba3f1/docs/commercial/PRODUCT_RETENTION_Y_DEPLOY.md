# Portabilidad de datos, exportaciones y deploy — retención comercial

Objetivo: **aumentar switching cost** honestos (datos únicos + flujo integrado) y **reducir miedo** del comprador B2B ofreciendo **salida ordenada** (portabilidad).

## Dónde viven los datos (referencia técnica)

Definido en [config.py](../../config.py):

- `Maestra_Transaccional.csv` — operaciones consolidadas.
- `Maestra_Inversiones.xlsx` — legado / migración.
- `Analisis_Empresas.xlsx` — universo análisis.
- `Universo_120_CEDEARs.xlsx` — tickers y ratios.
- `master_quant.db` — clientes, usuarios, transacciones ORM si se usan.

Script de paquete portátil: [scripts/export_portability_bundle.py](../../scripts/export_portability_bundle.py) (`python scripts/export_portability_bundle.py`).

## Exportaciones ya disponibles en la app

| Ubicación | Qué exporta |
|-----------|-------------|
| Libro Mayor ([ui/tab_ledger.py](../../ui/tab_ledger.py)) | Excel libro mayor |
| Cartera / optimización | `_boton_exportar` Excel desde [run_mq26.py](../../run_mq26.py) |
| Lab optimización | Pesos, PDF comparativa |
| Reporte ([ui/tab_reporte.py](../../ui/tab_reporte.py)) | Descargas varias según rol |
| Inversor ([ui/tab_inversor.py](../../ui/tab_inversor.py)) | Informe HTML |

Argumento B2B: *“Tu historial queda en archivos estándar (CSV/Excel/HTML); no estás en un silo cerrado.”*

## Estabilidad deploy (checklist)

Variables típicas [Railway](https://railway.app) / Docker:

- `MQ26_PASSWORD`, `DATABASE_URL` o SQLite persistente en volumen.
- `MQ26_DEPLOY_MARKER` / healthcheck Streamlit.

Prácticas:

- Tests antes de release: `pytest tests/ -q`.
- Backup **diario** de `0_Data_Maestra/` en B2B enterprise (script rsync/S3 — definir en contrato).

## Mejora continua (producto)

- Informe PDF nativo ampliado si el mercado lo pide (hoy hay HTML + rutas PDF en reportes según rol).
- API lectura limitada (solo enterprise) cuando haya demanda formalizada.
