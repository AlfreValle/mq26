"""
services/data_quality.py — Calidad y validación cruzada de fundamentales.

Score de confianza 0-100 que detecta:
  - Campos faltantes (yfinance no expone todos los ratios para todos los tickers)
  - Valores en escala dudosa (ej: ROE = 270 ó 0.0027 — probablemente bug)
  - Inconsistencias entre fuentes (P/E TTM y forward muy distintos)
  - Datos stale (cache > 24h)

Resultado: cada análisis MQ26 incluye un "confianza_datos" + lista de issues.
Permite al usuario saber CUÁNDO confiar y cuándo dudar.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataQualityScore:
    """Resultado de evaluación de calidad de fundamentales."""
    ticker: str
    confianza_pct: float            # 0-100
    nivel: str                       # ALTA | MEDIA | BAJA
    campos_disponibles: int
    campos_totales: int
    issues_criticos: list[str] = field(default_factory=list)    # 🔴 — descalifica análisis
    issues_advertencia: list[str] = field(default_factory=list) # 🟡 — usar con precaución
    issues_info: list[str] = field(default_factory=list)        # 🟢 — solo info
    cache_edad_horas: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Campos esenciales para que un análisis tenga confianza alta ──────────────

# Campos mínimos para análisis básico (sin estos, no podemos hacer nada confiable)
_CAMPOS_CRITICOS = ["precio_actual_usd", "pe_ttm", "market_cap"]

# Campos importantes para análisis fundamental
_CAMPOS_FUNDAMENTAL = [
    "roe", "roa", "profit_margin", "operating_margin",
    "debt_to_equity", "revenue_growth", "earnings_growth",
]

# Campos importantes para DCF
_CAMPOS_DCF = ["shares_outstanding", "beta", "pe_forward"]

# Campos importantes para contexto (no críticos)
_CAMPOS_CONTEXTO = [
    "sector", "industry", "country", "dividend_yield",
    "next_earnings_date", "current_ratio", "gross_margin",
]


def _detectar_escala_anormal(campo: str, valor: float | None) -> str | None:
    """
    Detecta si un campo está en escala absurda.
    Retorna mensaje de warning o None si OK.
    """
    if valor is None or valor == 0:
        return None

    v = float(valor)
    rangos_validos = {
        # Ratios fundamentales (deberían estar en fracción [-1, 1] o porcentaje [-100, 100])
        "roe":              (-1.5, 2.0),       # ROE entre -150% y 200%
        "roa":              (-1.0, 1.0),
        "profit_margin":    (-2.0, 1.0),
        "operating_margin": (-2.0, 1.0),
        "gross_margin":     (-1.0, 1.0),
        "revenue_growth":   (-1.0, 5.0),       # crecimiento -100% a 500%
        "earnings_growth":  (-2.0, 10.0),      # más errático
        "dividend_yield":   (0, 0.30),         # 0% a 30%
        "payout_ratio":     (0, 5.0),          # hasta 500% para casos extremos
        # Múltiplos
        "pe_ttm":           (-100, 500),
        "pe_forward":       (-100, 500),
        "pb_ratio":         (-50, 100),
        "ps_ratio":         (-10, 200),
        "peg_ratio":        (-10, 50),
        # Beta
        "beta":             (-3, 5),
        # D/E en yfinance suele venir en porcentaje (ej: 67.73)
        "debt_to_equity":   (-50, 2000),
        "current_ratio":    (0, 50),
    }

    rng = rangos_validos.get(campo)
    if rng is None:
        return None

    lo, hi = rng
    # Auto-detect si está en porcentaje vs fracción (para ratios fundamentales)
    if campo in ("roe", "roa", "profit_margin", "operating_margin", "gross_margin",
                  "revenue_growth", "earnings_growth", "dividend_yield"):
        # Si valor > 5 pero rango espera < 1, probablemente está en porcentaje (no error)
        if abs(v) > 5 and abs(v) <= 500:
            return None   # OK, está en porcentaje
        if abs(v) > 500:
            return f"escala absurda ({v})"
        # else: está en fracción, validar contra rango
        if not (lo <= v <= hi):
            return f"fuera de rango fracción [{lo:.2f}, {hi:.2f}]"
        return None

    if not (lo <= v <= hi):
        return f"fuera de rango razonable [{lo:.0f}, {hi:.0f}]"
    return None


def evaluar_calidad(snap) -> DataQualityScore:
    """
    Evalúa la calidad de los datos en un FundamentalsSnapshot.

    Returns DataQualityScore con confianza 0-100 y listas de issues.
    """
    issues_criticos: list[str] = []
    issues_advertencia: list[str] = []
    issues_info: list[str] = []

    # ── 1) Campos críticos ──
    n_criticos_ok = 0
    for campo in _CAMPOS_CRITICOS:
        v = getattr(snap, campo, None)
        if v is None or v == 0:
            issues_criticos.append(f"falta {campo}")
        else:
            n_criticos_ok += 1

    # ── 2) Campos fundamentales ──
    n_fund_ok = 0
    for campo in _CAMPOS_FUNDAMENTAL:
        v = getattr(snap, campo, None)
        if v is None:
            issues_advertencia.append(f"falta {campo}")
        else:
            n_fund_ok += 1
            # Detectar escala anormal
            problema = _detectar_escala_anormal(campo, v)
            if problema:
                issues_advertencia.append(f"{campo}: {problema}")

    # ── 3) Campos DCF ──
    n_dcf_ok = 0
    for campo in _CAMPOS_DCF:
        v = getattr(snap, campo, None)
        if v is None or v == 0:
            issues_advertencia.append(f"DCF requiere {campo} (no disponible)")
        else:
            n_dcf_ok += 1

    # ── 4) Campos de contexto ──
    n_ctx_ok = 0
    for campo in _CAMPOS_CONTEXTO:
        v = getattr(snap, campo, None)
        if v is not None and v != 0 and v != "":
            n_ctx_ok += 1

    # ── 5) Edad del caché ──
    cache_edad_horas = None
    try:
        if snap.fetched_at:
            fetched = dt.datetime.fromisoformat(snap.fetched_at.replace("Z", "+00:00"))
            cache_edad_horas = (dt.datetime.now(dt.UTC) - fetched).total_seconds() / 3600
            if cache_edad_horas > 168:   # 7 días
                issues_advertencia.append(f"caché muy stale ({cache_edad_horas:.0f}h)")
            elif cache_edad_horas > 48:
                issues_info.append(f"caché de {cache_edad_horas:.0f}h (TTL 24h)")
    except Exception:
        pass

    # ── 6) Consistencia P/E TTM vs Forward ──
    if snap.pe_ttm and snap.pe_forward and snap.pe_ttm > 0 and snap.pe_forward > 0:
        ratio = snap.pe_ttm / snap.pe_forward
        if ratio > 3 or ratio < 0.33:
            issues_advertencia.append(
                f"P/E TTM ({snap.pe_ttm:.1f}) muy divergente vs forward ({snap.pe_forward:.1f})"
            )

    # ── 7) Calcular score 0-100 ──
    # Pesos: críticos 40%, fundamentales 35%, DCF 15%, contexto 10%
    score_criticos = (n_criticos_ok / len(_CAMPOS_CRITICOS)) * 100 if _CAMPOS_CRITICOS else 100
    score_fund     = (n_fund_ok / len(_CAMPOS_FUNDAMENTAL)) * 100 if _CAMPOS_FUNDAMENTAL else 100
    score_dcf      = (n_dcf_ok / len(_CAMPOS_DCF)) * 100 if _CAMPOS_DCF else 100
    score_ctx      = (n_ctx_ok / len(_CAMPOS_CONTEXTO)) * 100 if _CAMPOS_CONTEXTO else 100

    confianza = 0.40 * score_criticos + 0.35 * score_fund + 0.15 * score_dcf + 0.10 * score_ctx

    # Penalizaciones por issues
    confianza -= len(issues_criticos) * 15
    confianza -= len(issues_advertencia) * 3
    confianza = max(0, min(100, confianza))

    # Nivel
    if confianza >= 75:
        nivel = "ALTA"
    elif confianza >= 50:
        nivel = "MEDIA"
    else:
        nivel = "BAJA"

    total_disp = n_criticos_ok + n_fund_ok + n_dcf_ok + n_ctx_ok
    total_total = (len(_CAMPOS_CRITICOS) + len(_CAMPOS_FUNDAMENTAL) +
                   len(_CAMPOS_DCF) + len(_CAMPOS_CONTEXTO))

    return DataQualityScore(
        ticker=getattr(snap, "ticker", "?"),
        confianza_pct=round(confianza, 1),
        nivel=nivel,
        campos_disponibles=total_disp,
        campos_totales=total_total,
        issues_criticos=issues_criticos,
        issues_advertencia=issues_advertencia,
        issues_info=issues_info,
        cache_edad_horas=round(cache_edad_horas, 1) if cache_edad_horas else None,
    )


# ─── Render HTML del bloque de calidad de datos ───────────────────────────────

def data_quality_html(dq: DataQualityScore) -> str:
    """HTML para mostrar el score de confianza de datos en el reporte."""
    from ui.color_palette import PALETTE

    if dq.nivel == "ALTA":
        color_bg = PALETTE.success_bg
        color_fg = PALETTE.success_fg
        icono = "✓"
    elif dq.nivel == "MEDIA":
        color_bg = PALETTE.warning_bg
        color_fg = PALETTE.warning_fg
        icono = "⚠"
    else:
        color_bg = PALETTE.danger_bg
        color_fg = PALETTE.danger_fg
        icono = "⚠️"

    issues_html = ""
    if dq.issues_criticos:
        items = "".join(f"<li style='color:{PALETTE.danger_fg};'>{i}</li>" for i in dq.issues_criticos)
        issues_html += f"<div><b style='color:{PALETTE.danger_fg};'>🔴 Críticos:</b><ul>{items}</ul></div>"
    if dq.issues_advertencia:
        items = "".join(f"<li style='color:{PALETTE.warning_fg};'>{i}</li>" for i in dq.issues_advertencia[:5])
        n_extra = max(0, len(dq.issues_advertencia) - 5)
        extra = f" <i>(+{n_extra} más)</i>" if n_extra else ""
        issues_html += (
            f"<div style='margin-top:6px;'>"
            f"<b style='color:{PALETTE.warning_fg};'>🟡 Advertencias:</b>"
            f"<ul>{items}</ul>{extra}</div>"
        )

    return f"""
<div style="background:{color_bg};border:1px solid {color_fg};padding:12px;
            border-radius:8px;margin:10px 0;color:{color_fg};">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <b style="font-size:1.05em;">{icono} Confianza de datos: {dq.nivel}</b>
    <span style="background:{PALETTE.surface_card};color:{color_fg};
                 padding:4px 12px;border-radius:12px;font-weight:700;">
      {dq.confianza_pct:.0f}/100
    </span>
  </div>
  <div style="font-size:0.85em;margin-top:6px;color:{color_fg};">
    {dq.campos_disponibles}/{dq.campos_totales} campos disponibles ·
    Cache: {f"{dq.cache_edad_horas:.0f}h de antigüedad" if dq.cache_edad_horas is not None else "sin cache"}
  </div>
  {issues_html}
</div>
"""
