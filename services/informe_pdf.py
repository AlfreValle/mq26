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
    posiciones: Any = None,
    contexto_mercado: str = "",
) -> bytes:
    """Devuelve el informe del cliente como bytes PDF. Pura, sin Streamlit.

    posiciones: DataFrame de la cartera actual (TICKER/TIPO/VALOR_ARS/PESO_PCT/
    PNL_PCT). contexto_mercado: línea opcional de régimen de mercado.
    """
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
    valor_ars = float(metricas.get("total_valor", 0) or 0)
    if valor_ars <= 0 and valor_usd > 0 and ccl > 0:
        valor_ars = valor_usd * ccl
    score = getattr(diag, "score_total", None)
    rend = getattr(diag, "rendimiento_ytd_usd_pct", None)
    rend_txt = f"{float(rend) * 100:+.1f}%" if isinstance(rend, (int, float)) else "—"
    rf_act = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
    rf_req = float(getattr(diag, "pct_defensivo_requerido", 0) or 0)
    rf_txt = f"{rf_act * 100:.0f}% (objetivo {rf_req * 100:.0f}%)" if rf_req else f"{rf_act * 100:.0f}%"
    kpis = [
        ["Valor de la cartera", f"USD {valor_usd:,.0f}  ·  ARS {valor_ars:,.0f}" if valor_usd else "—"],
        ["Rendimiento (USD)", rend_txt],
        ["Estado de salud", f"{_semaforo_txt(diag)}" + (f"  ·  {float(score):.0f}/100" if isinstance(score, (int, float)) else "")],
        ["Renta fija en cartera", rf_txt],
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

    if contexto_mercado:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Contexto de mercado:</b> {contexto_mercado}", body))

    # ── Tu cartera actual (posiciones) ───────────────────────────────────────
    try:
        import pandas as _pd

        if isinstance(posiciones, _pd.DataFrame) and not posiciones.empty and "TICKER" in posiciones.columns:
            from core.renta_fija_ar import es_renta_fija as _esrf

            dfp = posiciones.copy()
            _total = float(_pd.to_numeric(dfp.get("VALOR_ARS", 0), errors="coerce").fillna(0).sum()) or 1.0
            dfp = dfp.sort_values("VALOR_ARS", ascending=False) if "VALOR_ARS" in dfp.columns else dfp
            story.append(Paragraph("Tu cartera actual", h2))
            filas_p = [["Activo", "Tipo", "Valor ARS", "Peso", "P&L"]]
            for _, r in dfp.head(25).iterrows():
                tk = str(r.get("TICKER", "") or "").upper()
                if not tk:
                    continue
                v = float(_pd.to_numeric(r.get("VALOR_ARS", 0), errors="coerce") or 0)
                peso = (r.get("PESO_PCT") if "PESO_PCT" in dfp.columns else v / _total)
                peso = float(_pd.to_numeric(peso, errors="coerce") or 0)
                peso = peso * 100 if peso <= 1.5 else peso
                pnl = float(_pd.to_numeric(r.get("PNL_PCT", 0), errors="coerce") or 0) * 100
                filas_p.append([
                    tk, "RF" if _esrf(tk) else "RV", f"{v:,.0f}", f"{peso:.1f}%", f"{pnl:+.1f}%",
                ])
            if len(filas_p) > 1:
                tp = Table(filas_p, colWidths=[30 * mm, 16 * mm, 38 * mm, 22 * mm, 24 * mm], repeatRows=1)
                tp.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e2538")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fc")]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(tp)
    except Exception:
        pass

    # ── Salud y diagnóstico (todas las observaciones) ────────────────────────
    obs_list = list(getattr(diag, "observaciones", None) or [])
    titulo_sem = str(getattr(diag, "titulo_semaforo", "") or "").strip()
    if titulo_sem or obs_list:
        story.append(Paragraph("Salud y diagnóstico", h2))
        if titulo_sem:
            story.append(Paragraph(f"<b>{titulo_sem}</b>", body))
        for o in obs_list[:8]:
            ic = str(getattr(o, "icono", "") or "").strip()
            ti = str(getattr(o, "titulo", "") or "").strip()
            de = str(getattr(o, "detalle", "") or getattr(o, "descripcion", "") or "").strip()
            if not ti:
                continue
            txt = f"• <b>{ti}</b>" + (f": {de}" if de else "")
            story.append(Paragraph(txt, body))

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
