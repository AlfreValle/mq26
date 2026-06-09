"""
services/industry_benchmarks.py — Benchmarks por industria específica.

Más granular que el sector amplio del scoring_multifactor:
  - Sector amplio:    "Healthcare" → PE 18 / ROE 18% (genérico)
  - Industria:        "Drug Manufacturers - General" → PE 23.75 / ROE 30.68% (real)

Datos cargados desde `data/industry_benchmarks.json` (editable manualmente
con datos curados de Bloomberg/Investing/Reuters).

Uso:
    from services.industry_benchmarks import obtener_benchmark_industria, comparar_vs_industria

    bench = obtener_benchmark_industria("Drug Manufacturers - General")
    comp = comparar_vs_industria(snap, "Drug Manufacturers - General")
    # → {"pe": {"empresa": 25.89, "industria": 23.75, "ratio": 1.09, "interpretacion": "más caro"}}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BENCHMARKS_PATH = Path(__file__).resolve().parent.parent / "data" / "industry_benchmarks.json"
_CACHE: dict[str, Any] | None = None


def _cargar_benchmarks() -> dict[str, Any]:
    """Carga (con caché en memoria) el JSON de benchmarks por industria."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not _BENCHMARKS_PATH.exists():
        logger.warning("industry_benchmarks: %s no existe", _BENCHMARKS_PATH)
        _CACHE = {}
        return _CACHE
    try:
        _CACHE = json.loads(_BENCHMARKS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("industry_benchmarks: error parseando %s: %s", _BENCHMARKS_PATH, e)
        _CACHE = {}
    return _CACHE


def refresh_benchmarks() -> None:
    """Fuerza recarga desde disco (útil tras editar el JSON manualmente)."""
    global _CACHE
    _CACHE = None
    _cargar_benchmarks()


def listar_industrias() -> list[str]:
    """Industrias específicas con benchmark cargado."""
    b = _cargar_benchmarks()
    return sorted([k for k in b.keys() if not k.startswith("_")])


def obtener_benchmark_industria(industria: str | None) -> dict[str, float] | None:
    """
    Retorna el benchmark de una industria específica si existe.
    Si no hay industria o no está cargada, retorna None.
    """
    if not industria:
        return None
    b = _cargar_benchmarks()
    return b.get(industria)


def obtener_benchmark_sector(sector: str | None) -> dict[str, float] | None:
    """Fallback al benchmark sectorial amplio (genérico)."""
    if not sector:
        return None
    b = _cargar_benchmarks()
    defaults = b.get("_default_sector", {})
    return defaults.get(sector)


def obtener_benchmark(industria: str | None, sector: str | None) -> tuple[dict[str, float] | None, str]:
    """
    Estrategia de fallback en cascada:
      1. Industria específica (mejor: "Drug Manufacturers - General")
      2. Sector amplio fallback ("Healthcare")
    Returns (benchmark, fuente) donde fuente es "industria" | "sector" | "—".
    """
    bench = obtener_benchmark_industria(industria)
    if bench is not None:
        return bench, "industria"
    bench = obtener_benchmark_sector(sector)
    if bench is not None:
        return bench, "sector"
    return None, "—"


# ─── Comparativa empresa vs industria ─────────────────────────────────────────

# Métrica → (snap_field, bench_field, mas_alto_es_mejor)
_METRICAS_COMPARABLES: dict[str, tuple[str, str, bool]] = {
    "P/E TTM":              ("pe_ttm",          "pe_med",                    False),
    "P/E Forward":          ("pe_forward",      "pe_med",                    False),
    "P/B":                  ("pb_ratio",        "pb_med",                    False),
    "P/S":                  ("ps_ratio",        "ps_med",                    False),
    "ROE":                  ("roe",             "roe_med",                   True),
    "ROA":                  ("roa",             "roa_med",                   True),
    "Margen Bruto":         ("gross_margin",    "margen_bruto_med",          True),
    "Margen Operativo":     ("operating_margin","margen_operativo_med",      True),
    "Margen Neto":          ("profit_margin",   "margen_neto_med",           True),
    "Crec. Ingresos":       ("revenue_growth",  "crecimiento_ventas_5y_med", True),
    "Crec. Ganancias":      ("earnings_growth", "crecimiento_bpa_5y_med",    True),
    "Deuda/Equity":         ("debt_to_equity",  "deuda_equity_med",          False),
    "Dividend Yield":       ("dividend_yield",  "dividend_yield_med",        True),
    "Payout":               ("payout_ratio",    "payout_med",                False),
}


def comparar_vs_industria(snap, industria: str | None, sector: str | None = None) -> dict[str, Any]:
    """
    Compara los fundamentales de una empresa con su industria/sector.

    Returns dict con:
        fuente: "industria" | "sector" | "—"
        industria: nombre usado
        metricas: dict {nombre: {empresa, industria, ratio, mejor_que_industria, interpretacion}}
        summary: {n_mejor, n_peor, n_neutral, total_evaluado}
    """
    if sector is None and hasattr(snap, "sector"):
        sector = snap.sector

    bench, fuente = obtener_benchmark(industria, sector)
    if bench is None:
        return {"fuente": "—", "industria": industria or sector or "—", "metricas": {}, "summary": {}}

    metricas: dict[str, dict[str, Any]] = {}
    n_mejor = n_peor = n_neutral = 0

    for nombre, (snap_field, bench_field, mas_alto_mejor) in _METRICAS_COMPARABLES.items():
        valor_emp = getattr(snap, snap_field, None)
        valor_bench = bench.get(bench_field)
        if valor_emp is None or valor_bench is None or valor_emp == 0 or valor_bench == 0:
            continue

        try:
            ratio = float(valor_emp) / float(valor_bench)
        except (TypeError, ValueError, ZeroDivisionError):
            continue

        # Interpretar: si más alto es mejor y ratio > 1.05 → empresa mejor
        if mas_alto_mejor:
            if ratio >= 1.10:
                interp, mejor = "🟢 supera industria", True
                n_mejor += 1
            elif ratio >= 0.95:
                interp, mejor = "🟡 en línea", None
                n_neutral += 1
            else:
                interp, mejor = "🔴 debajo de industria", False
                n_peor += 1
        else:
            # Más bajo es mejor (PE, deuda)
            if ratio <= 0.90:
                interp, mejor = "🟢 mejor (más bajo)", True
                n_mejor += 1
            elif ratio <= 1.05:
                interp, mejor = "🟡 en línea", None
                n_neutral += 1
            else:
                interp, mejor = "🔴 peor (más alto)", False
                n_peor += 1

        metricas[nombre] = {
            "empresa":    round(float(valor_emp), 4),
            "industria":  round(float(valor_bench), 4),
            "ratio":      round(ratio, 2),
            "mejor_que_industria": mejor,
            "interpretacion": interp,
        }

    return {
        "fuente":    fuente,
        "industria": industria if fuente == "industria" else (sector or "—"),
        "metricas":  metricas,
        "summary": {
            "n_mejor":   n_mejor,
            "n_peor":    n_peor,
            "n_neutral": n_neutral,
            "total":     n_mejor + n_peor + n_neutral,
            "score_pct": round((n_mejor / (n_mejor + n_peor + n_neutral)) * 100, 1)
                         if (n_mejor + n_peor + n_neutral) > 0 else 0,
        },
    }


# ─── HTML del bloque comparativo (para incluir en reportes BDI) ───────────────

def comparativa_html(comp: dict[str, Any]) -> str:
    """Renderiza la comparativa empresa-vs-industria como tabla HTML con paleta WCAG AA."""
    from ui.color_palette import PALETTE

    if not comp.get("metricas"):
        return (
            f'<div style="background:{PALETTE.surface_card_alt};padding:10px;border-radius:6px;'
            f'color:{PALETTE.text_muted};font-style:italic;">'
            f'Sin benchmark específico para esta industria. '
            f'Editar <code>data/industry_benchmarks.json</code> para agregarla.'
            f'</div>'
        )

    # Métricas que se renderizan como % (auto-detecta escala con pct_seguro)
    METRICAS_PORCENTAJE = {
        "ROE", "ROA", "Margen Bruto", "Margen Operativo", "Margen Neto",
        "Crec. Ingresos", "Crec. Ganancias", "Dividend Yield", "Payout",
    }

    from services.fundamental_cache import pct_seguro

    rows = ""
    for nombre, m in comp["metricas"].items():
        emp = m["empresa"]
        ind = m["industria"]
        if nombre in METRICAS_PORCENTAJE:
            # Usa pct_seguro: detecta si viene en fracción (0.2642) o % (26.42)
            emp_pct = pct_seguro(emp, decimals=2)
            ind_pct = pct_seguro(ind, decimals=2)
            emp_str = f"{emp_pct:.2f}%" if emp_pct is not None else "—"
            ind_str = f"{ind_pct:.2f}%" if ind_pct is not None else "—"
        else:
            # Múltiplos (P/E, P/B, P/S, etc.)
            emp_str = f"{emp:.2f}"
            ind_str = f"{ind:.2f}"
        # Color según mejor/peor
        mejor = m["mejor_que_industria"]
        if mejor is True:
            row_bg = PALETTE.success_bg
            row_color = PALETTE.success_fg
        elif mejor is False:
            row_bg = PALETTE.danger_bg
            row_color = PALETTE.danger_fg
        else:
            row_bg = PALETTE.surface_card_alt
            row_color = PALETTE.text_primary
        rows += (
            f'<tr style="background:{row_bg};border-bottom:1px solid {PALETTE.border_subtle};">'
            f'<td style="padding:8px 6px;color:{row_color};font-weight:600;">{nombre}</td>'
            f'<td style="padding:8px 6px;color:{row_color};">{emp_str}</td>'
            f'<td style="padding:8px 6px;color:{row_color};">{ind_str}</td>'
            f'<td style="padding:8px 6px;color:{row_color};">{m["interpretacion"]}</td>'
            f'</tr>'
        )

    s = comp.get("summary", {})
    score_color = (
        PALETTE.success_fg if s.get("score_pct", 0) >= 65
        else PALETTE.warning_fg if s.get("score_pct", 0) >= 50
        else PALETTE.danger_fg
    )

    return f"""
<div style="background:{PALETTE.surface_card_alt};padding:14px;border-radius:8px;
            border:1px solid {PALETTE.border_subtle};margin:10px 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <b style="color:{PALETTE.brand};font-size:1.08em;">
      🏭 Empresa vs Industria · <span style="color:{PALETTE.text_primary};">{comp.get("industria", "—")}</span>
    </b>
    <span style="background:{PALETTE.surface_card};padding:5px 12px;border-radius:14px;
                 color:{score_color};font-weight:700;border:1px solid {PALETTE.border_default};">
      Score relativo: {s.get("score_pct", 0):.0f}% ({s.get("n_mejor", 0)}↑ {s.get("n_neutral", 0)}= {s.get("n_peor", 0)}↓)
    </span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:0.92em;">
    <thead><tr style="background:{PALETTE.surface_section};">
      <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Métrica</th>
      <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Empresa</th>
      <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Industria</th>
      <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Lectura</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div style="margin-top:8px;font-size:0.82em;color:{PALETTE.text_muted};">
    Fuente: {comp.get("fuente", "—")} · datos cargados desde data/industry_benchmarks.json
  </div>
</div>
"""


# ─── Enriquecimiento de fundamentales con datos profesionales ─────────────────

def enriquecer_snapshot_con_datos_curados(snap, datos_curados: dict[str, Any]):
    """
    Permite override de campos del snapshot con datos profesionales
    (cuando los de yfinance están desactualizados o erróneos).

    Args:
        snap: FundamentalsSnapshot
        datos_curados: dict con claves del snapshot a sobreescribir.

    Mutates snap in place. Devuelve snap.

    Ejemplo:
        # Datos de JNJ desde Investing.com:
        enriquecer_snapshot_con_datos_curados(snap, {
            "dividend_yield": 0.0232,
            "pe_ttm": 25.89,
            "roe": 0.2642,
            "profit_margin": 0.2183,
            "earnings_growth": -0.5286,  # caída BPA -52.86% vs sector +31.85%
        })
    """
    for campo, valor in datos_curados.items():
        if hasattr(snap, campo):
            setattr(snap, campo, valor)
    # Marcar como enriquecido para trazabilidad
    if hasattr(snap, "errores"):
        snap.errores.append(f"enriquecido_con_datos_curados: {list(datos_curados.keys())}")
    return snap
