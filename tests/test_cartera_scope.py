"""Filtrado del transaccional por rol."""
import pandas as pd

from core.cartera_scope import (
    filtrar_transaccional_por_rol,
    normalizar_transacciones_inversor_una_cartera,
)


def test_inversor_unifica_varias_carteras_a_una_sola_clave():
    df = pd.DataFrame({
        "CARTERA": [
            "Ana | Libro A",
            "Ana | Libro B",
        ],
        "TICKER": ["SPY", "KO"],
        "CANTIDAD": [1.0, 2.0],
    })
    out, canon = normalizar_transacciones_inversor_una_cartera(df, "Ana")
    assert canon == "Ana | Cartera principal"
    assert len(out) == 2
    assert out["CARTERA"].unique().tolist() == [canon]


def test_inversor_normaliza_cuando_sesion_tiene_nombre_completo_demo():
    df = pd.DataFrame({
        "CARTERA": ["Pablo Romero | Primera Cartera", "Otro | X"],
        "TICKER": ["SPY", "META"],
    })
    out, canon = normalizar_transacciones_inversor_una_cartera(df, "Pablo Romero | Primera Cartera")
    assert canon == "Pablo Romero | Primera Cartera | Cartera principal"
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"
    assert (out["CARTERA"] == canon).all()


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


def test_inversor_nombre_bd_completo_con_pipe_coincide_csv():
    """Sesión con Nombre completo de BD (demo) debe ver filas del CSV con la misma CARTERA."""
    df = pd.DataFrame({
        "CARTERA": ["Carlos Rodríguez | Crecimiento", "María Fernández | Ahorro Familiar"],
        "TICKER": ["SPY", "KO"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez | Crecimiento"]})
    out = filtrar_transaccional_por_rol(df, "inversor", "Carlos Rodríguez | Crecimiento", df_cli)
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"


def test_estudio_nombre_bd_completo_con_pipe():
    df = pd.DataFrame({
        "CARTERA": ["Carlos Rodríguez | Crecimiento", "Otro | X"],
        "TICKER": ["SPY", "ZZZ"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez | Crecimiento"]})
    out = filtrar_transaccional_por_rol(df, "estudio", "", df_cli)
    assert len(out) == 1
    assert out.iloc[0]["TICKER"] == "SPY"


def test_estudio_mismo_alcance_que_super_admin_sobre_transaccional():
    df = pd.DataFrame({
        "CARTERA": [
            "Carlos Rodríguez | Crecimiento",
            "Extraño | X",
        ],
        "TICKER": ["SPY", "ZZZ"],
    })
    df_cli = pd.DataFrame({"Nombre": ["Carlos Rodríguez"]})
    out = filtrar_transaccional_por_rol(df, "estudio", "", df_cli)
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


def test_estudio_df_clientes_vacio_no_expone_transaccional():
    """Fail-closed: sin df_clientes válido no se devuelve el transaccional completo (IDOR)."""
    df = pd.DataFrame({"CARTERA": ["Otro | X"], "TICKER": ["SPY"]})
    out = filtrar_transaccional_por_rol(df, "estudio", "", None)
    assert len(out) == 0

    out2 = filtrar_transaccional_por_rol(df, "estudio", "", pd.DataFrame())
    assert len(out2) == 0
