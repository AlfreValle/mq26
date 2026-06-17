"""
core/renta_fija_monitor.py — monitor de ONs USD y cashflow ilustrativo.

Extraído de core/renta_fija_ar.py (Fase 2.1, segundo slice): panel de
monitoreo hard-dollar (buckets de riesgo, paridades, TIR), calendario de
cupones, cashflow ilustrativo por 100 VN y vencimientos por mes.
renta_fija_ar re-exporta todo para compatibilidad.

Convenciones (idénticas al catálogo): paridad_ref = % sobre VN USD;
cashflow ILUSTRATIVO — no es asesoramiento ni promesa de pago.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from core.renta_fija_catalogo import INSTRUMENTOS_RF, ON_USD_PARIDAD_BASE_VN

_CALIF_RANK: dict[str, int] = {
    "AAA": 100, "AA+": 95, "AA": 90, "AA-": 85, "A+": 82, "A": 78, "A-": 75,
    "BBB+": 55, "BBB": 50, "BBB-": 48, "BB+": 40, "CCC+": 25, "CCC": 10,
}

MONITOR_ON_USD_DISCLAIMER = (
    "Todas las ON USD del catálogo usan la misma convención: paridad en % sobre nominal USD; "
    "el precio en pesos por cada 100 nominales USD ≈ paridad_% × CCL. "
    "Referencia educativa (paridad, TIR y cupón por instrumento). "
    "No reemplaza cotizaciones BYMA, láminas oficiales ni informes de custodio."
)


def bucket_riesgo_on_hd(meta: dict[str, Any]) -> str:
    """
    Banda tipo monitor HD: calificación (riesgo crédito) + TIR de referencia.
    Conservador: AA- o mejor y TIR ref. moderada (hasta 7,6 %).
    Agresivo: rating por debajo de BBB+ o TIR alta (más de 8,5 %).
    Moderado: casos intermedios.
    """
    try:
        tir = float(meta.get("tir_ref") or 0.0)
    except (TypeError, ValueError):
        tir = 0.0
    r = _calif_rank(str(meta.get("calificacion", "")))
    if r >= 85 and tir <= 7.6:
        return "conservador"
    if tir > 8.5 or r < 55:
        return "agresivo"
    return "moderado"


def _frecuencia_cupon_label(meta: dict[str, Any]) -> str:
    try:
        n = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 4:
        return "Trimestral"
    if n == 2:
        return "Semestral"
    if n == 1:
        return "Anual"
    if n <= 0:
        return "Al vencimiento"
    return str(n)


def monitor_on_usd_panel_df(
    byma_live: dict[str, dict[str, Any]] | None = None,
    *,
    ccl: float | None = None,
) -> pd.DataFrame:
    """
    Tabla tipo monitor ON en dólares (Hard Dollar / cable).
    Columnas alineadas a paneles de mercado; campos faltantes en metadatos → "—".

    Args:
        byma_live: dict opcional {ticker: {paridad_ref, var_diaria_pct, precio_ars,
                   fecha_ref, fuente, escala_div100}} proveniente de services.byma_market_data.
                   Cuando se provee, los campos de precio se actualizan con datos en vivo.
                   ``escala_div100`` indica si se aplicó heurística ÷100 al último/cierre (P2-RF-04).
    """
    _byma: dict[str, dict[str, Any]] = byma_live if byma_live else {}

    rows: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue

        # ── Datos de BYMA en vivo (tienen prioridad sobre metadatos estáticos) ──
        live = _byma.get(ticker.upper(), {})
        es_live = bool(live)

        try:
            paridad = float(live.get("paridad_ref") or meta.get("paridad_ref") or 0.0)
        except (TypeError, ValueError):
            paridad = 0.0
        try:
            tir = float(meta.get("tir_ref") or 0.0)
        except (TypeError, ValueError):
            tir = 0.0
        try:
            cupon = float(meta.get("cupon_anual") or 0.0) * 100.0
        except (TypeError, ValueError):
            cupon = 0.0

        # Variación diaria: BYMA primero, luego metadatos estáticos
        var_dia_raw = live.get("var_diaria_pct") if es_live else meta.get("var_diaria_pct")
        try:
            var_dia = round(float(var_dia_raw), 2) if var_dia_raw is not None else None
        except (TypeError, ValueError):
            var_dia = None

        # Precio en ARS (solo disponible vía BYMA)
        precio_ars_raw = live.get("precio_ars") if es_live else None
        try:
            precio_ars = round(float(precio_ars_raw), 2) if precio_ars_raw is not None else None
        except (TypeError, ValueError):
            precio_ars = None

        ven_raw = meta.get("vencimiento", "")
        ven_s = str(ven_raw)[:10] if ven_raw else "—"
        lamina = meta.get("lamina_min")
        if lamina is None:
            lamina = meta.get("lamina_vn")
        try:
            lamina_i = int(lamina) if lamina is not None else 1_000
        except (TypeError, ValueError):
            lamina_i = 1_000
        call_raw = meta.get("callable")
        if call_raw is None:
            callable_txt = "—"
        else:
            callable_txt = "Sí" if bool(call_raw) else "No"

        fecha_dato = (
            str(live.get("fecha_ref", ""))[:16]
            if es_live
            else str(meta.get("fecha_ref") or "—")[:10]
        )

        escala_div100 = bool(live.get("escala_div100")) if es_live else False

        ars_100_vn: float | None = None
        try:
            ccl_f = float(ccl) if ccl is not None else 0.0
        except (TypeError, ValueError):
            ccl_f = 0.0
        if paridad and ccl_f > 0:
            from core.renta_fija_ar import precio_ars_on_usd_por_base_vn

            ars_100_vn = round(
                precio_ars_on_usd_por_base_vn(paridad, ccl_f, vn_usd=ON_USD_PARIDAD_BASE_VN),
                2,
            )

        # ── Días al vencimiento + alerta próximo vto ─────────────────────────
        dias_al_vto: int | None = None
        alerta_vto = ""
        try:
            vcto_d = date.fromisoformat(str(ven_raw)[:10])
            dias_al_vto = (vcto_d - date.today()).days
            if dias_al_vto <= 35:
                alerta_vto = "🔴 ≤35d"
            elif dias_al_vto <= 90:
                alerta_vto = "🟡 ≤90d"
        except (ValueError, TypeError):
            dias_al_vto = None

        rows.append({
            "Banda":           bucket_riesgo_on_hd(meta),
            "Ticker":          ticker,
            "Emisor":          str(meta.get("emisor") or "—"),
            "Tipo":            "Hard Dollar",
            "Paridad %":       round(paridad, 2) if paridad else None,
            f"ARS / {int(ON_USD_PARIDAD_BASE_VN)} VN USD": ars_100_vn,
            "Precio ARS":      precio_ars,
            "Var. % día":      var_dia,
            "Cupón %":         round(cupon, 2),
            "TIR ref. %":      round(tir, 2),
            "MD":              meta.get("modified_duration", "—"),
            "Vencimiento":     ven_s,
            "Días al vto.":    dias_al_vto,
            "⚠️ Próx. vto.":   alerta_vto,
            "Moneda":          "CABLE",
            "Amortización":    str(meta.get("amortizacion") or "Bullet"),
            "Callable":        callable_txt,
            "Calificación":    str(meta.get("calificacion") or "—"),
            "Lámina mín.":     lamina_i,
            "ISIN":            str(meta.get("isin") or "—"),
            "Frecuencia cupón":_frecuencia_cupon_label(meta),
            "Ley":             str(meta.get("ley") or "—"),
            "Fecha dato":      fecha_dato,
            "Fuente":          "🟢 BYMA en vivo" if es_live else "📋 Catálogo",
            # P2-RF-04 — Sí = último/cierre BYMA normalizado ÷100 (feed en escala ×100)
            "Ajuste ×100 BYMA": "Sí" if escala_div100 else ("No" if es_live else "—"),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    _order = {"conservador": 0, "moderado": 1, "agresivo": 2}
    df["_sort_banda"] = df["Banda"].map(lambda b: _order.get(str(b), 9))
    df = df.sort_values(["_sort_banda", "TIR ref. %"], ascending=[True, False]).drop(
        columns=["_sort_banda"]
    )
    return df.reset_index(drop=True)


_MESES_ES_VTO = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF = (
    "Importes **por cada 100 unidades de valor nominal (VN)** en la **moneda de emisión** del catálogo. "
    "Las fechas se **aproximan** desde la fecha de vencimiento y la frecuencia de cupón de los metadatos "
    "internos (no desde el prospecto). **No** es un calendario legal de pagos: no sustituye prospecto, "
    "suplementos ni comunicación del emisor. Se asume cupón fijo y amortización **bullet** al vencimiento, "
    "sin impuestos ni comisiones."
)


def fecha_vencimiento_desde_meta(meta: dict[str, Any] | None) -> date | None:
    """Parsea `vencimiento` (YYYY-MM-DD u otras formas pandas) a `date`."""
    if not meta:
        return None
    ven_raw = meta.get("vencimiento")
    ts = pd.to_datetime(ven_raw, errors="coerce")
    if pd.isna(ts):
        return None
    d = ts.date()
    return d if isinstance(d, date) else None


def _meses_entre_cupones(frecuencia: int) -> int:
    """Meses entre fechas de pago aproximadas (1=año, 2=semestre, 4=trimestre)."""
    try:
        f = int(frecuencia)
    except (TypeError, ValueError):
        f = 0
    if f <= 0:
        return 12
    if f == 1:
        return 12
    if f == 2:
        return 6
    if f >= 4:
        return 3
    return max(1, 12 // f)


def cashflow_ilustrativo_por_100_vn(
    meta: dict[str, Any] | None,
    *,
    hoy: date | None = None,
    max_filas: int = 60,
    solo_futuros: bool = True,
) -> dict[str, Any]:
    """
    P2-RF-02: cashflow **ilustrativo** en base 100 VN y moneda de emisión.

    Calendario aproximado (hacia atrás desde el vencimiento con paso fijo según frecuencia).
    Cupón cero: un solo flujo al vencimiento con amortización del nominal.
    """
    from dateutil.relativedelta import relativedelta

    base = 100.0
    hoy_d = hoy or date.today()
    out: dict[str, Any] = {
        "ok": False,
        "base_vn": base,
        "moneda_emision": "",
        "disclaimer": DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF,
        "filas": [],
        "aviso": "",
    }
    if not meta:
        out["aviso"] = "Sin metadatos de instrumento."
        return out

    vm = fecha_vencimiento_desde_meta(meta)
    if vm is None:
        out["aviso"] = "Sin fecha de vencimiento parseable."
        return out

    moneda = str(meta.get("moneda") or "USD").strip()[:12] or "USD"
    out["moneda_emision"] = moneda

    try:
        cupon_anual = float(meta.get("cupon_anual") or 0.0)
    except (TypeError, ValueError):
        cupon_anual = 0.0
    try:
        freq = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        freq = 0

    if cupon_anual <= 1e-15:
        fila = {
            "fecha": vm.isoformat(),
            "concepto": "Amortización nominal al vencimiento (ilustrativo, sin cupones)",
            "monto_100vn": round(base, 4),
            "moneda": moneda,
        }
        if solo_futuros and vm < hoy_d:
            out["ok"] = True
            out["aviso"] = "Vencimiento ya ocurrió: no hay flujos futuros ilustrativos."
            out["filas"] = []
            return out
        out["ok"] = True
        out["filas"] = [fila]
        return out

    if freq <= 0:
        freq = 2

    meses = _meses_entre_cupones(freq)
    cupon_por_periodo = base * (cupon_anual / float(freq))

    fechas_rev: list[date] = []
    d = vm
    for _ in range(max(4, max_filas)):
        fechas_rev.append(d)
        d = d - relativedelta(months=meses)
        if len(fechas_rev) >= max_filas:
            break

    fechas = sorted(set(fechas_rev))
    if solo_futuros:
        fechas = [x for x in fechas if x >= hoy_d]
    fechas = [x for x in fechas if x <= vm]
    fechas.sort()

    if not fechas:
        out["ok"] = True
        out["aviso"] = "Sin fechas de pago ilustrativas en el rango (revisá vencimiento vs. hoy)."
        out["filas"] = []
        return out

    filas: list[dict[str, Any]] = []
    for fd in fechas:
        es_vto = fd == vm
        if es_vto:
            monto = cupon_por_periodo + base
            concepto = "Cupón + amortización VN (ilustrativo)"
        else:
            monto = cupon_por_periodo
            concepto = "Cupón (ilustrativo)"
        filas.append({
            "fecha": fd.isoformat(),
            "concepto": concepto,
            "monto_100vn": round(monto, 4),
            "moneda": moneda,
        })

    out["ok"] = True
    out["filas"] = filas
    return out


def _meses_calendario_pago_cupon(meta: dict[str, Any], fecha_vto: date) -> tuple[set[int], str]:
    """
    Meses del año (1–12) en que habitualmente hay pago de cupón, según frecuencia y fecha de vencimiento
    del catálogo (convención estándar: calendario alineado al último cupón en la fecha de vto).

    - Sin cupón periódico / al vencimiento: solo el mes del vencimiento (devolución de principal).
    - Semestral: mes del vto y mes opuesto (+6).
    - Trimestral: mes del vto y cada -3 meses (4 fechas/año).
    - Anual: solo mes del vto.
    """
    if not isinstance(fecha_vto, date):
        return set(), ""
    m = int(fecha_vto.month)
    try:
        cup = float(meta.get("cupon_anual") or 0.0)
    except (TypeError, ValueError):
        cup = 0.0
    try:
        freq = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        freq = 0

    if cup <= 1e-12 or freq <= 0:
        s = {m}
        note = f"{_MESES_ES_VTO[m - 1].title()} (solo principal al venc.)"
        return s, note

    if freq == 1:
        s = {m}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    if freq == 2:
        o = ((m - 1 + 6) % 12) + 1
        s = {m, o}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    if freq >= 4:
        s = {((m - 1 - 3 * k) % 12) + 1 for k in range(4)}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    s = {m}
    note = _MESES_ES_VTO[m - 1].title()
    return s, note


def monitor_on_usd_vencimientos_por_mes_df() -> pd.DataFrame:
    """
    ON USD activas del catálogo: **calendario por mes de pago de cupón** (enero…diciembre).

    Cada fila es un (ticker, mes calendario): una misma ON puede repetirse en varios meses si paga
    varias veces al año. Referencia educativa: fechas inferidas desde vencimiento + frecuencia del catálogo.
    """
    rows: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue
        ven_raw = meta.get("vencimiento")
        ts = pd.to_datetime(ven_raw, errors="coerce")
        if pd.isna(ts):
            continue
        d = ts.date()
        if not isinstance(d, date):
            continue
        meses_cup, cal_label = _meses_calendario_pago_cupon(meta, d)
        lamina = meta.get("lamina_min")
        if lamina is None:
            lamina = meta.get("lamina_vn")
        try:
            lamina_i = int(lamina) if lamina is not None else 1_000
        except (TypeError, ValueError):
            lamina_i = 1_000
        try:
            tir = float(meta.get("tir_ref") or 0.0)
        except (TypeError, ValueError):
            tir = 0.0
        try:
            cupon = float(meta.get("cupon_anual") or 0.0) * 100.0
        except (TypeError, ValueError):
            cupon = 0.0
        ven_str = d.strftime("%d/%m/%Y")
        frec_lbl = _frecuencia_cupon_label(meta)
        emisor = str(meta.get("emisor") or "—")

        for mes_ord in sorted(meses_cup):
            mes_lab = _MESES_ES_VTO[mes_ord - 1].title()
            rows.append({
                "_mes_ord": mes_ord,
                "_vto_key": d.year * 10_000 + d.month * 100 + d.day,
                "Mes": mes_lab,
                "Vencimiento": ven_str,
                "Ticker": ticker,
                "Emisor": emisor,
                "TIR ref. %": round(tir, 2),
                "Cupón %": round(cupon, 2),
                "Frec. cupón": frec_lbl,
                "Pagos en el año (cupón)": cal_label,
                "Lámina mín.": lamina_i,
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values(["_mes_ord", "_vto_key", "Ticker"], ascending=[True, True, True]).reset_index(
        drop=True
    )
    return df.drop(columns=["_mes_ord", "_vto_key"])


def _calif_rank(cal: str) -> int:
    return _CALIF_RANK.get(str(cal or "").strip().upper(), 0)


