"""
services/scoring_multifactor.py — Capa 2 del motor MQ26.

Motor multifactor que pondera 4 dimensiones:

    1. VALOR             35%   →  P/E forward, P/B, P/S, PEG
    2. CALIDAD           30%   →  ROE, ROA, márgenes, deuda
    3. MOMENTUM MOD-23   20%   →  Score técnico del scoring_engine existente
    4. COMPARATIVA       15%   →  Sectorial vs pares (P/E sector, ROE sector)

Output: ActionScore con 0-100 + flags de alerta detectados.

Pipeline:
    Capa 1 (fundamental_cache) → Capa 2 (este módulo) → Capa 3 (bdi_generator)
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Pesos canónicos (no hardcoded — los pidió el usuario) ────────────────────

PESO_VALOR      = 0.35
PESO_CALIDAD    = 0.30
PESO_MOMENTUM   = 0.20
PESO_SECTORIAL  = 0.15

assert abs(PESO_VALOR + PESO_CALIDAD + PESO_MOMENTUM + PESO_SECTORIAL - 1.0) < 1e-9


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class ActionScore:
    """Score multifactor 0-100 con flags y trazabilidad."""
    ticker: str
    timestamp: str
    score_total: float
    score_valor: float
    score_calidad: float
    score_momentum: float
    score_sectorial: float
    pesos: dict[str, float] = field(default_factory=dict)
    recomendacion: str = "MANTENER"   # COMPRAR | MANTENER | VENDER
    flags_alerta: list[str] = field(default_factory=list)
    detalle_valor: dict[str, Any] = field(default_factory=dict)
    detalle_calidad: dict[str, Any] = field(default_factory=dict)
    detalle_momentum: dict[str, Any] = field(default_factory=dict)
    detalle_sectorial: dict[str, Any] = field(default_factory=dict)
    sector: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Helpers de normalización 0-100 ───────────────────────────────────────────

def _score_invertido(valor: float | None, optimo: float, malo: float) -> float:
    """
    Valor MÁS BAJO = MEJOR (ej: P/E, deuda).
    Devuelve 100 si valor <= optimo, 0 si valor >= malo, lineal en el medio.
    """
    if valor is None or valor <= 0:
        return 50.0   # neutral si no hay dato
    if valor <= optimo:
        return 100.0
    if valor >= malo:
        return 0.0
    return round(100.0 * (malo - valor) / (malo - optimo), 1)


def _score_directo(valor: float | None, optimo: float, malo: float) -> float:
    """
    Valor MÁS ALTO = MEJOR (ej: ROE, márgenes).
    Devuelve 100 si valor >= optimo, 0 si valor <= malo, lineal en el medio.
    """
    if valor is None:
        return 50.0
    if valor >= optimo:
        return 100.0
    if valor <= malo:
        return 0.0
    return round(100.0 * (valor - malo) / (optimo - malo), 1)


# ─── Dimensión 1: VALOR (35%) ─────────────────────────────────────────────────

def _score_valor(snap) -> tuple[float, dict[str, Any]]:
    """
    Compone score 0-100 desde múltiplos de valuación.
    P/E forward 50% del subscore, P/B 20%, P/S 20%, PEG 10%.
    """
    detalle = {}

    # P/E forward: óptimo ≤ 15, malo ≥ 35
    sc_pe = _score_invertido(snap.pe_forward or snap.pe_ttm, optimo=15, malo=35)
    detalle["pe_forward"] = {"valor": snap.pe_forward or snap.pe_ttm, "score": sc_pe}

    # P/B: óptimo ≤ 2, malo ≥ 8
    sc_pb = _score_invertido(snap.pb_ratio, optimo=2, malo=8)
    detalle["pb_ratio"] = {"valor": snap.pb_ratio, "score": sc_pb}

    # P/S: óptimo ≤ 2, malo ≥ 10
    sc_ps = _score_invertido(snap.ps_ratio, optimo=2, malo=10)
    detalle["ps_ratio"] = {"valor": snap.ps_ratio, "score": sc_ps}

    # PEG: óptimo ≤ 1, malo ≥ 3
    sc_peg = _score_invertido(snap.peg_ratio, optimo=1, malo=3)
    detalle["peg_ratio"] = {"valor": snap.peg_ratio, "score": sc_peg}

    score = 0.50 * sc_pe + 0.20 * sc_pb + 0.20 * sc_ps + 0.10 * sc_peg
    return round(score, 1), detalle


# ─── Dimensión 2: CALIDAD (30%) ───────────────────────────────────────────────

def _score_calidad(snap) -> tuple[float, dict[str, Any]]:
    """
    Compone score 0-100 desde rentabilidad y solvencia.
    ROE 30%, ROA 15%, margen neto 20%, margen operativo 15%,
    deuda/equity 15%, current ratio 5%.

    Normaliza ratios (ROE, márgenes) a fracción antes de comparar
    contra umbrales — evita confundir 26.42 (porcentaje) con 26.42 (fracción).
    """
    from services.fundamental_cache import fraccion_segura
    detalle = {}

    # ROE: óptimo ≥ 0.20 (20%), malo ≤ 0.05 (5%)
    sc_roe = _score_directo(fraccion_segura(snap.roe), optimo=0.20, malo=0.05)
    detalle["roe"] = {"valor": snap.roe, "score": sc_roe}

    # ROA: óptimo ≥ 0.10 (10%), malo ≤ 0.02
    sc_roa = _score_directo(fraccion_segura(snap.roa), optimo=0.10, malo=0.02)
    detalle["roa"] = {"valor": snap.roa, "score": sc_roa}

    # Margen neto: óptimo ≥ 0.15, malo ≤ 0.03
    sc_mn = _score_directo(fraccion_segura(snap.profit_margin), optimo=0.15, malo=0.03)
    detalle["profit_margin"] = {"valor": snap.profit_margin, "score": sc_mn}

    # Margen operativo: óptimo ≥ 0.20, malo ≤ 0.05
    sc_mo = _score_directo(fraccion_segura(snap.operating_margin), optimo=0.20, malo=0.05)
    detalle["operating_margin"] = {"valor": snap.operating_margin, "score": sc_mo}

    # Deuda/Equity: óptimo ≤ 50, malo ≥ 250 (yfinance lo devuelve como %)
    sc_de = _score_invertido(snap.debt_to_equity, optimo=50, malo=250)
    detalle["debt_to_equity"] = {"valor": snap.debt_to_equity, "score": sc_de}

    # Current ratio: óptimo ≥ 1.5, malo ≤ 0.8
    sc_cr = _score_directo(snap.current_ratio, optimo=1.5, malo=0.8)
    detalle["current_ratio"] = {"valor": snap.current_ratio, "score": sc_cr}

    score = (0.30 * sc_roe + 0.15 * sc_roa + 0.20 * sc_mn +
             0.15 * sc_mo + 0.15 * sc_de + 0.05 * sc_cr)
    return round(score, 1), detalle


# ─── Dimensión 3: MOMENTUM MOD-23 (20%) ───────────────────────────────────────

def _score_momentum(ticker: str) -> tuple[float, dict[str, Any]]:
    """
    Usa el scoring técnico MOD-23 existente (Score_Tec).
    Si no está disponible, devuelve neutral.
    """
    try:
        from services.scoring_engine import calcular_score_total
        d = calcular_score_total(ticker, tipo="CEDEAR")
        score_tec = float(d.get("Score_Tec", 0) or 0)
        # Score_Tec viene en 0-100 (escala MOD-23). Lo usamos directo.
        return round(score_tec, 1), {
            "score_tecnico": score_tec,
            "rsi": d.get("RSI"),
            "macd": d.get("MACD"),
            "bb_pos": d.get("BB_Pos"),
            "max_dd_1y": d.get("MaxDD_1Y"),
            "hv20d": d.get("HV20d"),
            "senal": d.get("Senal"),
        }
    except Exception as e:
        logger.debug("scoring_multifactor: momentum no disponible para %s: %s", ticker, e)
        return 50.0, {"error": str(e), "score_tecnico": 50.0}


# ─── Dimensión 4: COMPARATIVA SECTORIAL (15%) ─────────────────────────────────

# Medianas de referencia por sector (P/E, ROE) — actualizable según mercado.
# Estos son benchmarks de mercado USA reales; sirven como pivot.
_BENCHMARKS_SECTOR: dict[str, dict[str, float]] = {
    "Technology":            {"pe_med": 28.0, "roe_med": 0.22},
    "Financial Services":    {"pe_med": 12.0, "roe_med": 0.12},
    "Healthcare":            {"pe_med": 18.0, "roe_med": 0.18},
    "Consumer Cyclical":     {"pe_med": 18.0, "roe_med": 0.15},
    "Consumer Defensive":    {"pe_med": 20.0, "roe_med": 0.20},
    "Communication Services":{"pe_med": 20.0, "roe_med": 0.18},
    "Industrials":           {"pe_med": 18.0, "roe_med": 0.15},
    "Energy":                {"pe_med": 12.0, "roe_med": 0.14},
    "Basic Materials":       {"pe_med": 14.0, "roe_med": 0.12},
    "Utilities":             {"pe_med": 16.0, "roe_med": 0.10},
    "Real Estate":           {"pe_med": 30.0, "roe_med": 0.08},
}


def _calcular_score_vs_benchmark(snap, bench: dict, fuente: str, industria: str | None = None) -> tuple[float, dict[str, Any]]:
    """
    Score sectorial 0-100 contra cualquier benchmark (industria o sector).
    Considera múltiples métricas si están en el benchmark.
    """
    detalle = {"fuente": fuente, "benchmark": bench}
    if industria:
        detalle["industria"] = industria

    sub_scores = []

    # PE: más bajo = mejor
    pe = snap.pe_forward or snap.pe_ttm or 0
    pe_med = bench.get("pe_med", 0)
    if pe > 0 and pe_med > 0:
        ratio = pe / pe_med
        sc = max(0, min(100, 100 - (ratio - 0.7) * 166))
        sub_scores.append(sc)
        detalle["pe_vs"] = {"empresa": pe, "industria": pe_med, "score": round(sc, 1)}

    # ROE: más alto = mejor
    roe = snap.roe or 0
    roe_med = bench.get("roe_med", 0)
    if roe > 0 and roe_med > 0:
        ratio = roe / roe_med
        sc = max(0, min(100, 50 + (ratio - 1.0) * 100))
        sub_scores.append(sc)
        detalle["roe_vs"] = {"empresa": roe, "industria": roe_med, "score": round(sc, 1)}

    # Margen neto: más alto = mejor (opcional, si benchmark lo trae)
    mn = snap.profit_margin or 0
    mn_med = bench.get("margen_neto_med", 0)
    if mn > 0 and mn_med > 0:
        ratio = mn / mn_med
        sc = max(0, min(100, 50 + (ratio - 1.0) * 100))
        sub_scores.append(sc)
        detalle["margen_neto_vs"] = {"empresa": mn, "industria": mn_med, "score": round(sc, 1)}

    # Crecimiento de ganancias: más alto = mejor (CRÍTICO — detecta JNJ -52% vs +31%)
    eg = snap.earnings_growth
    eg_med = bench.get("crecimiento_bpa_5y_med", 0)
    if eg is not None and eg_med > 0:
        # ratio puede ser negativo si la empresa cae y el sector crece
        ratio = (eg + 0.5) / (eg_med + 0.5)  # offset para evitar /0 con negativos
        sc = max(0, min(100, 50 + (ratio - 1.0) * 50))
        sub_scores.append(sc)
        detalle["crec_bpa_vs"] = {"empresa": eg, "industria": eg_med, "score": round(sc, 1)}

    if not sub_scores:
        return 50.0, detalle

    score = sum(sub_scores) / len(sub_scores)
    detalle["score_final"] = round(score, 1)
    return round(score, 1), detalle


def _score_sectorial(snap) -> tuple[float, dict[str, Any]]:
    """
    Compara los múltiplos del ticker con los benchmarks de su INDUSTRIA específica
    (fallback a sector amplio si no hay industria cargada).
    Score alto si: PE < industria (más barato) Y ROE > industria (más rentable).
    """
    # Estrategia en cascada: industria específica → sector amplio
    try:
        from services.industry_benchmarks import obtener_benchmark
        bench, fuente = obtener_benchmark(getattr(snap, "industry", None), snap.sector)
        if bench is not None:
            return _calcular_score_vs_benchmark(snap, bench, fuente,
                                                 industria=getattr(snap, "industry", None))
    except Exception:
        pass

    # Fallback al benchmark inline (compat con versión anterior)
    if not snap.sector:
        return 50.0, {"sin_sector": True}
    bench = _BENCHMARKS_SECTOR.get(snap.sector)
    if not bench:
        return 50.0, {"sector_sin_benchmark": snap.sector}

    detalle = {"sector": snap.sector, "benchmark": bench, "fuente": "sector (fallback inline)"}

    # Sub-score 1: P/E vs sector (más bajo = mejor)
    pe = snap.pe_forward or snap.pe_ttm or 0
    if pe > 0:
        ratio_pe = pe / bench["pe_med"]
        # ratio_pe=0.7 → 100 (30% más barato), ratio=1.0 → 50, ratio=1.3 → 0
        sc_pe_rel = max(0, min(100, 100 - (ratio_pe - 0.7) * 166))
    else:
        sc_pe_rel = 50
    detalle["pe_vs_sector"] = {"valor": pe, "sector_med": bench["pe_med"], "score": round(sc_pe_rel, 1)}

    # Sub-score 2: ROE vs sector (más alto = mejor)
    roe = snap.roe or 0
    if roe > 0:
        ratio_roe = roe / bench["roe_med"]
        # ratio_roe=1.5 → 100, ratio=1.0 → 50, ratio=0.5 → 0
        sc_roe_rel = max(0, min(100, 50 + (ratio_roe - 1.0) * 100))
    else:
        sc_roe_rel = 50
    detalle["roe_vs_sector"] = {"valor": roe, "sector_med": bench["roe_med"], "score": round(sc_roe_rel, 1)}

    # Promedio simple (50/50)
    score = (sc_pe_rel + sc_roe_rel) / 2
    return round(score, 1), detalle


# ─── Flags de alerta automáticos ──────────────────────────────────────────────

def _detectar_flags_alerta(snap, score_v, score_c, score_m, score_s) -> list[str]:
    """
    Genera flags de alerta accionables desde fundamentales + scoring.

    SEGURO contra escala: usa pct_seguro/fraccion_segura para auto-detectar
    si el dato viene en fracción (yfinance: 0.2642) o porcentaje (curado: 26.42).
    """
    from services.fundamental_cache import fraccion_segura, pct_seguro

    flags = []

    # Fundamentales críticos
    if snap.debt_to_equity and snap.debt_to_equity > 250:
        flags.append(f"🔴 Deuda/Equity {snap.debt_to_equity:.0f}% — apalancamiento muy alto")
    if snap.current_ratio is not None and snap.current_ratio < 1.0:
        flags.append(f"🔴 Current ratio {snap.current_ratio:.2f} — stress de liquidez")

    payout_frac = fraccion_segura(snap.payout_ratio)
    if payout_frac is not None and payout_frac > 0.90:
        flags.append(f"🟡 Payout {pct_seguro(snap.payout_ratio):.0f}% — dividendo en zona riesgosa")

    # Valuación
    if snap.pe_ttm and snap.pe_ttm > 40:
        flags.append(f"🟡 P/E TTM {snap.pe_ttm:.1f}x — valuación exigente")
    if snap.pe_forward and 0 < snap.pe_forward < 12:
        flags.append(f"🟢 P/E forward {snap.pe_forward:.1f}x — posible subvaluación")

    # Calidad
    roe_frac = fraccion_segura(snap.roe)
    if roe_frac is not None and roe_frac > 0.25:
        flags.append(f"🟢 ROE {pct_seguro(snap.roe):.1f}% — calidad excepcional")

    eg_frac = fraccion_segura(snap.earnings_growth)
    if eg_frac is not None and eg_frac < -0.20:
        flags.append(f"🔴 Ganancias {pct_seguro(snap.earnings_growth):.1f}% i.a. — contracción severa")
    elif eg_frac is not None and eg_frac > 0.30:
        flags.append(f"🟢 Ganancias +{pct_seguro(snap.earnings_growth):.0f}% i.a. — crecimiento fuerte")

    # Eventos próximos
    if snap.next_earnings_date:
        try:
            d_earn = dt.date.fromisoformat(snap.next_earnings_date[:10])
            dias = (d_earn - dt.date.today()).days
            if 0 <= dias <= 7:
                flags.append(f"🟡 Earnings en {dias} día(s) ({snap.next_earnings_date}) — volatilidad esperada")
        except Exception:
            pass

    # Posición técnica (descuento ya es siempre fracción [0,1])
    if snap.precio_actual_usd and snap.precio_52w_high:
        descuento = (snap.precio_52w_high - snap.precio_actual_usd) / snap.precio_52w_high
        # Cap por sanidad: si el feed dio precios raros, evitar mostrar % absurdos
        descuento = max(-0.99, min(0.99, descuento))
        if descuento > 0.30:
            flags.append(f"🟢 {descuento*100:.0f}% bajo el máximo 52 sem — oportunidad de reversión")
        elif 0 < descuento < 0.03:
            flags.append(f"🟡 Cerca del máximo 52 sem ({descuento*100:.0f}% de margen) — momentum/risk")

    # Combinaciones riesgosas
    if snap.beta and snap.beta > 1.5 and snap.pe_ttm and snap.pe_ttm > 30:
        flags.append(f"🔴 Beta {snap.beta:.2f} + P/E {snap.pe_ttm:.1f}x — alto riesgo de drawdown")

    # Scoring extremo
    if score_v >= 80 and score_c >= 80:
        flags.append("🟢 VALOR + CALIDAD ambos altos — combinación ideal estilo Buffett")
    if score_m < 30:
        flags.append("🔴 Momentum técnico débil — esperar mejor punto de entrada")
    if score_s >= 75:
        flags.append("🟢 Outperformer sectorial — mejor que la mediana del sector")

    return flags


def _recomendacion_desde_score(score_total: float, flags: list[str]) -> str:
    """Recomendación final tomando en cuenta el score y los flags rojos."""
    n_rojos = sum(1 for f in flags if f.startswith("🔴"))
    if n_rojos >= 2:
        # Demasiados flags rojos: bajar la recomendación
        if score_total >= 70:
            return "MANTENER"
        return "VENDER"
    if score_total >= 70:
        return "COMPRAR"
    if score_total >= 50:
        return "MANTENER"
    return "VENDER"


# ─── API principal ────────────────────────────────────────────────────────────

def calcular_action_score(ticker: str, *, force_refresh: bool = False) -> ActionScore:
    """
    Calcula el score multifactor MQ26 para un ticker.

    Pipeline:
      1. Capa 1: obtener fundamentales (caché TTL 24h)
      2. Evaluar 4 dimensiones: Valor / Calidad / Momentum / Sectorial
      3. Ponderar con pesos canónicos (35/30/20/15)
      4. Detectar flags de alerta
      5. Inferir recomendación

    Args:
        ticker: símbolo (CEDEAR o subyacente).
        force_refresh: si True, ignora caché y re-descarga fundamentales.

    Returns:
        ActionScore con score 0-100, breakdown por dimensión, flags y recomendación.
    """
    ticker = ticker.upper().strip()
    from services.fundamental_cache import obtener_fundamentales

    snap = obtener_fundamentales(ticker, force_refresh=force_refresh)

    sc_v, det_v = _score_valor(snap)
    sc_c, det_c = _score_calidad(snap)
    sc_m, det_m = _score_momentum(ticker)
    sc_s, det_s = _score_sectorial(snap)

    score_total = round(
        PESO_VALOR * sc_v + PESO_CALIDAD * sc_c +
        PESO_MOMENTUM * sc_m + PESO_SECTORIAL * sc_s,
        1,
    )

    flags = _detectar_flags_alerta(snap, sc_v, sc_c, sc_m, sc_s)
    recom = _recomendacion_desde_score(score_total, flags)

    return ActionScore(
        ticker=ticker,
        timestamp=dt.datetime.now(dt.UTC).isoformat(),
        score_total=score_total,
        score_valor=sc_v,
        score_calidad=sc_c,
        score_momentum=sc_m,
        score_sectorial=sc_s,
        pesos={
            "valor": PESO_VALOR,
            "calidad": PESO_CALIDAD,
            "momentum": PESO_MOMENTUM,
            "sectorial": PESO_SECTORIAL,
        },
        recomendacion=recom,
        flags_alerta=flags,
        detalle_valor=det_v,
        detalle_calidad=det_c,
        detalle_momentum=det_m,
        detalle_sectorial=det_s,
        sector=snap.sector,
    )


def ranking_multifactor(tickers: list[str], *, force_refresh: bool = False) -> list[ActionScore]:
    """Calcula scores para múltiples tickers, ordenados de mayor a menor score_total."""
    scores = []
    for t in tickers:
        try:
            scores.append(calcular_action_score(t, force_refresh=force_refresh))
        except Exception as e:
            logger.warning("ranking_multifactor: error con %s: %s", t, e)
    scores.sort(key=lambda s: -s.score_total)
    return scores
