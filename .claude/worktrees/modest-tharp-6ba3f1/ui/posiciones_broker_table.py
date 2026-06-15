"""
Tabla HTML tipo homebroker (Balanz/Bull) — compartida entre inversor y cartera profesional.
Sin Streamlit: solo armado de HTML + formato AR.
"""
from __future__ import annotations

import html as html_module
import math
from datetime import date

import pandas as pd

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
from core.renta_fija_ar import es_fila_renta_fija_ar


def fmt_enteros_ar(n: float) -> str:
    """Miles con punto (estilo AR)."""
    x = int(round(float(n)))
    neg = x < 0
    s = str(abs(x))
    chunks: list[str] = []
    while s:
        chunks.insert(0, s[-3:])
        s = s[:-3]
    body = ".".join(chunks) if chunks else "0"
    return ("-" if neg else "") + body


def fmt_decimal_ar(n: float, dec: int = 2) -> str:
    """Decimal con coma (estilo AR)."""
    neg = float(n) < 0
    x = abs(float(n))
    s = f"{x:.{dec}f}"
    ip_s, frac = s.split(".")
    ip = int(ip_s)
    ip_fmt = fmt_enteros_ar(float(ip))
    return ("-" if neg else "") + ip_fmt + "," + frac


def pnl_css_class(v: float) -> str:
    if v > 1e-9:
        return "mq-pos-pnl-pos"
    if v < -1e-9:
        return "mq-pos-pnl-neg"
    return "mq-pos-pnl-neu"


def _annual_total_return_pct(pnl_frac: float, dias: int) -> float | None:
    """Tasa anual compuesta implícita del retorno acumulado pnl_frac en `dias` días."""
    # Evitar anualizar ventanas demasiado cortas: genera cifras explosivas y poco útiles.
    if dias < 30 or pnl_frac <= -1.0 + 1e-12:
        return None
    try:
        ann = (math.exp(math.log1p(float(pnl_frac)) * (365.0 / float(dias))) - 1.0) * 100.0
    except (ValueError, OverflowError):
        return None
    # Guardrail de legibilidad: fuera de rango razonable se oculta.
    if not math.isfinite(ann) or abs(ann) > 9999.0:
        return None
    return ann


def _fecha_primera_compra_desde_fila(r: pd.Series) -> date | None:
    """Primera compra utilizable (FIFO agregado o última fila CSV)."""
    _fpc = r.get("FECHA_PRIMERA_COMPRA")
    if _fpc is None or (isinstance(_fpc, float) and pd.isna(_fpc)):
        _fpc = r.get("FECHA_COMPRA")
    if _fpc is None or (isinstance(_fpc, float) and pd.isna(_fpc)):
        return None
    try:
        if hasattr(_fpc, "date") and callable(getattr(_fpc, "date", None)):
            return _fpc.date()  # type: ignore[union-attr]
        _dt = pd.to_datetime(str(_fpc), errors="coerce")
        return _dt.date() if pd.notna(_dt) else None
    except Exception:
        return None


_NEED_COLS = (
    "TICKER",
    "CANTIDAD_TOTAL",
    "PRECIO_ARS",
    "PESO_PCT",
    "PPC_ARS",
    "VALOR_ARS",
    "INV_ARS",
    "PNL_ARS",
    "PNL_PCT",
    "PNL_PCT_USD",
)

_NUMERIC_COLS = tuple(c for c in _NEED_COLS if c != "TICKER")


