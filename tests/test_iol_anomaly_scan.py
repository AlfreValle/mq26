from __future__ import annotations

import numpy as np
import pandas as pd

from services.iol_api.anomaly_scan import (
    PearlAnomalyConfig,
    hist_meets_minimum,
    parse_iol_quote_price_volume,
    score_pearl_buy,
)


def test_parse_iol_quote_ultimo_precio():
    px, vol = parse_iol_quote_price_volume({"ultimoPrecio": 150.25})
    assert px == 150.25
    assert vol is None


def test_parse_iol_quote_fallback_keys():
    px, vol = parse_iol_quote_price_volume({"precioUltimo": 10, "volumen": 5000})
    assert px == 10.0
    assert vol == 5000.0


def test_parse_iol_quote_invalid():
    assert parse_iol_quote_price_volume({}) == (None, None)
    assert parse_iol_quote_price_volume("x") == (None, None)


def test_score_spike_close_positive_z():
    rng = np.random.default_rng(42)
    # Ruido pequeño para std > 0; ultimo cierre alineado con live moderado en hist
    close = pd.Series(100.0 + rng.normal(0, 0.25, 28))
    cfg = PearlAnomalyConfig(
        return_window=20,
        min_z_for_signal=0.5,
        min_hist_bars=10,
        tech_strategy_name=None,
        weight_return=1.0,
        weight_volume=0.0,
        weight_tech=0.0,
    )
    r = score_pearl_buy(close, 110.0, cfg)
    assert r.score > 0.5
    assert r.z_return is not None and r.z_return > 3.0


def test_score_flat_market_zero():
    close = pd.Series([100.0 + 0.01 * i for i in range(30)])
    cfg = PearlAnomalyConfig(min_z_for_signal=2.0, tech_strategy_name=None, weight_volume=0.0, weight_tech=0.0)
    r = score_pearl_buy(close, float(close.iloc[-1]), cfg)
    assert r.score == 0.0


def test_volume_component_boosts_score():
    rng = np.random.default_rng(7)
    close = pd.Series(100.0 + rng.normal(0, 0.35, 28))
    vol = pd.Series(np.maximum(1000.0, rng.lognormal(10, 0.25, 28)))
    last_med = float(vol.median())
    cfg = PearlAnomalyConfig(
        min_z_for_signal=0.3,
        z_cap=6.0,
        min_vol_ratio=1.5,
        tech_strategy_name=None,
        weight_return=0.5,
        weight_volume=0.5,
        weight_tech=0.0,
    )
    r = score_pearl_buy(close, 112.0, cfg, volume_hist=vol, live_volume=last_med * 6.0)
    assert r.vol_ratio is not None and r.vol_ratio > 1.5
    assert r.score > 0.25


def test_hist_meets_minimum():
    c = pd.Series(np.linspace(100, 105, 20))
    assert hist_meets_minimum(c, PearlAnomalyConfig(min_hist_bars=15)) is True
    assert hist_meets_minimum(c.iloc[:10], PearlAnomalyConfig(min_hist_bars=15)) is False
