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
from core.logging_config import get_logger
from services.copy_inversor import historial_meses_copy

_log = get_logger(__name__)
from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    descripcion_legible,
    get_meta,
    tickers_por_tipo,
    tickers_rf_activos,
    tir_al_precio,
    valor_nominal_a_ars,
)


def _aplicar_guard_paridad_rf(
    filas: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """KPI dictamen: no persistir ON/bono USD con PPC_USD fuera de escala."""
    from core.pricing_utils import validar_ppc_usd_paridad_rf

    ok: list[dict[str, Any]] = []
    errores: list[str] = []
    avisos: list[str] = []
    for f in filas:
        ticker = str(f.get("TICKER", "") or "")
        tipo = str(f.get("TIPO", "") or "")
        try:
            ppc = float(f.get("PPC_USD") or 0)
        except (TypeError, ValueError):
            ppc = 0.0
        persistible, marca, msg = validar_ppc_usd_paridad_rf(ticker, tipo, ppc)
        if not persistible:
            errores.append(msg or f"{ticker}: paridad RF inválida.")
            continue
        if marca:
            f = dict(f)
            f["ALERTA_PARIDAD"] = marca
            avisos.append(msg)
        ok.append(f)
    return ok, errores, avisos


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
    pairs = sorted(zip(m.keys(), m.values(), strict=True), key=lambda x: x[1])
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



def _validar_tickers(filas: list[dict[str, Any]], ctx: dict) -> list[str]:
    """Advierte contra el maestro de instrumentos (A45). No bloquea el guardado."""
    from core.instrument_master import get_master

    master = get_master(ctx.get("universo_df"))
    warnings_out: list[str] = []
    for f in filas:
        ticker = str(f.get("TICKER", "")).strip().upper()
        if not ticker:
            continue
        v = master.validar(ticker, str(f.get("TIPO", "") or ""))
        if v.valido and not v.motivo:
            continue
        if not v.valido:
            msg = (
                f"**{ticker}** no está en el maestro de instrumentos "
                "(universo + catálogo RF). Verificá el símbolo antes de confirmar."
            )
            if v.sugerencias:
                msg += f" ¿Quisiste decir **{', '.join(v.sugerencias)}**?"
            warnings_out.append(msg)
        else:
            warnings_out.append(f"**{ticker}**: {v.motivo}")
    return warnings_out


def _label_cedear(row: pd.Series) -> str:
    """Label enriquecido para selectbox: TICKER — Nombre (ratio X:1) · Sector."""
    ticker = str(row.get("TICKER", row.get("Ticker", ""))).strip().upper()
    nombre = str(row.get("Nombre", row.get("nombre", ""))).strip()
    ratio = row.get("ratio", row.get("Ratio", None))
    sector = str(row.get("sector", row.get("Sector", ""))).strip()
    label = ticker
    if nombre and nombre.upper() != ticker:
        label += f" — {nombre[:28]}"
    try:
        r = float(ratio)
        if r > 1.0:
            label += f" ({r:.0f}:1)"
    except (TypeError, ValueError):
        pass
    if sector:
        label += f" · {sector[:18]}"
    return label

def _cartera_csv(ctx: dict) -> str:
    return str(ctx.get("cartera_activa") or "Principal").strip()


_TIPOS_COMPRA_UNITARIA = frozenset({"CEDEAR", "ACCION_LOCAL", "ETF", "FCI", "OTRO"})
_LOTES_UNITARIOS_KEY = "ca_lotes_unitarios"
_MAX_LOTES_UNITARIOS = 50


def _ccl_de_compra(fecha: date | Any, ccl_spot: float) -> float:
    """CCL de la fecha de operación (histórico mensual); spot si no hay serie."""
    spot = float(ccl_spot or 0.0)
    try:
        from core.fx import ccl_para_fecha

        v = float(ccl_para_fecha(fecha, spot=spot).valor)
        return v if v > 0 else spot
    except Exception:
        return spot


def resolver_tipo_compra_unitaria(
    ticker: str,
    universo_df: pd.DataFrame | None = None,
) -> str:
    """Tipo RV para una compra por unidad. Renta fija se rechaza (va por VN + paridad)."""
    from core.instrument_master import get_master

    t = str(ticker or "").strip().upper()
    if not t:
        raise ValueError("Falta el ticker.")
    inst = get_master(universo_df).get(t)
    if inst is not None and inst.es_renta_fija:
        raise ValueError(
            f"{t} es renta fija ({inst.tipo}). "
            "Cargalo en «Una compra» con valor nominal y paridad, "
            "no como precio unitario de acción."
        )
    if inst is not None and inst.tipo in _TIPOS_COMPRA_UNITARIA:
        return inst.tipo
    return "CEDEAR"


def fila_desde_compra_unitaria(
    *,
    ticker: str,
    cantidad: float,
    precio_unitario: float,
    fecha: date | Any,
    ccl_spot: float,
    moneda: str = "ARS",
    universo_df: pd.DataFrame | None = None,
    ccl_operacion: float | None = None,
) -> dict[str, Any]:
    """
    Convierte una compra unitaria (unidades × precio por unidad) a fila de Maestra.

    Cada llamada es un lote FIFO. No consolida PPC acá: eso lo hace agregar_cartera.
    """
    t = str(ticker or "").strip().upper()
    tipo = resolver_tipo_compra_unitaria(t, universo_df)
    cant = float(cantidad)
    px = float(precio_unitario)
    if cant < 1:
        raise ValueError("La cantidad tiene que ser al menos 1 unidad.")
    if px <= 0:
        raise ValueError("El precio unitario tiene que ser mayor a 0.")
    ccl_op = float(ccl_operacion) if ccl_operacion and float(ccl_operacion) > 0 else _ccl_de_compra(fecha, ccl_spot)
    if ccl_op <= 0:
        raise ValueError("No hay CCL para convertir ARS ↔ USD de esta compra.")
    es_mep = str(moneda or "ARS").upper().startswith("USD")
    if es_mep:
        ppc_usd = px
        ppc_ars = px * ccl_op
        moneda_precio = "USD_MEP"
    else:
        ppc_ars = px
        ppc_usd = px / ccl_op
        moneda_precio = "ARS"
    return {
        "FECHA_COMPRA": fecha,
        "TICKER": t,
        "CANTIDAD": int(cant),
        "PPC_USD": round(ppc_usd, 6),
        "PPC_ARS": round(ppc_ars, 4),
        "TIPO": tipo,
        "LAMINA_VN": float("nan"),
        "MONEDA_PRECIO": moneda_precio,
    }


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


def aplicar_vaciar_cartera(ctx: dict, cartera: str) -> int:
    """
    Elimina todas las filas del Maestra_Transaccional cuyo CARTERA corresponde al cliente/cartera.
    Devuelve cuántas filas se quitaron. Si hubo cambios, invalida cachés de Streamlit.

    Nota de matching:
      El rol 'inversor' normaliza el campo CARTERA en memoria a "<Cliente> | Cartera principal"
      (ver core/cartera_scope.py), pero el CSV puede tener "<Cliente> | Retiro" u otro sufijo.
      Por eso intentamos primero coincidencia exacta; si no hay match, usamos el prefijo del
      propietario (parte antes del '|') para identificar todas las sub-carteras del cliente.
    """
    ed = ctx.get("engine_data")
    if ed is None:
        raise RuntimeError("Motor de datos no disponible.")
    c = str(cartera or "").strip()
    if not c or c == "-- Todas las carteras --":
        raise RuntimeError("Cartera inválida.")
    trans = ed.cargar_transaccional().copy()
    if trans.empty or "CARTERA" not in trans.columns:
        return 0

    c_col = trans["CARTERA"].astype(str).str.strip()

    # 1. Match exacto (flujo asesor con valor real del CSV)
    mask_eliminar = c_col == c

    # 2. Fallback por prefijo del propietario (flujo inversor con cartera normalizada)
    #    "Alfredo | Cartera principal" → busca por prefijo "Alfredo" y borra todo lo suyo
    if not mask_eliminar.any():
        cn_pref = c.split("|")[0].strip()
        if cn_pref:
            mask_eliminar = c_col.str.split("|").str[0].str.strip() == cn_pref

    n_rem = int(mask_eliminar.sum())
    if n_rem:
        nuevos = trans.loc[~mask_eliminar].reset_index(drop=True)
        ed.guardar_transaccional(nuevos)
        from core.cache_manager import invalidar_cache_tras_cambio_transaccional

        invalidar_cache_tras_cambio_transaccional()
    return n_rem


def _persist_filas(
    ctx: dict,
    filas: list[dict[str, Any]],
    modo: str,
    *,
    cartera_override: str | None = None,
    session_keys_clear: list[str] | None = None,
) -> None:
    ed = ctx.get("engine_data")
    if ed is None:
        st.error("Motor de datos no disponible.")
        return
    advertencias = _validar_tickers(filas, ctx)
    for adv in advertencias:
        st.warning(adv)
    # M2: completar lámina de renta fija desde el catálogo antes de persistir
    # (una ON sin LAMINA_VN se valúa mal). Avisos informativos, no bloquean.
    try:
        from core.renta_fija_ar import completar_lamina_vn_filas

        for aviso in completar_lamina_vn_filas(filas):
            st.info(aviso)
    except Exception as _e_lam:
        _log.warning("completar_lamina_vn_filas falló (no bloquea): %s", _e_lam)
    filas, err_paridad, warn_paridad = _aplicar_guard_paridad_rf(filas)
    for e in err_paridad:
        st.error(e)
    for w in warn_paridad:
        st.warning(w)
    if not filas:
        if err_paridad:
            st.error("Ninguna fila se guardó: paridad de ON/bono USD fuera de escala.")
        return
    try:
        df_prev = ed.cargar_transaccional().copy()
    except Exception as e:
        st.error(f"No se pudo leer el transaccional: {e}")
        return
    cart = (cartera_override or _cartera_csv(ctx)).strip()
    for f in filas:
        if cartera_override:
            f["CARTERA"] = cart
        else:
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
        from core.cache_manager import invalidar_cache_tras_cambio_transaccional

        invalidar_cache_tras_cambio_transaccional()
        st.success(f"Listo: guardamos **{len(filas)}** compra(s). Tu cartera se actualizó.")
        st.session_state["inv_ultima_carga"] = filas[-1] if filas else {}
        st.session_state.pop("inv_diagnostico", None)
        st.session_state.pop("diagnostico_cache", None)
        if session_keys_clear:
            for _k in session_keys_clear:
                st.session_state.pop(_k, None)
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
    u = ctx.get("universo_df")
    col = _ticker_col_univ(u)
    if u is None or u.empty or not col:
        st.warning("No hay universo cargado o no hay coincidencias.")
        return
    qu = q.strip().lower()
    pairs: list[tuple[str, str]] = []
    for _, row in u.iterrows():
        tkr = str(row[col]).strip().upper()
        if not tkr or tkr == "NAN":
            continue
        lbl = _label_cedear(row)
        if qu and qu not in lbl.lower():
            continue
        pairs.append((lbl, tkr))
    pairs = sorted(pairs, key=lambda x: x[1])[:400]
    if not pairs:
        st.warning("No hay universo cargado o no hay coincidencias.")
        return
    labels = [p[0] for p in pairs]
    label_map = dict(pairs)
    sel = st.selectbox("Elegí el activo", labels, key="ca_cedear_sel")
    ticker = label_map.get(sel, str(sel).split("—")[0].strip())
    ccl = float(ctx.get("ccl") or 1.0)
    precios = ctx.get("precios_dict") or {}
    precio_ref_ars = float(precios.get(ticker, 0.0) or 0.0)
    precio_ref_usd_mep = (precio_ref_ars / ccl) if ccl and precio_ref_ars > 0 else 0.0

    moneda_px = st.radio(
        "¿En qué moneda cargás el precio pagado por cuotaparte?",
        ("Pesos (ARS)", "USD MEP (dólar CCL)"),
        index=0,
        horizontal=True,
        key="ca_cedear_moneda",
        help="Por defecto **pesos**, como cotiza en BYMA. Elegí **USD MEP** si querés cargar "
        "el precio en dólares contado con liqui (misma referencia que el CCL del panel).",
    )
    es_usd_mep = moneda_px.startswith("USD")

    c1, c2, c3 = st.columns(3)
    with c1:
        cant = st.number_input("¿Cuántas unidades?", min_value=0.0, value=0.0, step=1.0, key="ca_cedear_cant")
    with c2:
        if es_usd_mep:
            px = st.number_input(
                "Precio unitario (USD MEP)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="ca_cedear_px",
                help="Dólares MEP por cuotaparte (contado con liqui). Se convierte a ARS con el CCL del panel.",
            )
        else:
            px = st.number_input(
                "Precio unitario (ARS)",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="ca_cedear_px",
                help="Pesos pagados por cuotaparte, como en tu broker (BYMA).",
            )
    with c3:
        fc = st.date_input("¿Cuándo?", value=date.today(), key="ca_cedear_fecha")

    if es_usd_mep:
        ppc_usd = float(px)
        ppc_ars = float(px) * ccl
        if px > 0 and precio_ref_usd_mep > 0 and px > precio_ref_usd_mep * 3:
            st.warning(
                f"¿Seguro? **{ticker}** ronda **USD MEP ~{precio_ref_usd_mep:,.2f}** por cuotaparte "
                "(referencia con tu CCL actual)."
            )
    else:
        ppc_ars = float(px)
        ppc_usd = round(float(px) / ccl, 8) if ccl else 0.0
        if px > 0 and precio_ref_ars > 0 and px > precio_ref_ars * 3:
            st.warning(
                f"¿Seguro? **{ticker}** cotiza cerca de **ARS {precio_ref_ars:,.0f}** según la última lectura."
            )

    monto_ars = cant * ppc_ars
    if es_usd_mep:
        st.info(
            f"Vista previa: **USD MEP {cant * float(px):,.2f}** → **ARS {monto_ars:,.0f}** "
            f"(CCL {ccl:,.0f})."
        )
    else:
        st.info(
            f"Vista previa: **ARS {monto_ars:,.0f}** "
            f"(~ **USD MEP {cant * ppc_usd:,.2f}** al CCL {ccl:,.0f})."
        )
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
            "MONEDA_PRECIO": "USD_MEP" if es_usd_mep else "ARS",
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
        par = st.number_input(
            "Paridad % (precio limpio)", min_value=0.01, value=par_def, step=0.5,
            key="ca_on_par",
            help="Las ONs/bonos se cotizan como % del valor nominal. Ejemplo: si "
            "pagaste ARS 9.700 por USD 100 nominales, la paridad es ~97%. "
            "Rango típico de mercado: 80–115%. Mirá el comprobante de tu broker.",
        )
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
        # Convención PPC_USD para ON/bono USD: almacenar la paridad % directamente (ej. 97.5 = 97.5%).
        # agregar_cartera usa (ppc_usd / 100.0) × ccl_hist para derivar el costo ARS por nominal.
        # NO dividir aquí por 100: el motor ya lo hace.
        ppc_usd = par  # paridad % (ej. 97.5), NO pcc fraccional (0.975)
        ppc_ars_unit = (monto_ars / vn) if vn > 0 else 0.0
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker,
            "CANTIDAD": float(vn),
            "PPC_USD": round(ppc_usd, 6),
            "PPC_ARS": round(ppc_ars_unit, 6),
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
    ppc_ars_unit = (pagado / vn) if vn > 0 else 0.0
    if st.button("Guardar", disabled=vn <= 0, key="ca_letra_save", use_container_width=True):
        _persist_filas(ctx, [{
            "FECHA_COMPRA": fc,
            "TICKER": ticker or "LETRA",
            "CANTIDAD": float(vn),
            "PPC_USD": max(ppc_usd, 1e-8),
            "PPC_ARS": round(ppc_ars_unit, 6),
            "TIPO": "LETRA",
            "LAMINA_VN": float("nan"),
        }], modo=st.session_state.get("ca_merge_mode", "agregar"))


def _broker_to_maestra_rows(
    df_imp: pd.DataFrame,
    ctx: dict,
    *,
    incluir_ventas: bool = False,
) -> list[dict[str, Any]]:
    """Convierte filas del importador a esquema Maestra_Transaccional.
    Las ventas se guardan con CANTIDAD negativa (posición neta y FIFO en el motor).
    """
    cart = _cartera_csv(ctx)
    ccl = float(ctx.get("ccl") or 1.0)
    # Tipos RF explícitos que el importador o parsers IOL ya resolvieron correctamente.
    # Convención PPC_USD para ON/bono USD: paridad % (ej. 97.5), NO fracción (0.975).
    _RF_TIPOS_EXPLÍCITOS = frozenset({
        "ON", "ON_USD", "BONO", "BONO_USD", "LETRA", "LECAP", "LEDE",
        "BONCER", "BOPREAL", "DUAL", "USD_LINKED",
    })
    out: list[dict[str, Any]] = []
    for _, r in df_imp.iterrows():
        tipo_op = str(r.get("Tipo_Op", "")).upper()
        if tipo_op == "COMPRA":
            sign = 1
        elif incluir_ventas and tipo_op == "VENTA":
            sign = -1
        else:
            continue
        tick = str(
            r.get("TICKER", r.get("Ticker", "")),
        ).strip().upper()
        cant_raw = int(float(r.get("CANTIDAD", r.get("Cantidad", 0)) or 0))
        cant = sign * abs(cant_raw) if cant_raw != 0 else 0
        if cant == 0 or not tick:
            continue
        precio_ars = float(r.get("Precio_ARS", 0) or 0)
        ppc_usd = float(r.get("PPC_USD", 0) or 0)
        f_raw = r.get("Fecha", r.get("FECHA_COMPRA"))
        if hasattr(f_raw, "date"):
            fc = f_raw.date()
        else:
            fc = pd.to_datetime(f_raw, errors="coerce")
            fc = fc.date() if pd.notna(fc) else date.today()
        tipo_act = str(r.get("TIPO", r.get("Tipo_Activo", ""))).upper()
        if tipo_act in _RF_TIPOS_EXPLÍCITOS:
            tipo_m = "ON_USD" if tipo_act in ("ON", "ON_USD") else (
                "BONO_USD" if tipo_act in ("BONO", "BONO_USD") else tipo_act
            )
        elif "ACCION" in tipo_act or tipo_act in ("ACCIÓN", "ACCION_LOCAL"):
            tipo_m = "ACCION_LOCAL"
        elif "ETF" in tipo_act:
            tipo_m = "ETF"
        else:
            # Fallback: consultar catálogo RF para instrumentos no etiquetados (Balanz, BMB)
            _meta_rf = get_meta(tick)
            if _meta_rf:
                tipo_m = str(_meta_rf.get("tipo", "ON_USD")).upper()
            else:
                tipo_m = "CEDEAR"
        out.append({
            "CARTERA": cart,
            "FECHA_COMPRA": fc,
            "TICKER": tick,
            "CANTIDAD": cant,
            "PPC_USD": round(ppc_usd, 6) if ppc_usd > 0 else round(precio_ars / max(ccl, 1e-9), 6),
            "PPC_ARS": round(precio_ars, 4),
            "TIPO": tipo_m,
            "LAMINA_VN": float("nan"),
        })
    return out


def _render_carga_venta_simple(ctx: dict) -> None:
    """Venta manual: CANTIDAD negativa (compatible con agregar_cartera / FIFO)."""
    st.markdown("##### Registrar una venta")
    st.caption(
        "Indicá ticker, cuántas unidades vendiste y el precio por unidad (como en el comprobante). "
        "MQ26 guarda la operación con cantidad **negativa** y actualiza tu posición neta."
    )
    ccl = float(ctx.get("ccl") or 1.0)
    ticker = st.text_input("Ticker BYMA", "", key="ca_vta_tick").strip().upper()
    c1, c2, c3 = st.columns(3)
    with c1:
        cant = st.number_input(
            "Unidades vendidas",
            min_value=1.0,
            value=1.0,
            step=1.0,
            key="ca_vta_cant",
        )
    es_usd = st.checkbox(
        "Precio en USD MEP (typ. CEDEAR)",
        value=False,
        key="ca_vta_usd",
        help="Desmarcado: precio en pesos por cuotaparte (acciones locales o si ya cargaste ARS).",
    )
    with c2:
        lab = "Precio USD MEP c/u" if es_usd else "Precio ARS c/u"
        px = st.number_input(lab, min_value=0.0, value=0.0, step=0.01, key="ca_vta_px")
    with c3:
        fc = st.date_input("Fecha de la venta", value=date.today(), key="ca_vta_fecha")
    if es_usd:
        ppc_usd = float(px)
        ppc_ars = float(px) * ccl
    else:
        ppc_ars = float(px)
        ppc_usd = round(float(px) / max(ccl, 1e-9), 8) if ccl else 0.0
    tipo_u = "CEDEAR"
    udf = ctx.get("universo_df")
    ct = _ticker_col_univ(udf)
    if udf is not None and ct is not None and ticker:
        row = udf[udf[ct].astype(str).str.upper() == ticker.upper()]
        if not row.empty:
            tipo_cell = row.iloc[0].get("TIPO", row.iloc[0].get("Tipo", ""))
            tipo_u = str(tipo_cell).strip().upper() or "CEDEAR"
    if tipo_u in ("ACCION", "ACCIÓN"):
        tipo_u = "ACCION_LOCAL"
    if tipo_u not in (
        "ETF",
        "CEDEAR",
        "ACCION_LOCAL",
        "ON",
        "ON_USD",
        "BONO",
        "BONO_USD",
        "LETRA",
    ):
        tipo_u = "CEDEAR"
    st.session_state.setdefault("ca_merge_mode", "agregar")
    if st.button(
        "Registrar venta",
        disabled=cant < 1 or px <= 0 or not ticker,
        key="ca_vta_save",
        use_container_width=True,
    ):
        _persist_filas(
            ctx,
            [{
                "FECHA_COMPRA": fc,
                "TICKER": ticker,
                "CANTIDAD": -float(abs(cant)),
                "PPC_USD": round(ppc_usd, 6),
                "PPC_ARS": round(ppc_ars, 4),
                "TIPO": tipo_u,
                "LAMINA_VN": float("nan"),
            }],
            modo=st.session_state.get("ca_merge_mode", "agregar"),
        )


def _render_importar_broker(ctx: dict) -> None:
    st.caption(
        "Balanz, IOL o Bull Market. Exportá Excel o CSV y subilo — detectamos el formato. "
        f"Se guarda en **{_cartera_csv(ctx)}**."
    )
    prop = str(ctx.get("prop_nombre") or ctx.get("cliente_nombre") or "Cliente")
    uploaded = st.file_uploader(
        "Archivo Excel o CSV",
        type=["xlsx", "xls", "csv", "txt"],
        key="ca_up_broker",
    )
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
            imp_res = importar_archivo_broker(
                uploaded,
                propietario=prop,
                cartera=_cartera_csv(ctx),
                ccl=float(ctx.get("ccl") or 1450.0),
            )
        except Exception:
            _log.exception("carga_activos: importar_archivo_broker inesperado")
            st.error("No se pudo procesar el archivo. Si el problema persiste, contactá soporte.")
            df_imp = pd.DataFrame()
        else:
            for msg in imp_res.errors:
                st.error(msg)
            for msg in imp_res.warnings:
                st.warning(msg)
            df_imp = imp_res.df
            if not df_imp.empty:
                resumen = f"**{len(df_imp)}** operaciones listas para confirmar."
                if imp_res.filas_omitidas:
                    resumen += (
                        f" Filas omitidas en el parser (Bull Market): **{imp_res.filas_omitidas}** "
                        "(detalle arriba si aplica)."
                    )
                st.info(resumen)
        if df_imp is not None and not df_imp.empty:
            _n_imp = len(df_imp)
            st.caption(
                f"Vista previa: primeras {min(30, _n_imp)} de **{_n_imp}** operaciones. "
                "Revisá ticker, cantidad y precio antes de confirmar."
            )
            st.dataframe(df_imp.head(30), use_container_width=True)
            if _n_imp > 30:
                st.info(f"Hay {_n_imp - 30} fila(s) más que no se muestran en el preview, pero se importarán.")
            incluir_v = st.checkbox(
                "Incluir ventas del archivo (reducen o cierran posiciones)",
                value=False,
                key="ca_imp_incluir_ventas",
                help="Cada venta se importa con cantidad negativa; el motor recalcula posición y PPC (FIFO si está activo).",
            )
            modo = st.radio(
                "Si ya tenés operaciones para esta cartera:",
                ("agregar", "sobrescribir"),
                format_func=lambda x: "Agregar al historial" if x == "agregar" else "Reemplazar solo esta cartera (riesgoso)",
                key="ca_imp_mode",
            )
            st.session_state["ca_merge_mode"] = modo
            if st.button("Confirmar importación", key="ca_imp_ok", use_container_width=True):
                filas = _broker_to_maestra_rows(df_imp, ctx, incluir_ventas=incluir_v)
                if not filas:
                    st.error(
                        "No quedaron filas COMPRA ni VENTA válidas."
                        if incluir_v
                        else "No quedaron filas COMPRA válidas."
                    )
                else:
                    _persist_filas(ctx, filas, modo=modo)
    plantilla = (
        "CARTERA,FECHA_COMPRA,TICKER,CANTIDAD,PPC_USD,PPC_ARS,TIPO,LAMINA_VN,MONEDA_PRECIO\n"
    )
    st.download_button(
        "Descargar plantilla CSV",
        data=plantilla,
        file_name="plantilla_mq26_transacciones.csv",
        mime="text/csv",
        use_container_width=True,
    )


def _render_compras_unitarias(ctx: dict) -> None:
    """Varias compras reales: cada fila es un lote (unidades × precio unitario)."""
    st.markdown("##### Compras unitarias")
    st.caption(
        "Cada fila es una compra del comprobante: ticker, unidades y precio **por unidad**. "
        "Si compraste el mismo activo varias veces, cargá cada lote — el PPC se consolida solo. "
        "ON, bonos y letras van en **Una compra** (valor nominal + paridad)."
    )
    lotes: list[dict[str, Any]] = list(st.session_state.get(_LOTES_UNITARIOS_KEY) or [])
    ccl_spot = float(ctx.get("ccl") or 0.0)
    univ = ctx.get("universo_df")

    q = st.text_input(
        "Buscá por nombre o ticker",
        "",
        key="ca_unit_q",
        help="Ej.: nvidia, AAPL, GGAL.",
    )
    labels, label_map = _filtrar_univ_por_busqueda(ctx, q)
    ticker_sel = ""
    if labels:
        sel = st.selectbox("Elegí el activo", labels, key="ca_unit_sel")
        ticker_sel = label_map.get(sel, str(sel).split("—")[0].strip())
    ticker_manual = st.text_input(
        "O escribí el ticker",
        ticker_sel,
        key="ca_unit_tick",
    ).strip().upper()
    ticker = ticker_manual or ticker_sel

    moneda_px = st.radio(
        "Moneda del precio unitario",
        ("Pesos (ARS)", "USD MEP (dólar CCL)"),
        index=0,
        horizontal=True,
        key="ca_unit_moneda",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        cant = st.number_input(
            "Unidades",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key="ca_unit_cant",
        )
    with c2:
        es_mep = moneda_px.startswith("USD")
        px = st.number_input(
            "Precio unitario (USD MEP)" if es_mep else "Precio unitario (ARS)",
            min_value=0.0,
            value=0.0,
            step=0.01 if es_mep else 1.0,
            key="ca_unit_px",
        )
    with c3:
        fc = st.date_input("Fecha de compra", value=date.today(), key="ca_unit_fecha")

    if ticker and px > 0 and cant >= 1:
        try:
            prev = fila_desde_compra_unitaria(
                ticker=ticker,
                cantidad=cant,
                precio_unitario=px,
                fecha=fc,
                ccl_spot=ccl_spot,
                moneda="USD_MEP" if es_mep else "ARS",
                universo_df=univ,
            )
            st.info(
                f"Vista previa: **{int(cant)} × {ticker}** → "
                f"**ARS {prev['PPC_ARS'] * int(cant):,.0f}** "
                f"(~ USD {prev['PPC_USD'] * int(cant):,.2f} · {prev['TIPO']})."
            )
        except ValueError as e:
            st.warning(str(e))
            prev = None
    else:
        prev = None

    puede_agregar = prev is not None and len(lotes) < _MAX_LOTES_UNITARIOS
    if st.button(
        "Agregar a la lista",
        disabled=not puede_agregar,
        key="ca_unit_add",
        use_container_width=True,
    ):
        lotes.append(prev)
        st.session_state[_LOTES_UNITARIOS_KEY] = lotes
        st.rerun()

    if not lotes:
        st.caption("Todavía no hay lotes en la lista.")
        return

    from ui.mq26_ux import dataframe_auto_height

    df_lotes = pd.DataFrame(lotes)
    mostrar = df_lotes[["FECHA_COMPRA", "TICKER", "CANTIDAD", "PPC_ARS", "PPC_USD", "TIPO"]].copy()
    mostrar.columns = ["Fecha", "Ticker", "Unidades", "Precio ARS", "Precio USD", "Tipo"]
    st.dataframe(
        mostrar,
        use_container_width=True,
        hide_index=True,
        height=dataframe_auto_height(mostrar),
    )
    total_ars = float((df_lotes["CANTIDAD"] * df_lotes["PPC_ARS"]).sum())
    st.caption(f"**{len(lotes)}** lote(s) · total aproximado **ARS {total_ars:,.0f}**.")

    qcol, gcol = st.columns(2)
    with qcol:
        idx_del = st.number_input(
            "Quitar fila Nº",
            min_value=1,
            max_value=len(lotes),
            value=1,
            step=1,
            key="ca_unit_del_idx",
        )
        if st.button("Quitar de la lista", key="ca_unit_del", use_container_width=True):
            lotes.pop(int(idx_del) - 1)
            st.session_state[_LOTES_UNITARIOS_KEY] = lotes
            st.rerun()
    with gcol:
        if st.button(
            f"Guardar {len(lotes)} compra(s) en la cartera",
            type="primary",
            key="ca_unit_save",
            use_container_width=True,
        ):
            _persist_filas(
                ctx,
                lotes,
                modo=st.session_state.get("ca_merge_mode", "agregar"),
                session_keys_clear=[_LOTES_UNITARIOS_KEY],
            )


def render_carga_activos(ctx: dict) -> None:
    """Menú principal de carga de activos."""
    ttab = st.session_state.get("inv_carga_tab")
    if ttab in ("importar", "manual", "unitarias", "venta"):
        st.session_state["ca_menu_main"] = ttab
        st.session_state.pop("inv_carga_tab", None)

    st.markdown("### Sumar a esta cartera")
    modo = st.radio(
        "¿Qué querés hacer?",
        ("importar", "manual", "unitarias", "venta", "historial"),
        format_func=lambda x: {
            "importar": "Archivo del broker",
            "manual": "Una compra",
            "unitarias": "Varias compras unitarias",
            "venta": "Una venta",
            "historial": "Historial",
        }[x],
        horizontal=True,
        key="ca_menu_main",
        label_visibility="collapsed",
    )
    st.session_state.setdefault("ca_merge_mode", "agregar")

    if modo == "importar":
        _render_importar_broker(ctx)
        return
    if modo == "unitarias":
        _render_compras_unitarias(ctx)
        last = st.session_state.get("inv_ultima_carga")
        if isinstance(last, dict) and last.get("TICKER"):
            st.divider()
            _render_confirmacion_carga(str(last["TICKER"]), float(last.get("PPC_ARS", 0) or 0), ctx)
        return
    if modo == "venta":
        _render_carga_venta_simple(ctx)
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
