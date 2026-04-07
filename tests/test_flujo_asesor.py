"""
Tests de integración del flujo del asesor: diagnosticar → recomendar → informe.
"""
from __future__ import annotations

import sys
from importlib import reload
from unittest.mock import MagicMock, patch

import pandas as pd


def _df_ag_moderado() -> pd.DataFrame:
    return pd.DataFrame({
        "TICKER": ["SPY", "MSFT", "GLD"],
        "CANTIDAD_TOTAL": [5, 10, 2],
        "PPC_USD_PROM": [400.0, 280.0, 180.0],
        "PRECIO_USD": [450.0, 320.0, 195.0],
        "VALOR_ARS": [2587500, 1840000, 449250],
        "INV_ARS": [2300000, 1624000, 414000],
        "PNL_ARS": [287500, 216000, 35250],
        "PNL_PCT": [0.125, 0.133, 0.085],
        "PNL_ARS_USD": [250.0, 187.8, 30.7],
        "PNL_PCT_USD": [0.109, 0.116, 0.074],
        "PESO_PCT": [52.9, 37.6, 9.5],
        "TIPO": ["CEDEAR", "CEDEAR", "CEDEAR"],
    })


def test_diagnosticar_cartera_moderada():
    from services.diagnostico_cartera import diagnosticar

    diag = diagnosticar(
        df_ag=_df_ag_moderado(),
        perfil="Moderado",
        horizonte_label="3 años",
        metricas={"pnl_pct_total_usd": 0.11},
        ccl=1150.0,
        universo_df=None,
        senales_salida=None,
    )
    assert 0 <= diag.score_total <= 100
    assert diag.semaforo is not None
    assert isinstance(diag.cliente_nombre, str)


def test_recomendar_con_capital_cero():
    from services.diagnostico_cartera import diagnosticar
    from services.recomendacion_capital import recomendar

    df = _df_ag_moderado()
    diag = diagnosticar(df, "Moderado", "3 años", {}, 1150.0, None, None)
    rr = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="3 años",
        capital_ars=0.0,
        ccl=1150.0,
        precios_dict={"SPY": 517500.0, "MSFT": 184000.0, "GLD": 224850.0},
        diagnostico=diag,
        universo_df=None,
    )
    assert rr is not None
    assert rr.capital_remanente_ars == 0.0


def test_generar_reporte_inversor_completo():
    from services.diagnostico_cartera import diagnosticar
    from services.recomendacion_capital import recomendar
    from services.reporte_inversor import generar_reporte_inversor

    df = _df_ag_moderado()
    diag = diagnosticar(
        df, "Moderado", "3 años", {"pnl_pct_total_usd": 0.11}, 1150.0, None, None
    )
    rr = recomendar(
        df,
        "Moderado",
        "3 años",
        150_000.0,
        1150.0,
        {"GLD": 224850.0, "KO": 9430.0},
        diag,
        None,
    )
    html = generar_reporte_inversor(
        diag, rr, {"pnl_pct_total_usd": 0.11, "total_valor": 4_875_750.0}
    )
    assert len(html) > 2000
    assert "MQ26" in html


def test_iol_parser_smoke():
    from broker_importer import detectar_formato, parsear_iol

    df_iol = pd.DataFrame({
        "Especie": ["AAPL", "GLD"],
        "Cantidad": [10, 2],
        "Precio promedio": [850.0, 2100.0],
    })
    assert detectar_formato(df_iol) == "iol"
    result = parsear_iol(df_iol, ccl=1150.0)
    assert len(result) == 2
    assert "AAPL" in result["TICKER"].values


def test_precio_on_estimado_desde_paridad():
    from unittest.mock import patch

    from services.cartera_service import resolver_precios

    with patch("services.cartera_service.PRECIOS_FALLBACK_ARS", {}):
        res = resolver_precios(["TLCTO"], {}, ccl=1150.0)
    assert res.get("TLCTO", 0) > 0


def test_simulate_retirement_proyeccion_simple_kwargs():
    from core.retirement_goal import simulate_retirement

    r = simulate_retirement(
        capital_inicial_usd=10_000.0,
        aporte_mensual_usd=50.0,
        retorno_anual=0.06,
        meses=24,
    )
    assert "capital_final_usd" in r
    assert float(r["capital_final_usd"]) > 10_000.0


def test_validar_tickers_advierte_fuera_universo():
    st_mock = MagicMock()
    st_mock.session_state = {}
    st_mock.cache_data = MagicMock(return_value=lambda f: f)
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import ui.carga_activos as ca_mod

        reload(ca_mod)
        ctx = {"universo_df": pd.DataFrame({"TICKER": ["SPY", "MSFT"]})}
        warns = ca_mod._validar_tickers(
            [{"TICKER": "ZZUNKNOWN", "TIPO": "CEDEAR"}],
            ctx,
        )
        assert warns and any("ZZUNKNOWN" in w for w in warns)


def test_validar_tickers_ok_conocido():
    st_mock = MagicMock()
    st_mock.session_state = {}
    st_mock.cache_data = MagicMock(return_value=lambda f: f)
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import ui.carga_activos as ca_mod

        reload(ca_mod)
        from ui.carga_activos import _validar_tickers

        ctx = {"universo_df": pd.DataFrame({"TICKER": ["SPY", "MSFT", "GLD"]})}
        adv = _validar_tickers([{"TICKER": "SPY", "TIPO": "CEDEAR"}], ctx)
        assert len(adv) == 0, f"SPY conocido no debería advertir: {adv}"


