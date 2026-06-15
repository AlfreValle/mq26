"""
services/primera_cartera.py — Motor "Mi Primera Cartera" (selección, narrativa, persistencia).
Sin dependencias de Streamlit.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from config import RATIOS_CEDEAR
from core import db_manager as dbm
from core.pricing_utils import precio_cedear_ars
from sqlalchemy import text

logger = logging.getLogger(__name__)

CLAVE_ACTIVA = "primera_cartera_activa"

# Presupuesto semanal orientativo (ARS); variación suave por semana ISO
PRESUPUESTO_MIN_ARS = 75_000.0
PRESUPUESTO_MAX_ARS = 100_000.0

DISCLAIMER = (
    "Este documento es educativo y no constituye recomendación personalizada de inversión, "
    "oferta pública ni asesoramiento financiero. Los mercados involucran riesgo de pérdida de capital. "
    "Consultá con un asesor calificado antes de invertir."
)

# Categorías para diversificación (>1 activo por categoría solo si faltan alternativas).
UNIVERSO_PRIMERA_CARTERA: list[dict[str, str]] = [
    {"ticker": "AAPL", "tipo": "CEDEAR", "categoria": "tech"},
    {"ticker": "MSFT", "tipo": "CEDEAR", "categoria": "tech"},
    {"ticker": "KO", "tipo": "CEDEAR", "categoria": "consumo"},
    {"ticker": "PEP", "tipo": "CEDEAR", "categoria": "consumo"},
    {"ticker": "BRKB", "tipo": "CEDEAR", "categoria": "valor"},
    {"ticker": "SPY", "tipo": "CEDEAR", "categoria": "indice"},
    {"ticker": "QQQ", "tipo": "CEDEAR", "categoria": "indice"},
    {"ticker": "VALE", "tipo": "CEDEAR", "categoria": "materiales"},
    {"ticker": "V", "tipo": "CEDEAR", "categoria": "financiero"},
    {"ticker": "MELI", "tipo": "CEDEAR", "categoria": "ecommerce"},
    {"ticker": "YPFD", "tipo": "Acción Local", "categoria": "energia_ar"},
    {"ticker": "CEPU", "tipo": "Acción Local", "categoria": "energia_ar"},
    {"ticker": "PAMP", "tipo": "Acción Local", "categoria": "energia_ar"},
]


def numero_semana_del_año(d: date | None = None) -> int:
    d = d or date.today()
    return int(d.isocalendar()[1])


def presupuesto_semana(week: int | None = None) -> float:
    """ARS objetivo de la semana entre PRESUPUESTO_MIN_ARS y PRESUPUESTO_MAX_ARS."""
    if week is None:
        week = numero_semana_del_año()
    span = PRESUPUESTO_MAX_ARS - PRESUPUESTO_MIN_ARS
    paso = span / 5.0
    return round(PRESUPUESTO_MIN_ARS + (week % 6) * paso, 2)


def _ticker_yahoo_symbol(ticker: str, tipo: str) -> str:
    from services.scoring_engine import _ticker_yahoo

    return _ticker_yahoo(ticker, tipo)


def _precio_ars_actual(ticker: str, tipo: str, ccl: float) -> float:
    """Último Close en ARS: CEDEAR vía subyacente USD + ratio + CCL; local .BA en ARS."""
    try:
        import yfinance as yf

        sym = _ticker_yahoo_symbol(ticker, tipo)
        hist = yf.Ticker(sym).history(period="7d")
        if hist.empty or "Close" not in hist.columns:
            return 0.0
        close = float(hist["Close"].dropna().iloc[-1])
        if tipo in ("Acción Local", "Merval"):
            return round(close, 2)
        ratio = float(RATIOS_CEDEAR.get(ticker.upper(), 1) or 1)
        return precio_cedear_ars(close, ratio, ccl)
    except Exception as e:
        logger.debug("_precio_ars_actual %s: %s", ticker, e)
        return 0.0


def _variacion_30d(ticker: str, tipo: str) -> float:
    try:
        import yfinance as yf

        sym = _ticker_yahoo_symbol(ticker, tipo)
        hist = yf.Ticker(sym).history(period="45d")
        if hist.empty or "Close" not in hist.columns or len(hist) < 2:
            return 0.0
        series = hist["Close"].dropna()
        c0 = float(series.iloc[0])
        c1 = float(series.iloc[-1])
        if c0 <= 0:
            return 0.0
        return round(100.0 * (c1 - c0) / c0, 2)
    except Exception:
        return 0.0


def seleccionar_recomendaciones(
    ccl: float,
    n: int = 3,
    min_score: float = 45.0,
) -> list[dict[str, Any]]:
    """
    Rankea por Score_Total y diversifica por `categoria`; completá slots por score.
    """
    from services.scoring_engine import calcular_score_total

    ranked: list[dict[str, Any]] = []
    for row in UNIVERSO_PRIMERA_CARTERA:
        ticker = row["ticker"]
        tipo = row["tipo"]
        cat = row["categoria"]
        try:
            sc = calcular_score_total(ticker, tipo)
        except Exception as e:
            logger.debug("score %s: %s", ticker, e)
            continue
        st = float(sc.get("Score_Total") or 0)
        if st < min_score:
            continue
        precio = _precio_ars_actual(ticker, tipo, float(ccl or 0))
        var30 = _variacion_30d(ticker, tipo)
        ranked.append({
            "ticker": ticker,
            "tipo": tipo,
            "categoria": cat,
            "score": sc,
            "score_total": st,
            "precio_ars": precio,
            "variacion_30d_pct": var30,
            "sector": str(sc.get("Sector") or ""),
        })

    ranked.sort(key=lambda x: x["score_total"], reverse=True)
    tickers_elegidos: set[str] = set()
    cats_usadas: set[str] = set()
    seleccionados: list[dict[str, Any]] = []

    for cand in ranked:
        if len(seleccionados) >= n:
            break
        t = cand["ticker"]
        cat = cand["categoria"]
        if t in tickers_elegidos:
            continue
        if cat in cats_usadas:
            continue
        seleccionados.append(cand)
        tickers_elegidos.add(t)
        cats_usadas.add(cat)

    for cand in ranked:
        if len(seleccionados) >= n:
            break
        t = cand["ticker"]
        if t in tickers_elegidos:
            continue
        seleccionados.append(cand)
        tickers_elegidos.add(t)

    return seleccionados[:n]


def calcular_unidades(presupuesto_ars: float, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reparto equitativo del presupuesto; unidades enteras mínimo 0."""
    if not items:
        return []
    por_activo = float(presupuesto_ars) / len(items)
    out: list[dict[str, Any]] = []
    for it in items:
        row = dict(it)
        px = float(row.get("precio_ars") or 0)
        if px > 0:
            row["unidades"] = max(0, int(por_activo / px))
        else:
            row["unidades"] = 0
        row["subtotal_ars"] = round(row["unidades"] * px, 2)
        out.append(row)
    return out


