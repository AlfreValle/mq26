"""
Monitor de ON en USD (Hard Dollar) — datos en vivo de BYMA + catálogo interno.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Asegurar que el paquete raíz esté en sys.path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    MONITOR_ON_USD_DISCLAIMER,
    analisis_obligaciones_negociables_usd_df,
    ficha_rf_minima_bundle,
    monitor_on_usd_panel_df,
    monitor_on_usd_vencimientos_por_mes_df,
)
from ui.components.ficha_rf_minima import render_ficha_rf_minima


@st.cache_data(ttl=600)
def _cached_on_usd_advisory_df(byma_live: dict | None = None):
    from services.on_usd_advisory import on_usd_advisory_table
    return on_usd_advisory_table(byma_live=byma_live)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_byma_on(ccl: float):
    """Datos en vivo de ONs desde BYMA — caché 5 min."""
    try:
        from services.byma_market_data import enriquecer_on_desde_byma
        return enriquecer_on_desde_byma(ccl)
    except Exception:
        return {}


def _get_ccl() -> float:
    """Obtiene el CCL vigente; fallback 1500."""
    try:
        from services.market_connector import obtener_ccl_mep
        return obtener_ccl_mep()
    except Exception:
        pass
    try:
        from config import CCL_FALLBACK
        return float(CCL_FALLBACK)
    except Exception:
        return 1500.0


def render_monitor_on_usd(*, expanded: bool = False) -> None:
    with st.expander(
        "🇺🇸 Monitor de obligaciones negociables en USD (Hard Dollar)",
        expanded=expanded,
    ):
        st.caption(MONITOR_ON_USD_DISCLAIMER)
        st.markdown(
            "**Motor 60/20/20 (referencia)** — compra / acumulación / mantener / salida, "
            "alineado al resto del universo (fundamental + técnico + contexto)."
        )

        # Obtener CCL y datos en vivo (se reutiliza en scoring + panel principal).
        ccl = _get_ccl()
        byma_live = _cached_byma_on(ccl)

        # ── Scoring advisory ────────────────────────────────────────────────
        try:
            df_scores = _cached_on_usd_advisory_df(byma_live)
            if df_scores is not None and not df_scores.empty:
                st.dataframe(
                    df_scores,
                    use_container_width=True,
                    height=min(420, 56 + 28 * len(df_scores.index)),
                    hide_index=True,
                )
                st.caption(
                    "Precios y volumen vía Yahoo Finance (=RX / .BA según ticker); puede no "
                    "haber serie para todos. Nada de esto constituye recomendación personalizada."
                )
        except Exception as ex:
            st.caption(f"No se pudo calcular el scoring automático: {ex}")

        # ── Calendario de cupones ────────────────────────────────────────────
        st.markdown("#### Calendario de pagos de cupón por mes (ON USD)")
        st.caption(
            "Agrupado por **mes calendario** (enero, febrero, …) en que habitualmente "
            "**cae el cupón**, según la **frecuencia** y la **fecha de vencimiento** del "
            "catálogo (convención estándar alineada al último pago). La misma ON puede "
            "aparecer en varios meses si paga semestral o trimestral. Sin cupón periódico: "
            "se muestra el mes del **vencimiento** (devolución de principal). "
            "Referencia educativa; el calendario real puede seguir el prospecto."
        )
        df_cal = monitor_on_usd_vencimientos_por_mes_df()
        if df_cal.empty:
            st.info("No hay ON USD activas con fecha de vencimiento válida en el catálogo.")
        else:
            _n_meses = int(df_cal["Mes"].nunique())
            st.caption(
                f"**{_n_meses}** mes(es) calendario con al menos un pago · "
                f"{len(df_cal)} filas (ticker × mes de cupón)."
            )
            for mes, grp in df_cal.groupby("Mes", sort=False):
                sub = grp.drop(columns=["Mes"]).reset_index(drop=True)
                st.markdown(f"**{mes}** — {len(sub)} instrumento(s)")
                st.dataframe(sub, use_container_width=True, hide_index=True)

        # ── Ficha RF unificada (P2-RF-01) — alineada al panel BYMA / catálogo ──
        st.markdown("---")
        st.markdown("#### Ficha RF — detalle por instrumento (P2-RF-01)")
        st.caption(
            "Mismos tickers y paridad que la tabla de abajo; TIR al precio usa la **Paridad %** "
            "de la fila (BYMA en vivo o catálogo). Cashflow ilustrativo en el expander."
        )
        _byma_ficha = _cached_byma_on(ccl)
        _n_bf = len(_byma_ficha)
        _df_ficha = monitor_on_usd_panel_df(
            byma_live=_byma_ficha if _n_bf else None,
            ccl=ccl,
        )
        if _df_ficha.empty:
            st.info("No hay ON USD activas en el catálogo para armar la ficha.")
        else:
            _tickers_ficha = sorted(_df_ficha["Ticker"].astype(str).unique().tolist())
            _pick_ficha = st.selectbox(
                "Instrumento (panel / catálogo)",
                _tickers_ficha,
                key="mon_ficha_rf_ticker",
            )
            _row_f = _df_ficha[_df_ficha["Ticker"] == _pick_ficha].iloc[0]
            _meta_f = INSTRUMENTOS_RF.get(_pick_ficha) or {}
            _par_raw = _row_f.get("Paridad %")
            _par_f: float | None = None
            if _par_raw is not None and not pd.isna(_par_raw):
                try:
                    _par_f = float(_par_raw)
                except (TypeError, ValueError):
                    _par_f = None
            _px_raw = _row_f.get("Precio ARS")
            _px_f: float | None = None
            if _px_raw is not None and not pd.isna(_px_raw):
                try:
                    _px_f = float(_px_raw)
                except (TypeError, ValueError):
                    _px_f = None
            _fuente_f = _row_f.get("Fuente")
            _fuente_s = str(_fuente_f).strip() if _fuente_f is not None and str(_fuente_f).strip() else None
            _aj_x100 = str(_row_f.get("Ajuste ×100 BYMA", "")).strip() == "Sí"
            _nota_esc = None
            if _aj_x100:
                _nota_esc = (
                    "Último BYMA en escala ×100 (ARS por 100 VN); se aplicó ÷100 para alinear a "
                    "ARS por 1 VN nominal USD. Ver columna **Ajuste ×100 BYMA** y "
                    "`docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`."
                )
            _bundle_f = ficha_rf_minima_bundle(
                _pick_ficha,
                _meta_f,
                paridad_pct=_par_f,
                precio_mercado_ars=_px_f,
                fuente_precio=_fuente_s,
                escala_div100_aplicada=_aj_x100,
                nota_escala=_nota_esc,
            )
            render_ficha_rf_minima(_bundle_f, key_prefix=f"mon_ficha_{_pick_ficha}")

        # ── Panel principal con datos BYMA en vivo ──────────────────────────
        st.markdown("---")
        _hdr_col, _btn_col = st.columns([5, 1])
        with _hdr_col:
            st.markdown("#### 📊 Panel de mercado — ONs Hard Dollar")
        with _btn_col:
            st.write("")
            if st.button("🔄 Actualizar", key="mon_on_refresh", help="Forzar actualización desde BYMA"):
                st.cache_data.clear()
                st.rerun()

        with st.spinner("Consultando BYMA — Obligaciones Negociables..."):
            byma_live = _cached_byma_on(ccl)

        n_live = len(byma_live)

        if n_live:
            st.success(
                f"**{n_live}** ON(s) con precio en vivo desde BYMA · "
                f"CCL utilizado: **${ccl:,.0f}** · "
                f"Caché: 5 min"
            )
        else:
            st.warning(
                "No se pudieron obtener precios en vivo desde BYMA. "
                "Se muestran los datos del catálogo interno. "
                "Verificá la conexión a internet."
            )

        df = monitor_on_usd_panel_df(byma_live=byma_live if n_live else None, ccl=ccl)

        if df.empty:
            st.info("No hay ON en dólares activas en el catálogo interno.")
            return

        if "Ajuste ×100 BYMA" in df.columns and (df["Ajuste ×100 BYMA"].astype(str) == "Sí").any():
            st.info(
                "**P2-RF-04:** al menos un ticker trajo el último de BYMA en escala ×100 "
                "(ARS por 100 VN); se aplicó **÷100** para alinear a ARS por 1 VN nominal USD. "
                "Columna **Ajuste ×100 BYMA** = Sí en esas filas. Ver "
                "`docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`."
            )

        # ── Resumen por perfil de riesgo ─────────────────────────────────
        st.markdown("**Resumen por perfil de riesgo (referencia)**")
        for banda, emoji, titulo in (
            ("conservador", "🟢", "Alternativas conservadoras"),
            ("moderado",    "🟡", "Alternativas moderadas"),
            ("agresivo",    "🔴", "Alternativas agresivas"),
        ):
            sub = df[df["Banda"] == banda]
            if sub.empty:
                continue
            st.markdown(f"**{emoji} {titulo}**")
            lines = []
            for _, r in sub.iterrows():
                lam = r.get("Lámina mín.")
                vn = "VN" if lam == 1 else "VNs"
                paridad_txt = f" | Paridad: {r['Paridad %']:.1f}%" if r.get("Paridad %") else ""
                var_txt = ""
                if r.get("Var. % día") is not None:
                    signo = "+" if float(r["Var. % día"]) >= 0 else ""
                    var_txt = f" | Día: {signo}{r['Var. % día']:.2f}%"
                fuente_ico = " 🟢" if "BYMA" in str(r.get("Fuente", "")) else ""
                lines.append(
                    f"- **{r['Ticker']}** ({r['Emisor']}): "
                    f"**{r['TIR ref. %']}%** TIR"
                    f"{paridad_txt}{var_txt} "
                    f"(mín. {lam:,} {vn}){fuente_ico}".replace(",", ".")
                )
            st.markdown("\n".join(lines))

        # ── Tabla detallada ──────────────────────────────────────────────
        st.markdown("**Tabla detallada**")

        # Columnas a mostrar (ocultar las que son todas nulas)
        cols_mostrar = ["Fuente", "Banda", "Ticker", "Emisor",
                        "Paridad %", "ARS / 100 VN USD", "Precio ARS", "Var. % día",
                        "TIR ref. %", "Cupón %", "Vencimiento",
                        "Calificación", "Ley", "Lámina mín.", "Callable",
                        "Frecuencia cupón", "Fecha dato", "Ajuste ×100 BYMA"]
        cols_disponibles = [c for c in cols_mostrar if c in df.columns]
        disp = df[cols_disponibles].copy()

        # Estilo: colorear Var. % día y Fuente
        def _color_var(val):
            try:
                v = float(val)
                return "color:#27AE60;font-weight:bold" if v >= 0 else "color:#E74C3C;font-weight:bold"
            except Exception:
                return ""

        def _color_fuente(val):
            if "BYMA" in str(val):
                return "color:#27AE60;font-weight:bold"
            return "color:#9E9E9E"

        styler = disp.style
        if "Var. % día" in disp.columns:
            styler = styler.map(_color_var, subset=["Var. % día"])
        if "Fuente" in disp.columns:
            styler = styler.map(_color_fuente, subset=["Fuente"])

        fmt: dict[str, str] = {}
        if "Paridad %"  in disp.columns: fmt["Paridad %"]  = "{:.2f}%"
        if "ARS / 100 VN USD" in disp.columns:
            fmt["ARS / 100 VN USD"] = "${:,.2f}"
        if "Precio ARS" in disp.columns: fmt["Precio ARS"] = "${:,.2f}"
        if "Var. % día" in disp.columns: fmt["Var. % día"] = "{:+.2f}%"
        if "TIR ref. %" in disp.columns: fmt["TIR ref. %"] = "{:.2f}%"
        if "Cupón %"    in disp.columns: fmt["Cupón %"]    = "{:.2f}%"
        if "Lámina mín." in disp.columns: fmt["Lámina mín."] = "{:,.0f}"
        if fmt:
            styler = styler.format(fmt, na_rep="—")

        st.dataframe(
            styler,
            use_container_width=True,
            height=min(560, 64 + 28 * len(disp.index)),
            hide_index=True,
        )
        if n_live:
            st.caption(
                f"🟢 **{n_live}** ticker(s) con precio en vivo de BYMA · "
                "Paridad % inferida del último (ARS por VN o por 100 VN, o % directo). "
                f"**ARS / 100 VN USD** = paridad_% × CCL (CCL **${ccl:,.0f}**). "
                "TIR ref. del catálogo interno."
            )
        else:
            st.caption(
                "📋 Paridad y datos de referencia del catálogo interno. "
                f"**ARS / 100 VN USD** = paridad_% × CCL (CCL **${ccl:,.0f}**). "
                "Sin cotización en vivo (BYMA no respondió)."
            )

        with st.expander("📐 Análisis de unidades — todas las obligaciones negociables USD", expanded=False):
            st.caption(
                "Misma convención para cada fila: **CANTIDAD** = nominales USD; **PPC_USD** = paridad %; "
                "valor en pesos por cada 100 nominales USD ≈ **paridad × CCL**."
            )
            df_units = analisis_obligaciones_negociables_usd_df(
                ccl,
                byma_live=byma_live if n_live else None,
            )
            if df_units.empty:
                st.info("Sin filas de análisis.")
            else:
                st.dataframe(df_units, use_container_width=True, hide_index=True)
