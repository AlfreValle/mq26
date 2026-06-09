"""
Alcance de clientes en la UI (Streamlit) según sesión y rol.

Compartido por run_mq26 (app_id=mq26) y app_main (app_id=app). Las claves de
session_state dependen del app_id pasado a check_password (p. ej. app_allowed_cliente_ids).
"""
from __future__ import annotations

import os

import pandas as pd


def scope_clientes_df_por_sesion(df: pd.DataFrame, *, app_id: str) -> pd.DataFrame:
    """
    Filtra por ``{app_id}_allowed_cliente_ids`` si el login vino de BD (None = sin filtro por ID).

    Rol **inversor**: como mucho **un** cliente en listas (ingreso, sidebar, selectores).
    - Varios IDs en BD: prioriza ``{app_id}_cliente_default_id``.
    - Login solo por .env: opcional ``MQ26_INVESTOR_CLIENTE_IDS`` (IDs numéricos).
    - Heurística: nombre de cliente cuyo prefijo coincide con el usuario de login.
    - Último recurso: menor ID (no exponer todo el tenant).
    """
    import streamlit as st

    from core.auth import get_user_role

    aid = (app_id or "mq26").strip() or "mq26"
    allowed = st.session_state.get(f"{aid}_allowed_cliente_ids")
    if allowed is None:
        out = df
    elif not allowed:
        out = df.iloc[0:0].copy()
    else:
        out = df[df["ID"].isin(allowed)].copy()

    if get_user_role(aid) != "inversor":
        return out

    if out.empty or len(out) <= 1:
        return out

    default_id = st.session_state.get(f"{aid}_cliente_default_id")
    if default_id is not None:
        one = out[out["ID"] == int(default_id)]
        if not one.empty:
            return one

    env_raw = (os.environ.get("MQ26_INVESTOR_CLIENTE_IDS") or "").strip()
    if env_raw:
        want: list[int] = []
        for part in env_raw.split(","):
            p = part.strip()
            if p.isdigit():
                want.append(int(p))
        if want:
            filt = out[out["ID"].isin(want)]
            if not filt.empty:
                return filt.iloc[0:1]

    lu = (st.session_state.get(f"{aid}_login_user") or "").strip().lower()
    if lu:
        def _match_nombre(n: str) -> bool:
            s = (n or "").strip().lower()
            pref = s.split("|")[0].strip()
            return lu == pref or lu in s

        try:
            m = out[out["Nombre"].astype(str).apply(_match_nombre)]
            if len(m) == 1:
                return m
        except Exception:
            pass

    return out.sort_values("ID").iloc[0:1]