def _rsi_texto(rsi: float) -> str:
    if rsi < 35:
        return f"RSI en zona de posible valor técnico ({rsi:.0f})."
    if rsi > 65:
        return f"RSI elevado ({rsi:.0f}); entrada más exigente en tiempo."
    return f"RSI en rango neutral ({rsi:.0f})."


def _var_texto(var_pct: float) -> str:
    if var_pct > 0:
        return f"Subió {var_pct:.1f}% aprox. en los últimos 30 días cotizados."
    if var_pct < 0:
        return f"Cayó {abs(var_pct):.1f}% aprox. en los últimos 30 días; puede interesar acumulación gradual."
    return "Variación reciente próxima a cero o dato no disponible."


def generar_narrativa_semana(
    items_con_unidades: list[dict[str, Any]],
    presupuesto_ars: float,
    ccl: float,
    nota_admin: str = "",
    fecha: date | None = None,
) -> dict[str, Any]:
    fecha = fecha or date.today()
    sem = numero_semana_del_año(fecha)
    anio = fecha.year
    bloques = []
    narr_items = []
    for it in items_con_unidades:
        sc = it.get("score") or {}
        rsi = float(sc.get("RSI") or 50)
        var_pct = float(it.get("variacion_30d_pct") or 0)
        var_txt = _var_texto(var_pct)
        rsi_txt = _rsi_texto(rsi)
        senal = str(sc.get("Senal") or "")
        nombre = str(it.get("ticker") or "")

        # Fundamentals + objetivo de salida + tesis
        fund: dict[str, Any] = {}
        tesis = ""
        try:
            fund = _ficha_fundamentals(nombre, it.get("tipo", "CEDEAR"), ccl)
            tesis = _tesis_inversion(nombre, it.get("tipo", "CEDEAR"), sc, fund)
        except Exception as e:
            logger.debug("fundamentals %s: %s", nombre, e)

        narr_items.append({
            **it,
            "var_txt":       var_txt,
            "rsi_txt":       rsi_txt,
            "senal":         senal,
            "nombre_display": nombre,
            "fundamentals":  fund,
            "tesis":         tesis,
        })
        bloques.append(
            f"{nombre} ({it.get('tipo')}): puntuación {it.get('score_total'):.0f}, {var_txt} {rsi_txt}"
        )

    intro = (
        f"Semana {sem} de {anio}: presupuesto orientativo ${presupuesto_ars:,.0f} ARS "
        f"(CCL referencia ${float(ccl):,.0f}). "
        "Se priorizó diversificar entre categorías y el score interno MQ26."
    )
    resumen = intro + "\n\n" + "\n".join(bloques)
    if (nota_admin or "").strip():
        resumen += "\n\nNota del equipo: " + nota_admin.strip()
    return {
        "anio": anio,
        "semana": sem,
        "fecha_generacion": fecha.isoformat(),
        "presupuesto_ars": presupuesto_ars,
        "ccl": float(ccl),
        "nota": (nota_admin or "").strip(),
        "items": narr_items,
        "resumen_ejecutivo": resumen,
        "disclaimer": DISCLAIMER,
    }