def build_posiciones_broker_html(
    df_ag: pd.DataFrame,
    metricas: dict | None = None,
    *,
    hint_text: str | None = None,
    group_rf_rv: bool = True,
) -> str | None:
    """
    Devuelve HTML completo (hint + wrap + table) o None si faltan columnas.
    """
    if df_ag is None or df_ag.empty:
        return None
    if not all(c in df_ag.columns for c in _NEED_COLS):
        return None

    df = df_ag
    _cols = list(_NEED_COLS)
    for _opt in ("TIPO", "ES_LOCAL", "FECHA_PRIMERA_COMPRA", "FECHA_COMPRA"):
        if _opt in df.columns and _opt not in _cols:
            _cols.append(_opt)
    work = df[_cols].copy()
    # Nunca forzar TICKER a numérico (rompe símbolos → 0.0).
    for c in _NUMERIC_COLS:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["TICKER"] = work["TICKER"].astype(str).str.strip().str.upper()

    if group_rf_rv:

        def _grp(row: pd.Series) -> tuple[int, str]:
            if es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
                return (0, "Renta fija")
            return (1, "Renta variable y CEDEARs")

        g = work.apply(_grp, axis=1, result_type="expand")
        work["_gk"] = g[0]
        work["_glabel"] = g[1]
        work = work.sort_values(["_gk", "PESO_PCT"], ascending=[True, False])
    else:
        work["_gk"] = 0
        work["_glabel"] = ""
        work = work.sort_values("PESO_PCT", ascending=False)

    total_v = float(work["VALOR_ARS"].sum())
    total_i = float(work["INV_ARS"].sum())
    total_pnl = float(work["PNL_ARS"].sum())
    pnl_pct_tot = (total_pnl / total_i) if total_i > 1e-9 else 0.0

    hoy = date.today()
    show_hold_metrics = any(
        _fecha_primera_compra_desde_fila(r) is not None for _, r in work.iterrows()
    )
    ncols = 13 if show_hold_metrics else 10
    foot_label_span = 8 if show_hold_metrics else 5
    th = (
        "<th class='mq-pos-col-ticker'>Ticker</th>"
        + (
            "<th>1ª compra</th>"
            "<th>Días</th>"
            "<th>Tasa anual posición*</th>"
            if show_hold_metrics
            else ""
        )
        + "<th>Cantidad</th>"
        "<th>Precio ARS</th>"
        "<th>% tenencia</th>"
        "<th>PPC prom.</th>"
        "<th>Valor actual</th>"
        "<th>Costo (inicial)</th>"
        "<th class='mq-pos-col-pnl'>Resultado</th>"
        "<th>% resultado</th>"
        "<th>% rend. USD</th>"
    )

    body_parts: list[str] = []
    prev_gk: int | None = None
    for _, r in work.iterrows():
        gk = int(r["_gk"])
        if group_rf_rv and gk != prev_gk:
            prev_gk = gk
            glabel = html_module.escape(str(r["_glabel"]))
            body_parts.append(
                f"<tr class='mq-pos-group'><td colspan='{ncols}'>{glabel}</td></tr>"
            )

        tk = html_module.escape(str(r["TICKER"]).strip().upper())
        cant = float(r["CANTIDAD_TOTAL"])
        px = float(r["PRECIO_ARS"])
        peso = float(r["PESO_PCT"]) * 100.0
        ppc = float(r["PPC_ARS"])
        va = float(r["VALOR_ARS"])
        inv = float(r["INV_ARS"])
        pnl = float(r["PNL_ARS"])
        pp = float(r["PNL_PCT"]) * 100.0
        pup = float(r["PNL_PCT_USD"]) * 100.0
        pnl_frac = float(r["PNL_PCT"])

        hold_cells = ""
        if show_hold_metrics:
            fecha_d = _fecha_primera_compra_desde_fila(r)
            if fecha_d is None:
                fecha_txt = "—"
                dias_disp = "—"
                ann_txt = "—"
                ann_cls = "mq-pos-pnl-neu"
            else:
                fecha_txt = html_module.escape(fecha_d.strftime("%d/%m/%Y"))
                dias = max(1, (hoy - fecha_d).days)
                dias_disp = str(int(dias))
                ann = _annual_total_return_pct(pnl_frac, dias)
                if ann is None:
                    ann_txt = "—"
                    ann_cls = "mq-pos-pnl-neu"
                else:
                    sign_a = "+" if ann > 0 else ""
                    ann_txt = html_module.escape(sign_a + fmt_decimal_ar(ann, 1))
                    ann_cls = pnl_css_class(ann)
            hold_cells = (
                f"<td class='mq-pos-num'>{fecha_txt}</td>"
                f"<td class='mq-pos-num'>{html_module.escape(dias_disp)}</td>"
                f"<td class='mq-pos-num'><span class='{ann_cls}'>{ann_txt}</span></td>"
            )

        sign_m = "+" if pnl > 0 else ""
        sign_p = "+" if pp > 0 else ""
        sign_u = "+" if pup > 0 else ""

        pnl_cls = pnl_css_class(pnl)
        body_parts.append(
            "<tr>"
            f"<td class='mq-pos-ticker'><strong>{tk}</strong></td>"
            f"{hold_cells}"
            f"<td class='mq-pos-num'>{html_module.escape(fmt_decimal_ar(cant, 2))}</td>"
            f"<td class='mq-pos-num'>{html_module.escape(fmt_decimal_ar(px, 2))}</td>"
            f"<td class='mq-pos-num'>{html_module.escape(fmt_decimal_ar(peso, 1))}</td>"
            f"<td class='mq-pos-num'>{html_module.escape(fmt_decimal_ar(ppc, 2))}</td>"
            f"<td class='mq-pos-num'>$ {html_module.escape(fmt_enteros_ar(va))}</td>"
            f"<td class='mq-pos-num'>$ {html_module.escape(fmt_enteros_ar(inv))}</td>"
            f"<td class='mq-pos-num mq-pos-pnl-cell'><span class='{pnl_cls}'>"
            f"$ {html_module.escape(sign_m + fmt_enteros_ar(pnl))}</span></td>"
            f"<td class='mq-pos-num'><span class='{pnl_css_class(pp)}'>"
            f"{html_module.escape(sign_p + fmt_decimal_ar(pp, 1))}</span></td>"
            f"<td class='mq-pos-num'><span class='{pnl_css_class(pup)}'>"
            f"{html_module.escape(sign_u + fmt_decimal_ar(pup, 1))}</span></td>"
            "</tr>"
        )

    sign_tp = "+" if total_pnl > 0 else ""
    sign_tpp = "+" if pnl_pct_tot > 0 else ""
    _m = metricas or {}
    _foot_papel = "—"
    if isinstance(_m, dict) and "pnl_pct_total_usd" in _m:
        _pap = float(_m.get("pnl_pct_total_usd", 0.0) or 0.0) * 100.0
        _sp = "+" if _pap > 0 else ""
        _foot_papel = (
            f"<strong><span class='{pnl_css_class(_pap)}'>"
            f"{html_module.escape(_sp + fmt_decimal_ar(_pap, 1))}</span></strong>"
        )

    # Primera columna de importes = "Valor actual" (tras Ticker + opc. 1ª compra/Días/Tasa + 5 cols)
    foot = (
        "<tfoot><tr class='mq-pos-totals'>"
        f"<td colspan='{foot_label_span}'><strong>Totales (ARS)</strong></td>"
        f"<td class='mq-pos-num'><strong>$ {html_module.escape(fmt_enteros_ar(total_v))}</strong></td>"
        f"<td class='mq-pos-num'><strong>$ {html_module.escape(fmt_enteros_ar(total_i))}</strong></td>"
        f"<td class='mq-pos-num mq-pos-pnl-cell'><strong><span class='{pnl_css_class(total_pnl)}'>"
        f"$ {html_module.escape(sign_tp + fmt_enteros_ar(total_pnl))}</span></strong></td>"
        f"<td class='mq-pos-num'><strong><span class='{pnl_css_class(pnl_pct_tot * 100.0)}'>"
        f"{html_module.escape(sign_tpp + fmt_decimal_ar(pnl_pct_tot * 100.0, 1))}</span></strong></td>"
        f"<td class='mq-pos-num'>{_foot_papel}</td>"
        "</tr></tfoot>"
    )

    _hint = (
        hint_text
        if hint_text is not None
        else "Valores en pesos — último precio cargado en MQ26."
    )
    if show_hold_metrics:
        _note_static = (
            "<strong>Tasa anual posición*</strong> (estim.): tasa compuesta anual que iguala tu "
            "<em>% resultado</em> y los días desde la primera compra registrada. "
            "<strong>No es</strong> el simulador de jubilación ni tu “año de retiro”: la proyección de retiro está en "
            "<em>Plan y simulaciones</em>. "
            "<strong>% rend. USD:</strong> rendimiento sobre la base en moneda del certificado "
            "(USD × CCL) o, en locales, el costo en ARS comparable; refleja la pata dólar del resultado. "
            "<em>% resultado</em> sigue siendo sobre costo histórico en pesos (CCL de la época de compra si hay fechas)."
        )
    else:
        _note_static = (
            "<strong>1ª compra / días / tasa anual</strong> no se muestran: hace falta al menos una "
            "<strong>FECHA_COMPRA</strong> (o primera compra agregada) en el CSV de operaciones para estimar "
            "días en cartera y anualizar el retorno. "
            "<strong>% rend. USD</strong> y <strong>% resultado</strong> siguen disponibles sin esa fecha. "
            "<em>% resultado</em>: costo histórico en pesos; <strong>% rend. USD</strong>: base USD×CCL del certificado."
        )
    return (
        f"<div class='mq-broker-pos-hint'>{html_module.escape(_hint)}</div>"
        f"<div class='mq-broker-pos-hint' style='font-size:0.7rem;margin-top:0.15rem;line-height:1.35;'>"
        f"{_note_static}</div>"
        "<div class='mq-broker-pos-wrap'>"
        "<table class='mq-broker-pos'><thead><tr>"
        f"{th}</tr></thead><tbody>{''.join(body_parts)}</tbody>{foot}</table>"
        "</div>"
    )
