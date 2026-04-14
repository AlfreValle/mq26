# Catálogo de fuentes de datos (MQ26)

Documento de auditoría (Fase 0 — trazabilidad). Actualizar cuando cambie el pipeline.

| Recurso | Fuente principal | Frecuencia | Zona horaria | Notas |
|--------|-------------------|------------|--------------|--------|
| Precios EOD CEDEARs / ADRs | Yahoo Finance (`yfinance`) vía `1_Scripts_Motor/data_engine.py` | EOD (cierre NY) | America/New_York en origen; **alineación explícita** | Ver política C03 abajo. |

## Política C03 — Calendario NY vs BYMA

`DataEngine.descargar_historico` aplica por defecto **intersección de fechas** (`dropna(how="any")` tras descarga): solo se conservan días hábiles en los que **todos** los tickers del panel tienen cierre. Esto reduce el sesgo de rellenar huecos con `ffill` entre mercados con calendarios distintos (US vs Argentina `.BA`).

Si tras el inner join quedan **menos de 30 filas**, se reintenta un fallback: `ffill`/`bfill` con límite acotado (3 días) y nuevo `dropna(how="any")`.

## Política C02 — Outliers en retornos

Opcional en `RiskEngine`: winsorizado por columna en cuantiles configurables (p.ej. 0.5% / 99.5%) sobre retornos diarios antes de estimar μ y Σ; el reporte de recortes puede mostrarse en UI.
| Universo BYMA / ratios | `0_Data_Maestra/Universo_120_CEDEARs.xlsx` + CSV maestro | Manual / ETL | — | Ratios CEDEAR como fallback en `config.RATIOS_CEDEAR`. |
| BYMA Open Data (listas tiempo real, ONs) | `https://open.bymadata.com.ar` vía `services/byma_market_data.py` | Caché 5 min (Streamlit) | AR | Mapeo de campos y escalas: [`docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`](product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md). No sustituye API comercial licenciada. |
| Precios ARS lote (opcional) | `MQ26_BYMA_API_URL` → `services/byma_provider.py` | On demand | — | Contrato `POST …/cotizaciones`; ver mismo doc producto. |
| Ingesta batch a fallback BD | `services/precios_mercado_ingest.py` → tabla `precios_fallback` | Job / manual | AR | Escala ON USD = feed BYMA; [`docs/product/BYMA_INGESTA_BD_P2_BYMA02.md`](product/BYMA_INGESTA_BD_P2_BYMA02.md). |
| Tasas libre de riesgo | Constante `RISK_FREE_RATE` en `config.py` | Config (actualización manual) | — | Aprox. T-Bill USA; documentar fecha de última revisión al cambiar. |
| CCL / tipo de cambio | `obtener_ccl` + `yfinance` / conectores en `data_engine` | Intradía sujeto a caché | AR | Ver `CCL_FALLBACK` si falla el proveedor. |
| Base de datos app | SQLite local (`master_quant.db`) o `DATABASE_URL` (Postgres/Supabase) | Transaccional | UTC típico en servidor | Sin precios de mercado históricos completos; posiciones y snapshots. |

## Entornos

- **Producción / Railway:** variables `MQ26_PASSWORD`, `DATABASE_URL`, etc. según `.env.example`.
- **Datos simulados:** los tests usan precios sintéticos (`tests/test_risk_engine.py`); no llaman a red salvo tests de integración explícitos.

## Licencias y límites

- Yahoo Finance: uso no comercial según términos del proveedor; MQ26 no redistribuye series crudas.
- Para uso institucional con requisitos de compliance, planificar feed BYMA o vendor licenciado (backlog J04).
