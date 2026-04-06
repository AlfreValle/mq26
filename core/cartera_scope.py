"""
Restricción del transaccional por rol: inversor solo ve su cliente;
asesor (super_admin / estudio) ve carteras cuyo prefijo coincide con clientes del tenant.
"""
from __future__ import annotations

import pandas as pd

from core.logging_config import get_logger

logger = get_logger(__name__)


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
    if r == "inversor":
        cn = (cliente_nombre or "").strip()
        if not cn:
            return trans.iloc[0:0].copy()
        pref = trans["CARTERA"].astype(str).str.split("|").str[0].str.strip()
        return trans.loc[pref == cn].copy()

    if r in ("super_admin", "estudio", "asesor"):
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
        pref = trans["CARTERA"].astype(str).str.split("|").str[0].str.strip()
        return trans.loc[pref.isin(nombres)].copy()

    # Rol desconocido: no exponer el universo completo.
    logger.warning("filtrar_transaccional_por_rol: rol no reconocido %r — bloqueando.", r)
    return trans.iloc[0:0].copy()