# ─── Fundamentales y objetivo de salida ──────────────────────────────────────

def _ficha_fundamentals(
    ticker: str,
    tipo: str,
    ccl: float,
) -> dict[str, Any]:
    """
    Trae métricas fundamentales vía yfinance y calcula precio objetivo ARS.

    Retorna dict con todas las métricas (None si no disponibles) más:
      objetivo_salida_usd, objetivo_salida_ars, upside_pct, horizonte_meses,
      fuente_objetivo ("consenso_analistas" | "proyeccion_eps" | "n/a").
    """
    import yfinance as yf  # noqa: PLC0415

    sym = _ticker_yahoo_symbol(ticker, tipo)
    ratio = float(RATIOS_CEDEAR.get(ticker.upper(), 1) or 1)
    info: dict[str, Any] = {}
    try:
        info = yf.Ticker(sym).info or {}
    except Exception as e:
        logger.debug("_ficha_fundamentals %s: %s", ticker, e)

    def _f(key: str, mult: float = 1.0) -> float | None:
        v = info.get(key)
        if v is None or (isinstance(v, float) and (v != v)):  # NaN guard
            return None
        try:
            return round(float(v) * mult, 4)
        except Exception:
            return None

    pe       = _f("trailingPE") or _f("forwardPE")
    roe      = _f("returnOnEquity", 100)       # → %
    dce      = _f("debtToEquity")              # 0–∞, ya en %
    div_y    = _f("dividendYield", 100)        # → %
    eps_g    = _f("earningsGrowth", 100)       # → %
    rev_g    = _f("revenueGrowth", 100)        # → %
    margin   = _f("profitMargins", 100)        # → %
    beta     = _f("beta")
    mkt_cap  = info.get("marketCap")           # USD
    target_c = info.get("targetMeanPrice")     # USD — consenso analistas
    n_anal   = info.get("numberOfAnalystOpinions") or 0
    curr_usd = info.get("regularMarketPrice") or info.get("currentPrice")
    sector_yf = info.get("sector") or info.get("industry") or ""

    # ── Precio objetivo ARS ───────────────────────────────────────────────────
    obj_usd: float | None = None
    fuente_obj = "n/a"
    horizonte = 12  # meses default

    if target_c and curr_usd and float(target_c) > 0 and int(n_anal) >= 3:
        obj_usd = round(float(target_c), 2)
        fuente_obj = f"consenso {n_anal} analistas"
        horizonte = 12
    elif curr_usd and eps_g is not None:
        # Proyección simple: precio crece con EPS un año, ajustado por calidad
        growth = max(float(eps_g) / 100, 0.03)  # floor 3%
        quality_mult = 1.0
        if roe is not None and float(roe) > 20:
            quality_mult += 0.04
        if pe is not None and float(pe) < 18:
            quality_mult += 0.03  # re-rating potencial
        obj_usd = round(float(curr_usd) * (1 + growth) * quality_mult, 2)
        fuente_obj = "proyeccion_eps"
        horizonte = 12
    elif curr_usd:
        # Mínimo: precio flat + rendimiento histórico mercado 8%
        obj_usd = round(float(curr_usd) * 1.08, 2)
        fuente_obj = "flat+8pct"
        horizonte = 12

    # Convertir a ARS
    obj_ars: float | None = None
    if obj_usd is not None and tipo not in ("Acción Local", "Merval"):
        obj_ars = round(obj_usd * ratio * max(float(ccl), 1.0), 2)
    elif obj_usd is not None:
        obj_ars = round(obj_usd, 2)  # ya en ARS

    # Upside
    precio_ars_now = _precio_ars_actual(ticker, tipo, ccl)
    upside: float | None = None
    if obj_ars and precio_ars_now and precio_ars_now > 0:
        upside = round((obj_ars / precio_ars_now - 1) * 100, 1)

    return {
        "pe_ratio":          pe,
        "roe_pct":           roe,
        "deuda_capital_pct": dce,
        "div_yield_pct":     div_y,
        "eps_growth_pct":    eps_g,
        "rev_growth_pct":    rev_g,
        "profit_margin_pct": margin,
        "beta":              beta,
        "mkt_cap_usd_b":     round(float(mkt_cap) / 1e9, 1) if mkt_cap else None,
        "sector_yf":         sector_yf,
        "n_analistas":       int(n_anal),
        "objetivo_salida_usd":  obj_usd,
        "objetivo_salida_ars":  obj_ars,
        "upside_pct":           upside,
        "horizonte_meses":      horizonte,
        "fuente_objetivo":      fuente_obj,
    }


