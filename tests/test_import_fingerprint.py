import pandas as pd

from core.import_fingerprint import FINGERPRINT_COL, merge_idempotent


def _df_base() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "CARTERA": "Ana | Principal",
                "FECHA_COMPRA": "2026-04-01",
                "TICKER": "AAPL",
                "CANTIDAD": 10,
                "PPC_USD": 200.0,
                "PPC_ARS": 0.0,
                "TIPO": "CEDEAR",
                "LAMINA_VN": float("nan"),
                "MONEDA_PRECIO": "USD_MEP",
            }
        ]
    )


def test_merge_idempotent_omite_duplicados_exactos():
    existing = _df_base()
    incoming = _df_base()
    merged, n_new, n_dup = merge_idempotent(existing, incoming)
    assert n_new == 0
    assert n_dup == 1
    assert len(merged) == 1
    assert FINGERPRINT_COL in merged.columns


def test_merge_idempotent_inserta_si_cambia_cantidad():
    existing = _df_base()
    incoming = _df_base()
    incoming.loc[0, "CANTIDAD"] = 12
    merged, n_new, n_dup = merge_idempotent(existing, incoming)
    assert n_new == 1
    assert n_dup == 0
    assert len(merged) == 2
