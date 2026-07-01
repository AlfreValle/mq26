"""tests/test_recomendacion_capital.py — Motor recomendación capital S5."""
import pandas as pd

from core.renta_fija_ar import es_renta_fija
from services.recomendacion_capital import generar_primera_cartera, recomendar


def test_generar_primera_cartera_desplegar_todo_invierte_casi_todo():
    """desplegar_todo=True (wizard de capital del asesor) deja <5% en efectivo;
    sin la flag reserva pólvora seca (perlas + renta AR) y deja bastante más.
    Regresión del hallazgo del dictamen: Arriesgado dejaba ~34% ocioso."""
    cap = 15_000_000.0
    kw = dict(
        capital_ars=cap, perfil="Arriesgado", ccl=1450.0, precios_dict={},
        universo_df=None, cliente_nombre="T", df_analisis=None, df_scores=None,
    )
    rr_full = generar_primera_cartera(**kw, desplegar_todo=True)
    rr_base = generar_primera_cartera(**kw, desplegar_todo=False)
    assert rr_full.compras_recomendadas, "debe haber compras"
    rem_full = float(rr_full.capital_remanente_ars)
    rem_base = float(rr_base.capital_remanente_ars)
    # Con la flag, el efectivo ocioso queda <5% del capital.
    assert rem_full <= cap * 0.05, f"efectivo {rem_full / cap:.1%} debería ser <5%"
    # Y estrictamente menos efectivo que sin la flag (que reserva el 20% perlas).
    assert rem_full < rem_base


def test_n_activos_objetivo_escala_por_capital():
    """La cantidad de activos objetivo escala por tramo de capital (negocio)."""
    from core.cartera_optima import n_activos_objetivo

    assert n_activos_objetivo(1_000_000) == 8
    assert n_activos_objetivo(3_000_000) == 8       # límite inferior inclusive
    assert n_activos_objetivo(3_000_001) == 10
    assert n_activos_objetivo(5_000_000) == 10
    assert n_activos_objetivo(7_500_000) == 12
    assert n_activos_objetivo(10_000_000) == 12
    assert n_activos_objetivo(10_000_001) == 15
    assert n_activos_objetivo(50_000_000) == 15


def test_desplegar_todo_menos_5pct_con_pocos_activos():
    """Regresión: con scanner activo la cartera trae POCOS activos; cada uno topaba
    el cap de overweight y dejaba ~21% en efectivo. La fase 3 debe colocar el
    residual igual y dejar <5%, aun con un universo de scoring chico."""
    scores = pd.DataFrame(
        [
            {"Ticker": "AAPL", "Sector": "Tech", "Score_Total": 80.0},
            {"Ticker": "MSFT", "Sector": "Tech", "Score_Total": 75.0},
            {"Ticker": "KO", "Sector": "Consumo", "Score_Total": 60.0},
        ]
    )
    cap = 12_000_000.0
    rr = generar_primera_cartera(
        capital_ars=cap, perfil="Arriesgado", ccl=1500.0, precios_dict={},
        universo_df=None, cliente_nombre="T", df_analisis=None,
        df_scores=scores, desplegar_todo=True,
    )
    assert rr.compras_recomendadas
    assert float(rr.capital_remanente_ars) <= cap * 0.05, (
        f"efectivo {rr.capital_remanente_ars / cap:.1%} debería ser <5% aun con pocos activos"
    )


def test_cartera_recomendada_alcanza_target_rf_del_diagnostico():
    """Regresión (reporte de usuario): la cartera recomendada arrancaba con score
    bajo (54/100) porque traía ~15-21pp MENOS renta fija que la que el diagnóstico
    exige (target_rf_efectivo), penalizando 'cobertura defensiva'. El recomendador y
    el diagnóstico ahora comparten UNA fuente de verdad: la RF desplegada debe quedar
    cerca del target del perfil (single source of truth), sin dejar efectivo ocioso."""
    from core.perfil_allocation import target_rf_efectivo
    from core.renta_fija_ar import es_renta_fija

    # Precios ARS realistas (los ONs se resuelven por paridad_ref×CCL del catálogo).
    rv = ["AAPL", "ABBV", "AMZN", "BABA", "BRKB", "COST", "CVX", "DIA", "GOOGL",
          "JNJ", "JPM", "KO", "MA", "MCD", "MELI", "META", "MSFT", "NVDA", "QQQ",
          "SPY", "UBER", "V", "VIST", "YPFD", "CEPU", "PAMP"]
    precios = {t: 25_000.0 for t in rv}
    precios.update({"SPY": 70_000.0, "QQQ": 65_000.0, "NVDA": 18_000.0, "AAPL": 30_000.0})

    for perfil in ("Conservador", "Moderado", "Arriesgado"):
        target = float(target_rf_efectivo(perfil, "largo"))
        for cap in (5_000_000.0, 12_000_000.0):
            rr = generar_primera_cartera(
                capital_ars=cap, perfil=perfil, ccl=1200.0, precios_dict=precios,
                desplegar_todo=True,
            )
            items = rr.compras_recomendadas or []
            tot = sum(float(i.monto_ars) for i in items) or 1.0
            rf = sum(float(i.monto_ars) for i in items if es_renta_fija(i.ticker)) / tot
            # RF desplegada cerca del target (banda amplia: láminas enteras + tope
            # de concentración por nombre limitan la precisión, pero no debe quedar
            # ni muy por debajo (score bajo) ni disparada por encima (poca RV)).
            assert target - 0.12 <= rf <= target + 0.10, (
                f"{perfil} cap={cap/1e6:.0f}M: RF desplegada {rf:.0%} lejos del "
                f"target {target:.0%} (single source of truth recomendador↔diagnóstico)"
            )


