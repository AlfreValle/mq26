"""
scripts/generate_demo_data.py — Genera base de datos demo para MQ26.

Crea 10 clientes representativos con transacciones ORM y precios sintéticos reproducibles.
Uso:
    python scripts/generate_demo_data.py
    DEMO_DB_PATH=C:/tmp/demo.db python scripts/generate_demo_data.py

La app detecta DEMO_MODE=true en .env y carga esta BD automáticamente.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

# ── CCL histórico aproximado por fecha (ARS/USD) ─────────────────────────────
# Usado para convertir precios USD → ARS en las transacciones demo
_CCL_POR_FECHA: dict[str, float] = {
    "2022-03-14": 200.0,
    "2022-06-01": 210.0,
    "2022-09-15": 265.0,
    "2023-01-10": 350.0,
    "2023-01-20": 355.0,
    "2023-02-15": 380.0,
    "2023-03-01": 390.0,
    "2023-04-01": 405.0,
    "2023-04-10": 420.0,
    "2023-05-10": 455.0,
    "2023-06-01": 480.0,
    "2023-06-05": 490.0,
    "2023-07-01": 505.0,
    "2023-07-03": 510.0,
    "2023-08-15": 530.0,
    "2023-09-20": 555.0,
    "2023-10-01": 600.0,
    "2024-01-10": 960.0,
    "2024-01-13": 980.0,
    "2024-01-15": 970.0,
    "2024-01-20": 990.0,
    "2024-02-01": 1000.0,
    "2024-02-03": 1015.0,
    "2024-02-20": 1010.0,
    "2024-02-26": 1010.0,
    "2024-03-01": 1020.0,
    "2024-03-10": 1030.0,
    "2024-03-15": 1040.0,
    "2024-04-01": 1050.0,
    "2024-04-15": 1060.0,
    "2024-05-10": 1070.0,
    "2024-06-10": 1080.0,
    "2024-06-15": 1090.0,
    "2025-01-06": 1200.0,
    "2025-01-13": 1210.0,
    "2025-02-03": 1220.0,
}


def _ccl(fecha: str) -> float:
    """Retorna CCL aproximado para una fecha dada."""
    return _CCL_POR_FECHA.get(fecha, 500.0)


def _precio_sintetico(ticker: str, n_dias: int = 756) -> pd.Series:
    """Genera serie de precios sintéticos reproducibles para un ticker."""
    precios_base = {
        "KO": 58.0, "XOM": 110.0, "GLD": 185.0, "PG": 145.0,
        "SPY": 400.0, "AAPL": 175.0, "MSFT": 300.0, "GOOGL": 135.0,
        "MELI": 1500.0, "NVDA": 80.0, "META": 350.0, "AMZN": 180.0,
        "YPFD": 15.0, "BRKB": 380.0, "SHY": 84.0,
    }
    vols = {"NVDA": 0.025, "META": 0.022, "MELI": 0.020, "YPFD": 0.028}
    px0 = precios_base.get(ticker, 100.0)
    vol = vols.get(ticker, 0.012)
    rng = np.random.default_rng(seed=hash(ticker) % (2 ** 32))
    idx = pd.date_range("2023-01-01", periods=n_dias, freq="B")
    prices = px0 * np.cumprod(1 + rng.normal(0.0004, vol, n_dias))
    return pd.Series(prices, index=idx, name=ticker)


# ── Transacciones demo: (nombre_cartera_unico, fecha, ticker, qty, ppc_usd) ─
_TRANS_DEMO = [
    # ── María — conservadora ──────────────────────────────────────────────
    ("María Fernández | Ahorro Familiar", "2023-02-15", "KO", 50, 57.0),
    ("María Fernández | Ahorro Familiar", "2023-04-10", "XOM", 20, 112.0),
    ("María Fernández | Ahorro Familiar", "2023-07-03", "GLD", 6, 183.0),
    ("María Fernández | Ahorro Familiar", "2024-02-20", "PG", 8, 155.0),
    ("María Fernández | Ahorro Familiar", "2024-06-10", "SHY", 15, 84.0),
    # ── Carlos — moderado ─────────────────────────────────────────────────
    ("Carlos Rodríguez | Crecimiento", "2022-09-15", "AAPL", 15, 148.0),
    ("Carlos Rodríguez | Crecimiento", "2022-09-15", "MSFT", 5, 237.0),
    ("Carlos Rodríguez | Crecimiento", "2023-01-20", "MELI", 2, 920.0),
    ("Carlos Rodríguez | Crecimiento", "2024-01-10", "NVDA", 10, 49.6),
    ("Carlos Rodríguez | Crecimiento", "2024-03-15", "SPY", 3, 510.0),
    # ── Diego — arriesgado ──────────────────────────────────────────────────
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "NVDA", 30, 25.6),
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "META", 15, 198.0),
    ("Diego Martínez | Alta Rentabilidad", "2023-06-05", "NVDA", 20, 38.5),
    ("Diego Martínez | Alta Rentabilidad", "2024-02-26", "META", 8, 486.0),
    ("Diego Martínez | Alta Rentabilidad", "2024-05-10", "AMZN", 12, 183.0),
    # ── Ana — conservadora ────────────────────────────────────────────────
    ("Ana García | Retiro 2030", "2023-03-01", "GLD", 12, 178.0),
    ("Ana García | Retiro 2030", "2023-03-01", "BRKB", 8, 320.0),
    ("Ana García | Retiro 2030", "2023-08-15", "KO", 30, 59.0),
    ("Ana García | Retiro 2030", "2024-01-20", "XOM", 15, 98.0),
    # ── Martín — moderado, empezando ──────────────────────────────────────
    ("Martín López | Empezando", "2024-01-15", "SPY", 2, 478.0),
    ("Martín López | Empezando", "2024-02-01", "AAPL", 5, 186.0),
    ("Martín López | Empezando", "2024-03-10", "GLD", 3, 195.0),
    # ── Roberto — moderado ────────────────────────────────────────────────
    ("Roberto Silva | Empresario", "2023-05-10", "SPY", 5, 415.0),
    ("Roberto Silva | Empresario", "2023-05-10", "MSFT", 8, 305.0),
    ("Roberto Silva | Empresario", "2023-09-20", "GOOGL", 6, 135.0),
    ("Roberto Silva | Empresario", "2024-04-01", "BRKB", 4, 385.0),
    # ── Lucía — arriesgada ─────────────────────────────────────────────────
    ("Lucía Pérez | Joven Profesional", "2023-07-01", "NVDA", 20, 44.0),
    ("Lucía Pérez | Joven Profesional", "2023-07-01", "META", 10, 290.0),
    ("Lucía Pérez | Joven Profesional", "2024-01-10", "AMZN", 15, 154.0),
    ("Lucía Pérez | Joven Profesional", "2024-06-15", "MELI", 3, 1680.0),
    # ── Jorge — conservador ───────────────────────────────────────────────
    ("Jorge Herrera | Conservador Total", "2022-06-01", "GLD", 20, 172.0),
    ("Jorge Herrera | Conservador Total", "2022-06-01", "BRKB", 10, 282.0),
    ("Jorge Herrera | Conservador Total", "2023-01-10", "KO", 40, 61.0),
    ("Jorge Herrera | Conservador Total", "2023-06-01", "PG", 20, 148.0),
    ("Jorge Herrera | Conservador Total", "2024-03-01", "SHY", 30, 83.5),
    # ── Sofía — muy arriesgada ────────────────────────────────────────────
    ("Sofía Castro | Mix Internacional", "2023-04-01", "NVDA", 25, 28.0),
    ("Sofía Castro | Mix Internacional", "2023-04-01", "META", 12, 240.0),
    ("Sofía Castro | Mix Internacional", "2023-10-01", "MELI", 5, 1340.0),
    ("Sofía Castro | Mix Internacional", "2024-02-01", "AMZN", 20, 174.0),
    ("Sofía Castro | Mix Internacional", "2024-04-15", "AAPL", 15, 172.0),
    # ── Pablo — primera cartera ───────────────────────────────────────────
    ("Pablo Romero | Primera Cartera", "2025-01-06", "SPY", 2, 580.0),
    ("Pablo Romero | Primera Cartera", "2025-01-06", "GLD", 3, 244.0),
    ("Pablo Romero | Primera Cartera", "2025-01-13", "BRKB", 1, 460.0),
    ("Pablo Romero | Primera Cartera", "2025-01-13", "AAPL", 2, 226.0),
    ("Pablo Romero | Primera Cartera", "2025-02-03", "MSFT", 3, 420.0),
]


def run(demo_db_path: str | None = None) -> str:
    """
    Crea la BD demo con 10 clientes y transacciones ORM reales.
    Monkey-patchea temporalmente engine + SessionLocal de db_manager.
    Restaura ambos en el bloque finally.
    Retorna el path de la BD creada.
    """
    import tempfile
    demo_path = demo_db_path or os.environ.get(
        "DEMO_DB_PATH",
        str(Path(tempfile.gettempdir()) / "mq26_demo.db"),
    )
    demo_db = Path(demo_path)
    demo_db.parent.mkdir(parents=True, exist_ok=True)
    demo_db.unlink(missing_ok=True)

    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    import core.db_manager as _dbm

    _demo_engine = _ce(
        f"sqlite:///{demo_path}",
        connect_args={"check_same_thread": False},
    )
    _dbm.Base.metadata.create_all(_demo_engine)

    _orig_engine       = _dbm.engine
    _orig_session_local = _dbm.SessionLocal

    # Patch engine Y SessionLocal para que get_session() y read_sql_query usen la BD demo
    _dbm.engine       = _demo_engine
    _dbm.SessionLocal = _sm(bind=_demo_engine, autocommit=False, autoflush=False)

    try:
        # ── 1. Registrar 10 clientes (nombre = clave CARTERA / transacciones) ─
        CLIENTES = [
            {
                "nombre": "María Fernández | Ahorro Familiar",
                "perfil_riesgo": "Conservador",
                "horizonte_label": "3 años",
                "capital_usd": 18_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Carlos Rodríguez | Crecimiento",
                "perfil_riesgo": "Moderado",
                "horizonte_label": "+5 años",
                "capital_usd": 45_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Diego Martínez | Alta Rentabilidad",
                "perfil_riesgo": "Arriesgado",
                "horizonte_label": "3 años",
                "capital_usd": 85_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Ana García | Retiro 2030",
                "perfil_riesgo": "Conservador",
                "horizonte_label": "+5 años",
                "capital_usd": 22_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Martín López | Empezando",
                "perfil_riesgo": "Moderado",
                "horizonte_label": "1 año",
                "capital_usd": 12_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Roberto Silva | Empresario",
                "perfil_riesgo": "Moderado",
                "horizonte_label": "3 años",
                "capital_usd": 62_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Lucía Pérez | Joven Profesional",
                "perfil_riesgo": "Arriesgado",
                "horizonte_label": "+5 años",
                "capital_usd": 38_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Jorge Herrera | Conservador Total",
                "perfil_riesgo": "Conservador",
                "horizonte_label": "+5 años",
                "capital_usd": 55_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Sofía Castro | Mix Internacional",
                "perfil_riesgo": "Muy arriesgado",
                "horizonte_label": "3 años",
                "capital_usd": 72_000.0,
                "tipo_cliente": "Persona",
            },
            {
                "nombre": "Pablo Romero | Primera Cartera",
                "perfil_riesgo": "Moderado",
                "horizonte_label": "1 año",
                "capital_usd": 9_000.0,
                "tipo_cliente": "Persona",
            },
        ]
        ids: dict[str, int] = {}
        for c in CLIENTES:
            cid = _dbm.registrar_cliente(**{k: v for k, v in c.items()})
            ids[c["nombre"]] = cid

        # ── 2. Registrar transacciones ORM reales ────────────────────────────
        n_trans = 0
        for nombre, fecha, ticker, qty, ppc_usd in _TRANS_DEMO:
            cliente_id = ids.get(nombre)
            if cliente_id is None:
                continue
            precio_ars = round(ppc_usd * _ccl(fecha), 2)
            _dbm.registrar_transaccion(
                cliente_id=cliente_id,
                ticker=ticker,
                tipo_op="COMPRA",
                nominales=qty,
                precio_ars=precio_ars,
                fecha=fecha,
                notas="[DEMO]",
            )
            n_trans += 1

        # ── 3. Guardar precios sintéticos en tabla auxiliar ──────────────────
        TICKERS_DEMO = [
            "KO", "XOM", "GLD", "PG", "SPY", "AAPL", "SHY", "BRKB",
            "MSFT", "GOOGL", "MELI", "NVDA", "META", "AMZN", "YPFD",
        ]
        df_px = pd.DataFrame({t: _precio_sintetico(t) for t in TICKERS_DEMO})
        with sqlite3.connect(demo_path) as cn:
            df_px.to_sql("demo_prices", cn, if_exists="replace", index=True)

        # ── 4. Generar CSV transaccional demo (para DataEngine/cartera view) ─
        csv_rows = []
        for nombre, fecha, ticker, qty, ppc_usd in _TRANS_DEMO:
            csv_rows.append({
                "CARTERA":      nombre,
                "FECHA_COMPRA": fecha,
                "TICKER":       ticker,
                "CANTIDAD":     qty,
                "PPC_USD":      ppc_usd,
                "PPC_ARS":      0.0,
                "TIPO":         "CEDEAR",
            })
        df_csv = pd.DataFrame(csv_rows)
        csv_path = Path(demo_path).with_suffix(".csv")
        df_csv.to_csv(csv_path, index=False, encoding="utf-8-sig")

        print(f"BD demo creada: {demo_path}")
        print(f"  Clientes: {len(ids)}")
        print(f"  Transacciones ORM: {n_trans}")
        print(f"  CSV transaccional: {csv_path}")
        print(f"  Tickers con precios: {len(TICKERS_DEMO)}")
        print("\nPara usar:")
        print("  DEMO_MODE=true streamlit run run_mq26.py --server.port 8502")
        return demo_path

    finally:
        _dbm.engine       = _orig_engine
        _dbm.SessionLocal = _orig_session_local


if __name__ == "__main__":
    run()
