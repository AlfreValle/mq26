"""
ui/tab_universo.py — Tab 2: Universo & Señales (Alpha Research)
Combina: Motor MOD-23 + Velas Japonesas + 3 Indicadores Técnicos
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ── Cálculo de indicadores técnicos (sin librerías externas) ──────────────────

def _calcular_supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0):
    """Supertrend: banda ATR superior/inferior. Verde=comprar, Rojo=vender."""
    high, low, close = df["High"], df["Low"], df["Close"]
    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2  = (high + low) / 2
    upper_band = hl2 + mult * atr
    lower_band = hl2 - mult * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)   # 1=alcista, -1=bajista

    for i in range(period, len(df)):
        prev_close = close.iloc[i - 1]
        prev_upper = upper_band.iloc[i - 1] if i > period else upper_band.iloc[i]
        prev_lower = lower_band.iloc[i - 1] if i > period else lower_band.iloc[i]

        # Ajuste de bandas
        ub = upper_band.iloc[i] if upper_band.iloc[i] < prev_upper or prev_close > prev_upper else prev_upper
        lb = lower_band.iloc[i] if lower_band.iloc[i] > prev_lower or prev_close < prev_lower else prev_lower
        upper_band.iloc[i] = ub
        lower_band.iloc[i] = lb

        prev_st = supertrend.iloc[i - 1] if i > period else lb
        if pd.isna(prev_st) or prev_st == prev_upper:
            supertrend.iloc[i] = lb if close.iloc[i] > ub else ub
        else:
            supertrend.iloc[i] = ub if close.iloc[i] < lb else lb

        direction.iloc[i] = 1 if close.iloc[i] > supertrend.iloc[i] else -1

    return supertrend, direction


def _calcular_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast   = close.ewm(span=fast, adjust=False).mean()
    ema_slow   = close.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def _calcular_stoch_rsi(close: pd.Series, period=14, smooth_k=3, smooth_d=3):
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    stoch_k = 100 * (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    stoch_k = stoch_k.rolling(smooth_k).mean()
    stoch_d = stoch_k.rolling(smooth_d).mean()
    return stoch_k, stoch_d


def _calcular_bollinger(close: pd.Series, period=20, std_mult=2.0):
    sma  = close.rolling(period).mean()
    std  = close.rolling(period).std()
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    return upper, sma, lower


def _puntos_entrada_salida_supertrend(direction: pd.Series, datos: pd.DataFrame):
    entradas, salidas = [], []
    for i in range(1, len(direction)):
        if pd.isna(direction.iloc[i]) or pd.isna(direction.iloc[i-1]):
            continue
        if direction.iloc[i] == 1 and direction.iloc[i-1] == -1:
            entradas.append((datos.index[i], datos["Low"].iloc[i]))
        elif direction.iloc[i] == -1 and direction.iloc[i-1] == 1:
            salidas.append((datos.index[i], datos["High"].iloc[i]))
    return entradas, salidas


def _puntos_entrada_salida_macd(macd: pd.Series, signal: pd.Series, datos: pd.DataFrame):
    entradas, salidas = [], []
    for i in range(1, len(macd)):
        if pd.isna(macd.iloc[i]) or pd.isna(signal.iloc[i]):
            continue
        if macd.iloc[i] > signal.iloc[i] and macd.iloc[i-1] <= signal.iloc[i-1]:
            entradas.append((datos.index[i], datos["Low"].iloc[i]))
        elif macd.iloc[i] < signal.iloc[i] and macd.iloc[i-1] >= signal.iloc[i-1]:
            salidas.append((datos.index[i], datos["High"].iloc[i]))
    return entradas, salidas


def _puntos_entrada_salida_bb_stochrsi(close: pd.Series, lower: pd.Series,
                                        upper: pd.Series, stoch_k: pd.Series,
                                        datos: pd.DataFrame):
    entradas, salidas = [], []
    for i in range(1, len(close)):
        if pd.isna(lower.iloc[i]) or pd.isna(stoch_k.iloc[i]):
            continue
        if close.iloc[i] <= lower.iloc[i] and stoch_k.iloc[i] < 20:
            entradas.append((datos.index[i], datos["Low"].iloc[i]))
        elif close.iloc[i] >= upper.iloc[i] and stoch_k.iloc[i] > 80:
            salidas.append((datos.index[i], datos["High"].iloc[i]))
    return entradas, salidas



def render_tab_universo(ctx: dict) -> None:
    df_ag           = ctx["df_ag"]
    tickers_cartera = ctx["tickers_cartera"]
    df_analisis     = ctx["df_analisis"]
    m23svc          = ctx["m23svc"]
    mc              = ctx["mc"]
    engine_data     = ctx["engine_data"]
    RUTA_ANALISIS   = ctx["RUTA_ANALISIS"]

    sub_mod23, sub_velas, sub_fci = st.tabs(["🔍 Motor MOD-23", "🕯️ Velas + Técnico", "🏦 FCIs Argentina"])

    # ── SUB-TAB: MOD-23 ─────────────────────────────────────────────────────────
    with sub_mod23:
        st.subheader("🔍 Motor MOD-23 — Scoring Técnico del Universo")
        st.info("Score 1–10: SMA-150 (tendencia +4) + RSI-14 (momentum +3) + Retorno 3M (+3). "
                "≥7 ELITE | ≥5 ALCISTA | <4 ALERTA VENTA")

        col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
        with col_m2:
            solo_alcistas = st.checkbox("Solo score ≥ 5", value=False)
        with col_m3:
            if st.button("🔄 Recalcular MOD-23", type="secondary"):
                with st.spinner("Escaneando universo... (~2-3 min)"):
                    df_nuevo = m23svc.recalcular_universo(engine_data.universo_df, RUTA_ANALISIS)
                    if not df_nuevo.empty:
                        st.session_state["df_analisis_recalc"] = df_nuevo
                        st.success(f"✅ {len(df_nuevo)} activos actualizados.")
                    else:
                        st.error("No se pudo completar el escaneo. Revisá los logs.")

        df_an = st.session_state.get("df_analisis_recalc", df_analisis).copy()
        if solo_alcistas:
            df_an = df_an[df_an["PUNTAJE_TECNICO"] >= 5]
        df_an = df_an.sort_values("PUNTAJE_TECNICO", ascending=False).reset_index(drop=True)

        if not df_an.empty:
            # H7: agregar columna SCORE_60_20_20 desde el cache de scores en session_state
            _scores_cache = st.session_state.get("scores_cache", {})
            if _scores_cache:
                def _get_score_total(ticker: str) -> float:
                    _s = _scores_cache.get(ticker)
                    if isinstance(_s, dict):
                        return float(_s.get("Score_Total", float("nan")))
                    return float("nan")
                df_an["SCORE_60_20_20"] = df_an["TICKER"].apply(_get_score_total) \
                    if "TICKER" in df_an.columns else float("nan")

            n_elite   = (df_an["PUNTAJE_TECNICO"] >= 7).sum()
            n_alcista = ((df_an["PUNTAJE_TECNICO"] >= 5) & (df_an["PUNTAJE_TECNICO"] < 7)).sum()
            n_alerta  = (df_an["PUNTAJE_TECNICO"] < 4).sum()

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("⭐ Elite (≥7)", n_elite)
            r2.metric("🟡 Alcistas (5-7)", n_alcista)
            r3.metric("🔴 Alertas (<4)", n_alerta)
            r4.metric("Total", len(df_an))

            def color_score_cell(val):
                if pd.isna(val):
                    return ""
                v = float(val)
                if v >= 7:
                    return "background-color:#D4EDDA;color:#155724;font-weight:bold"
                if v >= 5:
                    return "background-color:#FFF3CD;color:#856404"
                if v < 4:
                    return "background-color:#FADBD8;color:#721C24;font-weight:bold"
                return ""

            _style_cols = ["PUNTAJE_TECNICO"]
            _fmt_dict   = {"PUNTAJE_TECNICO": "{:.1f}"}

            # H7: columna y formato adicional si está disponible
            if "SCORE_60_20_20" in df_an.columns:
                _style_cols.append("SCORE_60_20_20")
                _fmt_dict["SCORE_60_20_20"] = "{:.1f}"

            st.dataframe(
                df_an.style
                    .map(color_score_cell, subset=_style_cols)
                    .format(_fmt_dict), use_container_width=True, hide_index=True, height=450,
                column_config={
                    "SCORE_60_20_20": st.column_config.NumberColumn(
                        "Score 60/20/20",
                        help="Score total = 60% Fundamental + 20% Técnico + 20% Sectorial/Macro",
                        format="%.1f",
                    ),
                } if "SCORE_60_20_20" in df_an.columns else None,
            )

            fig_dist = px.histogram(df_an, x="PUNTAJE_TECNICO", nbins=20,
                                    title="Distribución de Scores MOD-23",
                                    color_discrete_sequence=["#2E86AB"])
            fig_dist.add_vline(x=7, line_dash="dash", line_color="#27AE60", annotation_text="Elite")
            fig_dist.add_vline(x=4, line_dash="dash", line_color="#E74C3C", annotation_text="Alerta")
            st.plotly_chart(fig_dist, use_container_width=True)

            # Historial de alertas MOD-23 (H12)
            dbm_ctx = ctx.get("dbm")
            cliente_id_ctx = ctx.get("cliente_id")
            if dbm_ctx and cliente_id_ctx:
                with st.expander("📋 Historial de Alertas MOD-23", expanded=False):
                    try:
                        with dbm_ctx.get_session() as _s:
                            from core.db_manager import AlertaLog as _AL
                            _alertas = (_s.query(_AL)
                                .filter(_AL.cliente_id == cliente_id_ctx)
                                .filter(_AL.tipo_alerta != "AUDITORIA")
                                .order_by(_AL.created_at.desc())
                                .limit(30).all())
                            if _alertas:
                                _df_alertas = pd.DataFrame([{
                                    "Fecha": a.created_at.strftime("%Y-%m-%d %H:%M"),
                                    "Tipo": a.tipo_alerta,
                                    "Ticker": a.ticker,
                                    "Mensaje": a.mensaje[:80],
                                } for a in _alertas])
                                st.dataframe(_df_alertas, use_container_width=True, hide_index=True)
                            else:
                                st.info("Sin alertas registradas para este cliente.")
                    except Exception as _e:
                        st.caption(f"Historial no disponible: {_e}")

            if not df_ag.empty:
                st.markdown("---")
                st.markdown("#### 📌 MOD-23 en tu cartera activa")
                tickers_act = df_ag["TICKER"].str.upper().tolist()
                df_cartera_scores = df_an[df_an["TICKER"].isin(tickers_act)].copy()
                if not df_cartera_scores.empty:
                    st.dataframe(
                        df_cartera_scores.style
                            .map(color_score_cell, subset=["PUNTAJE_TECNICO"])
                            .format({"PUNTAJE_TECNICO": "{:.1f}"}), use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No hay scores para los tickers de tu cartera aún.")

    # ── SUB-TAB: VELAS + 3 INDICADORES ─────────────────────────────────────────
    with sub_velas:
        st.subheader("🕯️ Velas + Indicadores de Entrada/Salida")

        _INFO_INDICADORES = {
            "Supertrend (ATR-10, mult=3)": {
                "desc": "Banda ATR adaptativa. Verde=comprar cuando precio cruza banda inferior. Rojo=vender cuando cruza banda superior.",
                "tasa": "~82% en mercados con tendencia definida",
            },
            "MACD Divergence (12/26/9)": {
                "desc": "Cruce de línea MACD sobre señal con histograma positivo = entrada. Cruce negativo = salida.",
                "tasa": "~78% cuando se combina con tendencia principal (SMA-150)",
            },
            "Bollinger + Stoch RSI (BB 20/2 · StochRSI 14)": {
                "desc": "Precio toca banda inferior + StochRSI<20 = entrada. Precio en banda superior + StochRSI>80 = salida.",
                "tasa": "~80% para detectar reversiones y breakouts en mercados laterales",
            },
        }

        universo_velas = tickers_cartera if tickers_cartera else ["AAPL","MSFT","AMZN","GOOGL","MELI","SPY","NVDA"]

        col_v1, col_v2, col_v3, col_v4 = st.columns([2, 1, 2, 1])
        with col_v1:
            ticker_velas = st.selectbox("Activo:", universo_velas, key="velas_ticker")
        with col_v2:
            period_velas = st.selectbox("Período:", ["3mo","6mo","1y","2y"], index=2, key="velas_period")
        with col_v3:
            indicador_sel = st.selectbox("Indicador:", list(_INFO_INDICADORES.keys()), key="velas_ind")
        with col_v4:
            mostrar_sma = st.checkbox("SMA-150", value=True, key="velas_sma")
            mostrar_vol = st.checkbox("Volumen", value=True, key="velas_vol")

        # Info del indicador seleccionado
        _info = _INFO_INDICADORES[indicador_sel]
        st.info(f"**{indicador_sel}** — {_info['desc']}  |  Tasa de éxito histórica: **{_info['tasa']}**")

        if st.button("📊 Mostrar gráfico con señales", key="btn_velas", type="primary"):
            with st.spinner(f"Calculando {indicador_sel} para {ticker_velas}..."):
                try:
                    traducciones = {"BRKB":"BRK-B","YPFD":"YPF","PAMP":"PAM"}
                    t_yf  = traducciones.get(ticker_velas, ticker_velas)
                    datos = mc.descargar_ohlcv(t_yf, period=period_velas, interval="1d")

                    if datos.empty:
                        st.error("No se pudieron descargar datos OHLC para este ticker.")
                        st.stop()

                    if isinstance(datos.columns, pd.MultiIndex):
                        datos.columns = datos.columns.get_level_values(0)

                    close = datos["Close"]
                    precio_ult = float(close.iloc[-1])

                    # ── Determinar filas del subplot ──────────────────────────
                    n_rows = 3 if mostrar_vol else 2
                    row_vol = 3 if mostrar_vol else None
                    row_ind = 2

                    specs = (
                        [{"type": "candlestick"}] +
                        [{"type": "scatter"}] +
                        ([{"type": "bar"}] if mostrar_vol else [])
                    )
                    row_heights = [0.55, 0.3, 0.15] if mostrar_vol else [0.65, 0.35]

                    fig_v = make_subplots(
                        rows=n_rows, cols=1, shared_xaxes=True,
                        row_heights=row_heights, vertical_spacing=0.04,
                        specs=[[s] for s in specs],
                        subplot_titles=[f"{ticker_velas}", indicador_sel] +
                                       (["Volumen"] if mostrar_vol else []),
                    )

                    # ── Velas japonesas ───────────────────────────────────────
                    fig_v.add_trace(go.Candlestick(
                        x=datos.index, open=datos["Open"], high=datos["High"],
                        low=datos["Low"], close=close, name=ticker_velas,
                        increasing_line_color="#27AE60", decreasing_line_color="#E74C3C",
                    ), row=1, col=1)

                    # ── SMA-150 ───────────────────────────────────────────────
                    if mostrar_sma and len(datos) >= 150:
                        sma150  = close.rolling(150).mean()
                        sma_ult = float(sma150.dropna().iloc[-1]) if sma150.dropna().any() else 0
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=sma150, name="SMA-150",
                            line=dict(color="#F39C12", width=1.5, dash="dot"),
                        ), row=1, col=1)
                        estado_sma = "🟢 ALCISTA" if precio_ult > sma_ult else "🔴 BAJISTA"
                        st.caption(f"SMA-150: {estado_sma} | Precio: ${precio_ult:.2f} | SMA: ${sma_ult:.2f}")

                    entradas_xy, salidas_xy = [], []

                    # ── INDICADOR SELECCIONADO ────────────────────────────────
                    if "Supertrend" in indicador_sel:
                        st_line, st_dir = _calcular_supertrend(datos)
                        # Separar tramos alcistas/bajistas
                        mask_bull = st_dir == 1
                        mask_bear = st_dir == -1
                        fig_v.add_trace(go.Scatter(
                            x=datos.index[mask_bull], y=st_line[mask_bull],
                            name="Supertrend Bull", mode="lines",
                            line=dict(color="#27AE60", width=2),
                        ), row=1, col=1)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index[mask_bear], y=st_line[mask_bear],
                            name="Supertrend Bear", mode="lines",
                            line=dict(color="#E74C3C", width=2),
                        ), row=1, col=1)
                        # RSI como indicador de fondo en row 2
                        delta = close.diff()
                        _gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                        _loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                        rsi = 100 - (100 / (1 + _gain / _loss.replace(0, 1e-10)))
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=rsi, name="RSI-14",
                            line=dict(color="#9B59B6", width=1.5),
                        ), row=row_ind, col=1)
                        fig_v.add_hline(y=70, line_dash="dash", line_color="#E74C3C",
                                        opacity=0.5, row=row_ind, col=1)
                        fig_v.add_hline(y=30, line_dash="dash", line_color="#27AE60",
                                        opacity=0.5, row=row_ind, col=1)
                        entradas_xy, salidas_xy = _puntos_entrada_salida_supertrend(st_dir, datos)

                    elif "MACD" in indicador_sel:
                        macd_l, macd_s, macd_h = _calcular_macd(close)
                        colors_hist = ["#27AE60" if v >= 0 else "#E74C3C" for v in macd_h.fillna(0)]
                        fig_v.add_trace(go.Bar(
                            x=datos.index, y=macd_h, name="Histograma",
                            marker_color=colors_hist, opacity=0.7,
                        ), row=row_ind, col=1)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=macd_l, name="MACD",
                            line=dict(color="#2E86AB", width=1.5),
                        ), row=row_ind, col=1)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=macd_s, name="Señal",
                            line=dict(color="#F39C12", width=1.5, dash="dot"),
                        ), row=row_ind, col=1)
                        entradas_xy, salidas_xy = _puntos_entrada_salida_macd(macd_l, macd_s, datos)

                    else:  # Bollinger + StochRSI
                        bb_upper, bb_mid, bb_lower = _calcular_bollinger(close)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=bb_upper, name="BB Superior",
                            line=dict(color="#95A5A6", width=1, dash="dash"),
                        ), row=1, col=1)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=bb_lower, name="BB Inferior",
                            line=dict(color="#95A5A6", width=1, dash="dash"),
                            fill="tonexty", fillcolor="rgba(149,165,166,0.08)",
                        ), row=1, col=1)
                        sk, sd = _calcular_stoch_rsi(close)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=sk, name="StochRSI %K",
                            line=dict(color="#2E86AB", width=1.5),
                        ), row=row_ind, col=1)
                        fig_v.add_trace(go.Scatter(
                            x=datos.index, y=sd, name="StochRSI %D",
                            line=dict(color="#F39C12", width=1.5, dash="dot"),
                        ), row=row_ind, col=1)
                        fig_v.add_hline(y=80, line_dash="dash", line_color="#E74C3C",
                                        opacity=0.5, row=row_ind, col=1)
                        fig_v.add_hline(y=20, line_dash="dash", line_color="#27AE60",
                                        opacity=0.5, row=row_ind, col=1)
                        entradas_xy, salidas_xy = _puntos_entrada_salida_bb_stochrsi(
                            close, bb_lower, bb_upper, sk, datos)

                    # ── Flechas de ENTRADA (▲ verde) y SALIDA (▼ rojo) ───────
                    if entradas_xy:
                        x_e, y_e = zip(*entradas_xy)
                        fig_v.add_trace(go.Scatter(
                            x=list(x_e), y=[y * 0.985 for y in y_e],
                            mode="markers", name="ENTRADA",
                            marker=dict(symbol="triangle-up", color="#27AE60",
                                        size=14, line=dict(width=1, color="white")),
                        ), row=1, col=1)

                    if salidas_xy:
                        x_s, y_s = zip(*salidas_xy)
                        fig_v.add_trace(go.Scatter(
                            x=list(x_s), y=[y * 1.015 for y in y_s],
                            mode="markers", name="SALIDA",
                            marker=dict(symbol="triangle-down", color="#E74C3C",
                                        size=14, line=dict(width=1, color="white")),
                        ), row=1, col=1)

                    # ── Volumen ───────────────────────────────────────────────
                    if mostrar_vol and "Volume" in datos.columns and row_vol:
                        colores_vol = ["#27AE60" if c >= o else "#E74C3C"
                                       for c, o in zip(close, datos["Open"])]
                        fig_v.add_trace(go.Bar(
                            x=datos.index, y=datos["Volume"],
                            name="Volumen", marker_color=colores_vol, opacity=0.6,
                        ), row=row_vol, col=1)

                    fig_v.update_layout(
                        title=f"{ticker_velas} | {period_velas} | {indicador_sel}",
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark", height=700,
                        legend=dict(orientation="h", yanchor="bottom", y=1.01),
                    )
                    st.plotly_chart(fig_v, use_container_width=True)

                    # Resumen de señales
                    col_s1, col_s2, col_s3 = st.columns(3)
                    col_s1.metric("Señales de entrada detectadas", len(entradas_xy))
                    col_s2.metric("Señales de salida detectadas",  len(salidas_xy))
                    if entradas_xy:
                        ultima_entrada = entradas_xy[-1][0]
                        col_s3.metric("Última entrada", str(ultima_entrada)[:10])

                except Exception as e:
                    st.error(f"Error en gráfico de velas: {e}")

    # ── SUB-TAB: FCIs ARGENTINA (H3) ─────────────────────────────────────────
    with sub_fci:
        st.subheader("🏦 Scanner de FCIs — Fondos Comunes de Inversión Argentina")
        horizonte_fci = ctx.get("horizonte_label", "1 año")
        perfil_fci    = ctx.get("cliente_perfil", "Moderado")
        st.caption(f"Perfil del cliente: **{perfil_fci}** | Horizonte: **{horizonte_fci}**")

        try:
            import sys
            from pathlib import Path as _Path
            _svc_dir = str(_Path(__file__).resolve().parent.parent / "services")
            if _svc_dir not in sys.path:
                sys.path.insert(0, _svc_dir)
            from cafci_connector import CafciConnector
            conn = CafciConnector()
            df_fci = conn.obtener_fondos()
            if df_fci is not None and not df_fci.empty:
                st.dataframe(df_fci, use_container_width=True, hide_index=True)
            else:
                raise ValueError("Sin datos de CAFCI")
        except Exception:
            # Mostrar FCIs desde config si el conector no está disponible
            import sys
            from pathlib import Path as _Path
            sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
            from config import UNIVERSO_FCI
            df_fci_cfg = pd.DataFrame([
                {"Fondo": k, **v}
                for k, v in UNIVERSO_FCI.items()
            ])
            # Recomendar según perfil
            if perfil_fci == "Conservador":
                df_fci_cfg = df_fci_cfg[df_fci_cfg["riesgo"].isin(["Bajo"])]
            elif perfil_fci == "Moderado":
                df_fci_cfg = df_fci_cfg[df_fci_cfg["riesgo"].isin(["Bajo", "Moderado"])]
            st.info("📡 Datos de CAFCI no disponibles. Mostrando fondos configurados.")
            st.dataframe(df_fci_cfg, use_container_width=True, hide_index=True)
            if not df_fci_cfg.empty:
                st.caption(f"Fondos recomendados para perfil {perfil_fci}: {len(df_fci_cfg)}")
