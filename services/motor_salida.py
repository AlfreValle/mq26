"""
services/motor_salida.py — Motor de Salida con Objetivos y Kelly Sizing
Mejoras #4 y #5 de Estrategia

Motor completo de salida que incluye:
  - Objetivos de precio por posición (target % por perfil)
  - Progreso visual hacia el objetivo
  - 5 disparadores de salida combinados
  - Kelly Criterion para sizing óptimo de nuevas posiciones

Perfil Conservador: +25% target, -12% stop
Perfil Moderado:    +35% target, -15% stop
Perfil Agresivo:    +50% target, -20% stop
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CCL_FALLBACK

# ─── OBJETIVOS POR PERFIL ────────────────────────────────────────────────────
OBJETIVOS_PERFIL = {
    "Conservador": {"target_pct": 25.0, "stop_pct": -12.0, "tiempo_max_dias": 365},
    "Moderado":    {"target_pct": 35.0, "stop_pct": -15.0, "tiempo_max_dias": 540},
    "Agresivo":    {"target_pct": 50.0, "stop_pct": -20.0, "tiempo_max_dias": 720},
}


# ─── MOTOR DE SALIDA ─────────────────────────────────────────────────────────

def evaluar_salida(
    ticker:       str,
    ppc_usd:      float,
    px_usd_actual:float,
    rsi:          float,
    score_actual: float,
    score_semana_anterior: float,
    fecha_compra: date,
    perfil:       str = "Moderado",
    override_target_pct: float | None = None,
    override_stop_pct:   float | None = None,
    max_pnl_historico:   float | None = None,
) -> dict:
    """
    Evalúa si una posición debe cerrarse basándose en 6 disparadores.

    `ppc_usd` y `px_usd_actual` deben estar en la **misma unidad y moneda** (recomendado: ARS
    cotización BYMA por unidad negociada — certificado CEDEAR, acción, bono según lámina del libro).

    Retorna dict con: señal, prioridad, progreso%, precio_target, precio_stop,
    trailing_stop, disparadores_activos, y texto explicativo.
    """
    # Validación y clampeo de inputs
    ppc_usd               = max(0.0, float(ppc_usd or 0))
    px_usd_actual         = max(0.0, float(px_usd_actual or 0))
    rsi                   = max(0.0, min(100.0, float(rsi or 50.0)))
    score_actual          = max(0.0, min(100.0, float(score_actual or 50.0)))
    score_semana_anterior = max(0.0, min(100.0, float(score_semana_anterior or score_actual)))

    # Guard: ppc_usd=0 es inválido — retornar resultado neutro en lugar de dividir por cero
    if ppc_usd <= 0:
        return {
            "ticker": ticker, "ppc_usd": 0.0, "px_actual": px_usd_actual,
            "precio_target": 0.0, "precio_stop": 0.0, "trailing_stop": None,
            "target_pct": 0.0, "stop_pct": 0.0, "pnl_pct": 0.0,
            "progreso_pct": 0.0, "max_pnl_historico": 0.0,
            "dias_cartera": 0, "rsi": rsi, "senal": "—", "color": "#6c757d",
            "disparadores": [], "disparadores_activos": [],
            "n_disparadores": 0, "prioridad": 0,
        }

    obj = OBJETIVOS_PERFIL.get(perfil, OBJETIVOS_PERFIL["Moderado"])
    target_pct = override_target_pct if override_target_pct is not None else obj["target_pct"]
    stop_pct   = override_stop_pct   if override_stop_pct   is not None else obj["stop_pct"]
    tiempo_max = obj["tiempo_max_dias"]

    precio_target = round(ppc_usd * (1 + target_pct / 100), 4)
    precio_stop   = round(ppc_usd * (1 + stop_pct   / 100), 4)

    # Progreso hacia el objetivo: 0% en PPC, 100% en precio_target (misma escala que precio entrada).
    if px_usd_actual > 0 and ppc_usd > 0:
        pnl_pct = (px_usd_actual / ppc_usd - 1) * 100
        span = precio_target - ppc_usd
        if span > 1e-9:
            progreso = (px_usd_actual - ppc_usd) / span * 100.0
        else:
            progreso = 100.0 if px_usd_actual >= precio_target else 0.0
        progreso = min(200.0, max(-100.0, progreso))
    else:
        pnl_pct = 0.0
        progreso = 0.0

    # Trailing Stop (B2): se ajusta al máximo histórico de la posición
    max_pnl = max_pnl_historico if max_pnl_historico is not None else pnl_pct
    precio_max_alcanzado = ppc_usd * (1 + max(0.0, max_pnl) / 100)
    trailing_stop = round(precio_max_alcanzado * (1 + stop_pct / 100), 4)
    # El trailing stop solo aplica si la posición subió al menos 5% alguna vez
    trailing_activo = max_pnl >= 5.0

    # Días en cartera
    dias = (date.today() - fecha_compra).days if fecha_compra else 0

    # ── 6 disparadores ────────────────────────────────────────────────
    disparadores = []

    # 1. Objetivo alcanzado o superado
    if px_usd_actual >= precio_target:
        disparadores.append({
            "tipo": "🎯 OBJETIVO ALCANZADO",
            "detalle": f"+{pnl_pct:.1f}% vs target +{target_pct:.0f}%",
            "prioridad": "ALTA",
        })

    # 2. Stop loss fijo
    if px_usd_actual <= precio_stop:
        disparadores.append({
            "tipo": "🛑 STOP LOSS",
            "detalle": f"{pnl_pct:.1f}% vs stop {stop_pct:.0f}%",
            "prioridad": "ALTA",
        })

    # 3. Trailing Stop (solo si la posición subió > 5%)
    if trailing_activo and px_usd_actual <= trailing_stop:
        disparadores.append({
            "tipo": "🔻 TRAILING STOP",
            "detalle": (f"Precio {px_usd_actual:.3f} ≤ trailing {trailing_stop:.3f} "
                        f"(máx histórico +{max_pnl:.1f}%)"),
            "prioridad": "ALTA",
        })

    # 4. RSI sobrecomprado
    if rsi > 75:
        disparadores.append({
            "tipo": "📈 RSI SOBRECOMPRADO",
            "detalle": f"RSI = {rsi:.0f} > 75",
            "prioridad": "MEDIA",
        })

    # 5. Score fundamental se deterioró
    caida_score = score_semana_anterior - score_actual
    if caida_score >= 15:
        disparadores.append({
            "tipo": "📉 SCORE DETERIORADO",
            "detalle": f"Cayó {caida_score:.0f} pts en 7 días",
            "prioridad": "MEDIA",
        })

    # 6. Tiempo máximo sin resultado
    if dias >= tiempo_max and pnl_pct < 10:
        disparadores.append({
            "tipo": "⏰ TIEMPO MÁXIMO",
            "detalle": f"{dias} días en cartera sin +10%",
            "prioridad": "BAJA",
        })

    # ── Señal final ───────────────────────────────────────────────────
    prioridades = [d["prioridad"] for d in disparadores]
    if "ALTA" in prioridades:
        senal    = "🔴 SALIR"
        color    = "#dc3545"
    elif "MEDIA" in prioridades:
        senal    = "🟠 REVISAR"
        color    = "#e67e22"
    elif len(disparadores) > 0:
        senal    = "🟡 ATENCIÓN"
        color    = "#f0ad4e"
    elif progreso >= 80:
        senal    = "🟡 CERCA DEL OBJETIVO"
        color    = "#f0ad4e"
    elif progreso >= 0:
        senal    = "⚪ EN CAMINO"
        color    = "#6c757d"
    else:
        senal    = "⚪ EN CAMINO"
        color    = "#6c757d"

    return {
        "ticker":           ticker,
        "ppc_usd":          ppc_usd,
        "px_actual":        px_usd_actual,
        "precio_target":    precio_target,
        "precio_stop":      precio_stop,
        "trailing_stop":    trailing_stop if trailing_activo else None,
        "target_pct":       target_pct,
        "stop_pct":         stop_pct,
        "pnl_pct":          round(pnl_pct, 2),
        "progreso_pct":     round(progreso, 1),
        "max_pnl_historico": round(max_pnl, 2),
        "dias_cartera":     dias,
        "rsi":              rsi,
        "senal":            senal,
        "color":            color,
        "disparadores":          disparadores,
        "disparadores_activos":  disparadores,
        "n_disparadores":        len(disparadores),
        "prioridad":             (3 if "ALTA" in prioridades
                                 else 2 if "MEDIA" in prioridades
                                 else 1 if disparadores
                                 else 0),
    }


# ─── KELLY CRITERION SIZING ──────────────────────────────────────────────────

def kelly_sizing(
    prob_exito:      float,  # probabilidad de llegar al target (0-1)
    target_pct:      float,  # ganancia si acierta (en %, e.g. 35.0)
    stop_pct:        float,  # pérdida si falla (en %, e.g. 15.0, positivo)
    capital_total:   float,  # capital disponible en ARS
    fraccion_kelly:  float = 0.25,  # fracción conservadora (Kelly completo = 1.0)
    max_posicion_pct:float = 20.0,  # límite máximo por activo (%)
) -> dict:
    """
    Calcula el tamaño óptimo de posición usando Kelly Criterion fraccionado.

    Kelly = (p * b - q) / b
    donde:
      p = probabilidad de éxito
      q = 1 - p = probabilidad de fracaso
      b = ganancia/pérdida = target_pct / stop_pct

    Se usa fracción de Kelly (0.25) para ser conservador y
    reducir la varianza del portafolio.
    """
    p = max(0.01, min(0.99, prob_exito))
    q = 1 - p
    b = target_pct / stop_pct if stop_pct > 0 else 1.0

    kelly_completo = (p * b - q) / b
    kelly_frac     = kelly_completo * fraccion_kelly

    # Limitar al máximo por activo
    kelly_aplicado = min(kelly_frac, max_posicion_pct / 100)
    kelly_aplicado = max(0.0, kelly_aplicado)  # No puede ser negativo

    capital_sugerido = capital_total * kelly_aplicado

    return {
        "kelly_completo_pct":  round(kelly_completo * 100, 2),
        "kelly_fraccionado_pct": round(kelly_frac * 100, 2),
        "kelly_aplicado_pct":  round(kelly_aplicado * 100, 2),
        "capital_sugerido_ars": round(capital_sugerido, 0),
        "prob_exito":          p,
        "ratio_ganancia_perdida": round(b, 2),
        "interpretacion": (
            "✅ Apuesta favorable — asignar capital"
            if kelly_completo > 0 else
            "❌ Apuesta desfavorable — no operar"
        ),
    }


def estimar_prob_exito(score_total: float, rsi: float) -> float:
    """
    Estima la probabilidad de éxito (llegar al target) basado en
    el score 60/20/20 y el RSI actual.
    """
    # Base desde el score (0-100 → 30-70%)
    prob_base = 0.30 + (score_total / 100) * 0.40

    # Ajuste por RSI
    if 35 <= rsi <= 55:
        prob_base += 0.05   # Zona compra ideal
    elif rsi < 30:
        prob_base += 0.08   # Sobrevendido → rebote probable
    elif rsi > 75:
        prob_base -= 0.10   # Sobrecomprado → riesgo de reversión

    return round(min(0.80, max(0.20, prob_base)), 3)


# ─── RENDER STREAMLIT ─────────────────────────────────────────────────────────
# G2: La lógica de dominio (evaluar_salida, kelly_sizing) es pura (sin Streamlit).
# Las funciones render_* importan streamlit localmente para no contaminar el módulo.

def render_motor_salida(
    df_posiciones:   pd.DataFrame,
    precios_actuales: dict[str, float],
    scores_actuales:  dict[str, float],
    rsi_actuales:     dict[str, float],
    perfil:          str = "Moderado",
    ccl:             float = 0.0,
    capital_disponible: float = 500_000,
    scores_semana_anterior: dict[str, float] = None,
):
    """
    Renderiza el motor de salida completo con objetivos, progreso y sizing.
    G2: streamlit importado localmente — la lógica de dominio no depende de Streamlit.
    """
    import streamlit as st  # G2: import local para mantener dominio libre de UI
    if ccl <= 0:
        ccl = CCL_FALLBACK
    st.markdown("## 🎯 Motor de Salida — Objetivos y Progreso")

    # ── Configuración ─────────────────────────────────────────────────
    with st.expander("⚙️ Configurar objetivos", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            perfil_sel = st.selectbox("Perfil", ["Conservador","Moderado","Agresivo"],
                                      index=["Conservador","Moderado","Agresivo"].index(perfil))
        with c2:
            fraccion_kelly = st.slider("Fracción Kelly", 0.1, 0.5, 0.25, 0.05,
                                       help="0.25 = conservador. Kelly completo es muy agresivo.")
        with c3:
            max_pos_pct = st.slider("Máx % por posición", 10, 30, 20)

    obj = OBJETIVOS_PERFIL[perfil_sel]
    st.info(
        f"**Perfil {perfil_sel}:** "
        f"Target +{obj['target_pct']:.0f}% · "
        f"Stop {obj['stop_pct']:.0f}% · "
        f"Tiempo máx {obj['tiempo_max_dias']} días"
    )

    if df_posiciones.empty:
        st.warning("Sin posiciones abiertas.")
        return

    # ── Evaluar cada posición ─────────────────────────────────────────
    evaluaciones = []
    for _, row in df_posiciones.iterrows():
        ticker = str(row.get("Ticker", row.get("TICKER", ""))).upper().strip()
        cant   = float(row.get("Cantidad", row.get("CANTIDAD_TOTAL", 0)))
        if cant <= 0 or not ticker:
            continue

        ppc_usd_raw = float(row.get("PPC_USD", row.get("PPC_USD_PROM", 0)) or 0)
        fecha_s = str(row.get("FECHA_INICIAL", row.get("Fecha", str(date.today()))))
        try:
            fecha_c = pd.to_datetime(fecha_s).date()
        except Exception:
            fecha_c = date.today()

        px_ars = float(precios_actuales.get(ticker, 0))
        # Misma escala que cartera / Posición Neta: USD por CEDEAR (o USD equiv. local) = ARS / CCL.
        ppc_usd = ppc_usd_raw
        px_usd_act = (px_ars / ccl) if ccl > 0 else 0.0

        rsi   = float(rsi_actuales.get(ticker, 50))
        score = float(scores_actuales.get(ticker, 50))
        score_ant = float((scores_semana_anterior or {}).get(ticker, score))

        ev = evaluar_salida(
            ticker=ticker, ppc_usd=ppc_usd, px_usd_actual=px_usd_act,
            rsi=rsi, score_actual=score, score_semana_anterior=score_ant,
            fecha_compra=fecha_c, perfil=perfil_sel,
        )
        ev["cantidad"] = int(cant)
        ev["valor_ars"] = cant * px_ars
        evaluaciones.append(ev)

    if not evaluaciones:
        st.info("Sin datos para evaluar.")
        return

    # Ordenar: primero los que necesitan acción
    orden = {"🔴 SALIR": 0, "🟠 REVISAR": 1, "🟡 CERCA DEL OBJETIVO": 2,
             "🟡 ATENCIÓN": 3, "⚪ EN CAMINO": 4}
    evaluaciones.sort(key=lambda x: (orden.get(x["senal"], 5), -x["progreso_pct"]))

    # ── Tabla de progreso ─────────────────────────────────────────────
    st.markdown("### 📊 Estado de todas las posiciones")

    for ev in evaluaciones:
        prog = ev["progreso_pct"]
        color_prog = ("#28a745" if prog >= 100 else
                      "#5cb85c" if prog >= 60  else
                      "#f0ad4e" if prog >= 30  else
                      "#dc3545" if prog < 0    else "#6c757d")

        # Barra de progreso visual
        prog_display = max(0, min(100, prog))
        barra = f"""
        <div style="background:#1a1a2e;border-radius:8px;padding:12px 16px;
                    margin:6px 0;border-left:4px solid {ev['color']}">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="color:white;font-weight:700;font-size:15px">{ev['ticker']}</span>
            <span style="color:{ev['color']};font-weight:600">{ev['senal']}</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:12px;
                      color:#aaa;margin:4px 0">
            <span>PPC: USD {ev['ppc_usd']:.4f}</span>
            <span>Actual: USD {ev['px_actual']:.4f}</span>
            <span>Target: USD {ev['precio_target']:.4f}</span>
            <span>Stop: USD {ev['precio_stop']:.4f}</span>
            <span>RSI: {ev['rsi']:.0f}</span>
            <span>{ev['dias_cartera']}d en cartera</span>
          </div>
          <div style="margin:6px 0">
            <div style="display:flex;justify-content:space-between;
                        font-size:11px;color:#aaa;margin-bottom:3px">
              <span>Entrada</span>
              <span style="color:{color_prog};font-weight:600">
                {'+'if ev['pnl_pct']>=0 else ''}{ev['pnl_pct']:.1f}%
                — Progreso: {prog:.0f}% del objetivo
              </span>
              <span>Target +{ev['target_pct']:.0f}%</span>
            </div>
            <div style="background:#333;border-radius:4px;height:8px;overflow:hidden">
              <div style="background:{color_prog};width:{prog_display}%;
                          height:100%;border-radius:4px;transition:width 0.5s"></div>
            </div>
          </div>
          {''.join([f'<div style="font-size:11px;color:#ff9900;margin-top:4px">⚡ {d["tipo"]}: {d["detalle"]}</div>' for d in ev['disparadores']])}
        </div>
        """
        st.markdown(barra, unsafe_allow_html=True)

    st.divider()

    # ── Kelly Sizing para próximas operaciones ────────────────────────
    st.markdown("### 📐 Kelly Criterion — Sizing óptimo")
    st.caption(
        "Calcula el % de capital a asignar a cada nueva posición. "
        f"Fracción Kelly: {fraccion_kelly:.0%} (conservador). "
        "Maximiza crecimiento geométrico del capital."
    )

    kelly_rows = []
    for ev in evaluaciones:
        if ev["pnl_pct"] < 0:
            continue
        prob = estimar_prob_exito(
            scores_actuales.get(ev["ticker"], 50),
            ev["rsi"]
        )
        k = kelly_sizing(
            prob_exito=prob,
            target_pct=ev["target_pct"],
            stop_pct=abs(ev["stop_pct"]),
            capital_total=capital_disponible,
            fraccion_kelly=fraccion_kelly,
            max_posicion_pct=max_pos_pct,
        )
        kelly_rows.append({
            "Ticker":           ev["ticker"],
            "Prob. éxito":      f"{prob*100:.0f}%",
            "Ratio G/P":        k["ratio_ganancia_perdida"],
            "Kelly completo":   f"{k['kelly_completo_pct']:.1f}%",
            f"Kelly {fraccion_kelly:.0%}": f"{k['kelly_fraccionado_pct']:.1f}%",
            "Capital sugerido": f"ARS ${k['capital_sugerido_ars']:,.0f}",
            "Decisión":         k["interpretacion"],
        })

    if kelly_rows:
        st.dataframe(pd.DataFrame(kelly_rows), use_container_width=True, hide_index=True)
