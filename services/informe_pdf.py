"""
services/informe_pdf.py — informe de cartera del cliente en PDF (entregable).

Genera un PDF de 1-2 páginas (reportlab — puro Python, sin dependencias de
sistema, Windows-friendly) desde el diagnóstico y la recomendación que ya
existen. Reusa el resumen en lenguaje natural (H1) y el "por qué" de cada activo.

Función pura: datos → bytes (para st.download_button). No Streamlit.
Si reportlab no está instalado, lanza RuntimeError con instrucción clara.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

_ACCENT = "#4f8ef7"  # azul de marca (consistente con --c-accent)


def _semaforo_txt(diag: Any) -> str:
    sem = getattr(diag, "semaforo", None)
    val = str(getattr(sem, "value", None) or sem or "neutro").lower()
    return {"verde": "Saludable", "amarillo": "Para revisar",
            "rojo": "Necesita atención"}.get(val, "Sin datos")


def generar_informe_pdf(
    *,
    cliente_nombre: str,
    perfil: str,
    diag: Any = None,
    recomendacion: Any = None,
    metricas: dict | None = None,
    ccl: float = 0.0,
) -> bytes:
    """Devuelve el informe del cliente como bytes PDF. Pura, sin Streamlit."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Falta reportlab para generar el PDF. Instalá: pip install reportlab"
        ) from e

    metricas = metricas or {}
    nombre_corto = str(cliente_nombre or "Cliente").split("|")[0].strip() or "Cliente"
    accent = colors.HexColor(_ACCENT)

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("mqTitle", parent=styles["Title"], textColor=accent, fontSize=18, spaceAfter=2)
    h_sub = ParagraphStyle("mqSub", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    h2 = ParagraphStyle("mqH2", parent=styles["Heading2"], textColor=accent, fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("mqBody", parent=styles["Normal"], fontSize=10, leading=14)
    small = ParagraphStyle("mqSmall", parent=styles["Normal"], fontSize=7.5, textColor=colors.grey, leading=10)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
        title=f"Informe de cartera — {nombre_corto}", author="Master Quant",
    )
    story: list = []

    # ── Encabezado ─────────────────────────────────────────────────────────
    story.append(Paragraph(f"Informe de cartera — {nombre_corto}", h_title))
    story.append(Paragraph(
        f"Master Quant · {date.today().strftime('%d/%m/%Y')} · Perfil: {perfil}", h_sub))
    story.append(Spacer(1, 8))

    # ── Resumen en lenguaje natural (reusa H1) ───────────────────────────────
    try:
        from services.resumen_natural import resumen_natural_cartera

        resumen = resumen_natural_cartera(diag, metricas, ccl=ccl, nombre=nombre_corto)
        # quitar el markdown ** del resumen para el PDF
        resumen = resumen.replace("**", "")
        if resumen:
            story.append(Paragraph(resumen, body))
            story.append(Spacer(1, 6))
    except Exception:
        pass

    # ── KPIs ─────────────────────────────────────────────────────────────────
    valor_usd = float(getattr(diag, "valor_cartera_usd", 0) or 0)
    if valor_usd <= 0 and ccl > 0:
        valor_usd = float(metricas.get("total_valor", 0) or 0) / ccl
    score = getattr(diag, "score_total", None)
    rend = getattr(diag, "rendimiento_ytd_usd_pct", None)
    rend_txt = f"{float(rend) * 100:+.1f}%" if isinstance(rend, (int, float)) else "—"
    kpis = [
        ["Valor (USD)", f"USD {valor_usd:,.0f}" if valor_usd else "—"],
        ["Rendimiento (USD)", rend_txt],
        ["Estado", _semaforo_txt(diag)],
        ["Puntaje", f"{float(score):.0f}/100" if isinstance(score, (int, float)) else "—"],
        ["Perfil de riesgo", str(perfil)],
    ]
    t_kpi = Table(kpis, colWidths=[55 * mm, 110 * mm])
    t_kpi.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#e5e7eb")),
    ]))
    story.append(t_kpi)

    # ── Recomendación de compras (si hay) ────────────────────────────────────
    items = list(getattr(recomendacion, "compras_recomendadas", None) or [])
    if items:
        from core.renta_fija_ar import es_renta_fija
        from services.recomendador_explicable import porque_recomendado

        story.append(Paragraph("Activos recomendados", h2))
        filas = [["Activo", "Tipo", "Unid.", "Monto ARS", "Por qué"]]
        for it in items:
            tk = str(getattr(it, "ticker", "") or "").upper()
            if not tk:
                continue
            porque = porque_recomendado(
                tk, justificacion=str(getattr(it, "justificacion", "") or ""),
                es_renta_fija=es_renta_fija(tk),
            )
            filas.append([
                tk,
                "RF" if es_renta_fija(tk) else "RV",
                f"{int(getattr(it, 'unidades', 0) or 0):,}",
                f"{float(getattr(it, 'monto_ars', 0) or 0):,.0f}",
                Paragraph(porque[:140], small),
            ])
        t = Table(filas, colWidths=[22 * mm, 14 * mm, 16 * mm, 28 * mm, 85 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fc")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # ── Disclaimer ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Master Quant es una herramienta de análisis. No constituye asesoramiento "
        "personalizado de inversión. Verificá siempre en tu broker antes de operar. "
        "Las sugerencias son simulaciones; no son promesa de resultado.", small))

    doc.build(story)
    return buf.getvalue()
