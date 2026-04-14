"""
core/transaccional_repository.py — Repositorio único para transaccional (P0-03).

Modo dual-write controlado:
- escritura a CSV (compatibilidad)
- mirror a BD (tabla transaccional_operaciones)

Flags:
- MQ26_PERSISTENCE_MODE=legacy_csv   -> solo CSV
- MQ26_PERSISTENCE_MODE=dual_write   -> CSV + BD
- MQ26_PERSISTENCE_MODE=db_only      -> solo BD (CSV como export opcional)
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config import RUTA_TRANSAC
from core.db_manager import get_engine

TABLE_NAME = "transaccional_operaciones"

# Serializa CSV + BD en dual_write para que no se intercalen escrituras concurrentes (SSOT).
_dual_write_lock = threading.Lock()


def get_persistence_mode() -> str:
    mode = str(os.environ.get("MQ26_PERSISTENCE_MODE", "dual_write")).strip().lower()
    if mode not in {"legacy_csv", "dual_write", "db_only"}:
        return "dual_write"
    return mode


def _columns_base() -> list[str]:
    return [
        "CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD",
        "PPC_USD", "PPC_ARS", "TIPO", "LAMINA_VN", "MONEDA_PRECIO",
    ]


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy() if df is not None else pd.DataFrame()
    for c in _columns_base():
        if c not in out.columns:
            out[c] = "" if c in ("CARTERA", "TICKER", "TIPO", "MONEDA_PRECIO") else float("nan")
    out["CARTERA"] = out["CARTERA"].astype(str).str.strip()
    out["TICKER"] = out["TICKER"].astype(str).str.strip().str.upper()
    out["TIPO"] = out["TIPO"].astype(str).str.strip().str.upper()
    out["MONEDA_PRECIO"] = out["MONEDA_PRECIO"].astype(str).str.strip().str.upper()
    out["CANTIDAD"] = pd.to_numeric(out["CANTIDAD"], errors="coerce").fillna(0.0)
    out["PPC_USD"] = pd.to_numeric(out["PPC_USD"], errors="coerce").fillna(0.0)
    out["PPC_ARS"] = pd.to_numeric(out["PPC_ARS"], errors="coerce").fillna(0.0)
    out["LAMINA_VN"] = pd.to_numeric(out["LAMINA_VN"], errors="coerce")
    out["FECHA_COMPRA"] = pd.to_datetime(out["FECHA_COMPRA"], errors="coerce").dt.date
    out = out.dropna(subset=["TICKER", "FECHA_COMPRA"])
    out = out[out["CANTIDAD"] != 0]
    return out[_columns_base()].reset_index(drop=True)


def load_transaccional() -> pd.DataFrame:
    mode = get_persistence_mode()
    if mode == "db_only":
        return _load_db()
    if Path(RUTA_TRANSAC).exists():
        return _normalize_df(pd.read_csv(RUTA_TRANSAC, encoding="utf-8-sig"))
    if mode == "dual_write":
        return _load_db()
    return pd.DataFrame(columns=_columns_base())


def save_transaccional(df: pd.DataFrame) -> None:
    mode = get_persistence_mode()
    norm = _normalize_df(df)
    if mode == "dual_write":
        with _dual_write_lock:
            Path(RUTA_TRANSAC).parent.mkdir(parents=True, exist_ok=True)
            norm.to_csv(RUTA_TRANSAC, index=False)
            _save_db(norm)
        return
    if mode == "legacy_csv":
        Path(RUTA_TRANSAC).parent.mkdir(parents=True, exist_ok=True)
        norm.to_csv(RUTA_TRANSAC, index=False)
    elif mode == "db_only":
        _save_db(norm)


def _load_db() -> pd.DataFrame:
    engine = get_engine()
    try:
        q = text(
            f"""
            SELECT cartera AS CARTERA, fecha_compra AS FECHA_COMPRA, ticker AS TICKER,
                   cantidad AS CANTIDAD, ppc_usd AS PPC_USD, ppc_ars AS PPC_ARS,
                   tipo AS TIPO, lamina_vn AS LAMINA_VN, moneda_precio AS MONEDA_PRECIO
            FROM {TABLE_NAME}
            ORDER BY id
            """
        )
        with engine.connect() as conn:
            df = pd.read_sql_query(q, conn)
        return _normalize_df(df)
    except Exception:
        return pd.DataFrame(columns=_columns_base())


def _save_db(df: pd.DataFrame) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cartera VARCHAR(300) NOT NULL,
                    fecha_compra DATE NOT NULL,
                    ticker VARCHAR(30) NOT NULL,
                    cantidad FLOAT NOT NULL,
                    ppc_usd FLOAT NOT NULL DEFAULT 0,
                    ppc_ars FLOAT NOT NULL DEFAULT 0,
                    tipo VARCHAR(40) NOT NULL DEFAULT 'CEDEAR',
                    lamina_vn FLOAT NULL,
                    moneda_precio VARCHAR(20) NULL DEFAULT ''
                )
                """
            )
        )
        conn.execute(text(f"DELETE FROM {TABLE_NAME}"))
        if df.empty:
            return
        payload = []
        for _, r in df.iterrows():
            payload.append({
                "cartera": str(r["CARTERA"]),
                "fecha_compra": str(r["FECHA_COMPRA"]),
                "ticker": str(r["TICKER"]),
                "cantidad": float(r["CANTIDAD"]),
                "ppc_usd": float(r["PPC_USD"]),
                "ppc_ars": float(r["PPC_ARS"]),
                "tipo": str(r["TIPO"]),
                "lamina_vn": None if pd.isna(r["LAMINA_VN"]) else float(r["LAMINA_VN"]),
                "moneda_precio": str(r["MONEDA_PRECIO"] or ""),
            })
        conn.execute(
            text(
                f"""
                INSERT INTO {TABLE_NAME}
                (cartera, fecha_compra, ticker, cantidad, ppc_usd, ppc_ars, tipo, lamina_vn, moneda_precio)
                VALUES
                (:cartera, :fecha_compra, :ticker, :cantidad, :ppc_usd, :ppc_ars, :tipo, :lamina_vn, :moneda_precio)
                """
            ),
            payload,
        )
