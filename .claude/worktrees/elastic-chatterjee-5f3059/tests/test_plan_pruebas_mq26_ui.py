"""
Smoke automatizado alineado al plan «Probar las funcionalidades MQ26» (tabs por rol + motor salida).
No reemplaza la revisión visual en el navegador; valida import/ejecución con Streamlit mockeado.

Checklist manual sugerida (viewport): 1366px ancho notebook, 390px móvil — columnas Streamlit,
tablas con scroll horizontal, contraste tema claro retail (MQ26_RETAIL_LIGHT).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_st_global():
    mock_st = MagicMock()
    mock_st.session_state = {}

    def _mock_columns(*a, **k):
        if a and isinstance(a[0], int):
            n = int(a[0])
        elif a and isinstance(a[0], (list, tuple)):
            n = len(a[0])
        else:
            n = 5
        return tuple(MagicMock() for _ in range(n))

    mock_st.columns.side_effect = _mock_columns

    def _tabs(*a, **k):
        labels = a[0] if a else []
        n = len(labels) if hasattr(labels, "__len__") else 6
        return tuple(MagicMock() for _ in range(n))

    mock_st.tabs.side_effect = _tabs

    def _cache_data(*dargs, **dkwargs):
        def _decorator(fn):
            return fn

        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            return dargs[0]
        return _decorator

    mock_st.cache_data = _cache_data
    mock_st.checkbox.return_value = False
    original = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    yield mock_st
    if original is not None:
        sys.modules["streamlit"] = original


def test_render_tab_inversor_df_vacio_no_lanza(mock_st_global):
    """Recarga tab_inversor tras parchear streamlit para que use el mock."""
    import importlib

    mock_st_global.number_input.return_value = 500_000.0
    mock_st_global.button.return_value = False
    mock_st_global.session_state = {}

    import ui.tab_inversor as ti_mod

    importlib.reload(ti_mod)
    ctx = {
        "df_ag": pd.DataFrame(),
        "cliente_nombre": "Test",
        "metricas": {},
        "ccl": 1400.0,
        "render_carga_activos_fn": lambda _c: None,
    }
    ti_mod.render_tab_inversor(ctx)


def test_render_tab_estudio_sin_clientes_wizard_no_lanza(mock_st_global):
    import importlib

    import ui.tab_estudio as te_mod

    importlib.reload(te_mod)

    class _Db:
        def obtener_clientes_df(self, tenant_id=None):
            return pd.DataFrame()

    ctx = {"dbm": _Db(), "tenant_id": "default"}
    te_mod.render_tab_estudio(ctx)


def test_render_motor_salida_sin_posiciones_no_lanza(mock_st_global):
    mock_st_global.selectbox.return_value = "Moderado"
    from services.motor_salida import render_motor_salida

    render_motor_salida(
        df_posiciones=pd.DataFrame(),
        precios_actuales={},
        scores_actuales={},
        rsi_actuales={},
        perfil="Moderado",
        ccl=1400.0,
    )


def test_tab_admin_exporta_primera_cartera_y_es_callable(mock_st_global):
    import importlib

    import ui.tab_admin as tab_admin_mod

    importlib.reload(tab_admin_mod)
    assert hasattr(tab_admin_mod, "_render_primera_cartera_admin")
    assert callable(tab_admin_mod.render_tab_admin)


def test_funciones_publicas_tabs_asesor_callables():
    from ui.tab_cartera import render_tab_cartera
    from ui.tab_ejecucion import render_tab_ejecucion
    from ui.tab_optimizacion import render_tab_optimizacion
    from ui.tab_reporte import render_tab_reporte
    from ui.tab_riesgo import render_tab_riesgo
    from ui.tab_universo import render_tab_universo

    for fn in (
        render_tab_cartera,
        render_tab_universo,
        render_tab_optimizacion,
        render_tab_riesgo,
        render_tab_ejecucion,
        render_tab_reporte,
    ):
        assert callable(fn)
