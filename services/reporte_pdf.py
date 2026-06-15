"""
services/reporte_pdf.py — Reporte exportable PDF completo, profesional y adaptado
al cliente usando fpdf2.

Estructura del reporte:
  1. Portada con datos del cliente y fecha.
  2. Resumen ejecutivo: métricas clave de la cartera.
  3. Composición de cartera: tabla de activos con pesos, rendimiento esperado y riesgo.
  4. Análisis de régimen de volatilidad.
  5. Resultados de stress test (escenarios macroeconómicos).
  6. Órdenes de rebalanceo (si se proveen).
  7. Nota legal / disclaimer.

Uso:
    from services.reporte_pdf import generar_reporte_pdf, ReporteInput

    inp = ReporteInput(
        nombre_cliente="Familia García",
        capital_total_ars=10_000_000,
        ...
    )
    pdf_bytes = generar_reporte_pdf(inp)
    with open("reporte.pdf", "wb") as f:
        f.write(pdf_bytes)
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ─── Colores corporativos ─────────────────────────────────────────────────────
_AZUL_OSCURO  = (14,  42,  71)    # encabezados principales
_AZUL_MEDIO   = (26,  82, 118)    # filas alternas
_GRIS_CLARO   = (245, 246, 248)   # fondo de filas pares
_BLANCO       = (255, 255, 255)
_NEGRO        = (30,  30,  30)
_VERDE        = (39, 174,  96)    # positivo
_ROJO         = (192,  57,  43)   # negativo / alerta
_AMARILLO     = (243, 156,  18)   # advertencia


# ─── Estructuras de datos de entrada ─────────────────────────────────────────

@dataclass
class FilaCartera:
    ticker:           str
    nombre:           str = ""
    tipo_activo:      str = ""
    moneda:           str = "ARS"
    peso_pct:         float = 0.0
    retorno_esp_pct:  float = 0.0
    vol_anual_pct:    float = 0.0
    sharpe:           float = 0.0


@dataclass
class FilaEscenario:
    nombre:              str
    descripcion:         str
    impacto_cartera_pct: float
    impacto_benchmark_pct: float = 0.0


@dataclass
class FilaRebalanceo:
    ticker:      str
    tipo:        str        # COMPRA / VENTA / HOLD
    delta_pct:   float
    monto_ars:   float
    prioridad:   int = 2


@dataclass
class MetricasCartera:
    retorno_esperado_pct: float = 0.0
    vol_anual_pct:        float = 0.0
    sharpe:               float = 0.0
    sortino:              float = 0.0
    max_drawdown_pct:     float = 0.0
    cvar_95_pct:          float = 0.0
    beta_vs_merval:       float | None = None
    tracking_error_pct:   float | None = None


@dataclass
class ReporteInput:
    """Toda la información necesaria para generar el PDF."""
    nombre_cliente:       str
    capital_total_ars:    float
    fecha_reporte:        date = field(default_factory=date.today)
    ccl:                  float = 1.0

    # Métricas globales
    metricas:             MetricasCartera = field(default_factory=MetricasCartera)

    # Composición
    filas_cartera:        list[FilaCartera]          = field(default_factory=list)

    # Régimen
    regimen_actual:       str = "NORMAL"
    vol_actual_ann_pct:   float = 0.0
    pct_dias_crisis:      float = 0.0

    # Stress test
    escenarios:           list[FilaEscenario]        = field(default_factory=list)

    # Rebalanceo
    ordenes_rebalanceo:   list[FilaRebalanceo]        = field(default_factory=list)
    turnover_pct:         float = 0.0
    costo_total_ars:      float = 0.0

    # Personalización
    nombre_empresa:       str = "MQ Capital"
    subtitulo_reporte:    str = "Informe de Gestión de Cartera"
    disclaimer:           str = (
        "Este documento es de carácter informativo y no constituye una recomendación "
        "de inversión. Los rendimientos pasados no garantizan resultados futuros. "
        "Toda inversión implica riesgos, incluyendo la posible pérdida del capital "
        "invertido. Este reporte ha sido preparado exclusivamente para el cliente "
        "indicado y no debe ser distribuido a terceros sin autorización expresa."
    )
    metadata:             dict[str, Any] = field(default_factory=dict)


# ─── Construcción del PDF ─────────────────────────────────────────────────────

def _try_import_fpdf():
    try:
        from fpdf import FPDF  # noqa: PLC0415
        return FPDF
    except ImportError as e:
        raise ImportError(
            "fpdf2 no está instalado. Ejecutá: pip install fpdf2"
        ) from e


class _ReportePDF:
    """Builder interno — no expongas directamente; usa generar_reporte_pdf()."""

    _COL_W_TICKER  = 28
    _COL_W_NOMBRE  = 48
    _COL_W_TIPO    = 28
    _COL_W_MONEDA  = 16
    _COL_W_PESO    = 18
    _COL_W_RET     = 22
    _COL_W_VOL     = 22
    _COL_W_SHARPE  = 18
    _MARGIN        = 15

    def __init__(self, inp: ReporteInput) -> None:
        FPDF = _try_import_fpdf()

        class _PDF(FPDF):
            def header(self_pdf):
                pass
            def footer(self_pdf):
                self_pdf.set_y(-12)
                self_pdf.set_font("Helvetica", "I", 7)
                self_pdf.set_text_color(*_GRIS_CLARO)
                self_pdf.set_text_color(150, 150, 150)
                self_pdf.cell(0, 5, f"Pag. {self_pdf.page_no()} - {inp.nombre_empresa} - Confidencial",
                              align="C")

        self.pdf = _PDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.inp = inp

    # ── Helpers de estilo ──────────────────────────────────────────────────────

    def _set_font(self, style: str = "", size: int = 10):
        self.pdf.set_font("Helvetica", style, size)

    def _h1(self, texto: str, *, fill: bool = True):
        self.pdf.set_fill_color(*_AZUL_OSCURO)
        self.pdf.set_text_color(*_BLANCO)
        self._set_font("B", 13)
        self.pdf.cell(0, 9, texto.upper(), ln=True, fill=fill, align="L")
        self.pdf.ln(2)
        self.pdf.set_text_color(*_NEGRO)

    def _h2(self, texto: str):
        self.pdf.set_fill_color(*_AZUL_MEDIO)
        self.pdf.set_text_color(*_BLANCO)
        self._set_font("B", 10)
        self.pdf.cell(0, 7, f"  {texto}", ln=True, fill=True, align="L")
        self.pdf.ln(1)
        self.pdf.set_text_color(*_NEGRO)

    def _par(self, texto: str, size: int = 9):
        self._set_font("", size)
        self.pdf.set_text_color(*_NEGRO)
        self.pdf.multi_cell(0, 5, texto)
        self.pdf.ln(1)

    def _kv(self, label: str, valor: str, col_w: float = 60.0):
        self._set_font("B", 9)
        self.pdf.set_text_color(*_AZUL_OSCURO)
        self.pdf.cell(col_w, 6, label + ":", ln=False)
        self._set_font("", 9)
        self.pdf.set_text_color(*_NEGRO)
        self.pdf.cell(0, 6, valor, ln=True)

    def _color_valor(self, v: float) -> tuple:
        if v > 0:
            return _VERDE
        if v < 0:
            return _ROJO
        return _NEGRO

    def _fmt_pct(self, v: float, decimals: int = 2) -> str:
        return f"{v:+.{decimals}f} %"

    def _fmt_ars(self, v: float) -> str:
        if abs(v) >= 1_000_000:
            return f"$ {v/1_000_000:.2f} M"
        if abs(v) >= 1_000:
            return f"$ {v/1_000:.1f} k"
        return f"$ {v:.0f}"

    # ── Páginas ────────────────────────────────────────────────────────────────

    def _portada(self):
        p = self.pdf
        inp = self.inp

        p.add_page()
        # Banda superior
        p.set_fill_color(*_AZUL_OSCURO)
        p.rect(0, 0, 210, 55, "F")

        # Nombre empresa
        p.set_xy(self._MARGIN, 12)
        self._set_font("B", 22)
        p.set_text_color(*_BLANCO)
        p.cell(0, 12, inp.nombre_empresa, ln=True, align="L")

        # Subtítulo
        p.set_x(self._MARGIN)
        self._set_font("", 12)
        p.set_text_color(200, 215, 230)
        p.cell(0, 8, inp.subtitulo_reporte, ln=True, align="L")

        p.ln(20)
        p.set_text_color(*_NEGRO)

        # Datos del cliente
        self._h2("Datos del Cliente")
        p.ln(3)
        self._kv("Cliente",        inp.nombre_cliente)
        self._kv("Fecha",          inp.fecha_reporte.strftime("%d de %B de %Y"))
        self._kv("AUM (ARS)",      self._fmt_ars(inp.capital_total_ars))
        self._kv("AUM (USD)",      self._fmt_ars(inp.capital_total_ars / max(inp.ccl, 1.0)))
        self._kv("CCL referencia", f"$ {inp.ccl:,.1f}")
        p.ln(8)

        # Régimen actual
        color_regimen = {
            "CRISIS":  _ROJO,
            "NORMAL":  _NEGRO,
            "LOW_VOL": _VERDE,
        }.get(inp.regimen_actual, _NEGRO)
        self._set_font("B", 10)
        p.set_text_color(*_AZUL_OSCURO)
        p.cell(60, 6, "Régimen de mercado actual:", ln=False)
        self._set_font("B", 10)
        p.set_text_color(*color_regimen)
        p.cell(0, 6, f" {inp.regimen_actual}  (vol. {inp.vol_actual_ann_pct:.1f} % anual)", ln=True)
        p.set_text_color(*_NEGRO)

    def _resumen_ejecutivo(self):
        p = self.pdf
        inp = self.inp
        m = inp.metricas

        p.add_page()
        self._h1("Resumen Ejecutivo")

        # Tarjetas de métricas 2×4
        campos = [
            ("Retorno Esperado",    f"{m.retorno_esperado_pct:.2f} %", m.retorno_esperado_pct > 0),
            ("Volatilidad Anual",   f"{m.vol_anual_pct:.2f} %",        None),
            ("Ratio Sharpe",        f"{m.sharpe:.3f}",                 m.sharpe > 1.0),
            ("Ratio Sortino",       f"{m.sortino:.3f}",                m.sortino > 1.0),
            ("Máx. Drawdown",       f"{m.max_drawdown_pct:.2f} %",     m.max_drawdown_pct > -15),
            ("CVaR 95 %",           f"{m.cvar_95_pct:.2f} %",          m.cvar_95_pct < 3.0),
        ]
        if m.beta_vs_merval is not None:
            campos.append(("Beta vs Merval", f"{m.beta_vs_merval:.2f}", None))
        if m.tracking_error_pct is not None:
            campos.append(("Tracking Error", f"{m.tracking_error_pct:.2f} %", None))

        card_w = (p.w - 2 * self._MARGIN - 4) / 4
        card_h = 20

        for i, (label, valor, bueno) in enumerate(campos):
            col = i % 4
            if col == 0 and i > 0:
                p.ln(card_h + 3)
            x = self._MARGIN + col * (card_w + 1.5)
            y = p.get_y()

            p.set_xy(x, y)
            p.set_fill_color(*_GRIS_CLARO)
            p.rect(x, y, card_w, card_h, "F")

            # Color del valor
            if bueno is True:
                vc = _VERDE
            elif bueno is False:
                vc = _ROJO
            else:
                vc = _AZUL_OSCURO

            p.set_xy(x + 2, y + 2)
            self._set_font("", 7)
            p.set_text_color(100, 100, 100)
            p.cell(card_w - 4, 5, label, ln=False)

            p.set_xy(x + 2, y + 8)
            self._set_font("B", 12)
            p.set_text_color(*vc)
            p.cell(card_w - 4, 8, valor, ln=False)

        p.ln(card_h + 5)
        p.set_text_color(*_NEGRO)

    def _composicion_cartera(self):
        p = self.pdf
        inp = self.inp

        p.add_page()
        self._h1("Composición de Cartera")

        if not inp.filas_cartera:
            self._par("Sin datos de composición disponibles.")
            return

        # Cabecera de tabla
        cols = [
            ("Ticker",   self._COL_W_TICKER,  "L"),
            ("Activo",   self._COL_W_NOMBRE,  "L"),
            ("Tipo",     self._COL_W_TIPO,    "L"),
            ("Moneda",   self._COL_W_MONEDA,  "C"),
            ("Peso %",   self._COL_W_PESO,    "R"),
            ("Ret. esp", self._COL_W_RET,     "R"),
            ("Vol. an.", self._COL_W_VOL,     "R"),
            ("Sharpe",   self._COL_W_SHARPE,  "R"),
        ]
        p.set_fill_color(*_AZUL_OSCURO)
        p.set_text_color(*_BLANCO)
        self._set_font("B", 8)
        for col_name, col_w, col_align in cols:
            p.cell(col_w, 7, col_name, border=0, align=col_align, fill=True)
        p.ln(7)

        # Filas
        for i, fila in enumerate(inp.filas_cartera):
            bg = _GRIS_CLARO if i % 2 == 0 else _BLANCO
            p.set_fill_color(*bg)
            p.set_text_color(*_NEGRO)
            self._set_font("", 8)

            row_data = [
                (fila.ticker,                          self._COL_W_TICKER, "L"),
                (fila.nombre[:22],                     self._COL_W_NOMBRE, "L"),
                (fila.tipo_activo[:16],                self._COL_W_TIPO,   "L"),
                (fila.moneda,                          self._COL_W_MONEDA, "C"),
                (f"{fila.peso_pct:.2f} %",             self._COL_W_PESO,   "R"),
                (f"{fila.retorno_esp_pct:+.2f} %",     self._COL_W_RET,    "R"),
                (f"{fila.vol_anual_pct:.2f} %",        self._COL_W_VOL,    "R"),
                (f"{fila.sharpe:.2f}",                 self._COL_W_SHARPE, "R"),
            ]
            for val, w, align in row_data:
                p.cell(w, 6, val, border=0, align=align, fill=True)
            p.ln(6)

        # Total
        total_peso = sum(f.peso_pct for f in inp.filas_cartera)
        p.set_fill_color(*_AZUL_MEDIO)
        p.set_text_color(*_BLANCO)
        self._set_font("B", 8)
        p.cell(self._COL_W_TICKER + self._COL_W_NOMBRE + self._COL_W_TIPO + self._COL_W_MONEDA,
               6, "TOTAL", fill=True, align="L")
        p.cell(self._COL_W_PESO, 6, f"{total_peso:.2f} %", fill=True, align="R")
        p.ln(8)
        p.set_text_color(*_NEGRO)

    def _regimen_y_riesgo(self):
        p = self.pdf
        inp = self.inp

        self._h2("Régimen de Volatilidad")
        p.ln(2)
        self._kv("Régimen actual",       inp.regimen_actual)
        self._kv("Volatilidad actual",   f"{inp.vol_actual_ann_pct:.2f} % anual")
        self._kv("% días en crisis (histórico)", f"{inp.pct_dias_crisis * 100:.1f} %")
        p.ln(4)

    def _stress_test(self):
        p = self.pdf
        inp = self.inp

        if not inp.escenarios:
            return

        p.add_page()
        self._h1("Análisis de Escenarios (Stress Test)")
        self._par(
            "Los escenarios a continuación simulan el impacto de shocks macroeconómicos "
            "sobre la cartera actual, manteniendo los pesos fijos.",
        )

        # Cabecera
        p.set_fill_color(*_AZUL_OSCURO)
        p.set_text_color(*_BLANCO)
        self._set_font("B", 8)
        p.cell(55, 7, "Escenario",   fill=True, align="L")
        p.cell(70, 7, "Descripción", fill=True, align="L")
        p.cell(35, 7, "Impacto Cartera", fill=True, align="R")
        p.cell(30, 7, "Vs Benchmark",    fill=True, align="R")
        p.ln(7)

        for i, esc in enumerate(inp.escenarios):
            bg = _GRIS_CLARO if i % 2 == 0 else _BLANCO
            p.set_fill_color(*bg)
            p.set_text_color(*_NEGRO)
            self._set_font("", 8)
            p.cell(55, 6, esc.nombre[:30], fill=True, align="L")
            p.cell(70, 6, esc.descripcion[:40], fill=True, align="L")

            # Color según impacto
            vc = _VERDE if esc.impacto_cartera_pct > 0 else _ROJO
            p.set_text_color(*vc)
            self._set_font("B", 8)
            p.cell(35, 6, f"{esc.impacto_cartera_pct:+.2f} %", fill=True, align="R")

            vc2 = _VERDE if esc.impacto_benchmark_pct > 0 else _ROJO
            p.set_text_color(*vc2)
            p.cell(30, 6, f"{esc.impacto_benchmark_pct:+.2f} %", fill=True, align="R")
            p.ln(6)
            p.set_text_color(*_NEGRO)

    def _rebalanceo(self):
        p = self.pdf
        inp = self.inp

        if not inp.ordenes_rebalanceo:
            return

        self._h2("Órdenes de Rebalanceo")
        p.ln(2)

        n_compras = sum(1 for o in inp.ordenes_rebalanceo if o.tipo == "COMPRA")
        n_ventas  = sum(1 for o in inp.ordenes_rebalanceo if o.tipo == "VENTA")
        n_holds   = sum(1 for o in inp.ordenes_rebalanceo if o.tipo == "HOLD")

        self._kv("Turnover estimado",    f"{inp.turnover_pct:.2f} %")
        self._kv("Costo total (ARS)",    self._fmt_ars(inp.costo_total_ars))
        self._kv("Órdenes COMPRA",       str(n_compras))
        self._kv("Órdenes VENTA",        str(n_ventas))
        self._kv("Sin cambio (HOLD)",    str(n_holds))
        p.ln(3)

        # Tabla — solo COMPRA y VENTA
        activas = [o for o in inp.ordenes_rebalanceo if o.tipo != "HOLD"]
        if not activas:
            self._par("No se requieren órdenes activas con la banda de tolerancia actual.")
            return

        p.set_fill_color(*_AZUL_OSCURO)
        p.set_text_color(*_BLANCO)
        self._set_font("B", 8)
        p.cell(30, 7, "Ticker",    fill=True, align="L")
        p.cell(22, 7, "Tipo",      fill=True, align="C")
        p.cell(28, 7, "Delta %",   fill=True, align="R")
        p.cell(45, 7, "Monto ARS", fill=True, align="R")
        p.cell(20, 7, "Prioridad", fill=True, align="C")
        p.ln(7)

        for i, o in enumerate(activas):
            bg = _GRIS_CLARO if i % 2 == 0 else _BLANCO
            p.set_fill_color(*bg)
            self._set_font("", 8)
            p.set_text_color(*_NEGRO)
            p.cell(30, 6, o.ticker, fill=True, align="L")

            vc = _VERDE if o.tipo == "COMPRA" else _ROJO
            p.set_text_color(*vc)
            self._set_font("B", 8)
            p.cell(22, 6, o.tipo, fill=True, align="C")

            p.set_text_color(*_NEGRO)
            self._set_font("", 8)
            p.cell(28, 6, f"{o.delta_pct:+.2f} %",      fill=True, align="R")
            p.cell(45, 6, self._fmt_ars(o.monto_ars),    fill=True, align="R")
            prio_label = {1: "Alta", 2: "Media", 3: "Baja"}.get(o.prioridad, "-")
            p.cell(20, 6, prio_label, fill=True, align="C")
            p.ln(6)

        p.ln(4)

    def _disclaimer(self):
        p = self.pdf
        inp = self.inp
        p.add_page()
        self._h1("Nota Legal y Descargo de Responsabilidad")
        p.ln(2)
        self._set_font("", 8)
        p.set_text_color(80, 80, 80)
        p.multi_cell(0, 5, inp.disclaimer)
        p.ln(4)

        self._set_font("I", 7)
        p.set_text_color(130, 130, 130)
        p.cell(0, 5,
               f"Generado el {inp.fecha_reporte.strftime('%d/%m/%Y')} - {inp.nombre_empresa}",
               align="C")

    # ── Ensamble ───────────────────────────────────────────────────────────────

    def build(self) -> bytes:
        self._portada()
        self._resumen_ejecutivo()
        self._composicion_cartera()
        self._regimen_y_riesgo()
        self._stress_test()
        self._rebalanceo()
        self._disclaimer()

        buf = io.BytesIO()
        # fpdf2 ≥ 2.7.x: output() sin destino devuelve bytes
        raw = self.pdf.output()
        if isinstance(raw, (bytes, bytearray)):
            buf.write(raw)
        else:
            buf.write(raw.encode("latin-1"))
        return buf.getvalue()


# ─── API pública ──────────────────────────────────────────────────────────────

def generar_reporte_pdf(inp: ReporteInput) -> bytes:
    """
    Genera el PDF completo y devuelve los bytes crudos.

    Ejemplo:
        pdf_bytes = generar_reporte_pdf(inp)
        with open("reporte_cliente.pdf", "wb") as f:
            f.write(pdf_bytes)
    """
    builder = _ReportePDF(inp)
    return builder.build()


def reporte_desde_cartera(
    *,
    nombre_cliente: str,
    capital_total_ars: float,
    ccl: float,
    pesos_dict: dict[str, float],
    metricas_dict: dict[str, float] | None = None,
    escenarios_dict: list[dict] | None = None,
    ordenes_dict: list[dict] | None = None,
    regime_dict: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> bytes:
    """
    Helper de alto nivel que construye ReporteInput desde dicts planos
    (útil para llamar desde FastAPI o Streamlit sin instanciar dataclasses).

    pesos_dict:   {ticker: peso_pct}
    metricas_dict: claves = campos de MetricasCartera
    escenarios_dict: lista de dicts con claves = campos de FilaEscenario
    ordenes_dict: lista de dicts con claves = campos de FilaRebalanceo
    regime_dict: claves = campos de ReporteInput relacionados al régimen
    """
    from config import SECTORES  # noqa: PLC0415 — opcional; no falla si no existe

    filas: list[FilaCartera] = []
    for ticker, peso in sorted(pesos_dict.items(), key=lambda x: -x[1]):
        sector = ""
        try:
            sector = SECTORES.get(ticker, "")
        except Exception:
            pass
        filas.append(FilaCartera(
            ticker      = ticker,
            nombre      = ticker,
            tipo_activo = sector,
            peso_pct    = float(peso),
        ))

    m_raw = metricas_dict or {}
    metricas = MetricasCartera(
        retorno_esperado_pct = float(m_raw.get("retorno_esperado_pct", 0.0)),
        vol_anual_pct        = float(m_raw.get("vol_anual_pct", 0.0)),
        sharpe               = float(m_raw.get("sharpe", 0.0)),
        sortino              = float(m_raw.get("sortino", 0.0)),
        max_drawdown_pct     = float(m_raw.get("max_drawdown_pct", 0.0)),
        cvar_95_pct          = float(m_raw.get("cvar_95_pct", 0.0)),
        beta_vs_merval       = m_raw.get("beta_vs_merval"),
        tracking_error_pct   = m_raw.get("tracking_error_pct"),
    )

    escenarios: list[FilaEscenario] = []
    for e in (escenarios_dict or []):
        escenarios.append(FilaEscenario(
            nombre                = str(e.get("nombre", "")),
            descripcion           = str(e.get("descripcion", "")),
            impacto_cartera_pct   = float(e.get("impacto_cartera_pct", 0.0)),
            impacto_benchmark_pct = float(e.get("impacto_benchmark_pct", 0.0)),
        ))

    ordenes: list[FilaRebalanceo] = []
    for o in (ordenes_dict or []):
        ordenes.append(FilaRebalanceo(
            ticker    = str(o.get("ticker", "")),
            tipo      = str(o.get("tipo", "HOLD")),
            delta_pct = float(o.get("delta_pct", 0.0)),
            monto_ars = float(o.get("monto_ars", 0.0)),
            prioridad = int(o.get("prioridad", 2)),
        ))

    rg = regime_dict or {}
    inp = ReporteInput(
        nombre_cliente      = nombre_cliente,
        capital_total_ars   = capital_total_ars,
        ccl                 = ccl,
        metricas            = metricas,
        filas_cartera       = filas,
        escenarios          = escenarios,
        ordenes_rebalanceo  = ordenes,
        regimen_actual      = str(rg.get("regimen_actual", "NORMAL")),
        vol_actual_ann_pct  = float(rg.get("vol_actual_ann_pct", 0.0)),
        pct_dias_crisis     = float(rg.get("pct_crisis", 0.0)),
        turnover_pct        = float(rg.get("turnover_pct", 0.0)),
        costo_total_ars     = float(rg.get("costo_total_ars", 0.0)),
        metadata            = metadata or {},
    )
    return generar_reporte_pdf(inp)