def test_cartera_recomendada_respeta_su_propio_limite_concentracion():
    """Regresión (reporte de usuario): una cartera RECOMENDADA por el wizard no debe
    arrancar marcada por "concentración elevada" en su propio diagnóstico. El sleeve
    de ONs caía entero en un nombre (p. ej. IRCPO/TLCTO ~30-60%) y las fases de
    mop-up del wizard amplificaban la mayor posición sin tope. Ahora ningún nombre
    supera el límite de concentración adaptativo del perfil (con ≥3 líneas)."""
    from core.diagnostico_types import LIMITE_CONCENTRACION

    def _limite_adaptativo(perfil: str, n: int) -> float:
        base = LIMITE_CONCENTRACION.get(perfil, 0.25)
        if 0 < n <= 6:
            return max(base, min(0.46, 1.0 / n + 0.05))
        return base

    # Precios ARS realistas para que los CEDEARs no se descarten por falta de precio
    # (en producción se resuelven): así el total invertido ≈ capital, como mide el
    # diagnóstico (peso = monto / total invertido, sin contar efectivo ocioso).
    rv = ["AAPL", "ABBV", "AMZN", "BABA", "BRKB", "COST", "CVX", "DIA", "GOOGL",
          "JNJ", "JPM", "KO", "MA", "MCD", "MELI", "META", "MSFT", "NVDA", "QQQ",
          "SPY", "UBER", "V", "VIST", "YPFD", "CEPU", "PAMP"]
    precios = {t: 25_000.0 for t in rv}
    precios.update({"SPY": 70_000.0, "QQQ": 65_000.0, "NVDA": 18_000.0, "AAPL": 30_000.0})

    for perfil in ("Conservador", "Moderado", "Arriesgado"):
        for cap in (3_000_000.0, 8_000_000.0, 20_000_000.0):
            rr = generar_primera_cartera(
                capital_ars=cap, perfil=perfil, ccl=1200.0, precios_dict=precios,
                desplegar_todo=True,
            )
            items = rr.compras_recomendadas or []
            invertido = sum(float(i.monto_ars) for i in items) or 1.0
            n = len(items)
            if n < 3:
                continue  # 1-2 líneas: concentrado por naturaleza, exento
            lim = _limite_adaptativo(perfil, n)
            peor_t, peor_w = max(
                ((i.ticker, float(i.monto_ars) / invertido) for i in items),
                key=lambda x: x[1], default=("", 0.0),
            )
            assert peor_w <= lim + 1e-6, (
                f"{perfil} cap={cap/1e6:.0f}M: {peor_t} pesa {peor_w:.1%} > límite "
                f"{lim:.1%} (n={n}) — la cartera recomendada se autopenaliza"
            )


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
    # ON defensivas de mayor calificación — el ranking varía según TIR actualizada:
    # PN43O (AA+, 6.8%), TSC4O (AA+, 7.0%), TLCTO (AA, 7.5%) son todas válidas
    assert r.compras_recomendadas[0].ticker in ("PN43O", "TLCTO", "TSC4O")


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
    """
    Con $100k ARS, instrumentos caros (SPY $120k, MSFT $80k) deben ir a pendientes
    porque su precio supera el capital asignado por peso.
    GLD fue eliminado del ideal (se remapó a SPY); esta versión usa SPY caro.
    """
    df = pd.DataFrame()
    # SPY a $120k y MSFT a $80k — ambos superan lo que puede asignarse con $100k
    precios = {"SPY": 120_000.0, "MSFT": 80_000.0, "QQQ": 90_000.0}
    r = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=100_000.0,
        ccl=1150.0,
        precios_dict=precios,
        diagnostico=None,
    )
    # Al menos un instrumento caro debe ir a pendientes O quedar mucho capital sin usar
    hay_pendiente_caro = any(
        p.get("precio_ars", 0) > 30_000 for p in r.pendientes_proxima_inyeccion
    )
    assert hay_pendiente_caro or r.capital_remanente_ars >= 50_000


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


