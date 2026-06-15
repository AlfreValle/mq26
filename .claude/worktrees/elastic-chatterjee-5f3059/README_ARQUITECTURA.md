# MQ26 + DSS Alfredo — Guía de Arquitectura

## Dos aplicaciones independientes, una base de datos compartida

| App | Entry point | Puerto | Proceso | Arranque |
|---|---|---|---|---|
| MQ26 — Inversiones | `run_mq26.py` (`mq26_main.py` legacy) | 8502 | independiente | ~10s (yfinance) |
| DSS Alfredo — Control Financiero | `dss_main.py` | 8501 | independiente | ~1s (solo BD) |

```
start_mq26.bat  → streamlit run run_mq26.py --server.port 8502
start_dss.bat   → streamlit run dss_main.py  --server.port 8501
```

## Estructura de carpetas

```
MQ26_v17/
├── run_mq26.py           # Entry point MQ26 (6 tabs; mq26_main.py delega aquí)
├── dss_main.py           # Entry point DSS Alfredo (navegación lateral)
├── app_main.py           # Legacy — 7 tabs unificados (respaldo)
├── config.py             # Constantes globales, lee .env
├── data_engine.py        # DataEngine: descarga yfinance, CSV, universo
├── risk_engine.py        # RiskEngine: Markowitz, Black-Litterman, Kelly...
├── libro_mayor.py        # Libro mayor de operaciones (Streamlit + lógica)
├── broker_importer.py    # Parser CSV de comprobantes Balanz
│
├── core/                 # Infraestructura compartida (SIN Streamlit directo*)
│   ├── __init__.py
│   ├── app_context.py    # AppContext dataclass (reemplaza dict ctx)
│   ├── auth.py           # Autenticación centralizada (rate limit, log)
│   ├── audit.py          # Registro de acciones críticas en alertas_log
│   ├── cache_manager.py  # TTLs y funciones @st.cache_data centralizadas
│   ├── constants.py      # CATEGORIAS_EGRESO/INGRESO, etiquetas, colores
│   ├── ctx_builder.py    # build_ctx() — construye AppContext desde run_mq26
│   ├── db_manager.py     # ORM SQLAlchemy, migraciones, CRUD
│   ├── logging_config.py # get_logger() — logging centralizado
│   ├── notificaciones.py # NotificadorDSS — toast/success/error + log
│   ├── pricing_utils.py  # Ratio CEDEAR, subyacente USD, CCL histórico
│   └── validators.py     # Validaciones de dominio reutilizables
│
├── services/             # Lógica de dominio (SIN Streamlit)
│   ├── __init__.py
│   ├── alert_bot.py      # Alertas Telegram
│   ├── backtester.py     # Backtesting histórico
│   ├── cartera_service.py# Posición neta, P&L, TWRR, rendimiento por tipo
│   ├── data_bridge.py    # Puente DSS ↔ MQ26 (capital_libre, CCL)
│   ├── decision_engine.py# Motor de señales
│   ├── dss_service.py    # Flujo de caja, tarjetas, semáforo
│   ├── ejecucion_service.py # Rebalanceo, órdenes
│   ├── market_connector.py  # ratios fundamentales, precios
│   ├── mod23_service.py  # MOD-23 scoring
│   ├── motor_salida.py   # Estrategia de salida por objetivo
│   ├── presupuesto_service.py # Presupuesto anual vs real
│   ├── report_service.py # Generación de reportes PDF/HTML
│   └── reporte_dss_service.py # Reporte mensual DSS
│
├── ui/                   # Componentes Streamlit
│   ├── __init__.py
│   ├── dss_configuracion.py  # Pantalla de configuración DSS
│   ├── dss_dashboard.py      # Dashboard ejecutivo DSS
│   ├── dss_nav.py            # Navegación lateral DSS (sidebar)
│   ├── dss_presupuesto.py    # Presupuesto anual editable
│   ├── pantalla_ingreso.py   # Selección/creación de cliente MQ26
│   ├── tab_cartera.py        # Tab 1 — Cartera & Libro Mayor
│   ├── tab_dss.py            # Módulo DSS en tabs (también usado por dss_main)
│   ├── tab_ejecucion.py      # Tab 5 — Mesa de Ejecución
│   ├── tab_optimizacion.py   # Tab 3 — Lab Quant
│   ├── tab_reporte.py        # Tab 6 — Reporte cliente
│   ├── tab_riesgo.py         # Tab 4 — Riesgo & Simulación
│   └── tab_universo.py       # Tab 2 — Universo & Señales
│
├── 1_Scripts_Motor/      # Motor cuantitativo (config.py propio — NO modificar)
│   ├── config.py         ← CUIDADO: mismo nombre que /config.py raíz
│   └── risk_engine.py    ← copia del motor (importado vía sys.path)
│
├── 0_Data_Maestra/       # Datos persistidos (NO commitear)
│   ├── master_quant.db   # Base de datos SQLite
│   ├── Maestra_Inversiones.xlsx
│   └── Maestra_Transaccional.csv
│
├── assets/
│   ├── style.css         # Tema MQ26 (azul institucional)
│   ├── dss_style.css     # Tema DSS Alfredo (verde profesional)
│   └── fonts/            # Inter.woff2 (fuente local)
│
├── .streamlit/
│   ├── dss.toml          # Puerto 8501, tema verde
│   └── mq26.toml         # Puerto 8502, tema azul
│
├── tests/                # Tests con pytest
├── requirements.txt      # Dependencias de producción
├── requirements-dev.txt  # Dependencias de desarrollo
└── pyproject.toml        # Configuración de proyecto (setuptools, ruff, mypy)
```

## Config.py — conflicto de nombre

La raíz tiene `config.py` y `1_Scripts_Motor/config.py`. El entry point carga la raíz
explícitamente via `importlib.util`:

```python
_cfg_spec = importlib.util.spec_from_file_location("config_root", str(BASE_DIR / "config.py"))
```

**No usar `import config` directo** — puede cargar el de 1_Scripts_Motor dependiendo del `sys.path`.

## Puente DSS ↔ MQ26

La comunicación entre procesos se hace vía la tabla `configuracion` de la BD:

```python
# En DSS Alfredo (dss_main.py / dss_dashboard.py)
from services.data_bridge import publicar_capital_libre
publicar_capital_libre(cliente_id=5, monto=450_000)

# En MQ26 (run_mq26.py / ui/pantalla_ingreso.py)
from services.data_bridge import leer_capital_libre
capital = leer_capital_libre(cliente_id=5)  # → 450000.0
```

## Dependencias por app

| Módulo | MQ26 | DSS Alfredo |
|---|---|---|
| yfinance | ✅ | ❌ |
| scipy | ✅ | ❌ |
| scikit-learn | ✅ | ❌ |
| RiskEngine | ✅ | ❌ |
| DataEngine | ✅ | ❌ |
| pandas | ✅ | ✅ |
| plotly | ✅ | ✅ |
| sqlalchemy | ✅ | ✅ |

DSS arranca en ~1s; MQ26 tarda ~8-12s en la primera carga por las descargas de yfinance.

## Comercialización y portabilidad (Master Quant)

- **Kit comercial (TyC plantilla, pricing B2B, casos anonimizados, webinars, partners):** [docs/commercial/README.md](docs/commercial/README.md)
- **Landing estática para campañas:** [commercial/landing/index.html](commercial/landing/index.html) (reemplazar links de demo y emails antes de publicar).
- **Backup / portabilidad de datos maestros:** `python scripts/export_portability_bundle.py` → genera un `.zip` con CSV/XLSX/DB presentes en `0_Data_Maestra/`.
