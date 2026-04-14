from __future__ import annotations

import threading

import pandas as pd
from sqlalchemy import create_engine

import core.transaccional_repository as tr


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "CARTERA": "Ana | Principal",
                "FECHA_COMPRA": "2026-04-10",
                "TICKER": "AAPL",
                "CANTIDAD": 1.0,
                "PPC_USD": 100.0,
                "PPC_ARS": 0.0,
                "TIPO": "CEDEAR",
                "LAMINA_VN": float("nan"),
                "MONEDA_PRECIO": "USD_MEP",
            }
        ]
    )


def _sample_df_ticker(ticker: str, qty: float) -> pd.DataFrame:
    df = _sample_df().copy()
    df.loc[0, "TICKER"] = str(ticker).upper()
    df.loc[0, "CANTIDAD"] = float(qty)
    return df


def _signature(df: pd.DataFrame) -> tuple:
    cols = ["CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD", "PPC_USD", "PPC_ARS", "TIPO", "MONEDA_PRECIO"]
    n = tr._normalize_df(df)  # noqa: SLF001 - test de integración sobre contrato interno
    if n.empty:
        return tuple()
    out = []
    for _, r in n[cols].sort_values(["TICKER", "FECHA_COMPRA"]).iterrows():
        out.append(tuple(str(r[c]) for c in cols))
    return tuple(out)


def test_save_legacy_csv_no_llama_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ26_PERSISTENCE_MODE", "legacy_csv")
    monkeypatch.setattr(tr, "RUTA_TRANSAC", tmp_path / "trans.csv")
    calls = {"db": 0}

    def _fake_save_db(_df):
        calls["db"] += 1

    monkeypatch.setattr(tr, "_save_db", _fake_save_db)
    tr.save_transaccional(_sample_df())
    assert (tmp_path / "trans.csv").exists()
    assert calls["db"] == 0


def test_save_db_only_llama_db_no_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ26_PERSISTENCE_MODE", "db_only")
    monkeypatch.setattr(tr, "RUTA_TRANSAC", tmp_path / "trans.csv")
    calls = {"db": 0}

    def _fake_save_db(_df):
        calls["db"] += 1

    monkeypatch.setattr(tr, "_save_db", _fake_save_db)
    tr.save_transaccional(_sample_df())
    assert not (tmp_path / "trans.csv").exists()
    assert calls["db"] == 1


def test_save_dual_write_csv_y_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ26_PERSISTENCE_MODE", "dual_write")
    monkeypatch.setattr(tr, "RUTA_TRANSAC", tmp_path / "trans.csv")
    calls = {"db": 0}

    def _fake_save_db(_df):
        calls["db"] += 1

    monkeypatch.setattr(tr, "_save_db", _fake_save_db)
    tr.save_transaccional(_sample_df())
    assert (tmp_path / "trans.csv").exists()
    assert calls["db"] == 1


def test_dual_write_concurrente_csv_bd_consistente(tmp_path, monkeypatch):
    """
    Cobertura de concurrencia SSOT:
    dos escrituras simultáneas en dual_write deben terminar en estado consistente
    entre CSV y BD (sin estado parcial/corrupto), aunque el resultado final sea LWW.
    """
    monkeypatch.setenv("MQ26_PERSISTENCE_MODE", "dual_write")
    monkeypatch.setattr(tr, "RUTA_TRANSAC", tmp_path / "trans.csv")
    db_path = tmp_path / "mq26_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    monkeypatch.setattr(tr, "get_engine", lambda: engine)

    df_a = _sample_df_ticker("AAPL", 1.0)
    df_b = _sample_df_ticker("MSFT", 2.0)
    excs: list[Exception] = []
    barrier = threading.Barrier(2)

    def _writer(df_in: pd.DataFrame) -> None:
        try:
            barrier.wait(timeout=10)
            tr.save_transaccional(df_in)
        except Exception as e:  # pragma: no cover
            excs.append(e)

    t1 = threading.Thread(target=_writer, args=(df_a,))
    t2 = threading.Thread(target=_writer, args=(df_b,))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not excs, f"Errores de concurrencia en save_transaccional: {excs}"
    assert (tmp_path / "trans.csv").exists()

    # Consistencia SSOT: CSV y BD reflejan el mismo snapshot final.
    df_csv = pd.read_csv(tmp_path / "trans.csv", encoding="utf-8-sig")
    df_db = tr._load_db()  # noqa: SLF001
    sig_csv = _signature(df_csv)
    sig_db = _signature(df_db)
    assert sig_csv == sig_db
    assert sig_csv in {_signature(df_a), _signature(df_b)}
