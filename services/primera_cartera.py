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
    {"ticker": "GLD", "tipo": "CEDEAR", "categoria": "cobertura"},
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
        narr_items.append({
            **it,
            "var_txt": var_txt,
            "rsi_txt": rsi_txt,
            "senal": senal,
            "nombre_display": nombre,
        })
        bloques.append(
            f"{nombre} ({it.get('tipo')}): puntuación {it.get('score_total')}, {var_txt} {rsi_txt}"
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