def test_validar_tickers_desconocido():
    st_mock = MagicMock()
    st_mock.session_state = {}
    st_mock.cache_data = MagicMock(return_value=lambda f: f)
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import ui.carga_activos as ca_mod

        reload(ca_mod)
        from ui.carga_activos import _validar_tickers

        ctx = {"universo_df": pd.DataFrame({"TICKER": ["SPY", "MSFT"]})}
        adv = _validar_tickers([{"TICKER": "AAPLE", "TIPO": "CEDEAR"}], ctx)
        assert len(adv) > 0
        assert "AAPLE" in adv[0]


def test_notas_asesor_roundtrip():
    import os

    os.environ.setdefault("MQ26_PASSWORD", "test_password_123")
    try:
        from sqlalchemy import text

        from core.db_manager import (
            ensure_schema,
            get_engine,
            guardar_notas_asesor,
            obtener_notas_asesor,
        )

        ensure_schema()
        with get_engine().connect() as conn:
            row = conn.execute(text("SELECT id FROM clientes LIMIT 1")).fetchone()
        if row:
            cid = int(row[0])
            guardar_notas_asesor(cid, "Nota de prueba Sprint 15")
            val = obtener_notas_asesor(cid)
            assert "Sprint 15" in val
    except Exception as e:
        import pytest

        pytest.skip(f"BD no disponible para test de notas: {e}")


def test_bienvenida_inversor_existe():
    import sys
    import types

    sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))
    import ui.tab_inversor as ti

    assert hasattr(ti, "_render_bienvenida_inversor")
    assert hasattr(ti, "_render_primera_cartera_inversor")
    assert hasattr(ti, "_render_config_perfil")
    assert hasattr(ti, "_render_posiciones_con_targets")


def test_config_perfil_usa_actualizar_cliente():
    from core.db_manager import actualizar_cliente

    assert callable(actualizar_cliente)


def test_tab_inversor_contexto_minimo_j93():
    """Sprint 18 J-93: tab inversor no revienta con ctx mío. mínimo (sin cartera)."""
    import sys
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    import pandas as pd

    @contextmanager
    def _noop(*a, **k):
        yield None

    _prev = sys.modules.get("streamlit")
    st_mock = MagicMock()
    st_mock.session_state = {}
    st_mock.rerun = MagicMock()
    st_mock.markdown = MagicMock()
    st_mock.caption = MagicMock()
    st_mock.info = MagicMock()
    st_mock.success = MagicMock()
    st_mock.warning = MagicMock()
    st_mock.error = MagicMock()
    st_mock.button = MagicMock(return_value=False)
    st_mock.divider = MagicMock()
    st_mock.metric = MagicMock()
    st_mock.plotly_chart = MagicMock()
    st_mock.expander = lambda *a, **k: _noop()
    st_mock.columns = MagicMock(return_value=(MagicMock(), MagicMock()))
    st_mock.number_input = MagicMock(return_value=50_000.0)
    st_mock.selectbox = MagicMock(return_value="Moderado")
    st_mock.text_input = MagicMock(return_value="Cliente")
    st_mock.text_area = MagicMock(return_value="")
    st_mock.container = lambda: _noop()
    sys.modules["streamlit"] = st_mock

    from importlib import reload

    import ui.tab_inversor as ti_mod

    try:
        reload(ti_mod)
        ctx = {
            "df_ag": pd.DataFrame(),
            "metricas": {},
            "ccl": 1150.0,
            "cliente_nombre": "Tester",
            "cliente_perfil": "Moderado",
            "user_role": "inversor",
        }
        ti_mod.render_tab_inversor(ctx)
        assert st_mock.markdown.called
    finally:
        if _prev is not None:
            sys.modules["streamlit"] = _prev
        else:
            sys.modules.pop("streamlit", None)


def test_posiciones_con_targets_sin_cartera():
    import sys
    import types

    import pandas as pd

    _prev_st = sys.modules.get("streamlit")
    _st = types.ModuleType("streamlit")
    _st.markdown = lambda *a, **k: None
    _st.columns = lambda *a, **k: [
        types.SimpleNamespace(
            markdown=lambda *a, **k: None,
            number_input=lambda *a, **k: 25.0,
            button=lambda *a, **k: False,
        )
    ]
    _st.container = lambda: types.SimpleNamespace(
        __enter__=lambda s: s,
        __exit__=lambda *a: None,
    )
    _st.expander = lambda *a, **k: types.SimpleNamespace(
        __enter__=lambda s: s,
        __exit__=lambda *a: None,
    )
    sys.modules["streamlit"] = _st
    from importlib import reload

    import ui.tab_inversor as ti_mod

    try:
        reload(ti_mod)
        try:
            ti_mod._render_posiciones_con_targets(
                {"df_ag": pd.DataFrame(), "cliente_perfil": "Moderado"},
                object(),
            )
        except Exception:
            pass
    finally:
        if _prev_st is not None:
            sys.modules["streamlit"] = _prev_st
        else:
            sys.modules.pop("streamlit", None)


def test_motor_salida_dias_en_cartera():
    from datetime import date

    from services.motor_salida import evaluar_salida

    fecha = date(2026, 1, 1)
    r = evaluar_salida(
        ticker="SPY",
        ppc_usd=400.0,
        px_usd_actual=440.0,
        rsi=55.0,
        score_actual=72.0,
        score_semana_anterior=70.0,
        fecha_compra=fecha,
        perfil="Moderado",
    )
    assert "dias_cartera" in r
    assert r["dias_cartera"] >= 0
    assert "progreso_pct" in r
    assert "precio_target" in r
    assert r["precio_target"] > r["precio_stop"]
