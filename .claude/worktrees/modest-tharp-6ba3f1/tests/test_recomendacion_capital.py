"""tests/test_recomendacion_capital.py — Motor recomendación capital S5."""
import pandas as pd

from core.renta_fija_ar import es_renta_fija
from services.recomendacion_capital import recomendar


def test_recomendacion_prioriza_defensa_primero():
    df = pd.DataFrame(
        [{"TICKER": "NVDA", "VALOR_ARS": 1_000_000.0, "TIPO": "CEDEAR", "PESO_PCT": 1.0}]
    )
    precios = {"PN43O": 80_000.0, "TLCTO": 70_000.0, "MSFT": 50_000.0, "NVDA": 100.0}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=500_000.0,
        ccl=1000.0,
        precios_dict=precios,
        diagnostico=None,
        universo_df=None,
        df_analisis=None,
    )
    assert r.compras_recomendadas, "debe haber al menos una compra"
    assert r.compras_recomendadas[0].ticker in ("PN43O", "TLCTO")


def test_recomendacion_unidades_enteras():
    df = pd.DataFrame()
    precios = {"GLD": 1000.0, "SPY": 2000.0}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=50_000.0,
        ccl=1150.0,
        precios_dict=precios,
        diagnostico=None,
    )
    for c in r.compras_recomendadas:
        assert isinstance(c.unidades, int)
        assert c.unidades >= 1


def test_recomendacion_capital_no_supera_disponible():
    df = pd.DataFrame(
        [{"TICKER": "KO", "VALOR_ARS": 100_000.0, "TIPO": "CEDEAR", "PESO_PCT": 1.0}]
    )
    precios = {"GLD": 10_000.0, "INCOME": 5000.0, "SPY": 15_000.0, "KO": 100.0}
    cap = 80_000.0
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=cap,
        ccl=1000.0,
        precios_dict=precios,
        diagnostico=None,
        df_analisis=None,
    )
    usado = sum(i.monto_ars for i in r.compras_recomendadas)
    assert usado <= cap + 1e-6


def test_pendientes_si_precio_supera_capital():
    df = pd.DataFrame()
    precios = {"GLD": 215_000.0}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=100_000.0,
        ccl=1150.0,
        precios_dict=precios,
        diagnostico=None,
    )
    hay_gld_pend = any(
        p.get("ticker") == "GLD" for p in r.pendientes_proxima_inyeccion
    )
    assert hay_gld_pend or r.capital_remanente_ars >= 99_000


def test_recomendacion_cartera_perfecta_no_compra_nada_innecesario():
    filas = []
    ideal_w = {
        "_RENTA_AR": 0.15,
        "PN43O": 0.20,
        "TLCTO": 0.15,
        "GLD": 0.05,
        "BRKB": 0.08,
        "SPY": 0.12,
        "MSFT": 0.10,
        "GOOGL": 0.08,
        "AMZN": 0.07,
    }
    total = 1_000_000.0
    for t, w in ideal_w.items():
        if t.startswith("_"):
            continue
        tipo = "ON_USD" if t in ("PN43O", "TLCTO") else "CEDEAR"
        filas.append(
            {"TICKER": t, "VALOR_ARS": total * w, "TIPO": tipo, "PESO_PCT": w}
        )
    df = pd.DataFrame(filas)
    precios = {t: 10_000.0 for t in ideal_w if not str(t).startswith("_")}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=25_000.0,
        ccl=1000.0,
        precios_dict=precios,
        diagnostico=None,
        df_analisis=pd.DataFrame(),
    )
    tickers_compra = {i.ticker for i in r.compras_recomendadas}
    assert "MSFT" not in tickers_compra or len(tickers_compra) == 0


def test_recomendacion_capital_cero():
    df = pd.DataFrame()
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=0.0,
        ccl=1150.0,
        precios_dict={"GLD": 1.0},
        diagnostico=None,
    )
    assert r.compras_recomendadas == []


def test_renta_ar_placeholder_o_compra_rf_concreta():
    df = pd.DataFrame(
        [{"TICKER": "SPY", "VALOR_ARS": 100_000.0, "TIPO": "CEDEAR", "PESO_PCT": 1.0}]
    )
    precios = {"GLD": 10_000.0, "INCOME": 5000.0, "SPY": 100.0}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=400_000.0,
        ccl=1000.0,
        precios_dict=precios,
        diagnostico=None,
        df_analisis=None,
    )
    pend_renta = [
        p for p in r.pendientes_proxima_inyeccion
        if p.get("ticker") == "_RENTA_AR" or "ON/Bonos AR" in str(p.get("motivo", ""))
    ]
    hay_compra_rf = any(es_renta_fija(c.ticker) for c in r.compras_recomendadas)
    assert hay_compra_rf or pend_renta


def test_recomendar_precios_vacios_no_falla():
    df = pd.DataFrame()
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=50_000.0,
        ccl=1000.0,
        precios_dict={},
        diagnostico=None,
    )
    assert r.capital_remanente_ars >= 0.0
    assert r.n_compras >= 0


def test_alerta_mercado_sin_compras():
    df = pd.DataFrame()
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=500_000.0,
        ccl=1000.0,
        precios_dict={"GLD": 10_000.0},
        diagnostico=None,
        market_stress={"vix": 35.0, "spy_drawdown_30d": None},
    )
    assert r.alerta_mercado is True
    assert r.compras_recomendadas == []
