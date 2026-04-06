"""
scripts/generate_demo_data.py — Genera base de datos demo para MQ26.

Crea 3 clientes con transacciones ORM reales y precios sintéticos reproducibles.
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
    "2022-09-15": 265.0,
    "2023-01-20": 355.0,
    "2023-02-15": 380.0,
    "2023-04-10": 420.0,
    "2023-06-05": 490.0,
    "2023-07-03": 510.0,
    "2024-01-10": 960.0,
    "2024-02-20": 1010.0,
    "2024-02-26": 1010.0,
}


def _ccl(fecha: str) -> float:
    """Retorna CCL aproximado para una fecha dada."""
    return _CCL_POR_FECHA.get(fecha, 500.0)


def _precio_sintetico(ticker: str, n_dias: int = 756) -> pd.Series:
    """Genera serie de precios sintéticos reproducibles para un ticker."""
    precios_base = {
        "KO": 58.0, "XOM": 110.0, "GLD": 185.0, "PG": 145.0,
        "SPY": 400.0, "AAPL": 175.0, "MSFT": 300.0, "GOOGL": 12.0,
        "MELI": 1500.0, "NVDA": 80.0, "META": 350.0, "AMZN": 18.0,
        "YPFD": 15.0,
    }
    vols = {"NVDA": 0.025, "META": 0.022, "MELI": 0.020, "YPFD": 0.028}
    px0 = precios_base.get(ticker, 100.0)
    vol = vols.get(ticker, 0.012)
    rng = np.random.default_rng(seed=hash(ticker) % (2 ** 32))
    idx = pd.date_range("2023-01-01", periods=n_dias, freq="B")
    prices = px0 * np.cumprod(1 + rng.normal(0.0004, vol, n_dias))
    return pd.Series(prices, index=idx, name=ticker)


# ── Transacciones demo: (nombre_cliente, fecha, ticker, qty, ppc_usd) ────────
_TRANS_DEMO = [
    # María — conservadora
    ("María Fernández | Ahorro Familiar", "2023-02-15", "KO",   50, 57.0),
    ("María Fernández | Ahorro Familiar", "2023-04-10", "XOM",  20, 112.0),
    ("María Fernández | Ahorro Familiar", "2023-07-03", "GLD",   6, 183.0),
    ("María Fernández | Ahorro Familiar", "2024-02-20", "PG",    8, 155.0),
    # Carlos — moderada
    ("Carlos Rodríguez | Crecimiento",    "2022-09-15", "AAPL", 15, 148.0),
    ("Carlos Rodríguez | Crecimiento",    "2022-09-15", "MSFT",  5, 237.0),
    ("Carlos Rodríguez | Crecimiento",    "2023-01-20", "MELI",  2, 920.0),
    ("Carlos Rodríguez | Crecimiento",    "2024-01-10", "NVDA", 10,  49.6),
    # Diego — agresiva
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "NVDA", 30,  25.6),
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "META", 15, 198.0),
    ("Diego Martínez | Alta Rentabilidad", "2023-06-05", "NVDA", 20,  38.5),
    ("Diego Martínez | Alta Rentabilidad", "2024-02-26", "META",  8, 486.0),
]


def run(demo_db_path: str | None = None) -> str:
    """
    Crea la BD demo con 3 clientes y transacciones ORM reales.
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
        # ── 1. Registrar 3 clientes ──────────────────────────────────────────
        CLIENTES = [
            {"nombre": "María Fernández",
             "perfil_riesgo": "Conservador", "horizonte_label": "1 año",
             "capital_usd": 18_000.0, "tipo_cliente": "Persona"},
            {"nombre": "Carlos Rodríguez",
             "perfil_riesgo": "Moderado", "horizonte_label": "3 años",
             "capital_usd": 45_000.0, "tipo_cliente": "Persona"},
            {"nombre": "Diego Martínez",
             "perfil_riesgo": "Agresivo", "horizonte_label": "+5 años",
             "capital_usd": 85_000.0, "tipo_cliente": "Persona"},
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
            "KO", "XOM", "GLD", "PG", "SPY", "AAPL",
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
