"""
Tests del wizard de capital del cliente en Estudio (ui/tab_estudio.py, pasos 3-5).

Foco en lo NUEVO y riesgoso del flujo de estudio: la aislación de datos entre
clientes (`_ctx_scoped_cliente` debe resolver la cartera del cliente correcto y
nunca cruzar libros) y que el render de los pasos 3-4-5 no explote en sus
caminos (cliente con y sin posiciones). El motor de recomendación/persistencia
ya está cubierto por test_flujo_roles_integracion y los tests de primera cartera.

Streamlit mockeado: valida ejecución, no la vista en navegador.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture()
def mock_st():
    mock = MagicMock()
    mock.session_state = {}

    def _columns(*a, **k):
        if a and isinstance(a[0], int):
            n = a[0]
        elif a and isinstance(a[0], (list, tuple)):
            n = len(a[0])
        else:
            n = 2
        return tuple(MagicMock() for _ in range(n))

    mock.columns.side_effect = _columns
    mock.button.return_value = False
    mock.checkbox.return_value = False
    mock.number_input.return_value = 500_000.0
    mock.selectbox.return_value = "⚖️ Equilibrio"
    original = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock
    yield mock
    if original is not None:
        sys.modules["streamlit"] = original


@pytest.fixture()
def te(mock_st):
    """tab_estudio recargado bajo el mock de streamlit."""
    import ui.tab_estudio as te_mod

    importlib.reload(te_mod)
    return te_mod


# ─── Aislación de datos: la pieza nueva y crítica ────────────────────────────

def _df_trans_dos_clientes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CARTERA": [
                "Ana Gómez | Cartera principal",
                "Ana Gómez | Cartera principal",
                "Beto Ruiz | Cartera principal",
            ],
            "TICKER": ["AAPL", "KO", "NVDA"],
            "CANTIDAD": [3, 5, 2],
        }
    )


def test_ctx_scoped_resuelve_cartera_del_cliente_correcto(te):
    """Scopear a Ana resuelve la cartera de Ana; a Beto, la de Beto. Sin cruce."""
    ctx = {"df_trans": _df_trans_dos_clientes(), "ccl": 1500.0}

    sc_ana = te._ctx_scoped_cliente(1, "Ana Gómez | Moderado", ctx)
    sc_beto = te._ctx_scoped_cliente(2, "Beto Ruiz | Arriesgado", ctx)

    assert sc_ana["cartera_activa"] == "Ana Gómez | Cartera principal"
    assert sc_beto["cartera_activa"] == "Beto Ruiz | Cartera principal"
    # cliente_id y nombre quedan apuntados al cliente correcto
    assert sc_ana["cliente_id"] == 1 and sc_beto["cliente_id"] == 2
    # No comparten el dict mutado (copia superficial)
    assert sc_ana["cartera_activa"] != sc_beto["cartera_activa"]


def test_ctx_scoped_fallback_cartera_principal_si_sin_datos(te):
    """Cliente sin cartera en el transaccional → 'Nombre | Cartera principal'."""
    ctx = {"df_trans": _df_trans_dos_clientes(), "ccl": 1500.0}
    sc = te._ctx_scoped_cliente(9, "Nuevo Cliente | Conservador", ctx)
    assert sc["cartera_activa"] == "Nuevo Cliente | Cartera principal"


def test_ctx_scoped_sin_trans_usa_fallback(te):
    """Sin df_trans (None) el scoping no explota y cae al fallback."""
    sc = te._ctx_scoped_cliente(3, "Carla | Moderado", {"ccl": 1500.0})
    assert sc["cartera_activa"] == "Carla | Cartera principal"


# ─── Smoke de render de los pasos 3-4-5 ──────────────────────────────────────

def test_wizard_render_sin_permiso_escritura_no_recomienda(te, mock_st):
    """Sin permiso de escritura, el wizard no ofrece el flujo (RBAC)."""
    ctx = {"user_role": "inversor", "ccl": 1500.0, "df_trans": pd.DataFrame()}
    te._render_wizard_capital_estudio(1, "Ana | Moderado", ctx)
    # No llegó a pedir capital: el number_input no se invocó.
    assert mock_st.number_input.call_count == 0


def test_wizard_render_paso3_sin_posiciones_no_lanza(te, mock_st):
    """Paso 3 (capital+objetivo) renderiza sin resultado previo y no explota."""
    ctx = {
        "user_role": "estudio",
        "ccl": 1500.0,
        "df_trans": pd.DataFrame(),
        "cliente_id": 1,
    }
    te._render_wizard_capital_estudio(1, "Ana | Moderado", ctx)
    # Pidió capital (paso 3) y, sin botón apretado ni resultado, no siguió.
    assert mock_st.number_input.called


def test_wizard_render_paso4y5_con_resultado_no_lanza(te, mock_st):
    """Con un resultado en sesión, los pasos 4-5 (tabla editable + adjuntar) renderizan."""
    cid = 7

    class _Item:
        ticker = "AAPL"
        unidades = 3
        precio_ars_estimado = 1000.0
        justificacion = "Núcleo CEDEAR"
        monto_ars = 3000.0

    class _RR:
        compras_recomendadas = [_Item()]
        capital_remanente_ars = 500.0
        alerta_mercado = False
        mensaje_alerta = ""

    # data_editor devuelve un DataFrame real para que el cálculo de totales corra.
    mock_st.data_editor.return_value = pd.DataFrame(
        [{"Ticker": "AAPL", "Unidades": 3, "Precio_ARS": 1000.0, "TIPO": "CEDEAR", "Notas": ""}]
    )
    mock_st.session_state = {
        f"est_wiz_rr_{cid}": {"rr": _RR(), "capital": 500_000.0, "perfil": "Moderado"}
    }

    ctx = {
        "user_role": "estudio",
        "ccl": 1500.0,
        "df_trans": pd.DataFrame(),
        "cliente_id": cid,
        "tenant_id": "default",
    }
    # No debe lanzar: render de paso 4 (tabla) + paso 5 (adjuntar, botón sin apretar).
    te._render_wizard_capital_estudio(cid, "Diana | Moderado", ctx)
    assert mock_st.data_editor.called
