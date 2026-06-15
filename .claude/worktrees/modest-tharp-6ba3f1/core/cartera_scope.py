"""
Restricción del transaccional por rol: inversor ve solo el cliente activo en sesión
(puede tener varios vinculados y cambiar en ingreso / sidebar);
admin/estudio (super_admin / estudio) ve carteras cuyo prefijo coincide con clientes del tenant.
"""
from __future__ import annotations

import pandas as pd

from core.logging_config import get_logger

logger = get_logger(__name__)

# Clave canónica de cartera al normalizar filas del CSV para el cliente activo inversor.
SUFIJO_CARTERA_INVERSOR_CANONICA = "Cartera principal"


def cartera_canonica_inversor(cliente_nombre: str) -> str:
    cn = (cliente_nombre or "").strip()
    return f"{cn} | {SUFIJO_CARTERA_INVERSOR_CANONICA}"


def normalizar_transacciones_inversor_una_cartera(
    trans: pd.DataFrame,
    cliente_nombre: str,
) -> tuple[pd.DataFrame, str]:
    """
    Inversor: un solo cliente y una sola clave CARTERA en memoria, aunque el CSV
    historial tenga varios sufijos ('| Libro 2', etc.). Así se agrega sin elegir cartera.
    """
    canon = cartera_canonica_inversor(cliente_nombre)
    if trans is None or trans.empty:
        return pd.DataFrame(), canon
    if "CARTERA" not in trans.columns:
        return trans.copy(), canon
    cn = (cliente_nombre or "").strip()
    if not cn:
        return trans.iloc[0:0].copy(), canon
    c_full = trans["CARTERA"].astype(str).str.strip()
    pref = c_full.str.split("|").str[0].str.strip()
    cn_pref = cn.split("|")[0].strip()
    # Nombre en sesión puede ser el de BD completo ("Pablo | Primera cartera") o solo el titular.
    sub = trans.loc[(c_full == cn) | (pref == cn_pref)].copy()
    if sub.empty:
        return sub, canon
    sub["CARTERA"] = canon
    return sub, canon


def filtrar_transaccional_por_rol(
    trans: pd.DataFrame,
    role: str,
    cliente_nombre: str,
    df_clientes: pd.DataFrame | None,
) -> pd.DataFrame:
    if trans is None or trans.empty:
        return trans.copy() if trans is not None else pd.DataFrame()
    if "CARTERA" not in trans.columns:
        return trans.copy()

    r = str(role or "").lower()
    c_full = trans["CARTERA"].astype(str).str.strip()
    pref = c_full.str.split("|").str[0].str.strip()

    if r == "inversor":
        cn = (cliente_nombre or "").strip()
        if not cn:
            return trans.iloc[0:0].copy()
        cn_pref = cn.split("|")[0].strip()
        return trans.loc[(c_full == cn) | (pref == cn_pref)].copy()

    if r in ("super_admin", "estudio"):
        # Fail-closed: sin lista de clientes válida, no mostrar ninguna fila (evita IDOR).
        if df_clientes is None or df_clientes.empty or "Nombre" not in df_clientes.columns:
            logger.error(
                "ALERTA SEGURIDAD: df_clientes vacío o mal formado en filtro por rol. "
                "Bloqueando acceso a datos transaccionales."
            )
            return trans.iloc[0:0].copy()
        nombres = set(df_clientes["Nombre"].dropna().astype(str).str.strip())
        if not nombres:
            return trans.iloc[0:0].copy()
        # BD puede guardar nombre corto o completo con "| libro"; el CSV suele compartir el mismo prefijo.
        nome_prefs = {n.split("|")[0].strip() for n in nombres if n}
        return trans.loc[c_full.isin(nombres) | pref.isin(nombres) | pref.isin(nome_prefs)].copy()

    # Rol desconocido: no exponer el universo completo.
    logger.warning("filtrar_transaccional_por_rol: rol no reconocido %r — bloqueando.", r)
    return trans.iloc[0:0].copy()
