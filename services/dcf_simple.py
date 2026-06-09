"""
services/dcf_simple.py — DCF (Discounted Cash Flow) simplificado.

Calcula el VALOR INTRÍNSECO de una empresa basado en sus flujos de caja libres
futuros proyectados y descontados a presente.

Es el método estándar de Buffett/Munger/value investing. Más confiable que un
target técnico (R/R 2:1 sobre volatilidad).

Modelo (2 etapas):
    Etapa 1 (5 años): FCFF crece a growth_rate explícito
    Etapa 2 (terminal): FCFF crece a tasa terminal (≈2-3%, GDP global)

    PV = Σ FCFF_t / (1+WACC)^t  +  Terminal_Value / (1+WACC)^5

WACC (costo de capital ponderado):
    WACC = (E/(E+D)) × Cost_Equity + (D/(E+D)) × Cost_Debt × (1-tax)

    Cost_Equity = Rf + Beta × Risk_Premium
    Rf (libre de riesgo)  = 4.5% (Treasury 10Y aprox)
    Risk_Premium (USA)    = 5.5% (Damodaran)
    Cost_Debt aproximada  = 5.5%
    Tax rate              = 21% (USA federal)

Limitaciones documentadas:
    - Asume FCFF estable (no funciona bien para growth puro en pre-rentabilidad)
    - Sensible al growth rate (cambios de 1pp mueven el target 10-20%)
    - No considera deuda contingente, opciones, fusiones pendientes
    - El target es indicativo, no preciso

Cuándo NO usar:
    - Empresas con FCFF negativo
    - Startups / growth pre-profit
    - Bancos / aseguradoras (modelo distinto)
    - Empresas con high CapEx ciclico (energía, minería)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)


# ─── Parámetros canónicos (auditables, no hardcoded por ticker) ───────────────

# Risk-free rate (Treasury 10Y aprox jun-2026)
RF_RATE = 0.045
# Equity risk premium (Damodaran USA)
ERP = 0.055
# Cost of debt aproximado (BBB corporate spread)
COST_DEBT_BASE = 0.055
# Tax rate USA federal corporate
TAX_RATE = 0.21
# Growth terminal (≈ GDP global)
TERMINAL_GROWTH = 0.025
# Años de proyección explícita
ANIOS_PROYECCION = 5


@dataclass
class DCFResultado:
    """Resultado del DCF para un ticker."""
    ticker: str
    precio_actual_usd: float
    valor_intrinseco_usd: float       # por acción
    margen_seguridad_pct: float        # (intrinseco - precio) / precio × 100
    recomendacion_dcf: str             # "INFRAVALORADA" | "FAIR" | "SOBREVALUADA"
    # Inputs usados
    fcff_anual_usd_m: float | None
    growth_explicito_pct: float
    wacc_pct: float
    terminal_growth_pct: float
    beta_usado: float
    shares_outstanding_m: float | None
    # Sensibilidad
    sensibilidad: dict[str, dict] = None
    # Warnings
    warnings: list[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Cálculos centrales ───────────────────────────────────────────────────────

def _wacc(beta: float, debt_to_equity_pct: float | None) -> float:
    """
    Costo de capital ponderado.

    Si no hay deuda info → asume 100% equity (peso D/V = 0).
    Si hay D/E en %, lo convierte a peso de deuda.
    """
    # Cost of equity (CAPM)
    cost_equity = RF_RATE + beta * ERP

    # Pesos D/V y E/V
    if debt_to_equity_pct is None or debt_to_equity_pct <= 0:
        peso_deuda = 0
        peso_equity = 1.0
    else:
        # D/E = 80% → D/V = 80/180 = 0.44
        d_over_e = debt_to_equity_pct / 100.0
        peso_deuda = d_over_e / (1 + d_over_e)
        peso_equity = 1 - peso_deuda

    wacc = peso_equity * cost_equity + peso_deuda * COST_DEBT_BASE * (1 - TAX_RATE)
    return round(wacc, 4)


def _proyectar_fcff(fcff_inicial_usd: float, growth: float, anios: int) -> list[float]:
    """Lista de FCFF proyectados año por año (cada uno = anterior × (1+growth))."""
    flujos = []
    actual = fcff_inicial_usd
    for _ in range(anios):
        actual = actual * (1 + growth)
        flujos.append(actual)
    return flujos


def _valor_presente_flujos(flujos: list[float], wacc: float, terminal_value: float) -> float:
    """
    Σ flujos descontados + terminal value descontado.
    Terminal_value se descuenta usando wacc^n donde n = años (último).
    """
    pv = 0.0
    for t, ft in enumerate(flujos, start=1):
        pv += ft / (1 + wacc) ** t
    # Terminal value se aplica al final del último año proyectado
    pv += terminal_value / (1 + wacc) ** len(flujos)
    return pv


def _calcular_sensibilidad(
    fcff_inicial: float,
    growth_base: float,
    wacc_base: float,
    shares: float,
    terminal_growth: float = TERMINAL_GROWTH,
) -> dict[str, dict]:
    """
    Matriz de sensibilidad: ¿cómo cambia el valor con ±1pp en growth y WACC?
    Devuelve dict con escenarios.
    """
    escenarios = {}
    for nombre, g_delta, w_delta in [
        ("base",        0.000,  0.000),
        ("optimista",  +0.010, -0.010),
        ("pesimista",  -0.010, +0.010),
    ]:
        g = growth_base + g_delta
        w = wacc_base + w_delta
        if w <= terminal_growth:
            escenarios[nombre] = {"valor_por_accion": None, "nota": "WACC ≤ growth terminal"}
            continue
        flujos = _proyectar_fcff(fcff_inicial, g, ANIOS_PROYECCION)
        fcff_n_plus_1 = flujos[-1] * (1 + terminal_growth)
        terminal_value = fcff_n_plus_1 / (w - terminal_growth)
        pv = _valor_presente_flujos(flujos, w, terminal_value)
        v_por_accion = pv / shares if shares > 0 else None
        escenarios[nombre] = {
            "growth_pct": round(g * 100, 1),
            "wacc_pct":   round(w * 100, 2),
            "valor_por_accion_usd": round(v_por_accion, 2) if v_por_accion else None,
        }
    return escenarios


# ─── API principal ────────────────────────────────────────────────────────────

def calcular_dcf(
    ticker: str,
    *,
    snap=None,                          # FundamentalsSnapshot opcional
    growth_override: float | None = None,
    terminal_growth: float = TERMINAL_GROWTH,
) -> DCFResultado | None:
    """
    Calcula valor intrínseco DCF para un ticker.

    Args:
        ticker: símbolo
        snap: FundamentalsSnapshot pre-cargado (sino lo busca)
        growth_override: forzar growth rate (sino usa revenue_growth o earnings_growth)
        terminal_growth: tasa de crecimiento terminal (default 2.5%)

    Returns:
        DCFResultado o None si faltan datos críticos.
    """
    if snap is None:
        from services.fundamental_cache import obtener_fundamentales
        snap = obtener_fundamentales(ticker)

    warnings: list[str] = []

    # ── Obtener FCFF (necesitamos un valor en millones USD) ───────────────────
    # yfinance no siempre expone FCFF directamente. Aproximamos:
    #   FCFF ≈ Net Income (profit_margin × revenue)
    # Esto es una APROXIMACIÓN — el FCFF real requiere capex y working capital.
    market_cap = snap.market_cap or 0
    if not market_cap:
        warnings.append("Market cap no disponible — DCF no se puede calcular")
        return None

    pe = snap.pe_ttm or snap.pe_forward
    if not pe or pe <= 0 or pe > 1000:
        warnings.append(f"P/E inválido ({pe}) — DCF no confiable")
        return None

    # Net income ≈ Market_Cap / P/E
    net_income_usd = market_cap / pe
    # FCFF ≈ Net income × 0.85 (asumimos 15% reinversión)
    fcff_aproximado = net_income_usd * 0.85
    warnings.append(
        "FCFF aproximado vía Net Income × 0.85 (no es FCFF real auditado)"
    )

    # ── Growth rate (orden de prioridad) ──────────────────────────────────────
    from services.fundamental_cache import fraccion_segura
    if growth_override is not None:
        growth = growth_override
    else:
        # Usar revenue_growth si está, sino earnings_growth, sino 5% default
        rg = fraccion_segura(snap.revenue_growth)
        eg = fraccion_segura(snap.earnings_growth)
        if rg is not None and 0 < rg < 0.50:    # cap razonable
            growth = rg
        elif eg is not None and 0 < eg < 0.50:
            growth = eg
        else:
            growth = 0.05
            warnings.append("Growth no disponible — asumimos 5% (conservador)")

    # Cap growth a [0, 30%] por sanidad (DCF se rompe con growths absurdos)
    growth = max(0.0, min(0.30, growth))

    # ── Beta para WACC ───────────────────────────────────────────────────────
    beta = snap.beta if snap.beta and 0.1 <= snap.beta <= 3.0 else 1.0
    if not snap.beta:
        warnings.append("Beta no disponible — asumimos 1.0 (mercado)")

    # ── Shares outstanding ───────────────────────────────────────────────────
    shares = snap.shares_outstanding
    if not shares or shares <= 0:
        warnings.append("Shares outstanding no disponible — DCF inválido")
        return None

    # ── WACC ─────────────────────────────────────────────────────────────────
    wacc = _wacc(beta, snap.debt_to_equity)

    # Sanidad: WACC debe ser > terminal_growth (sino la fórmula explota)
    if wacc <= terminal_growth:
        warnings.append(
            f"WACC ({wacc*100:.2f}%) ≤ terminal growth ({terminal_growth*100:.1f}%) — "
            "ajustando WACC a 5% mínimo"
        )
        wacc = max(0.05, terminal_growth + 0.02)

    # ── Proyección 5 años ────────────────────────────────────────────────────
    flujos = _proyectar_fcff(fcff_aproximado, growth, ANIOS_PROYECCION)

    # Terminal value: FCFF año 6 / (WACC - g_terminal)
    fcff_n_plus_1 = flujos[-1] * (1 + terminal_growth)
    terminal_value = fcff_n_plus_1 / (wacc - terminal_growth)

    # Valor presente
    pv_total = _valor_presente_flujos(flujos, wacc, terminal_value)

    # Valor por acción
    valor_intrinseco_usd = pv_total / shares

    # ── Decisión ─────────────────────────────────────────────────────────────
    precio_actual = snap.precio_actual_usd or 0
    if precio_actual <= 0:
        warnings.append("Precio actual no disponible — no se puede comparar")
        margen_seguridad = 0
        recom = "—"
    else:
        margen_seguridad = (valor_intrinseco_usd / precio_actual - 1) * 100
        if margen_seguridad >= 20:
            recom = "INFRAVALORADA"
        elif margen_seguridad >= -10:
            recom = "FAIR"
        else:
            recom = "SOBREVALUADA"

    # ── Sensibilidad ─────────────────────────────────────────────────────────
    sensibilidad = _calcular_sensibilidad(
        fcff_aproximado, growth, wacc, shares, terminal_growth
    )

    return DCFResultado(
        ticker=ticker.upper(),
        precio_actual_usd=round(precio_actual, 2),
        valor_intrinseco_usd=round(valor_intrinseco_usd, 2),
        margen_seguridad_pct=round(margen_seguridad, 1),
        recomendacion_dcf=recom,
        fcff_anual_usd_m=round(fcff_aproximado / 1e6, 1) if fcff_aproximado else None,
        growth_explicito_pct=round(growth * 100, 1),
        wacc_pct=round(wacc * 100, 2),
        terminal_growth_pct=round(terminal_growth * 100, 1),
        beta_usado=round(beta, 2),
        shares_outstanding_m=round(shares / 1e6, 1) if shares else None,
        sensibilidad=sensibilidad,
        warnings=warnings,
    )


# ─── Render HTML compatible con paleta WCAG AA ────────────────────────────────

def dcf_html(dcf: DCFResultado) -> str:
    """HTML del bloque DCF para mostrar dentro del reporte BDI."""
    from ui.color_palette import PALETTE

    if dcf is None:
        return ""

    # Color según recomendación
    if dcf.recomendacion_dcf == "INFRAVALORADA":
        color = PALETTE.success_accent
        color_bg = PALETTE.success_bg
        color_fg = PALETTE.success_fg
    elif dcf.recomendacion_dcf == "FAIR":
        color = PALETTE.warning_accent
        color_bg = PALETTE.warning_bg
        color_fg = PALETTE.warning_fg
    else:
        color = PALETTE.danger_accent
        color_bg = PALETTE.danger_bg
        color_fg = PALETTE.danger_fg

    # Sensibilidad
    sens_rows = ""
    for nombre, esc in (dcf.sensibilidad or {}).items():
        valor = esc.get("valor_por_accion_usd")
        valor_str = f"USD {valor:.2f}" if valor else "—"
        nota = esc.get("nota", "")
        sens_rows += (
            f'<tr style="border-bottom:1px solid {PALETTE.border_subtle};">'
            f'<td style="padding:6px;color:{PALETTE.text_primary};text-transform:capitalize;"><b>{nombre}</b></td>'
            f'<td style="padding:6px;color:{PALETTE.text_primary};">{esc.get("growth_pct", "—")}%</td>'
            f'<td style="padding:6px;color:{PALETTE.text_primary};">{esc.get("wacc_pct", "—")}%</td>'
            f'<td style="padding:6px;color:{PALETTE.text_primary};"><b>{valor_str}</b></td>'
            f'<td style="padding:6px;color:{PALETTE.text_muted};font-size:0.85em;">{nota}</td>'
            f'</tr>'
        )

    warnings_html = ""
    if dcf.warnings:
        items = "".join(f"<li style='color:{PALETTE.text_muted};margin-bottom:3px;'>{w}</li>" for w in dcf.warnings)
        warnings_html = (
            f'<div style="font-size:0.85em;color:{PALETTE.text_muted};margin-top:8px;">'
            f'<b>Asunciones del modelo:</b><ul style="margin:3px 0;padding-left:20px;">{items}</ul>'
            f'</div>'
        )

    return f"""