def test_blocklist_no_aparece_en_satelites():
    """ADM/GIS/CMCSA en df_analisis con score alto NO deben aparecer como compras."""
    from config import TICKERS_NO_CEDEAR_BYMA

    df_analisis = pd.DataFrame([
        {"TICKER": "ADM",   "PUNTAJE_TECNICO": 9.0, "RSI": 45},
        {"TICKER": "GIS",   "PUNTAJE_TECNICO": 9.0, "RSI": 45},
        {"TICKER": "CMCSA", "PUNTAJE_TECNICO": 9.0, "RSI": 45},
        {"TICKER": "MSFT",  "PUNTAJE_TECNICO": 8.5, "RSI": 50},
    ])
    precios = {
        "PN43O": 80_000.0, "TLCTO": 70_000.0, "GLD": 12_000.0,
        "BRKB": 30_000.0, "SPY": 55_000.0, "MSFT": 20_000.0,
        "ADM": 120_000.0, "GIS": 50_000.0, "CMCSA": 35_000.0,
    }
    r = recomendar(
        df_ag=pd.DataFrame(),
        perfil="Moderado",
        horizonte_label="1 año",
        capital_ars=2_000_000.0,
        ccl=1200.0,
        precios_dict=precios,
        diagnostico=None,
        df_analisis=df_analisis,
    )
    tickers_compras = {c.ticker for c in r.compras_recomendadas}
    blocked = TICKERS_NO_CEDEAR_BYMA & tickers_compras
    assert not blocked, f"Tickers bloqueados aparecieron en compras: {blocked}"


def test_cartera_ideal_suma_uno_por_perfil():
    """Cada perfil de CARTERA_IDEAL debe sumar 1.0."""
    from core.diagnostico_types import CARTERA_IDEAL

    for perfil, pesos in CARTERA_IDEAL.items():
        total = round(sum(pesos.values()), 3)
        assert total == 1.0, f"Perfil {perfil!r}: pesos suman {total}, esperado 1.0"


def test_cartera_ideal_no_incluye_bloqueados():
    """Ningún perfil de CARTERA_IDEAL debe incluir tickers bloqueados."""
    from config import TICKERS_NO_CEDEAR_BYMA
    from core.diagnostico_types import CARTERA_IDEAL

    for perfil, pesos in CARTERA_IDEAL.items():
        for ticker in pesos:
            if ticker.startswith("_"):
                continue
            assert ticker not in TICKERS_NO_CEDEAR_BYMA, (
                f"Ticker bloqueado {ticker!r} encontrado en CARTERA_IDEAL[{perfil!r}]"
            )


def test_cartera_ideal_arriesgado_cubre_mas_sectores():
    """El perfil Arriesgado debe tener tickers de Argentina (GGAL/YPFD) además de tech global."""
    from core.diagnostico_types import CARTERA_IDEAL
    from services.recomendacion_capital import _expandir_ideal

    # CARTERA_IDEAL ahora contiene pools dinámicos (_ON_USD_POOL, _RV_CEDEAR_POOL).
    # Hay que expandir antes de verificar los tickers concretos.
    ideal_exp = _expandir_ideal(CARTERA_IDEAL["Arriesgado"], "Arriesgado")
    tickers = {k for k in ideal_exp if not k.startswith("_")}
    has_ar = bool(tickers & {"GGAL", "YPFD", "CEPU", "PAMP", "TGNO4", "VIST"})
    has_defensivo = bool(tickers & {"KO", "PEP", "JNJ", "PG", "GLD", "SPY"})
    has_tech = bool(tickers & {"MSFT", "NVDA", "META", "AMZN", "GOOGL", "AAPL", "AMD", "PLTR"})
    assert has_ar,        "Perfil Arriesgado debe incluir al menos un activo local AR"
    assert has_defensivo, "Perfil Arriesgado debe incluir al menos un activo defensivo (GLD o SPY)"
    assert has_tech,      "Perfil Arriesgado debe incluir exposición tech"
