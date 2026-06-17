"""Tests core/macro_views.py — views automáticos desde MACRO_AR para Black-Litterman."""
from __future__ import annotations

import numpy as np

from core.macro_views import (
    TIPO_BONO_CER,
    TIPO_BONO_USD_SOB,
    TIPO_CAUCION_ARS,
    TIPO_CEDEAR,
    TIPO_FCI_ARS,
    TIPO_FCI_USD,
    TIPO_LOCAL_RV,
    TIPO_ON_USD,
    detectar_tipo_desde_ticker,
    enriquecer_bl_con_macro,
    views_desde_macro,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────
# Usar exactamente los mismos nombres de claves que lee macro_views.py

MACRO = {
    "risk_free_rate_us":     0.045,
    "prima_riesgo_global":   0.06,
    "embi_arg_bps":          650,
    "inflacion_mensual_ipc": 0.04,    # 4 % mensual
    "tna_plazo_fijo_30d":    0.60,
}

# Mapeo ticker → tipo para un universo diversificado
TIPOS_UNIVERSO = {
    "AAPL":  TIPO_CEDEAR,
    "GGAL":  TIPO_LOCAL_RV,
    "AL30":  TIPO_BONO_USD_SOB,
    "TSC2O": TIPO_ON_USD,
    "TX26":  TIPO_BONO_CER,
    "CAU1":  TIPO_CAUCION_ARS,
    "FCARS": TIPO_FCI_ARS,
    "FCUSD": TIPO_FCI_USD,
}


# ─── Tests views_desde_macro ─────────────────────────────────────────────────

def test_retorna_dict_con_todos_los_tickers():
    views = views_desde_macro(MACRO, TIPOS_UNIVERSO)
    for t in TIPOS_UNIVERSO:
        assert t in views, f"Falta ticker {t!r} en views"


def test_valores_son_floats():
    views = views_desde_macro(MACRO, TIPOS_UNIVERSO)
    for k, v in views.items():
        assert isinstance(v, float), f"{k}: {v!r} no es float"


def test_cedear_view_positivo_en_mercado_normal():
    """Con RF=4.5%, ERP=6%, CCL+ se espera retorno positivo en ARS."""
    views = views_desde_macro(MACRO, {"AAPL": TIPO_CEDEAR})
    assert views["AAPL"] > 0.0


def test_caucion_ars_razonable():
    """Caución ARS ≈ TNA * 0.95 para FCI; TNA directa para caución."""
    views_cau = views_desde_macro(MACRO, {"CAU1": TIPO_CAUCION_ARS}, moneda="ARS")
    tna = MACRO["tna_plazo_fijo_30d"]
    assert abs(views_cau["CAU1"] - tna) < 0.05


def test_fci_ars_menor_que_caucion():
    """FCI cobra fee de gestión → debe ser menor que caución."""
    views = views_desde_macro(MACRO, {"CAU1": TIPO_CAUCION_ARS, "FCARS": TIPO_FCI_ARS})
    assert views["FCARS"] < views["CAU1"]


def test_bono_cer_supera_caucion_en_alta_inflacion():
    """En inflación alta, BONO_CER debería superar caución."""
    macro_alta_inf = {**MACRO, "inflacion_mensual_ipc": 0.08}  # 8% mensual
    views = views_desde_macro(macro_alta_inf, {"TX26": TIPO_BONO_CER, "CAU1": TIPO_CAUCION_ARS})
    assert views["TX26"] > views["CAU1"]


def test_on_usd_sube_con_embi():
    """Mayor EMBI → mayor tasa ON → mayor retorno esperado."""
    views_bajo = views_desde_macro({**MACRO, "embi_arg_bps": 300},  {"TSC2O": TIPO_ON_USD})
    views_alto  = views_desde_macro({**MACRO, "embi_arg_bps": 1500}, {"TSC2O": TIPO_ON_USD})
    assert views_alto["TSC2O"] > views_bajo["TSC2O"]


def test_moneda_usd_difiere_de_ars_para_cedear():
    """En moneda USD no se aplica CCL drift completo; retorno debe diferir."""
    views_ars = views_desde_macro(MACRO, {"AAPL": TIPO_CEDEAR}, moneda="ARS")
    views_usd = views_desde_macro(MACRO, {"AAPL": TIPO_CEDEAR}, moneda="USD")
    assert views_ars["AAPL"] != views_usd["AAPL"]


def test_tipos_vacio_devuelve_dict_vacio():
    views = views_desde_macro(MACRO, {})
    assert views == {}


def test_tipo_desconocido_no_falla():
    views = views_desde_macro(MACRO, {"XTOK": "TIPO_RARO_XYZ"})
    assert "XTOK" in views
    assert isinstance(views["XTOK"], float)


# ─── Tests detectar_tipo_desde_ticker ────────────────────────────────────────

def test_cedear_detectado():
    assert detectar_tipo_desde_ticker("AAPL") == TIPO_CEDEAR
    assert detectar_tipo_desde_ticker("MSFT") == TIPO_CEDEAR
    assert detectar_tipo_desde_ticker("GOOG") == TIPO_CEDEAR


def test_bono_soberano_detectado():
    for ticker in ("AL30", "GD30", "AL35", "GD35"):
        result = detectar_tipo_desde_ticker(ticker)
        # Puede ser BONO_USD_SOB o TIPO_ON_USD si config no disponible
        assert result in (TIPO_BONO_USD_SOB, TIPO_ON_USD), f"{ticker} → {result}"


def test_on_detectada_por_sufijo_o():
    # TSC2O, YMCQO, MRCEO terminan en O con 5-6 chars
    for ticker in ("TSC2O", "YMCQO", "MRCEO"):
        t = detectar_tipo_desde_ticker(ticker)
        assert t == TIPO_ON_USD, f"{ticker} → {t}"


def test_bono_cer_detectado():
    for ticker in ("TX26", "TX28", "DICP"):
        t = detectar_tipo_desde_ticker(ticker)
        assert t == TIPO_BONO_CER, f"{ticker} → {t}"


def test_local_rv_detectado():
    for ticker in ("GGAL", "YPFD", "BMA", "SUPV"):
        t = detectar_tipo_desde_ticker(ticker)
        assert t == TIPO_LOCAL_RV, f"{ticker} → {t}"


def test_ticker_desconocido_devuelve_cedear():
    """Ticker no reconocido cae en default CEDEAR."""
    assert detectar_tipo_desde_ticker("XYZXYZ123") == TIPO_CEDEAR


# ─── Tests enriquecer_bl_con_macro ───────────────────────────────────────────

def test_enriquecer_devuelve_dict_esperado():
    n = 4
    tickers = ["AAPL", "GGAL", "AL30", "TSC2O"]
    mu_sample = np.array([0.15, 0.25, 0.12, 0.10])
    rng = np.random.default_rng(0)
    R = rng.normal(0, 0.01, (252, n))
    Sigma = np.cov(R.T) * 252
    result = enriquecer_bl_con_macro(MACRO, tickers, Sigma, mu_sample)
    assert "mu_bl" in result
    assert "Sigma" in result or "result" in result
    assert len(result["mu_bl"]) == n


def test_mu_bl_distinto_de_mu_sample():
    n = 4
    tickers = ["AAPL", "GGAL", "AL30", "TSC2O"]
    mu_sample = np.array([0.15, 0.25, 0.12, 0.10])
    rng = np.random.default_rng(1)
    R = rng.normal(0, 0.01, (252, n))
    Sigma = np.cov(R.T) * 252
    result = enriquecer_bl_con_macro(MACRO, tickers, Sigma, mu_sample)
    # BL mezcla mu_sample con views → no debe ser idéntico
    assert not np.allclose(result["mu_bl"], mu_sample, atol=1e-3)


def test_enriquecer_acepta_w_mkt():
    n = 3
    tickers = ["MSFT", "YPFD", "GD30"]
    mu_sample = np.array([0.18, 0.30, 0.09])
    rng = np.random.default_rng(2)
    Sigma = np.cov(rng.normal(0, 0.01, (200, n)).T) * 252
    w_mkt = np.array([0.5, 0.3, 0.2])
    result = enriquecer_bl_con_macro(MACRO, tickers, Sigma, mu_sample, w_mkt=w_mkt)
    assert result["mu_bl"].shape == (n,)


def test_enriquecer_tipos_explicitos():
    """Si se pasan tipos_activos explícitos, deben usarse esos en lugar de la heurística."""
    n = 2
    tickers = ["TKA", "TKB"]
    mu_sample = np.array([0.12, 0.20])
    rng = np.random.default_rng(3)
    Sigma = np.cov(rng.normal(0, 0.01, (100, n)).T) * 252
    tipos = {"TKA": TIPO_CAUCION_ARS, "TKB": TIPO_LOCAL_RV}
    result = enriquecer_bl_con_macro(MACRO, tickers, Sigma, mu_sample, tipos_activos=tipos)
    assert result["tipos"] == tipos
    assert "TKA" in result["views"]
