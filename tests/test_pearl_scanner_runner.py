from __future__ import annotations

import numpy as np
import pandas as pd

from services.iol_api.anomaly_scan import PearlAnomalyConfig
from services.iol_api.pearl_scanner_runner import (
    default_yahoo_ticker,
    read_symbol_rows,
    run_iteration,
)
from services.iol_api.pearl_state import PearlScannerState


def test_read_symbol_rows(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# comentario\nGGAL\nAAPL,QQQ\n", encoding="utf-8")
    assert read_symbol_rows(f) == [("GGAL", None), ("AAPL", "QQQ")]


def test_default_yahoo_ticker():
    assert default_yahoo_ticker("GGAL", "argentina") == "GGAL.BA"
    assert default_yahoo_ticker("AAPL", "usa") == "AAPL"
    assert default_yahoo_ticker("GGAL.BA", "argentina") == "GGAL.BA"


def test_run_iteration_offline_picks_spike(monkeypatch, tmp_path):
    from dataclasses import replace

    rng = np.random.default_rng(1)
    n = 30
    close = 100.0 + rng.normal(0, 0.4, n)
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "close": close,
            "volume": np.abs(rng.normal(1e6, 2e4, n)),
        }
    )
    df.loc[df.index[-1], "close"] = 118.0

    def fake_ensure(
        yahoo_ticker: str,
        period: str,
        cache_dir,
        ttl_sec: float,
    ) -> pd.DataFrame:
        return df

    monkeypatch.setattr("services.iol_api.pearl_scanner_runner.ensure_hist_cached", fake_ensure)

    state_path = tmp_path / "pearl.json"
    cfg = replace(
        PearlAnomalyConfig(),
        min_z_for_signal=0.2,
        tech_strategy_name=None,
        weight_return=1.0,
        weight_volume=0.0,
        weight_tech=0.0,
    )
    state, out = run_iteration(
        pairs=[("GGAL", None)],
        market="argentina",
        cfg=cfg,
        min_score=0.15,
        state=PearlScannerState(),
        state_path=state_path,
        client=None,
        offline=True,
        notify_telegram=False,
        use_position_state=False,
        dedupe_min_sec=0.0,
        dedupe_score_delta=0.0,
        cache_dir=tmp_path / "cache",
        hist_period="3mo",
        cache_ttl_sec=3600.0,
    )
    assert "picked" in out
    assert out["picked"]["symbol"] == "GGAL"
    assert float(out["picked"]["score"]) >= 0.15