def _tesis_inversion(
    ticker: str,
    tipo: str,
    score_dict: dict[str, Any],
    fund: dict[str, Any],
) -> str:
    """
    Genera párrafo profesional de tesis de inversión con datos reales.
    Cubre: valuación, rentabilidad, deuda, crecimiento, contexto técnico y objetivo.
    """
    bloques: list[str] = []

    # ── Valuación ─────────────────────────────────────────────────────────────
    pe = fund.get("pe_ratio")
    if pe is not None:
        if pe < 12:
            val_txt = f"valuación atractiva (P/E {pe:.1f}x) que sugiere descuento frente al mercado"
        elif pe < 22:
            val_txt = f"valuación razonable (P/E {pe:.1f}x), consistente con el sector"
        elif pe < 35:
            val_txt = f"múltiplo moderadamente elevado (P/E {pe:.1f}x); justificado si el crecimiento se sostiene"
        else:
            val_txt = f"P/E de {pe:.1f}x refleja expectativas de crecimiento alto — seguir de cerca la ejecución"
        bloques.append(val_txt.capitalize() + ".")

    # ── Rentabilidad ─────────────────────────────────────────────────────────
    roe = fund.get("roe_pct")
    margin = fund.get("profit_margin_pct")
    ren_parts: list[str] = []
    if roe is not None:
        if roe > 25:
            ren_parts.append(f"ROE del {roe:.1f}% — excepcional, señal de ventaja competitiva sostenida")
        elif roe > 15:
            ren_parts.append(f"ROE del {roe:.1f}% — sólido")
        elif roe > 8:
            ren_parts.append(f"ROE del {roe:.1f}% — aceptable")
        else:
            ren_parts.append(f"ROE del {roe:.1f}% — por debajo del promedio; vigilar tendencia")
    if margin is not None:
        if margin > 20:
            ren_parts.append(f"margen neto del {margin:.1f}% (amplio)")
        elif margin > 8:
            ren_parts.append(f"margen neto del {margin:.1f}%")
        else:
            ren_parts.append(f"margen neto ajustado del {margin:.1f}%")
    if ren_parts:
        bloques.append("Rentabilidad: " + "; ".join(ren_parts) + ".")

    # ── Deuda ─────────────────────────────────────────────────────────────────
    dce = fund.get("deuda_capital_pct")
    if dce is not None:
        if dce < 30:
            bloques.append(f"Balance sólido: deuda/capital del {dce:.0f}%, sin presión financiera significativa.")
        elif dce < 80:
            bloques.append(f"Deuda/capital del {dce:.0f}% — manejable en entorno de tasas actuales.")
        else:
            bloques.append(f"Deuda/capital del {dce:.0f}% — nivel a monitorear ante suba de tasas.")

    # ── Crecimiento ───────────────────────────────────────────────────────────
    eps_g = fund.get("eps_growth_pct")
    rev_g = fund.get("rev_growth_pct")
    crec_parts: list[str] = []
    if eps_g is not None:
        crec_parts.append(f"EPS {'creciendo' if eps_g >= 0 else 'contrayendo'} {abs(eps_g):.1f}% anual")
    if rev_g is not None:
        crec_parts.append(f"ingresos {'al alza' if rev_g >= 0 else 'a la baja'} {abs(rev_g):.1f}%")
    if crec_parts:
        bloques.append("Crecimiento: " + ", ".join(crec_parts) + ".")

    # ── Dividendo ─────────────────────────────────────────────────────────────
    div_y = fund.get("div_yield_pct")
    if div_y and div_y > 0.5:
        bloques.append(f"Dividend yield del {div_y:.2f}% — componente de retorno total.")

    # ── Contexto técnico ─────────────────────────────────────────────────────
    rsi = float(score_dict.get("RSI") or 50)
    st  = float(score_dict.get("Score_Total") or 0)
    senal = str(score_dict.get("Senal") or "")
    if rsi < 35:
        tec_txt = f"técnicamente sobrevendido (RSI {rsi:.0f}), zona de posible reversión"
    elif rsi > 65:
        tec_txt = f"momentum alcista (RSI {rsi:.0f}); confirmar antes de agregar posición"
    else:
        tec_txt = f"RSI neutral ({rsi:.0f}), sin señales de sobrecompra/sobreventa"
    bloques.append(f"Contexto técnico: {tec_txt}. Score MQ26: {st:.0f}/100.")

    # ── Objetivo de salida ────────────────────────────────────────────────────
    obj_ars = fund.get("objetivo_salida_ars")
    upside  = fund.get("upside_pct")
    horiz   = fund.get("horizonte_meses", 12)
    fuente  = fund.get("fuente_objetivo", "n/a")
    if obj_ars and upside is not None:
        fuente_lbl = f"({fuente})" if fuente not in ("n/a", "") else ""
        if upside > 0:
            bloques.append(
                f"Objetivo de salida: ${obj_ars:,.0f} ARS en {horiz} meses "
                f"{fuente_lbl} — potencial de apreciación del {upside:.1f}%."
            )
        else:
            bloques.append(
                f"Precio objetivo referencial: ${obj_ars:,.0f} ARS {fuente_lbl}. "
                f"Posición defensiva; evaluar en el horizonte de {horiz} meses."
            )

    return " ".join(bloques) if bloques else f"Activo seleccionado por score MQ26 de {st:.0f}/100."


