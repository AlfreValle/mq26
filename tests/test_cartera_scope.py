"""Filtrado del transaccional por rol."""
import pandas as pd

from core.cartera_scope import filtrar_transaccional_por_rol


def test_inversor_filtra_por_prefijo_cartera():
    df = pd.DataFrame({
        "CARTERA": [
            "Carlos Rodríguez | Crecimiento",
            "María Fernández | Ahorro",
        ],
        "TICKER": ["SPY", "KO"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez", "María Fernández"]})
    out = filtrar_transaccional_por_rol(df, "inversor", "Carlos Rodríguez", df_cli)
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"


def test_asesor_mismo_alcance_que_estudio_sobre_transaccional():
    df = pd.DataFrame({
        "CARTERA": [
            "Carlos Rodríguez | Crecimiento",
            "Extraño | X",
        ],
        "TICKER": ["SPY", "ZZZ"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez"]})
    out = filtrar_transaccional_por_rol(df, "asesor", "", df_cli)
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"


def test_super_admin_restringe_a_clientes_bd():
    df = pd.DataFrame({
        "CARTERA": [
            "Carlos Rodríguez | Crecimiento",
            "Extraño | X",
        ],
        "TICKER": ["SPY", "ZZZ"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez"]})
    out = filtrar_transaccional_por_rol(df, "super_admin", "", df_cli)
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"
