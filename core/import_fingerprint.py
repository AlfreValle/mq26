"""
Idempotencia fuerte para imports (broker/Gmail) vía fingerprint estable.
"""
from __future__ import annotations

import hashlib

import pandas as pd


FINGERPRINT_COL = "IMPORT_FINGERPRINT"


def _canon_str(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def _canon_num(v) -> str:
    try:
        return f"{float(v):.8f}"
    except Exception:
        return "0.00000000"


def _canon_date(v) -> str:
    dt = pd.to_datetime(v, errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.date().isoformat()


def build_import_fingerprint(row: pd.Series) -> str:
    # Campos con máxima capacidad de distinguir operación real.
    raw = "|".join([
        _canon_str(row.get("CARTERA", "")),
        _canon_date(row.get("FECHA_COMPRA", "")),
        _canon_str(row.get("TICKER", "")),
        _canon_num(row.get("CANTIDAD", 0)),
        _canon_num(row.get("PPC_USD", 0)),
        _canon_num(row.get("PPC_ARS", 0)),
        _canon_str(row.get("TIPO", "")),
        _canon_num(row.get("LAMINA_VN", float("nan"))),
        _canon_str(row.get("MONEDA_PRECIO", "")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def with_fingerprint(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        out = pd.DataFrame() if df is None else df.copy()
        if FINGERPRINT_COL not in out.columns:
            out[FINGERPRINT_COL] = pd.Series(dtype=str)
        return out
    out = df.copy()
    out[FINGERPRINT_COL] = out.apply(build_import_fingerprint, axis=1)
    return out


def merge_idempotent(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Retorna (merged, nuevos_insertados, duplicados_omitidos).
    """
    ex = with_fingerprint(existing)
    inc = with_fingerprint(incoming)
    if inc.empty:
        return ex, 0, 0
    fp_existing = set(ex[FINGERPRINT_COL].astype(str).tolist()) if not ex.empty else set()
    mask_new = ~inc[FINGERPRINT_COL].astype(str).isin(fp_existing)
    inc_new = inc.loc[mask_new].copy()
    dup = int((~mask_new).sum())
    if ex.empty:
        merged = inc_new.copy()
    else:
        cols = list(ex.columns)
        for c in inc_new.columns:
            if c not in cols:
                cols.append(c)
        merged = pd.concat([ex.reindex(columns=cols), inc_new.reindex(columns=cols)], ignore_index=True)
    return merged, int(len(inc_new)), dup
