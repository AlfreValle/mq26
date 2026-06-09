"""
services/bdi_reports.py — Catálogo de reportes BDI (análisis profesional)

Los reportes BDI son análisis fundamentales + técnicos + sectoriales producidos
por la consultora BDI Latam. Cuando existe un reporte BDI para un ticker, sus
recomendaciones (precio objetivo, stop loss, estrategia escalonada) tienen
prioridad sobre el cálculo dinámico del motor de perlas.

Estructura por reporte:
    data/bdi_reports/<TICKER>_<YYYY-MM>.json

Uso desde código:
    from services.bdi_reports import obtener_reporte_bdi, listar_tickers_con_bdi

    rep = obtener_reporte_bdi("RTX")        # último reporte de RTX
    if rep:
        print(rep.precio_objetivo_usd)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BDI_DIR = Path(__file__).resolve().parent.parent / "data" / "bdi_reports"


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class ReporteBDI:
    """Análisis profesional BDI para un ticker."""
    ticker: str
    fecha_publicacion: str
    recomendacion: str               # "COMPRAR" | "MANTENER" | "VENDER"
    precio_actual_usd: float
    precio_objetivo_usd: float
    potencial_pct: float
    horizonte_meses: int
    calificacion_total: float        # 0-5 (estrellas BDI)
    perfil_minimo: str
    peso_cartera_pct_min: float
    peso_cartera_pct_max: float
    stop_loss_usd: float
    primer_objetivo_usd: float
    objetivo_final_usd: float
    tesis_resumen: str
    razones_compra: list[str]        = field(default_factory=list)
    riesgos: list[str]               = field(default_factory=list)
    tramos_entrada: list[dict]       = field(default_factory=list)
    consenso_analistas: list[dict]   = field(default_factory=list)
    niveles_tecnicos: dict           = field(default_factory=dict)
    datos_clave: dict                = field(default_factory=dict)
    segmentos_negocio: list[dict]    = field(default_factory=list)
    cal_fundamental: float           = 0.0
    cal_tecnico: float               = 0.0
    cal_sectorial: float             = 0.0
    autor: str                       = "BDI Consultora de Inversiones"
    fuentes: list[str]               = field(default_factory=list)
    pdf_path: str | None             = None
    split_negocio: dict              = field(default_factory=dict)
    exchange: str                    = ""
    tipo_cartera_sugerida: str       = ""
    comparativa_industria: dict      = field(default_factory=dict)
    industry: str | None             = None
    sector: str | None               = None
    # ── Nivel A — Capas de confianza enriquecida ──
    calidad_datos: dict              = field(default_factory=dict)
    dcf_valuacion: dict | None       = None
    backtest_setup: dict | None      = None

    @property
    def upside_pct(self) -> float:
        if self.precio_actual_usd <= 0:
            return 0.0
        return round((self.precio_objetivo_usd / self.precio_actual_usd - 1) * 100, 1)

    @property
    def downside_stop_pct(self) -> float:
        if self.precio_actual_usd <= 0:
            return 0.0
        return round((1 - self.stop_loss_usd / self.precio_actual_usd) * 100, 1)

    @property
    def riesgo_recompensa(self) -> float:
        ganancia = self.precio_objetivo_usd - self.precio_actual_usd
        riesgo = self.precio_actual_usd - self.stop_loss_usd
        if riesgo <= 0:
            return 0.0
        return round(ganancia / riesgo, 2)

    def precio_actual_ars(self, ccl: float, ratio_cedear: float = 1.0) -> float:
        """USD subyacente → ARS por CEDEAR (precio_usd × ccl / ratio)."""
        if ccl <= 0 or ratio_cedear <= 0:
            return 0.0
        return round(self.precio_actual_usd * ccl / ratio_cedear, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker":              self.ticker,
            "fecha_publicacion":   self.fecha_publicacion,
            "recomendacion":       self.recomendacion,
            "precio_actual_usd":   self.precio_actual_usd,
            "precio_objetivo_usd": self.precio_objetivo_usd,
            "potencial_pct":       self.potencial_pct,
            "horizonte_meses":     self.horizonte_meses,
            "calificacion_total":  self.calificacion_total,
            "cal_fundamental":     self.cal_fundamental,
            "cal_tecnico":         self.cal_tecnico,
            "cal_sectorial":       self.cal_sectorial,
            "perfil_minimo":       self.perfil_minimo,
            "peso_cartera_pct_min": self.peso_cartera_pct_min,
            "peso_cartera_pct_max": self.peso_cartera_pct_max,
            "stop_loss_usd":       self.stop_loss_usd,
            "primer_objetivo_usd": self.primer_objetivo_usd,
            "objetivo_final_usd":  self.objetivo_final_usd,
            "tesis_resumen":       self.tesis_resumen,
            "razones_compra":      self.razones_compra,
            "riesgos":             self.riesgos,
            "tramos_entrada":      self.tramos_entrada,
            "consenso_analistas":  self.consenso_analistas,
            "niveles_tecnicos":    self.niveles_tecnicos,
            "datos_clave":         self.datos_clave,
            "segmentos_negocio":   self.segmentos_negocio,
            "autor":               self.autor,
            "fuentes":             self.fuentes,
            "pdf_path":            self.pdf_path,
            "split_negocio":       self.split_negocio,
            "exchange":            self.exchange,
            "upside_pct":          self.upside_pct,
            "downside_stop_pct":   self.downside_stop_pct,
            "riesgo_recompensa":   self.riesgo_recompensa,
        }


# ─── Carga de reportes ────────────────────────────────────────────────────────

def _construir_reporte(payload: dict) -> ReporteBDI:
    """Convierte un dict JSON al dataclass ReporteBDI con campos opcionales."""
    return ReporteBDI(
        ticker               = str(payload.get("ticker", "")).upper(),
        fecha_publicacion    = payload.get("fecha_publicacion", ""),
        recomendacion        = payload.get("recomendacion", "MANTENER"),
        precio_actual_usd    = float(payload.get("precio_actual_usd", 0) or 0),
        precio_objetivo_usd  = float(payload.get("precio_objetivo_usd", 0) or 0),
        potencial_pct        = float(payload.get("potencial_pct", 0) or 0),
        horizonte_meses      = int(payload.get("horizonte_meses", 12) or 12),
        calificacion_total   = float(payload.get("calificacion_total", 0) or 0),
        cal_fundamental      = float(payload.get("cal_fundamental", 0) or 0),
        cal_tecnico          = float(payload.get("cal_tecnico", 0) or 0),
        cal_sectorial        = float(payload.get("cal_sectorial", 0) or 0),
        perfil_minimo        = payload.get("perfil_minimo", "Moderado"),
        peso_cartera_pct_min = float(payload.get("peso_cartera_pct_min", 0.03) or 0.03),
        peso_cartera_pct_max = float(payload.get("peso_cartera_pct_max", 0.08) or 0.08),
        stop_loss_usd        = float(payload.get("niveles_seguimiento", {}).get("stop_loss_usd", 0) or 0),
        primer_objetivo_usd  = float(payload.get("niveles_seguimiento", {}).get("primer_objetivo_usd", 0) or 0),
        objetivo_final_usd   = float(payload.get("niveles_seguimiento", {}).get("objetivo_final_usd", 0) or 0),
        tesis_resumen        = payload.get("tesis_resumen", ""),
        razones_compra       = list(payload.get("razones_compra", []) or []),
        riesgos              = list(payload.get("riesgos", []) or []),
        tramos_entrada       = list(payload.get("tramos_entrada", []) or []),
        consenso_analistas   = list(payload.get("consenso_analistas", []) or []),
        niveles_tecnicos     = dict(payload.get("niveles_tecnicos", {}) or {}),
        datos_clave          = dict(payload.get("datos_clave", {}) or {}),
        segmentos_negocio    = list(payload.get("segmentos_negocio", []) or []),
        autor                = payload.get("autor", "BDI Consultora de Inversiones"),
        fuentes              = list(payload.get("fuentes", []) or []),
        pdf_path             = payload.get("pdf_path"),
        split_negocio        = dict(payload.get("split_negocio", {}) or {}),
        exchange             = payload.get("exchange", ""),
        tipo_cartera_sugerida = payload.get("tipo_cartera_sugerida", ""),
        comparativa_industria = dict(payload.get("comparativa_industria", {}) or {}),
        industry              = payload.get("industry"),
        sector                = payload.get("sector"),
        calidad_datos         = dict(payload.get("calidad_datos", {}) or {}),
        dcf_valuacion         = payload.get("dcf_valuacion"),
        backtest_setup        = payload.get("backtest_setup"),
    )


def listar_tickers_con_bdi(incluir_auto: bool = True) -> list[str]:
    """
    Retorna tickers con reporte BDI.

    Args:
        incluir_auto: si True, incluye reportes auto-generados (`*_auto.json`)
                      por el pipeline (bdi_auto_generator). Default True.
    """
    if not _BDI_DIR.exists():
        return []
    tickers = set()
    for f in _BDI_DIR.glob("*.json"):
        nombre = f.stem
        if not incluir_auto and nombre.endswith("_auto"):
            continue
        if "_" in nombre:
            tickers.add(nombre.split("_")[0].upper())
        else:
            tickers.add(nombre.upper())
    return sorted(tickers)


def obtener_reporte_bdi(ticker: str, preferir_manual: bool = True) -> ReporteBDI | None:
    """
    Retorna el reporte BDI más reciente para un ticker.

    Args:
        preferir_manual: si True (default), prefiere reportes manuales (sin sufijo _auto)
                         sobre auto-generados. Si no hay manual, cae al auto.
    """
    if not _BDI_DIR.exists():
        return None
    ticker_u = ticker.upper().strip()
    todos = list(_BDI_DIR.glob(f"{ticker_u}_*.json"))
    if not todos:
        exacto = _BDI_DIR / f"{ticker_u}.json"
        if exacto.exists():
            todos = [exacto]
    if not todos:
        return None

    manuales = [p for p in todos if not p.stem.endswith("_auto")]
    autos    = [p for p in todos if p.stem.endswith("_auto")]

    if preferir_manual and manuales:
        candidatos = sorted(manuales, key=lambda p: p.stem, reverse=True)
    elif autos and not preferir_manual:
        candidatos = sorted(autos, key=lambda p: p.stem, reverse=True)
    else:
        candidatos = sorted(todos, key=lambda p: p.stem, reverse=True)

    try:
        payload = json.loads(candidatos[0].read_text(encoding="utf-8"))
        return _construir_reporte(payload)
    except Exception as e:
        logger.warning("BDI: error leyendo %s: %s", candidatos[0], e)
        return None


def obtener_todos_reportes_bdi() -> dict[str, ReporteBDI]:
    """Retorna {ticker: ReporteBDI} para todos los tickers con reporte."""
    out: dict[str, ReporteBDI] = {}
    for t in listar_tickers_con_bdi():
        r = obtener_reporte_bdi(t)
        if r is not None:
            out[t] = r
    return out


# ─── Render HTML enriquecido ──────────────────────────────────────────────────

def reporte_bdi_html(reporte: ReporteBDI, ccl: float = 1490.0, ratio_cedear: float = 1.0) -> str:
    """
    Genera HTML del análisis BDI con paleta WCAG AA garantizada.
    Todos los pares (bg, fg) tienen contraste >= 4.5:1 sobre fondo claro.
    """
    from ui.color_palette import PALETTE, color_recomendacion

    r = reporte
    estrellas = "★" * int(round(r.calificacion_total)) + "☆" * (5 - int(round(r.calificacion_total)))
    rec_bg, rec_fg = color_recomendacion(r.recomendacion)

    razones_html = "".join(
        f'<li style="margin-bottom:6px;color:{PALETTE.text_primary};">{r}</li>'
        for r in r.razones_compra
    )
    riesgos_html = "".join(
        f'<li style="margin-bottom:6px;color:{PALETTE.text_secondary};">{rg}</li>'
        for rg in r.riesgos
    )

    tramos_rows = ""
    for t in r.tramos_entrada:
        prop_pct = float(t.get("proporcion", 0)) * 100
        px_min = float(t.get("precio_min_usd", 0))
        px_max = float(t.get("precio_max_usd", 0))
        px_min_ars = px_min * ccl / ratio_cedear if ratio_cedear > 0 else 0
        px_max_ars = px_max * ccl / ratio_cedear if ratio_cedear > 0 else 0
        comentario = t.get("comentario", "")
        tramos_rows += (
            f'<tr style="border-bottom:1px solid {PALETTE.border_subtle};">'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};"><b>Tramo {t.get("tramo", "?")}</b></td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};">{prop_pct:.0f}%</td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};">USD {px_min:.0f}–{px_max:.0f}</td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};">ARS {px_min_ars:,.0f}–{px_max_ars:,.0f}</td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_muted};font-size:0.9em;">{comentario}</td>'
            f'</tr>'
        )

    consenso_html = ""
    for c in r.consenso_analistas:
        target = c.get("target_usd")
        target_str = f"USD {float(target):.0f}" if target else c.get("consenso_ibes", "—")
        consenso_html += (
            f'<tr style="border-bottom:1px solid {PALETTE.border_subtle};">'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};">{c.get("fuente", "—")}</td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};">{c.get("recomendacion", "—")}</td>'
            f'<td style="padding:8px 6px;color:{PALETTE.text_primary};"><b>{target_str}</b></td>'
            f'</tr>'
        )

    # Bloque comparativa empresa-vs-industria (si hay datos)
    comparativa_html_str = ""
    if r.comparativa_industria and r.comparativa_industria.get("metricas"):
        try:
            from services.industry_benchmarks import comparativa_html
            comparativa_html_str = comparativa_html(r.comparativa_industria)
        except Exception:
            comparativa_html_str = ""

    # ── Nivel A: DCF valuation block ──
    dcf_html_str = ""
    if r.dcf_valuacion:
        try:
            from services.dcf_simple import DCFResultado, dcf_html
            dcf_obj = DCFResultado(**{
                k: v for k, v in r.dcf_valuacion.items()
                if k in DCFResultado.__dataclass_fields__
            })
            dcf_html_str = dcf_html(dcf_obj)
        except Exception:
            dcf_html_str = ""

    # ── Nivel A: data quality block ──
    dq_html_str = ""
    if r.calidad_datos and r.calidad_datos.get("nivel"):
        try:
            from services.data_quality import DataQualityScore, data_quality_html
            dq_obj = DataQualityScore(**{
                k: v for k, v in r.calidad_datos.items()
                if k in DataQualityScore.__dataclass_fields__
            })
            dq_html_str = data_quality_html(dq_obj)
        except Exception:
            dq_html_str = ""

    pdf_link = ""
    if r.pdf_path:
        pdf_link = (
            f'<div style="margin-top:8px;font-size:0.9em;">'
            f'📄 <a href="file://{r.pdf_path}" target="_blank" '
            f'style="color:{PALETTE.brand};text-decoration:underline;">'
            f'Abrir informe BDI completo (PDF)</a></div>'
        )

    # Detectar origen: auto MQ26 vs externo
    autor_lower = (r.autor or "").lower()
    es_externo = ("bdi consultora" in autor_lower or
                  "consultora" in autor_lower) and "mq26" not in autor_lower
    if es_externo:
        titulo_origen = f"📊 Análisis Externo · {r.ticker}"
        color_acento = PALETTE.success_accent     # verde para externo
        autor_label = r.autor
    else:
        titulo_origen = f"🤖 Análisis MQ26 · {r.ticker}"
        color_acento = PALETTE.brand              # azul corp para MQ26
        autor_label = r.autor or "Motor MQ26 (Fundamental + Multifactor + Generator)"

    html = f"""
