"""
P2-RF-01: ficha RF mínima unificada — solo consume el bundle de `ficha_rf_minima_bundle`.

El bloque de cashflow ilustrativo usa `get_meta(ticker)` del catálogo cuando el bundle
indica `cashflow_ilustrativo_disponible` (no se pasa un segundo dict de dominio al caller).
"""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st

from core.renta_fija_ar import (
    DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF,
    cashflow_ilustrativo_por_100_vn,
    get_meta,
)

_GUION = "—"


def _fmt_pct(x: Any) -> str:
    if x is None:
        return _GUION
    try:
        return f"{float(x):.2f}%"
    except (TypeError, ValueError):
        return _GUION


def _fmt_num(x: Any) -> str:
    if x is None:
        return _GUION
    try:
        v = float(x)
        return f"{v:,.2f}"
    except (TypeError, ValueError):
        return _GUION


def _motivo_tir_ap_txt(codigo: str | None) -> str | None:
    if not codigo:
        return None
    if codigo == "sin_tir_ref":
        return "Sin TIR de referencia en catálogo."
    if codigo == "sin_paridad_mercado":
        return "Sin paridad de mercado para estimar TIR al precio."
    return codigo


def render_ficha_rf_minima(
    bundle: Mapping[str, Any],
    *,
    mostrar_cashflow_expander: bool = True,
    key_prefix: str = "ficha_rf",
    titulo: str | None = None,
) -> None:
    """
    Renderiza la ficha a partir del dict devuelto por `ficha_rf_minima_bundle`.

    Parameters
    ----------
    bundle
        Resultado de `ficha_rf_minima_bundle` (o dict compatible).
    mostrar_cashflow_expander
        Si True y el bundle lo permite, muestra cashflow ilustrativo vía catálogo interno.
    key_prefix
        Prefijo para keys de widgets Streamlit (evitar colisiones entre instancias).
    titulo
        Título opcional (por defecto incluye el ticker).
    """
    if not bundle.get("ok"):
        st.warning(
            f"**{bundle.get('ticker', '?')}** — sin ficha en catálogo "
            f"({bundle.get('motivo', 'desconocido')})."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("ISIN")
            st.markdown(bundle.get("isin") or _GUION)
        with c2:
            st.caption("Denominación mín.")
            st.markdown(bundle.get("denominacion_min") or _GUION)
        with c3:
            st.caption("Forma amortización")
            st.markdown(bundle.get("forma_amortizacion") or _GUION)
        return

    tk = str(bundle.get("ticker") or "")
    head = titulo if titulo else f"Ficha RF — **{tk}**"
    st.markdown(head)

    if bundle.get("escala_div100_aplicada") or bundle.get("nota_escala"):
        _ns = bundle.get("nota_escala")
        if _ns:
            st.caption(f"**Escala / normalización:** {_ns}")
        elif bundle.get("escala_div100_aplicada"):
            st.caption("**Escala:** se aplicó ajuste ÷100 respecto de la fuente (ver columna/banner en tabla).")

    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        st.caption("Emisor")
        st.markdown(str(bundle.get("emisor") or _GUION))
    with r1c2:
        st.caption("Descripción")
        st.markdown(str(bundle.get("descripcion") or _GUION))
    with r1c3:
        st.caption("Tipo / moneda")
        st.markdown(f"{bundle.get('tipo') or _GUION} · {bundle.get('moneda_emision') or _GUION}")

    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        st.caption("ISIN")
        st.markdown(str(bundle.get("isin") or _GUION))
    with r2c2:
        st.caption("Denominación mín.")
        st.markdown(str(bundle.get("denominacion_min") or _GUION))
    with r2c3:
        st.caption("Forma amortización")
        st.markdown(str(bundle.get("forma_amortizacion") or _GUION))

    r3c1, r3c2, r3c3 = st.columns(3)
    with r3c1:
        st.caption("Vencimiento")
        st.markdown(str(bundle.get("vencimiento") or _GUION))
    with r3c2:
        st.caption("Cupón % nominal")
        st.markdown(_fmt_pct(bundle.get("cupon_pct_nominal")))
    with r3c3:
        st.caption("Frecuencia de pagos")
        st.markdown(str(bundle.get("frecuencia_pagos") or _GUION))

    r4c1, r4c2, r4c3 = st.columns(3)
    with r4c1:
        st.caption("TIR ref. %")
        st.markdown(_fmt_pct(bundle.get("tir_ref_pct")))
    with r4c2:
        st.caption("Paridad ref. %")
        st.markdown(_fmt_pct(bundle.get("paridad_ref_pct")))
    with r4c3:
        st.caption("TIR al precio % (estim.)")
        tap = bundle.get("tir_a_precio_pct")
        if tap is not None:
            st.markdown(_fmt_pct(tap))
        else:
            _m = _motivo_tir_ap_txt(bundle.get("tir_a_precio_motivo"))
            st.markdown(_m or _GUION)

    r5c1, r5c2 = st.columns(2)
    with r5c1:
        st.caption("Último / precio mercado (ARS)")
        st.markdown(_fmt_num(bundle.get("precio_mercado_ars")))
    with r5c2:
        st.caption("Fuente precio")
        st.markdown(str(bundle.get("fuente_precio") or _GUION))

    st.caption(f"**Unidad precio:** {bundle.get('unidad_precio') or _GUION}")

    if not mostrar_cashflow_expander or not bundle.get("cashflow_ilustrativo_disponible"):
        return

    meta = get_meta(tk)
    if not meta:
        return

    with st.expander(
        "Cashflow ilustrativo (base 100 VN — P2-RF-02)",
        expanded=False,
        key=f"{key_prefix}_cashflow",
    ):
        st.caption(DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF)
        _cf = cashflow_ilustrativo_por_100_vn(meta, solo_futuros=True)
        if _cf.get("aviso"):
            st.caption(str(_cf["aviso"]))
        if _cf.get("ok") and _cf.get("filas"):
            st.caption(
                f"Moneda emisión: **{_cf.get('moneda_emision', '—')}** · "
                "Montos por **100 VN** (ilustrativo)."
            )
            st.dataframe(
                pd.DataFrame(_cf["filas"]),
                use_container_width=True,
                hide_index=True,
            )
        elif _cf.get("ok") and not _cf.get("filas"):
            st.info("Sin filas ilustrativas para el rango (p. ej. vencimiento ya pasó).")