def guardar_recomendacion(payload: dict[str, Any], *, audit_user: str = "") -> None:
    """Persiste activa + snapshot por semana (JSON como str para evitar doble dumps)."""
    raw = json.dumps(payload, ensure_ascii=False)
    dbm.guardar_config(CLAVE_ACTIVA, raw, audit_user=audit_user)
    anio = int(payload.get("anio") or date.today().year)
    sem = int(payload.get("semana") or 0)
    if sem > 0:
        clave_sem = f"primera_cartera_{anio}_s{sem:02d}"
        dbm.guardar_config(clave_sem, raw, audit_user=audit_user)


def _parse_config_valor(val: Any) -> dict[str, Any] | None:
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return None


def cargar_recomendacion_activa() -> dict[str, Any] | None:
    return _parse_config_valor(dbm.obtener_config(CLAVE_ACTIVA))


def cargar_recomendacion_semana(anio: int, semana: int) -> dict[str, Any] | None:
    clave = f"primera_cartera_{int(anio)}_s{int(semana):02d}"
    return _parse_config_valor(dbm.obtener_config(clave))


def historial_recomendaciones(anio: int) -> list[dict[str, Any]]:
    pat = f"primera_cartera_{int(anio)}_s%"
    out: list[dict[str, Any]] = []
    try:
        with dbm.get_session() as s:
            rows = s.execute(
                text("SELECT clave, valor FROM configuracion WHERE clave LIKE :pat ORDER BY clave DESC"),
                {"pat": pat},
            ).fetchall()
        for clave, valor in rows:
            parsed = _parse_config_valor(valor)
            if parsed:
                parsed["_clave_config"] = clave
                out.append(parsed)
    except Exception as e:
        logger.warning("historial_recomendaciones: %s", e)
    return out


def construir_payload_completo(
    ccl: float,
    n: int = 3,
    min_score: float = 45.0,
    nota_admin: str = "",
    fecha: date | None = None,
) -> dict[str, Any] | None:
    """Pipeline: selección → unidades → narrativa."""
    fecha = fecha or date.today()
    pres = presupuesto_semana(numero_semana_del_año(fecha))
    sel = seleccionar_recomendaciones(ccl, n=n, min_score=min_score)
    if not sel:
        return None
    with_u = calcular_unidades(pres, sel)
    return generar_narrativa_semana(with_u, pres, ccl, nota_admin=nota_admin, fecha=fecha)
