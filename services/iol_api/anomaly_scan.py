"""
Deteccion de anomalias estadisticas (corto plazo) para escaneo de candidatos a compra.
Funciones puras + parseo defensivo de cotizacion IOL. No garantiza resultados de mercado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from services.iol_api.live_signals import LiveSignalEngine, build_live_engine


@dataclass(frozen=True)
class PearlAnomalyConfig:
    """Parametros de scoring (calibrables por CLI o JSON)."""

    return_window: int = 20
    min_hist_bars: int = 15
    min_z_for_signal: float = 1.25
    z_cap: float = 4.0
    volume_window: int = 20
    min_vol_ratio: float = 1.8
    weight_return: float = 0.55
    weight_volume: float = 0.25
    weight_tech: float = 0.20
    tech_strategy_name: str | None = "breakout_close_20"

    def __post_init__(self) -> None:
        w = self.weight_return + self.weight_volume + self.weight_tech
        if w <= 0:
            raise ValueError("La suma de pesos debe ser > 0.")


@dataclass(frozen=True)
class PearlScoreResult:
    score: float
    reasons: tuple[str, ...]
    features: dict[str, float]
    z_return: float | None
    vol_ratio: float | None
    tech_side: str | None


def parse_iol_quote_price_volume(quote: dict[str, Any]) -> tuple[float | None, float | None]:
    """
    Extrae ultimo precio y volumen (si existe) de la respuesta JSON de cotizacion IOL.
    Acepta varias claves habituales por versiones distintas del API.
    """
    if not isinstance(quote, dict):
        return None, None

    def _first_float(keys: tuple[str, ...]) -> float | None:
        for k in keys:
            v = quote.get(k)
            if v is None:
                continue
            try:
                x = float(v)
                if np.isfinite(x) and x > 0:
                    return x
            except (TypeError, ValueError):
                continue
        return None

    price = _first_float(
        (
            "ultimoPrecio",
            "ultimoOperado",
            "precioUltimo",
            "precio",
            "precioVenta",
            "precioCompra",
            "cierre",
            "ultimo",
        )
    )
    vol = _first_float(
        (
            "volumen",
            "volumenOperado",
            "cantidadOperada",
            "cantidad",
            "volume",
        )
    )
    return price, vol


def compute_return_zscore(close_hist: pd.Series, live_price: float, window: int) -> tuple[float | None, str]:
    """
    Retorno desde ultimo cierre historico hasta live_price vs media/std de retornos diarios previos.
    """
    c = pd.to_numeric(close_hist, errors="coerce").dropna()
    if len(c) < 2 or not np.isfinite(live_price) or live_price <= 0:
        return None, "sin_serie"
    last_close = float(c.iloc[-1])
    if last_close <= 0:
        return None, "cierre_invalido"
    r_live = (live_price / last_close) - 1.0
    tail = c.iloc[-(window + 1) : -1] if len(c) > window + 1 else c.iloc[:-1]
    if len(tail) < 2:
        return None, "historial_corto"
    rets = tail.pct_change().dropna()
    if len(rets) < 3:
        return None, "pocos_retornos"
    mu = float(rets.mean())
    sd = float(rets.std(ddof=1))
    if sd <= 0 or not np.isfinite(sd):
        return None, "std_cero"
    z = (r_live - mu) / sd
    if not np.isfinite(z):
        return None, "z_nan"
    return float(z), "ok"


def compute_volume_ratio(volume_hist: pd.Series | None, live_volume: float | None) -> tuple[float | None, str]:
    if volume_hist is None or live_volume is None or live_volume <= 0:
        return None, "sin_volumen"
    v = pd.to_numeric(volume_hist, errors="coerce").dropna()
    if len(v) < 5:
        return None, "hist_vol_corto"
    med = float(v.median())
    if med <= 0:
        return None, "mediana_cero"
    ratio = float(live_volume) / med
    if not np.isfinite(ratio):
        return None, "ratio_nan"
    return ratio, "ok"


def _tech_boost(close_hist: pd.Series, live_price: float, name: str | None) -> tuple[float, str | None]:
    if not name:
        return 0.0, None
    try:
        engine: LiveSignalEngine = build_live_engine(name)
    except ValueError:
        return 0.0, None
    extended = pd.concat(
        [pd.to_numeric(close_hist, errors="coerce").dropna(), pd.Series([live_price])],
        ignore_index=True,
    )
    d = engine.decide(extended)
    if d.side == "BUY":
        return 1.0, d.reason
    return 0.0, None


def score_pearl_buy(
    close_hist: pd.Series,
    live_price: float,
    cfg: PearlAnomalyConfig,
    *,
    volume_hist: pd.Series | None = None,
    live_volume: float | None = None,
) -> PearlScoreResult:
    """
    Score 0..1 para candidato alcista (anomalia + confirmacion tecnica opcional).
    """
    reasons: list[str] = []
    feats: dict[str, float] = {}

    z_ret, z_msg = compute_return_zscore(close_hist, live_price, cfg.return_window)
    feats["z_return"] = float(z_ret) if z_ret is not None else float("nan")
    if z_ret is None:
        return PearlScoreResult(0.0, ("sin_z_retorno:" + z_msg,), feats, None, None, None)

    # Componente retorno: solo direccion alcista anomala
    if z_ret < cfg.min_z_for_signal:
        return PearlScoreResult(
            0.0,
            (f"Z retorno {z_ret:.2f} bajo umbral {cfg.min_z_for_signal}.",),
            feats,
            z_ret,
            None,
            None,
        )
    z_clamped = min(z_ret, cfg.z_cap)
    span = max(1e-6, cfg.z_cap - cfg.min_z_for_signal)
    comp_ret = (z_clamped - cfg.min_z_for_signal) / span
    comp_ret = float(max(0.0, min(1.0, comp_ret)))
    reasons.append(f"Retorno anomalo z={z_ret:.2f} ({z_msg}).")

    comp_vol = 0.0
    vol_ratio: float | None = None
    vr, vr_msg = compute_volume_ratio(volume_hist, live_volume)
    vol_ratio = vr
    feats["vol_ratio"] = float(vr) if vr is not None else float("nan")
    if vr is not None and vr >= cfg.min_vol_ratio:
        comp_vol = min(1.0, (vr - cfg.min_vol_ratio) / max(cfg.min_vol_ratio, 1e-6))
        reasons.append(f"Volumen x{vr:.2f} vs mediana ({vr_msg}).")

    comp_tech, tech_reason = _tech_boost(close_hist, live_price, cfg.tech_strategy_name)
    feats["tech_boost"] = comp_tech
    tech_side = "BUY" if comp_tech >= 0.99 else "HOLD"
    if tech_reason:
        reasons.append(f"Tecnico: {tech_reason}")

    w_sum = cfg.weight_return + cfg.weight_volume + cfg.weight_tech
    score = (
        cfg.weight_return * comp_ret + cfg.weight_volume * comp_vol + cfg.weight_tech * comp_tech
    ) / w_sum
    score = float(max(0.0, min(1.0, score)))

    return PearlScoreResult(
        score=score,
        reasons=tuple(reasons),
        features=feats,
        z_return=z_ret,
        vol_ratio=vol_ratio,
        tech_side=tech_side,
    )


def hist_meets_minimum(close_hist: pd.Series, cfg: PearlAnomalyConfig) -> bool:
    c = pd.to_numeric(close_hist, errors="coerce").dropna()
    return len(c) >= cfg.min_hist_bars
