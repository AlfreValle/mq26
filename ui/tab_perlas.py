"""
ui/tab_perlas.py — 💎 Tab "Perlas del Mercado" (reserva táctica 20%)

Muestra:
  - Reserva táctica disponible para perlas (20% del capital)
  - Lista de perlas detectadas dinámicamente desde el motor de scoring
  - Por cada perla: tesis, entrada/stop/objetivo, R/R, horizonte, botón comprar
  - Si no hay scoring previo, ofrece botón para ejecutar escaneo del universo

Sin hardcoded: las perlas se calculan en tiempo real desde
``services.perlas_service.detectar_perlas_desde_scoring()``.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


# ─── Helpers UI ───────────────────────────────────────────────────────────────

def _color_score(score: float) -> str:
    if score >= 75: return "#27AE60"   # verde fuerte
    if score >= 65: return "#2ECC71"   # verde claro
    if score >= 55: return "#F39C12"   # ámbar
    return "#E74C3C"                    # rojo


def _color_rsi(rsi: float) -> str:
    if rsi <= 30: return "#27AE60"   # sobrevendido → oportunidad
    if rsi <= 45: return "#F39C12"   # zona de entrada
    if rsi <= 70: return "#3498DB"   # neutral
    return "#E74C3C"                  # sobrecomprado


def _badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};'
        f'padding:2px 8px;border-radius:8px;font-size:0.85em;'
        f'font-weight:600;">{label}</span>'
    )


# ─── Cálculos de capital ──────────────────────────────────────────────────────

def _capital_perlas_disponible(ctx: dict) -> tuple[float, float, float]:
    """
    Devuelve (capital_total_ars, perlas_target_ars, perlas_libre_ars).
    Asume 20% del capital total como pool táctico de perlas.
    """
    df_ag = ctx.get("df_ag")
    metricas = ctx.get("metricas") or {}
    capital_total = float(metricas.get("total_valor", 0) or 0)
    if capital_total <= 0 and df_ag is not None and not df_ag.empty and "VALOR_ARS" in df_ag.columns:
        capital_total = float(df_ag["VALOR_ARS"].sum())

    perlas_target = capital_total * 0.20
    # En esta versión inicial, el "disponible" es el target completo.
    # En futuras: restar perlas ya compradas y rastreadas vía session_state["pci_perlas_compradas"]
    perlas_compradas = float(st.session_state.get("perlas_compradas_ars_total", 0) or 0)
    perlas_libre = max(0.0, perlas_target - perlas_compradas)
    return capital_total, perlas_target, perlas_libre


# ─── Acción: ejecutar escaneo de universo ─────────────────────────────────────

def _ejecutar_escaneo(ctx: dict) -> None:
    """Lanza el scoring de universo CEDEARs y guarda df_scores en sesión."""
    with st.spinner("Escaneando universo de CEDEARs y acciones AR..."):
        try:
            from services.scoring_engine import escanear_universo_completo
            df_scores = escanear_universo_completo(
                incluir_cedears=True,
                incluir_merval=True,
                incluir_bonos=False,
                incluir_internacional=False,
                incluir_fci=False,
                max_activos=80,
            )
            st.session_state["df_scores"] = df_scores
            st.success(f"✓ Universo escaneado: {len(df_scores)} tickers procesados")
        except Exception as e:
            st.error(f"❌ Error al escanear: {e}")
            logger.exception("Error en escaneo de universo desde tab_perlas")


# ─── Acción: comprar perla ────────────────────────────────────────────────────

def _comprar_perla(perla_dict: dict, cantidad: int, ctx: dict) -> None:
    """Registra la compra de N unidades de una perla en el transaccional."""
    cartera = ctx.get("cartera_activa") or st.session_state.get("cliente_nombre", "")
    if not cartera:
        st.error("Seleccioná una cartera primero (sidebar).")
        return
    ticker = str(perla_dict.get("ticker", "")).upper().strip()
    precio = float(perla_dict.get("precio_entrada", 0) or 0)
    tipo = str(perla_dict.get("tipo", "CEDEAR"))
    monto_ars = cantidad * precio

    if precio <= 0 or cantidad < 1:
        st.error("Datos inválidos: precio o cantidad ≤ 0.")
        return

    try:
        # Persistir en transaccional vía repositorio (CSV + BD)
        from core.transaccional_repository import load_transaccional, save_transaccional

        df_actual = load_transaccional()
        nueva_op = pd.DataFrame([{
            "CARTERA": cartera,
            "FECHA_COMPRA": dt.date.today(),
            "TICKER": ticker,
            "CANTIDAD": float(cantidad),
            "PPC_USD": 0.0,   # CEDEAR: PPC en ARS
            "PPC_ARS": precio,
            "TIPO": tipo,
            "LAMINA_VN": float("nan"),
            "MONEDA_PRECIO": "ARS",
        }])
        df_nuevo = pd.concat([df_actual, nueva_op], ignore_index=True)
        save_transaccional(df_nuevo)

        # Actualizar contador de perlas compradas (para el pool)
        actual = float(st.session_state.get("perlas_compradas_ars_total", 0) or 0)
        st.session_state["perlas_compradas_ars_total"] = actual + monto_ars

        st.success(
            f"✅ Compra registrada: {cantidad} {ticker} a ${precio:,.0f} ARS = ${monto_ars:,.0f} ARS"
        )
        # Forzar refresh
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error al registrar compra: {e}")
        logger.exception("Error al comprar perla %s", ticker)


# ─── Render principal ─────────────────────────────────────────────────────────

def render_tab_perlas(ctx: dict | None = None) -> None:
    """Renderiza el tab 💎 Perlas del Mercado."""
    ctx = ctx or {}

    # ── Header ──────────────────────────────────────────────────────────────
    st.markdown("# 💎 Perlas del Mercado")
    st.markdown(
        "**Reserva táctica (20% del capital)** para oportunidades sobrevendidas "
        "con score alto. Detección 100% dinámica desde el motor MOD-23 — "
        "sin tickers hardcoded."
    )

    perfil = (ctx.get("cliente_perfil")
              or st.session_state.get("cliente_perfil", "Moderado"))
    ccl = float(ctx.get("ccl") or 1490.0)

    # ── KPIs de capital perlas ──────────────────────────────────────────────
    cap_total, perlas_target, perlas_libre = _capital_perlas_disponible(ctx)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Capital total", f"${cap_total:,.0f} ARS")
    with k2:
        st.metric("Reserva perlas (20%)", f"${perlas_target:,.0f} ARS")
    with k3:
        st.metric("Disponible para comprar", f"${perlas_libre:,.0f} ARS",
                  help="Reserva menos lo ya comprado en perlas")
    with k4:
        st.metric("Perfil", perfil)

    st.divider()

    # ── 🤖 Pipeline de análisis automático (Capa 1 + 2 + 3) ──────────────────
    with st.expander("🤖 **Generar análisis automático de cualquier ticker** (pipeline MQ26)", expanded=False):
        st.caption(
            "Pipeline 3 capas que corre en background: "
            "**1)** Cachea fundamentales (yfinance, TTL 24h) → "
            "**2)** Aplica scoring MOD-23 60/20/20 → "
            "**3)** Genera análisis MQ26 con tesis, razones, tramos escalonados, "
            "stop loss y target dinámicos."
        )
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            ticker_auto = st.text_input(
                "Ticker(s) a analizar (separar por coma):",
                placeholder="Ej: AAPL, MSFT, KO, JNJ",
                key="bdi_auto_input",
            )
        with col_btn:
            st.write("")
            if st.button("🚀 Generar análisis", type="primary",
                         use_container_width=True, key="btn_bdi_auto_gen"):
                tickers = [t.strip().upper() for t in (ticker_auto or "").split(",") if t.strip()]
                if not tickers:
                    st.warning("Ingresá al menos un ticker.")
                else:
                    progreso = st.progress(0.0, text="Iniciando pipeline...")
                    try:
                        # Motor MQ26 v2 — pipeline canónico de 3 capas
                        from services.bdi_generator import generar_reporte_bdi
                        for i, t in enumerate(tickers):
                            progreso.progress((i+1)/len(tickers),
                                              text=f"Analizando {t} ({i+1}/{len(tickers)})...")
                            rep = generar_reporte_bdi(t, persist=True)
                            sc = rep.get("scoring_multifactor", {})
                            st.success(
                                f"✓ **{t}**: {rep.get('recomendacion','—')} · "
                                f"score **{sc.get('score_total',0):.1f}/100** "
                                f"(Valor {sc.get('score_valor',0):.0f} · "
                                f"Calidad {sc.get('score_calidad',0):.0f} · "
                                f"Mom {sc.get('score_momentum',0):.0f} · "
                                f"Sect {sc.get('score_sectorial',0):.0f}) → "
                                f"target USD {rep.get('precio_objetivo_usd',0):.2f} "
                                f"(+{rep.get('potencial_pct',0):.1f}%) · "
                                f"{rep.get('calificacion_total',0):.1f}/5"
                            )
                        progreso.progress(1.0, text="✓ Pipeline 3 capas completo")
                        st.balloons()
                    except Exception as e_pipe:
                        st.error(f"❌ Error en pipeline: {e_pipe}")

        # Estadísticas del caché de fundamentales
        try:
            from services.fundamentals_cache import estadisticas_cache
            stats = estadisticas_cache()
            st.caption(
                f"💾 Caché de fundamentales: **{stats['frescos']}** frescos · "
                f"**{stats['stale']}** stale (>{stats['ttl_horas']}h) · "
                f"total **{stats['total']}** tickers"
            )
        except Exception:
            pass

    st.divider()

    # ── 📊 Backtest histórico de setups (Nivel A) ────────────────────────────
    with st.expander("📊 **Validar setup con datos históricos** (backtest)", expanded=False):
        st.caption(
            "Mide el desempeño REAL de los criterios del scanner sobre 3-5 años de historia. "
            "Compara win rate, retorno medio y alpha vs benchmark (SPY). "
            "Permite saber si el setup actual genera valor o solo replica al índice."
        )
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            bt_tickers = st.text_input(
                "Tickers a evaluar (separar por coma):",
                value="AAPL,MSFT,KO,JNJ,GOOGL,META,AMZN,NVDA,V,JPM",
                key="bt_tickers_input",
            )
        with c2:
            bt_setup = st.selectbox(
                "Setup",
                ["rsi_or_dd", "rsi_oversold", "drawdown_recovery", "score_premium"],
                index=0,
                key="bt_setup_input",
            )
        with c3:
            bt_meses = st.selectbox("Holding (meses)", [3, 6, 12], index=1, key="bt_meses_input")

        if st.button("🚀 Ejecutar backtest", type="primary", key="btn_run_backtest"):
            tickers_list = [t.strip().upper() for t in (bt_tickers or "").split(",") if t.strip()]
            if tickers_list:
                with st.spinner(f"Backtest sobre {len(tickers_list)} tickers · setup {bt_setup}..."):
                    try:
                        from services.backtest_signals import backtest_setup
                        r = backtest_setup(
                            tickers=tickers_list,
                            condicion=bt_setup,
                            holding_meses=int(bt_meses),
                            anios_historia=5,
                        )
                        # KPIs
                        k1, k2, k3, k4 = st.columns(4)
                        with k1:
                            st.metric("Signals", r.n_signals,
                                      f"{r.n_winners} winners / {r.n_losers} losers")
                        with k2:
                            st.metric("Win rate", f"{r.win_rate*100:.1f}%")
                        with k3:
                            st.metric("Return medio", f"{r.return_medio_pct:+.2f}%",
                                      f"mediano {r.return_mediano_pct:+.2f}%")
                        with k4:
                            alpha_color = "normal" if r.alpha_pct >= 0 else "inverse"
                            st.metric("Alpha vs SPY", f"{r.alpha_pct:+.2f}%",
                                      f"vs SPY {r.benchmark_return_medio_pct:+.2f}%",
                                      delta_color=alpha_color)

                        if r.alpha_pct > 0:
                            st.success(
                                f"✅ El setup **{bt_setup}** SUPERA a SPY en "
                                f"{r.alpha_pct:+.2f}% promedio en {r.holding_meses} meses · Sharpe {r.sharpe}"
                            )
                        else:
                            st.warning(
                                f"⚠️ El setup **{bt_setup}** NO supera a SPY ({r.alpha_pct:+.2f}% vs benchmark). "
                                f"Considerá refinar criterios."
                            )

                        # Tabla con los signals
                        if r.detalle_signals:
                            import pandas as pd
                            df_det = pd.DataFrame(r.detalle_signals)
                            st.dataframe(df_det, use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.error(f"❌ Error en backtest: {e}")
            else:
                st.warning("Ingresá al menos un ticker.")

    st.divider()

    # ── Tickers con Análisis MQ26 / Externo disponible ──────────────────────
    try:
        from pathlib import Path

        from config import RATIOS_CEDEAR
        from services.bdi_reports import (
            listar_tickers_con_bdi,
            obtener_reporte_bdi,
            reporte_bdi_html,
        )
        all_tickers = listar_tickers_con_bdi()

        # Distinguir: análisis MQ26 (auto) vs reportes externos manuales
        bdi_dir = Path(__file__).resolve().parent.parent / "data" / "bdi_reports"
        tickers_auto = set()
        tickers_externos = set()
        for tk in all_tickers:
            for f in bdi_dir.glob(f"{tk}_*.json"):
                if f.stem.endswith("_auto"):
                    tickers_auto.add(tk)
                else:
                    tickers_externos.add(tk)

        if all_tickers:
            n_mq = len(tickers_auto)
            n_ext = len(tickers_externos)
            st.markdown(
                f"### 📊 Análisis MQ26 disponibles "
                f"({n_mq} auto-generado{'s' if n_mq != 1 else ''} · "
                f"{n_ext} de consultoras externas)"
            )
            st.caption(
                "**MQ26 Auto** = generado por nuestro motor multifactor "
                "(fundamentales + scoring + comparativa industria). "
                "**Externos** = informes profesionales de consultoras "
                "(BDI Consultora u otras) cargados manualmente."
            )
            cols_bdi = st.columns(min(len(all_tickers), 4))
            for i, t_bdi in enumerate(all_tickers):
                rep = obtener_reporte_bdi(t_bdi)
                if rep is None:
                    continue
                es_auto = t_bdi in tickers_auto and t_bdi not in tickers_externos
                origen_badge = "🤖 MQ26 Auto" if es_auto else "📊 Externo"
                origen_bg = "#1d4ed8" if es_auto else "#7c3aed"   # azul / púrpura
                with cols_bdi[i % len(cols_bdi)]:
                    rec_color = {"COMPRAR": "#16a34a", "MANTENER": "#d97706",
                                 "VENDER": "#dc2626"}.get(rep.recomendacion, "#475569")
                    st.markdown(
                        f'<div style="background:#ffffff;border:2px solid {rec_color};'
                        f'border-radius:8px;padding:12px;text-align:center;'
                        f'color:#0f172a;">'
                        f'<div style="font-size:1.4em;font-weight:700;color:#0f172a;">{rep.ticker}</div>'
                        f'<div style="background:{origen_bg};color:#ffffff;font-weight:600;'
                        f'font-size:0.7em;padding:2px 8px;border-radius:10px;display:inline-block;'
                        f'margin:2px 0;letter-spacing:0.02em;">'
                        f'{origen_badge}</div>'
                        f'<div style="background:{rec_color};color:#ffffff;font-weight:700;'
                        f'font-size:0.85em;padding:3px 10px;border-radius:12px;display:inline-block;'
                        f'margin:4px 0;">'
                        f'{rep.recomendacion}</div>'
                        f'<div style="font-size:0.88em;color:#475569;font-weight:500;margin-top:4px;">'
                        f'USD {rep.precio_actual_usd:.0f} → USD {rep.precio_objetivo_usd:.0f}</div>'
                        f'<div style="color:#15803d;font-weight:700;font-size:1.05em;">+{rep.upside_pct:.0f}%</div>'
                        f'<div style="color:#b45309;font-size:1em;">'
                        f'{"★" * int(round(rep.calificacion_total))}{"☆" * (5 - int(round(rep.calificacion_total)))}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )
            sel_bdi = st.selectbox(
                "Ver análisis completo:",
                options=["—"] + all_tickers,
                key="bdi_select_full",
            )
            if sel_bdi != "—":
                rep_sel = obtener_reporte_bdi(sel_bdi)
                if rep_sel:
                    ratio_sel = float(RATIOS_CEDEAR.get(sel_bdi.upper(), 1) or 1)
                    st.markdown(reporte_bdi_html(rep_sel, ccl=ccl, ratio_cedear=ratio_sel),
                                unsafe_allow_html=True)
            st.divider()
    except Exception as _e_bdi_idx:
        import logging
        logging.getLogger(__name__).debug("BDI index render skipped: %s", _e_bdi_idx)

    # ── AUTO-SCAN al entrar (si no hay scoring previo) ──────────────────────
    df_scores = st.session_state.get("df_scores")
    tiene_scoring = (df_scores is not None
                     and hasattr(df_scores, "empty")
                     and not df_scores.empty)

    # Si no hay scoring cargado, ejecutarlo automáticamente UNA VEZ por sesión.
    # Marca la sesión para no reintentar si falla (evita loops).
    if not tiene_scoring and not st.session_state.get("_perlas_autoscan_intentado", False):
        st.session_state["_perlas_autoscan_intentado"] = True
        with st.spinner(
            "🔍 Cargando perlas automáticamente · escaneando universo "
            "de CEDEARs y acciones (≈30-60 segundos)..."
        ):
            try:
                from services.scoring_engine import escanear_universo_completo
                df_scores_new = escanear_universo_completo(
                    incluir_cedears=True,
                    incluir_merval=True,
                    incluir_bonos=False,
                    incluir_internacional=False,
                    incluir_fci=False,
                    max_activos=80,
                )
                st.session_state["df_scores"] = df_scores_new
                df_scores = df_scores_new
                tiene_scoring = df_scores_new is not None and not df_scores_new.empty
                if tiene_scoring:
                    st.success(
                        f"✓ Escaneo completo: {len(df_scores_new)} tickers procesados. "
                        f"Las perlas se actualizan automáticamente."
                    )
            except Exception as _e_autoscan:
                st.warning(
                    f"⚠️ No se pudo escanear automáticamente ({_e_autoscan}). "
                    "Podés intentar manualmente más abajo."
                )

    # Botón manual de re-escaneo (siempre disponible)
    _col_rs, _col_info = st.columns([1, 3])
    with _col_rs:
        if st.button("🔄 Re-escanear universo", key="btn_rescan_auto",
                     use_container_width=True, help="Fuerza un re-escaneo del universo"):
            try:
                from services.scoring_engine import escanear_universo_completo
                with st.spinner("Re-escaneando..."):
                    df_new = escanear_universo_completo(
                        incluir_cedears=True, incluir_merval=True,
                        incluir_bonos=False, incluir_internacional=False,
                        incluir_fci=False, max_activos=80,
                    )
                    st.session_state["df_scores"] = df_new
                    st.session_state["_perlas_autoscan_intentado"] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    with _col_info:
        if tiene_scoring:
            n_tickers = len(df_scores) if hasattr(df_scores, "__len__") else 0
            st.caption(
                f"📊 Universo escaneado: **{n_tickers}** tickers. "
                "Las perlas se filtran de este universo según el perfil de cada tab."
            )

    # Si tras el auto-scan tampoco hay scoring, mostrar mockup demo y salir
    if not tiene_scoring:
        st.info(
            "📊 No hay datos del universo todavía. "
            "Esperá a la próxima corrida o re-escaneá manualmente arriba."
        )
        with st.expander("Ver mockup de cómo se verían las perlas detectadas"):
            _render_mockup_demo(perlas_libre, ccl)
        return

    # ── PERLAS POR PERFIL DE RIESGO (tabs internos) ─────────────────────────
    from services.perlas_service import detectar_perlas_desde_scoring, resumen_perlas_df

    st.divider()
    st.markdown("### 💎 Perlas detectadas por perfil de riesgo")
    st.caption(
        f"**Tu perfil actual: {perfil}** — pero podés ver oportunidades de los 4 perfiles. "
        "Cada perfil exige un score mínimo distinto (Conservador 75+ es más estricto, "
        "Muy arriesgado 50+ es más permisivo)."
    )

    _PERFILES = ["Conservador", "Moderado", "Arriesgado", "Muy arriesgado"]
    _SCORE_MIN = {"Conservador": 75, "Moderado": 65, "Arriesgado": 55, "Muy arriesgado": 50}

    # Ordenar tabs poniendo el perfil del usuario PRIMERO
    perfiles_ordenados = ([perfil] +
                          [p for p in _PERFILES if p != perfil]) if perfil in _PERFILES else _PERFILES

    # Generar etiquetas de tabs con contador
    tab_labels = []
    perlas_por_perfil = {}
    for p in perfiles_ordenados:
        perlas_p = detectar_perlas_desde_scoring(
            df_scores=df_scores,
            perfil=p,
            n_max=8,
            ccl=ccl,
        )
        perlas_por_perfil[p] = perlas_p
        emoji = "⭐ " if p == perfil else ""
        tab_labels.append(f"{emoji}{p} ({len(perlas_p)})")

    perfil_tabs = st.tabs(tab_labels)
    for tab, perfil_actual in zip(perfil_tabs, perfiles_ordenados, strict=True):
        with tab:
            perlas_actual = perlas_por_perfil[perfil_actual]
            score_min_actual = _SCORE_MIN.get(perfil_actual, 65)
            st.caption(
                f"**Filtros perfil {perfil_actual}**: Score MOD-23 ≥ **{score_min_actual}** · "
                f"RSI ≤ 45 ó drawdown ≥ 20% · ordenadas por score descendente."
            )

            if not perlas_actual:
                st.info(
                    f"📊 No hay perlas que cumplan los filtros de **{perfil_actual}** ahora mismo. "
                    "Esperá a la próxima corrida o probá un perfil menos estricto."
                )
                continue

            # Render tarjetas para este perfil
            for i, perla in enumerate(perlas_actual):
                _render_perla_card(perla, ctx, perlas_libre,
                                   idx=f"{perfil_actual.lower().replace(' ', '_')}_{i}")
                st.divider()

            # Tabla resumen del perfil
            with st.expander(f"📋 Tabla resumen — {len(perlas_actual)} perlas de {perfil_actual}",
                             expanded=False):
                df_res = resumen_perlas_df(perlas_actual)
                st.dataframe(df_res, use_container_width=True, hide_index=True)

    # ── Disclaimer legal ────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "⚠️ Las perlas son sugerencias basadas en señales técnicas/fundamentales "
        "del motor MOD-23. NO constituyen recomendación de inversión. "
        "Cada compra debe ser confirmada por vos en tu broker."
    )


# ─── Render de tarjeta de perla individual ────────────────────────────────────

def _render_perla_card(perla, ctx: dict, perlas_libre: float, idx) -> None:
    """
    Renderiza una perla como tarjeta con:
      - Tesis HTML enriquecida (motivos detallados, plan de acción)
      - Precios en ARS y USD (equivalente al CCL del momento)
      - Selector de cantidad con cálculo USD+ARS en vivo
      - Botón comprar que persiste la operación
    """
    p = perla if isinstance(perla, dict) else perla.to_dict()

    ticker = p.get("ticker", "?")
    sector = p.get("sector", "—")
    entrada = float(p.get("precio_entrada", 0))
    objetivo = float(p.get("precio_objetivo", 0))
    stop = float(p.get("stop_loss", 0))
    upside = float(p.get("upside_pct", 0))
    downside = float(p.get("downside_pct", 0))
    rr = float(p.get("riesgo_recompensa", 0))
    horiz = int(p.get("horizonte_meses", 6))
    score = float(p.get("score_total", 0))
    rsi = float(p.get("rsi", 50))
    ccl = float(ctx.get("ccl") or 1490.0)

    # Equivalentes USD (precio CEDEAR en ARS / CCL)
    entrada_usd = entrada / ccl if ccl > 0 else 0
    objetivo_usd = objetivo / ccl if ccl > 0 else 0
    stop_usd = stop / ccl if ccl > 0 else 0

    # ── Header con badges ───────────────────────────────────────────────────
    # Detectar si hay análisis MQ26 (auto) o reporte externo
    tiene_analisis = False
    es_externo = False
    try:
        from pathlib import Path

        from services.bdi_reports import obtener_reporte_bdi
        if obtener_reporte_bdi(ticker) is not None:
            tiene_analisis = True
            # Existe archivo SIN sufijo _auto = externo (BDI Consultora u otro)
            bdi_dir = Path(__file__).resolve().parent.parent / "data" / "bdi_reports"
            for f in bdi_dir.glob(f"{ticker.upper()}_*.json"):
                if not f.stem.endswith("_auto"):
                    es_externo = True
                    break
    except Exception:
        pass
    if tiene_analisis:
        if es_externo:
            badge_bdi = _badge("📊 Análisis Externo", "#7c3aed")
        else:
            badge_bdi = _badge("🤖 MQ26 Auto", "#1d4ed8")
    else:
        badge_bdi = ""

    # ── Badges Nivel A: DCF + Confianza de datos ─────────────────────────
    dcf_recom = p.get("dcf_recomendacion")
    dcf_margen = p.get("dcf_margen_seguridad_pct")
    badge_dcf = ""
    if dcf_recom and dcf_margen is not None:
        if dcf_recom == "INFRAVALORADA":
            badge_dcf = _badge(f"🧮 DCF +{dcf_margen:.0f}%", "#15803d")
        elif dcf_recom == "FAIR":
            badge_dcf = _badge("🧮 DCF FAIR", "#b45309")
        elif dcf_recom == "SOBREVALUADA":
            badge_dcf = _badge(f"🧮 DCF {dcf_margen:.0f}%", "#dc2626")

    confianza_nivel = p.get("confianza_datos_nivel")
    confianza_pct = p.get("confianza_datos_pct")
    badge_confianza = ""
    if confianza_nivel and confianza_pct is not None:
        color_conf = {"ALTA": "#15803d", "MEDIA": "#b45309", "BAJA": "#dc2626"}.get(confianza_nivel, "#475569")
        badge_confianza = _badge(f"✓ Datos {confianza_pct:.0f}/100", color_conf)

    col_left, col_right = st.columns([3, 1])
    with col_left:
        st.markdown(
            f"### 💎 {ticker} · *{sector}*",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"{_badge(f'Score {score:.0f}', _color_score(score))}  "
            f"{_badge(f'RSI {rsi:.0f}', _color_rsi(rsi))}  "
            f"{_badge(f'R/R {rr:.1f}:1', '#2980B9')}  "
            f"{badge_dcf}  "
            f"{badge_confianza}  "
            f"{badge_bdi}",
            unsafe_allow_html=True,
        )
    with col_right:
        st.markdown(
            f'<div style="text-align:right;">'
            f'<div style="font-size:0.85em;color:#475569;font-weight:600;">Horizonte</div>'
            f'<div style="font-size:1.3em;font-weight:600;">{horiz} meses</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Tesis HTML enriquecida (completa, no truncada) ──────────────────────
    try:
        from services.perlas_service import construir_tesis_html
        tesis_html = construir_tesis_html(p)
        st.markdown(tesis_html, unsafe_allow_html=True)
    except Exception:
        st.markdown(f"📝 *{p.get('tesis', '')}*")

    # ── Análisis MQ26 / Externo (si existe para este ticker) ─────────────────
    try:
        from config import RATIOS_CEDEAR
        from services.bdi_reports import obtener_reporte_bdi, reporte_bdi_html
        reporte = obtener_reporte_bdi(ticker)
        if reporte is not None:
            ratio = float(RATIOS_CEDEAR.get(ticker.upper(), 1) or 1)
            titulo_origen = "📊 Análisis Externo" if es_externo else "🤖 Análisis MQ26"
            with st.expander(
                f"{titulo_origen} disponible — "
                f"{reporte.recomendacion} · target USD {reporte.precio_objetivo_usd:.0f} "
                f"(+{reporte.upside_pct:.0f}%) · {reporte.calificacion_total:.1f}/5",
                expanded=False,
            ):
                html = reporte_bdi_html(reporte, ccl=ccl, ratio_cedear=ratio)
                st.markdown(html, unsafe_allow_html=True)
    except Exception as _e_an:
        import logging
        logging.getLogger(__name__).debug("Análisis no disponible para %s: %s", ticker, _e_an)

    # ── KPIs de niveles: ARS principal + USD equivalente ───────────────────
    st.markdown("##### 💰 Niveles de operación (ARS principal · USD equivalente)")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(
            "Entrada CEDEAR",
            f"${entrada:,.0f} ARS",
            f"≈ USD {entrada_usd:,.2f}",
            delta_color="off",
            help="Precio actual del CEDEAR en BYMA. USD se calcula con CCL del momento.",
        )
    with k2:
        st.metric(
            "🎯 Objetivo (toma ganancia)",
            f"${objetivo:,.0f} ARS",
            f"+{upside:.0f}% · USD {objetivo_usd:,.2f}",
        )
    with k3:
        st.metric(
            "🛑 Stop loss",
            f"${stop:,.0f} ARS",
            f"-{downside:.0f}% · USD {stop_usd:,.2f}",
            delta_color="inverse",
        )
    with k4:
        max_perla_ars = perlas_libre * 0.50
        max_unidades_pool = int(max_perla_ars // entrada) if entrada > 0 else 0
        st.metric(
            "Máx. unidades",
            f"{max_unidades_pool}",
            f"≤ {max_perla_ars/ccl:,.0f} USD",
            delta_color="off",
            help="Máximo permitido por el pool de perlas (50% del disponible)",
        )

    # ── Botón de compra con cálculo USD+ARS ─────────────────────────────────
    col_qty, col_btn, col_calc = st.columns([1, 1, 2])
    max_units = max(1, int(perlas_libre * 0.50 // entrada) if entrada > 0 else 1)
    with col_qty:
        cant = st.number_input(
            "Cantidad",
            min_value=1,
            max_value=max_units,
            value=max(1, max_units // 2),
            step=1,
            key=f"perla_qty_{ticker}_{idx}",
        )
    with col_btn:
        st.write("")
        if st.button(
            f"🛒 Comprar {cant} {ticker}",
            type="primary",
            use_container_width=True,
            key=f"btn_comprar_perla_{ticker}_{idx}",
        ):
            _comprar_perla(p, int(cant), ctx)
    with col_calc:
        monto_ars = cant * entrada
        monto_usd = monto_ars / ccl if ccl > 0 else 0
        pct_pool = monto_ars / perlas_libre * 100 if perlas_libre > 0 else 0
        st.write("")
        st.markdown(
            f'<div style="background:#fef3c7;padding:12px;border-radius:6px;'
            f'border-left:4px solid #b45309;color:#78350f;">'
            f'<b style="color:#78350f;">Monto operación:</b><br>'
            f'💵 <b style="font-size:1.18em;color:#14532d;">'
            f'${monto_ars:,.0f} ARS</b> &nbsp;·&nbsp; '
            f'<b style="color:#1e3a8a;">USD {monto_usd:,.2f}</b><br>'
            f'<small style="color:#78350f;font-weight:500;">'
            f'{pct_pool:.1f}% del pool de perlas · CCL ${ccl:,.0f}</small>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ─── Mockup demo (cuando no hay scoring) ──────────────────────────────────────

def _render_mockup_demo(perlas_libre: float, ccl: float) -> None:
    """Muestra una vista demo con 2 perlas ejemplo (no se pueden comprar)."""
    st.caption(
        "🎭 **Mockup ilustrativo** — datos de ejemplo. "
        "Ejecutá el escaneo arriba para ver perlas reales."
    )
    demo = [
        {
            "ticker": "NVDA", "sector": "Tecnología", "score_total": 78, "rsi": 38,
            "tesis": "NVDA: corrección del 28% desde máximo, RSI 38 (sobrevendido). Score MOD-23 78/100 sostenido.",
            "precio_entrada": 8_500.0, "precio_objetivo": 11_900.0, "stop_loss": 6_375.0,
            "upside_pct": 40, "downside_pct": 25, "riesgo_recompensa": 1.6, "horizonte_meses": 9,
        },
        {
            "ticker": "VIST", "sector": "Energía AR", "score_total": 72, "rsi": 42,
            "tesis": "VIST: shale Vaca Muerta, caída 30% por baja temporal WTI. Score 72 sólido, RSI 42.",
            "precio_entrada": 14_000.0, "precio_objetivo": 22_400.0, "stop_loss": 9_800.0,
            "upside_pct": 60, "downside_pct": 30, "riesgo_recompensa": 2.0, "horizonte_meses": 12,
        },
    ]
    for i, p in enumerate(demo):
        col_l, col_r = st.columns([3, 1])
        with col_l:
            score_val = p["score_total"]
            rsi_val = p["rsi"]
            rr_val = p["riesgo_recompensa"]
            badges_html = (
                f"{_badge(f'Score {score_val}', _color_score(score_val))} "
                f"{_badge(f'RSI {rsi_val}', _color_rsi(rsi_val))} "
                f"{_badge(f'R/R {rr_val}:1', '#2980B9')}"
            )
            st.markdown(
                f"**💎 {p['ticker']}** · *{p['sector']}* {badges_html}",
                unsafe_allow_html=True,
            )
            st.caption(p["tesis"])
        with col_r:
            st.caption(f"Horizonte: {p['horizonte_meses']} meses")
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Entrada", f"${p['precio_entrada']:,.0f}")
        with c2: st.metric("🎯 Objetivo", f"${p['precio_objetivo']:,.0f}", f"+{p['upside_pct']}%")
        with c3: st.metric("🛑 Stop", f"${p['stop_loss']:,.0f}", f"-{p['downside_pct']}%", delta_color="inverse")
        if i < len(demo) - 1:
            st.markdown("---")
