"""
ui/carga_activos.py — Carga de activos para el inversor (Streamlit).

Una función principal `render_carga_activos(ctx)` con flujos por tipo de instrumento.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from broker_importer import importar_archivo_broker
from services.copy_inversor import broker_tarjeta_sub, historial_meses_copy
from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    descripcion_legible,
    get_meta,
    tickers_por_tipo,
    tickers_rf_activos,
    tir_al_precio,
    valor_nominal_a_ars,
)


def _ticker_col_univ(df: pd.DataFrame | None) -> str | None:
    if df is None or df.empty:
        return None
    if "Ticker" in df.columns:
        return "Ticker"
    if "TICKER" in df.columns:
        return "TICKER"
    return None


def _universo_opciones_labels(ctx: dict) -> tuple[list[str], dict[str, str]]:
    """Devuelve labels para selectbox y mapa label -> ticker."""
    u = ctx.get("universo_df")
    col = _ticker_col_univ(u)
    if col is None:
        return [], {}
    labels: list[str] = []
    m: dict[str, str] = {}
    for _, r in u.iterrows():
        t = str(r[col]).strip().upper()
        if not t or t == "NAN":
            continue
        nom = ""
        for nc in ("Nombre", "NOMBRE", "nombre", "Denominacion"):
            if nc in u.columns and pd.notna(r.get(nc)):
                nom = str(r[nc]).strip()[:72]
                break
        sec = ""
        if "Sector" in u.columns and pd.notna(r.get("Sector")):
            sec = str(r["Sector"]).strip()[:40]
        lbl = f"{t} — {nom}" + (f" ({sec})" if sec else "")
        labels.append(lbl)
        m[lbl] = t
    pairs = sorted(zip(m.keys(), m.values()), key=lambda x: x[1])
    labels_ord = [p[0] for p in pairs]
    m2 = {p[0]: p[1] for p in pairs}
    return labels_ord, m2


def _filtrar_univ_por_busqueda(ctx: dict, q: str) -> tuple[list[str], dict[str, str]]:
    labels, m = _universo_opciones_labels(ctx)
    if not q.strip():
        return labels[:400], m
    qu = q.strip().lower()
    sub = [lbl for lbl in labels if qu in lbl.lower()]
    return sub[:200], m


def _cartera_csv(ctx: dict) -> str:
    return str(ctx.get("cartera_activa") or "Principal").strip()


def _capturar_snapshot_pre_carga(ctx: dict) -> None:
    """Guarda % defensivo actual para mostrar antes/después tras el guardado (UX inversor)."""
    df_ag = ctx.get("df_ag")
    if df_ag is None or df_ag.empty:
        st.session_state.pop("inv_ux_before_load", None)
        return
    try:
        from services.diagnostico_cartera import diagnosticar

        metricas = ctx.get("metricas") or {}
        d0 = diagnosticar(
            df_ag=df_ag,
            perfil=str(ctx.get("cliente_perfil", "Moderado")),
            horizonte_label=str(ctx.get("horizonte_label", "1 año")),
            metricas=metricas,
            ccl=float(ctx.get("ccl") or 0.0),
            universo_df=ctx.get("universo_df"),
            senales_salida=None,
            cliente_nombre=str(ctx.get("cliente_nombre", "")),
        )
        st.session_state["inv_ux_before_load"] = {
            "pct": float(getattr(d0, "pct_defensivo_actual", 0.0) or 0.0) * 100.0,
            "sem": getattr(getattr(d0, "semaforo", None), "value", "") or "",
        }
    except Exception:
        st.session_state.pop("inv_ux_before_load", None)


def _persist_filas(ctx: dict, filas: list[dict[str, Any]], modo: str) -> None:
    ed = ctx.get("engine_data")
    if ed is None:
        st.error("Motor de datos no disponible.")
        return
    try:
        df_prev = ed.cargar_transaccional().copy()
    except Exception as e:
        st.error(f"No se pudo leer el transaccional: {e}")
        return
    cart = _cartera_csv(ctx)
    for f in filas:
        f.setdefault("CARTERA", cart)
    cols = list(df_prev.columns) if not df_prev.empty else [
        "CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD", "PPC_USD", "PPC_ARS", "TIPO", "LAMINA_VN",
    ]
    for f in filas:
        for k in f:
            if k not in cols:
                cols.append(k)
    df_prev = df_prev.reindex(columns=cols)
    add = pd.DataFrame(filas)
    add = add.reindex(columns=cols)
    if modo == "sobrescribir" and not df_prev.empty and "CARTERA" in df_prev.columns:
        df_prev = df_prev[df_prev["CARTERA"] != cart].copy()
    out = pd.concat([df_prev, add], ignore_index=True)
    try:
        _capturar_snapshot_pre_carga(ctx)
        ed.guardar_transaccional(out)
        st.success(f"Listo: guardamos **{len(filas)}** compra(s). Tu cartera se actualizó.")
        st.session_state["inv_ultima_carga"] = filas[-1] if filas else {}
        st.session_state.pop("inv_diagnostico", None)
        st.session_state.pop("diagnostico_cache", None)
        st.rerun()
    except Exception as e:
        st.error(f"No se pudo guardar: {e}")


def _render_confirmacion_carga(ticker: str, monto_ars: float, ctx: dict) -> None:
    st.markdown(f"**{ticker}** agregado — impacto estimado **ARS {monto_ars:,.0f}**.")
    try:
        from services.diagnostico_cartera import diagnosticar

        df_ag = ctx.get("df_ag")
        if df_ag is None or df_ag.empty:
            return
        perfil = str(ctx.get("cliente_perfil", "Moderado"))
        horiz = str(ctx.get("horizonte_label", "1 año"))
        metricas = ctx.get("metricas") or {}
        ccl = float(ctx.get("ccl") or 0.0)
        d = diagnosticar(
            df_ag=df_ag,
            perfil=perfil,
            horizonte_label=horiz,
            metricas=metricas,
            ccl=ccl,
            universo_df=ctx.get("universo_df"),
            senales_salida=None,
            cliente_nombre=str(ctx.get("cliente_nombre", "")),
        )
        pct_d = float(getattr(d, "pct_defensivo_actual", 0.0) or 0.0) * 100.0
        pct_v = max(0.0, 100.0 - pct_d)
        st.caption(str(getattr(d, "titulo_semaforo", "") or ""))
        st.progress(min(1.0, pct_d / 100.0))
        st.caption(f"Defensivo ~{pct_d:.0f}% · Variable ~{pct_v:.0f}%")
    except Exception:
        pass


def _render_carga_cedear(ctx: dict) -> None:
    st.markdown("##### CEDEAR, acción USA o ETF")
    q = st.text_input(
        "¿Qué compraste? (buscá por nombre o ticker)",
        "",
        key="ca_cedear_q",
        help="Ej.: nvidia, nvda, coca",
    )
    labels, label_map = _filtrar_univ_por_busqueda(ctx, q)
    if not labels:
        st.warning("No hay universo cargado o no hay coincidencias.")
        return
    sel = st.selectbox("Elegí el activo", labels, key="ca_cedear_sel")
    ticker = label_map.get(sel, str(sel).split("—")[0].strip())
    ccl = float(ctx.get("ccl") or 1.0)
    precios = ctx.get("precios_dict") or {}
    precio_ref = float(precios.get(ticker, 0.0) or 0.0)
    c1, c2, c3 = st.columns(3)
    with c1:
        cant = st.number_input("¿Cuántas unidades?", min_value=0.0, value=0.0, step=1.0, key="ca_cedear_cant")
    with c2:
        px = st.number_input(
            "¿A cuánto pagaste el activo (USD)?",
            min_value=0.0,
            value=0.0,
            step=0.01,
            key="ca_cedear_px",
            help="Precio en dólares por papel, como figura en el boleto. "
            "Lo pasamos a pesos con el CCL de hoy para estimar; al guardar usás el precio que cargaste.",
        )
    with c3:
        fc = st.date_input("¿Cuándo?", value=date.today(), key="ca_cedear_fecha")
    ppc_usd = px
    ppc_ars = px * ccl
    if px > 0 and precio_ref > 0 and px > precio_ref * 3:
        st.warning(f"¿Seguro? **{ticker}** cotiza cerca de USD {precio_ref:,.2f} según la última lectura.")
    monto_ars = cant * ppc_ars
    st.info(f"Vista previa: **USD {cant * px:,.2f}** → **ARS {monto_ars:,.0f}** (CCL {ccl:,.0f}).")
    tipo_u = "ETF"
    udf = ctx.get("universo_df")
    ct = _ticker_col_univ(udf)
    if udf is not None and ct is not None:
        row = udf[udf[ct].astype(str).str.upper() == ticker.upper()]
        if not row.empty:
            tipo_cell = row.iloc[0].get("TIPO", row.iloc[0].get("Tipo", ""))
            tipo_u = str(tipo_cell).strip().upper() or "CEDEAR"
    if tipo_u not in ("ETF", "CEDEAR", "ACCION_LOCAL"):
        tipo_u = "CEDEAR"
    disuf = st.button(
        "Guardar",
        disabled=cant < 1 or px <= 0,
        key="ca_cedear_save",
        use_container_width=True,
    )
    if disuf:
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker,
            "CANTIDAD": int(cant),
            "PPC_USD": round(ppc_usd, 6),
            "PPC_ARS": round(ppc_ars, 4),
            "TIPO": tipo_u,
            "LAMINA_VN": float("nan"),
        }], modo=st.session_state.get("ca_merge_mode", "agregar"))


def _render_carga_accion_local(ctx: dict) -> None:
    st.markdown("##### Acción argentina (precio en pesos)")
    ticker = st.text_input("Ticker en BYMA (ej. GGAL)", "", key="ca_loc_tick").strip().upper()
    ccl = float(ctx.get("ccl") or 1.0)
    c1, c2, c3 = st.columns(3)
    with c1:
        cant = st.number_input("Unidades", min_value=0.0, value=0.0, step=1.0, key="ca_loc_cant")
    with c2:
        px_ars = st.number_input("Precio unitario (ARS)", min_value=0.0, value=0.0, step=0.5, key="ca_loc_px")
    with c3:
        fc = st.date_input("Fecha compra", value=date.today(), key="ca_loc_fecha")
    ppc_usd = round(px_ars / ccl, 8) if ccl else 0.0
    st.caption(f"Equivale a ~USD {ppc_usd:,.4f} por unidad al CCL actual (referencia).")
    if st.button(
        "Guardar",
        disabled=cant < 1 or px_ars <= 0 or not ticker,
        key="ca_loc_save",
        use_container_width=True,
    ):
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker,
            "CANTIDAD": int(cant),
            "PPC_USD": ppc_usd,
            "PPC_ARS": round(px_ars, 4),
            "TIPO": "ACCION_LOCAL",
            "LAMINA_VN": float("nan"),
        }], modo=st.session_state.get("ca_merge_mode", "agregar"))


def _labels_rf_busqueda(q: str, tickers: list[str]) -> list[str]:
    if not q.strip():
        return [f"{t} — {descripcion_legible(t)}" for t in tickers]
    qu = q.lower()
    out = []
    for t in tickers:
        lab = f"{t} — {descripcion_legible(t)}"
        if qu in lab.lower():
            out.append(lab)
    return out


def _render_carga_on(ctx: dict) -> None:
    st.markdown("##### Obligación negociable o bono (como en el comprobante)")
    q = st.text_input("Buscá por emisor o ticker", "", key="ca_on_q")
    pool = tickers_rf_activos()
    pool_on = [t for t in pool if str(INSTRUMENTOS_RF[t].get("tipo", "")).upper() in ("ON_USD", "BONO_USD")]
    labels = _labels_rf_busqueda(q, pool_on)
    if not labels:
        st.warning("Sin coincidencias en el catálogo.")
    sel = st.selectbox("Instrumento", labels, key="ca_on_sel") if labels else ""
    ticker = sel.split("—")[0].strip().upper() if sel else ""
    manual = st.text_input("O escribí el ticker manualmente", ticker, key="ca_on_manual").strip().upper()
    if manual:
        ticker = manual
    meta = get_meta(ticker)
    ccl = float(ctx.get("ccl") or 1.0)
    c1, c2, c3 = st.columns(3)
    with c1:
        vn = st.number_input("Valor nominal (USD)", min_value=0.0, value=0.0, step=100.0, key="ca_on_vn")
    with c2:
        par_def = float(meta["paridad_ref"]) if meta else 100.0
        par = st.number_input("Paridad % (precio limpio)", min_value=0.01, value=par_def, step=0.5, key="ca_on_par")
    with c3:
        fc = st.date_input("Fecha", value=date.today(), key="ca_on_fecha")
    if par > 115:
        st.warning("¿Seguro? Las ONs rara vez cotizan por encima de 115%.")
    if par < 80:
        st.warning("¿Seguro? Precio muy bajo — revisá el comprobante.")
    monto_usd = vn * (par / 100.0)
    monto_ars = valor_nominal_a_ars(vn, par, ccl)
    tir_ef = tir_al_precio(ticker, par)
    if meta:
        vto = str(meta.get("vencimiento", ""))
        st.info(
            f"Pagás **USD {monto_usd:,.2f}** → **ARS {monto_ars:,.0f}**. "
            f"TIR estimada al precio: **{tir_ef}%**. Vence **{vto}**. "
            f"Calif.: **{meta.get('calificacion', '—')}**."
        )
    if st.button("Guardar", disabled=vn <= 0 or par <= 0, key="ca_on_save", use_container_width=True):
        tipo_g = "BONO_USD" if meta and str(meta.get("tipo", "")).upper() == "BONO_USD" else "ON_USD"
        ppc_usd = par / 100.0
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker,
            "CANTIDAD": float(vn),
            "PPC_USD": round(ppc_usd, 6),
            "PPC_ARS": round(monto_ars, 4),
            "TIPO": tipo_g,
            "LAMINA_VN": float("nan"),
        }], modo=st.session_state.get("ca_merge_mode", "agregar"))


def _render_carga_letra(ctx: dict) -> None:
    st.markdown("##### Letra del Tesoro (pagás con descuento, cobrás el nominal)")
    letras = tickers_por_tipo("LETRA")
    labels = [f"{t} — {descripcion_legible(t)}" for t in letras]
    sel = st.selectbox("Letra", labels, key="ca_letra_sel") if labels else ""
    ticker = sel.split("—")[0].strip() if sel else ""
    meta = get_meta(ticker)
    par_def = float(meta["paridad_ref"]) if meta else 97.0
    vn = st.number_input("Valor nominal a cobrar (ARS)", min_value=0.0, value=0.0, step=1000.0, key="ca_letra_vn")
    par = st.number_input("Precio % del nominal (desc.)", min_value=0.01, value=par_def, step=0.1, key="ca_letra_par")
    fc = st.date_input("Fecha compra", value=date.today(), key="ca_letra_fecha")
    pagado = vn * (par / 100.0)
    gan = max(0.0, vn - pagado)
    st.info(
        f"Pagás **ARS {pagado:,.0f}** ({par}% del nominal). "
        f"Al vencimiento cobrás **ARS {vn:,.0f}**. "
        f"Ganancia implícita **ARS {gan:,.0f}**."
    )
    ccl = float(ctx.get("ccl") or 1.0)
    ppc_usd = round((pagado / vn) / ccl, 8) if vn and ccl else 0.0
    if st.button("Guardar", disabled=vn <= 0, key="ca_letra_save", use_container_width=True):
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker or "LETRA",
            "CANTIDAD": float(vn),
            "PPC_USD": max(ppc_usd, 1e-8),
            "PPC_ARS": round(pagado, 4),
            "TIPO": "LETRA",
            "LAMINA_VN": float("nan"),
        }], modo=st.session_state.get("ca_merge_mode", "agregar"))


def _broker_to_maestra_rows(df_imp: pd.DataFrame, ctx: dict) -> list[dict[str, Any]]:
    """Convierte filas del importador a esquema Maestra_Transaccional."""
    cart = _cartera_csv(ctx)
    ccl = float(ctx.get("ccl") or 1.0)
    out: list[dict[str, Any]] = []
    for _, r in df_imp.iterrows():
        if str(r.get("Tipo_Op", "")).upper() != "COMPRA":
            continue
        tick = str(r.get("Ticker", "")).strip().upper()
        cant = int(float(r.get("Cantidad", 0) or 0))
        if cant <= 0 or not tick:
            continue
        precio_ars = float(r.get("Precio_ARS", 0) or 0)
        ppc_usd = float(r.get("PPC_USD", 0) or 0)
        f_raw = r.get("Fecha")
        if hasattr(f_raw, "date"):
            fc = f_raw.date()
        else:
            fc = pd.to_datetime(f_raw, errors="coerce")
            fc = fc.date() if pd.notna(fc) else date.today()
        tipo_act = str(r.get("Tipo_Activo", "")).upper()
        if "ACCION" in tipo_act or tipo_act == "ACCIÓN":
            tipo_m = "ACCION_LOCAL"
        elif "ETF" in tipo_act:
            tipo_m = "ETF"
        else:
            tipo_m = "CEDEAR"
        out.append({
            "CARTERA": cart,
            "FECHA_COMPRA": fc,
            "TICKER": tick,
            "CANTIDAD": cant,
            "PPC_USD": round(ppc_usd, 6) if ppc_usd > 0 else round(precio_ars / ccl, 6),
            "PPC_ARS": round(precio_ars, 4),
            "TIPO": tipo_m,
            "LAMINA_VN": float("nan"),
        })
    return out


def _render_importar_broker(ctx: dict) -> None:
    st.markdown("##### Importar desde tu broker")
    st.caption(
        "Elegí tu broker, exportá tu archivo (Excel o CSV) y subilo acá. "
        "Si usás otro broker, probá igual: a veces el formato es compatible."
    )
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        st.markdown("**Balanz**")
        st.caption(broker_tarjeta_sub("Balanz"))
        if st.button("Balanz", key="ca_br_balanz", use_container_width=True):
            st.info("Exportá desde Balanz y subí el archivo abajo.")
    with bc2:
        st.markdown("**IOL**")
        st.caption(broker_tarjeta_sub("IOL"))
        if st.button("IOL", key="ca_br_iol", use_container_width=True):
            st.info("Exportá desde IOL y subí el archivo abajo.")
    with bc3:
        st.markdown("**Bull Market**")
        st.caption(broker_tarjeta_sub("BMB"))
        if st.button("BMB", key="ca_br_bmb", use_container_width=True):
            st.info("Exportá operaciones en Excel/CSV desde Bull Market.")
    prop = str(ctx.get("prop_nombre") or ctx.get("cliente_nombre") or "Cliente")
    uploaded = st.file_uploader("Archivo Excel o CSV", type=["xlsx", "xls", "csv", "txt"], key="ca_up_broker")
    if uploaded:
        fmt_guess = "auto"
        try:
            head = uploaded.read(4096)
            uploaded.seek(0)
            if b"," in head[:200] or uploaded.name.lower().endswith(".csv"):
                fmt_guess = "csv"
        except Exception:
            pass
        st.caption(f"Detección: **{fmt_guess}** — revisá el preview.")
        try:
            df_imp = importar_archivo_broker(uploaded, propietario=prop, cartera=_cartera_csv(ctx), ccl=float(ctx.get("ccl") or 1450.0))
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
            df_imp = pd.DataFrame()
        if df_imp is not None and not df_imp.empty:
            st.dataframe(df_imp.head(30), use_container_width=True)
            modo = st.radio(
                "Si ya tenés operaciones para esta cartera:",
                ("agregar", "sobrescribir"),
                format_func=lambda x: "Agregar al historial" if x == "agregar" else "Reemplazar solo esta cartera (riesgoso)",
                key="ca_imp_mode",
            )
            st.session_state["ca_merge_mode"] = modo
            if st.button("Confirmar importación", key="ca_imp_ok", use_container_width=True):
                filas = _broker_to_maestra_rows(df_imp, ctx)
                if not filas:
                    st.error("No quedaron filas COMPRA válidas.")
                else:
                    _persist_filas(ctx, filas, modo=modo)
    plantilla = "CARTERA,FECHA_COMPRA,TICKER,CANTIDAD,PPC_USD,PPC_ARS,TIPO,LAMINA_VN\n"
    st.download_button(
        "Descargar plantilla CSV",
        data=plantilla,
        file_name="plantilla_mq26_transacciones.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_carga_activos(ctx: dict) -> None:
    """Menú principal de carga de activos."""
    ttab = st.session_state.get("inv_carga_tab")
    if ttab in ("importar", "manual"):
        st.session_state["ca_menu_main"] = ttab
        st.session_state.pop("inv_carga_tab", None)

    st.markdown("### Sumar operaciones a tu cartera")
    modo = st.radio(
        "¿Qué querés hacer?",
        ("importar", "manual", "historial"),
        format_func=lambda x: {
            "importar": "Importar archivo del broker",
            "manual": "Cargar una compra manual",
            "historial": "Ver historial de compras",
        }[x],
        horizontal=True,
        key="ca_menu_main",
    )
    st.session_state.setdefault("ca_merge_mode", "agregar")

    if modo == "importar":
        _render_importar_broker(ctx)
        return
    if modo == "historial":
        st.caption(historial_meses_copy())
        ed = ctx.get("engine_data")
        if ed is None:
            st.error("Sin motor de datos.")
            return
        try:
            tr = ed.cargar_transaccional()
            st.dataframe(tr, use_container_width=True, height=320)
        except Exception as e:
            st.error(str(e))
        return

    tipo = st.selectbox(
        "Tipo de instrumento",
        (
            "cedear",
            "on",
            "letra",
            "local",
        ),
        format_func=lambda x: {
            "cedear": "CEDEAR / Acción USA / ETF",
            "on": "ON / Bono USD",
            "letra": "Letra del Tesoro",
            "local": "Acción local (ARS)",
        }[x],
        key="ca_tipo_manual",
    )
    if tipo == "cedear":
        _render_carga_cedear(ctx)
    elif tipo == "on":
        _render_carga_on(ctx)
    elif tipo == "letra":
        _render_carga_letra(ctx)
    else:
        _render_carga_accion_local(ctx)

    last = st.session_state.get("inv_ultima_carga")
    if isinstance(last, dict) and last.get("TICKER"):
        st.divider()
        _render_confirmacion_carga(str(last["TICKER"]), float(last.get("PPC_ARS", 0) or 0), ctx)