<div style="background:{PALETTE.surface_card};
            border:2px solid {color_acento};border-radius:10px;padding:18px;
            margin:12px 0;line-height:1.6;color:{PALETTE.text_primary};">

  <div style="display:flex;justify-content:space-between;align-items:center;
              border-bottom:1px solid {PALETTE.border_default};padding-bottom:10px;margin-bottom:14px;">
    <div>
      <div style="font-size:1.3em;font-weight:700;color:{color_acento};">
        {titulo_origen}
      </div>
      <div style="font-size:0.9em;color:{PALETTE.text_muted};margin-top:3px;">
        {autor_label} · publicado {r.fecha_publicacion}
      </div>
    </div>
    <div style="text-align:right;">
      <div style="background:{rec_bg};color:{rec_fg};padding:6px 14px;
                  border-radius:20px;font-weight:700;display:inline-block;">
        {r.recomendacion}
      </div>
      <div style="font-size:1.4em;color:{PALETTE.warning_accent};margin-top:4px;">{estrellas}</div>
      <div style="font-size:0.85em;color:{PALETTE.text_secondary};">{r.calificacion_total:.2f}/5</div>
    </div>
  </div>

  <div style="background:{PALETTE.surface_highlight};padding:10px 14px;border-radius:6px;
              border-left:4px solid {PALETTE.warning_accent};margin-bottom:14px;
              color:{PALETTE.warning_fg};">
    <b>🎯 Tesis ejecutiva:</b> {r.tesis_resumen}
  </div>

  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
    <div style="background:{PALETTE.surface_card_alt};padding:10px;border-radius:6px;
                text-align:center;border:1px solid {PALETTE.border_subtle};">
      <div style="font-size:0.8em;color:{PALETTE.text_muted};font-weight:600;">Precio actual</div>
      <div style="font-size:1.15em;font-weight:700;color:{PALETTE.text_primary};">USD {r.precio_actual_usd:.2f}</div>
    </div>
    <div style="background:{PALETTE.success_bg};padding:10px;border-radius:6px;
                text-align:center;border:1px solid {PALETTE.success_accent};">
      <div style="font-size:0.8em;color:{PALETTE.success_fg};font-weight:600;">🎯 Objetivo</div>
      <div style="font-size:1.15em;font-weight:700;color:{PALETTE.success_fg};">USD {r.precio_objetivo_usd:.2f}</div>
      <div style="font-size:0.85em;color:{PALETTE.success_fg};font-weight:600;">+{r.upside_pct:.1f}%</div>
    </div>
    <div style="background:{PALETTE.danger_bg};padding:10px;border-radius:6px;
                text-align:center;border:1px solid {PALETTE.danger_accent};">
      <div style="font-size:0.8em;color:{PALETTE.danger_fg};font-weight:600;">🛑 Stop loss</div>
      <div style="font-size:1.15em;font-weight:700;color:{PALETTE.danger_fg};">USD {r.stop_loss_usd:.2f}</div>
      <div style="font-size:0.85em;color:{PALETTE.danger_fg};font-weight:600;">-{r.downside_stop_pct:.1f}%</div>
    </div>
    <div style="background:{PALETTE.info_bg};padding:10px;border-radius:6px;
                text-align:center;border:1px solid {PALETTE.info_accent};">
      <div style="font-size:0.8em;color:{PALETTE.info_fg};font-weight:600;">R/R · Horizonte</div>
      <div style="font-size:1.15em;font-weight:700;color:{PALETTE.info_fg};">{r.riesgo_recompensa:.1f}:1</div>
      <div style="font-size:0.85em;color:{PALETTE.info_fg};font-weight:600;">{r.horizonte_meses} meses</div>
    </div>
  </div>

  <div style="margin-bottom:14px;">
    <b style="color:{PALETTE.success_accent};font-size:1.05em;">
      ✓ Razones de compra ({len(r.razones_compra)})
    </b>
    <ul style="margin:6px 0 0 0;padding-left:22px;">{razones_html}</ul>
  </div>

  <div style="margin-bottom:14px;">
    <b style="color:{PALETTE.warning_accent};font-size:1.05em;">
      ⚠️ Riesgos a tener en cuenta ({len(r.riesgos)})
    </b>
    <ul style="margin:6px 0 0 0;padding-left:22px;">{riesgos_html}</ul>
  </div>

  <div style="background:{PALETTE.surface_card_alt};padding:12px;border-radius:6px;
              border:1px solid {PALETTE.border_subtle};margin-bottom:14px;">
    <b style="color:{PALETTE.brand};font-size:1.05em;">🎯 Estrategia de entrada escalonada</b>
    <table style="width:100%;margin-top:8px;font-size:0.92em;border-collapse:collapse;">
      <thead><tr style="background:{PALETTE.surface_section};">
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Tramo</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">%</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">USD</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">ARS (CEDEAR)</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Comentario</th>
      </tr></thead>
      <tbody>{tramos_rows}</tbody>
    </table>
  </div>

  <div style="background:{PALETTE.surface_card_alt};padding:12px;border-radius:6px;
              border:1px solid {PALETTE.border_subtle};margin-bottom:8px;">
    <b style="color:{PALETTE.brand};font-size:1.05em;">👥 Consenso de analistas externos</b>
    <table style="width:100%;margin-top:8px;font-size:0.92em;border-collapse:collapse;">
      <thead><tr style="background:{PALETTE.surface_section};">
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Fuente</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Recomendación</th>
        <th style="padding:8px 6px;text-align:left;color:{PALETTE.text_secondary};">Target</th>
      </tr></thead>
      <tbody>{consenso_html}</tbody>
    </table>
  </div>

  {comparativa_html_str}

  {dcf_html_str}

  {dq_html_str}

  <div style="font-size:0.85em;color:{PALETTE.text_secondary};
              border-top:1px solid {PALETTE.border_subtle};
              padding-top:10px;margin-top:8px;">
    Perfil mínimo: <b style="color:{PALETTE.text_primary};">{r.perfil_minimo}</b> ·
    Peso sugerido: <b style="color:{PALETTE.text_primary};">{r.peso_cartera_pct_min*100:.0f}%–{r.peso_cartera_pct_max*100:.0f}%</b> ·
    Cal. detalle: Fundamental <b>{r.cal_fundamental:.0f}/5</b> · Técnico <b>{r.cal_tecnico:.0f}/5</b> · Sectorial <b>{r.cal_sectorial:.0f}/5</b>
    {pdf_link}
  </div>
</div>
"""
    return html