<div style="background:{PALETTE.surface_card_alt};padding:14px;border-radius:8px;
            border:1px solid {PALETTE.border_subtle};margin:10px 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <b style="color:{color};font-size:1.08em;">
      🧮 Valor intrínseco DCF (modelo 2 etapas)
    </b>
    <span style="background:{color_bg};color:{color_fg};padding:5px 14px;border-radius:14px;
                 font-weight:700;">
      {dcf.recomendacion_dcf}
    </span>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px;">
    <div style="background:{PALETTE.surface_card};padding:10px;border-radius:6px;text-align:center;
                border:1px solid {PALETTE.border_subtle};">
      <div style="font-size:0.8em;color:{PALETTE.text_muted};font-weight:600;">Precio mercado</div>
      <div style="font-size:1.15em;font-weight:700;color:{PALETTE.text_primary};">
        USD {dcf.precio_actual_usd:.2f}
      </div>
    </div>
    <div style="background:{color_bg};padding:10px;border-radius:6px;text-align:center;
                border:1px solid {color};">
      <div style="font-size:0.8em;color:{color_fg};font-weight:600;">Valor intrínseco</div>
      <div style="font-size:1.15em;font-weight:700;color:{color_fg};">
        USD {dcf.valor_intrinseco_usd:.2f}
      </div>
    </div>
    <div style="background:{PALETTE.surface_card};padding:10px;border-radius:6px;text-align:center;
                border:1px solid {PALETTE.border_subtle};">
      <div style="font-size:0.8em;color:{PALETTE.text_muted};font-weight:600;">Margen seguridad</div>
      <div style="font-size:1.15em;font-weight:700;color:{color};">
        {dcf.margen_seguridad_pct:+.1f}%
      </div>
    </div>
  </div>

  <div style="font-size:0.85em;color:{PALETTE.text_secondary};margin-bottom:10px;">
    <b>Inputs:</b>
    FCFF≈ USD {dcf.fcff_anual_usd_m:.0f}M ·
    growth {dcf.growth_explicito_pct:.1f}% ·
    WACC {dcf.wacc_pct:.2f}% ·
    g_terminal {dcf.terminal_growth_pct:.1f}% ·
    β {dcf.beta_usado:.2f} ·
    {dcf.shares_outstanding_m:.0f}M acciones
  </div>

  <details>
    <summary style="cursor:pointer;color:{PALETTE.brand};font-weight:600;">
      📊 Análisis de sensibilidad (±1pp en growth y WACC)
    </summary>
    <table style="width:100%;margin-top:8px;font-size:0.88em;border-collapse:collapse;">
      <thead><tr style="background:{PALETTE.surface_section};">
        <th style="padding:6px;text-align:left;color:{PALETTE.text_secondary};">Escenario</th>
        <th style="padding:6px;text-align:left;color:{PALETTE.text_secondary};">Growth</th>
        <th style="padding:6px;text-align:left;color:{PALETTE.text_secondary};">WACC</th>
        <th style="padding:6px;text-align:left;color:{PALETTE.text_secondary};">Valor/acc</th>
        <th style="padding:6px;text-align:left;color:{PALETTE.text_secondary};">Nota</th>
      </tr></thead>
      <tbody>{sens_rows}</tbody>
    </table>
  </details>

  {warnings_html}
</div>
"""
