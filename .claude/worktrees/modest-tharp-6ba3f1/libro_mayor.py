"""
libro_mayor.py — Libro Mayor de Operaciones
MQ26-DSS | Tabla editable + importar desde Excel
Moneda principal: ARS | USD al lado
Maneja PPC mixto: "usd 1,60" | "$34,58" | 13.14 → siempre USD
Calcula: PPC_ARS = PPC_USD × CCL | Valor actual | P&L ARS y USD | Peso %
"""
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.logging_config import get_logger
from core.pricing_utils import parsear_ppc_usd  # centralizado en pricing_utils

logger = get_logger(__name__)


# ─── CARGA DESDE EXCEL ────────────────────────────────────────────────────────
def cargar_desde_excel(ruta: Path) -> pd.DataFrame:
    """
    Lee Maestra_Inversiones.xlsx y normaliza a formato estándar del Libro Mayor.
    Columnas de salida:
        Propietario | Cartera | Ticker | Tipo | Cantidad | PPC_USD | Fecha
    """
    if not ruta.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(ruta, sheet_name=0)
        df.columns = [c.strip() for c in df.columns]

        resultado = pd.DataFrame({
            'Propietario': df.get('Propietario', '').astype(str).str.strip(),
            'Cartera':     df.get('Cartera', '').astype(str).str.strip(),
            'Ticker':      df.get('Ticker', '').astype(str).str.strip().str.upper(),
            'Tipo':        df.get('Tipo', 'Cedears').astype(str).str.strip(),
            'Cantidad':    pd.to_numeric(df.get('Cantidad', 0), errors='coerce').fillna(0).astype(int),
            'PPC_USD':     df.get('PPC_USD', 0).apply(parsear_ppc_usd),
            'Fecha':       pd.to_datetime(df.get('FECHA_INICIAL', df.get('Fecha', date.today())), errors='coerce').dt.date,
        })
        resultado = resultado[resultado['Cantidad'] > 0]
        resultado = resultado[resultado['Ticker'] != '']
        return resultado.reset_index(drop=True)
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
        return pd.DataFrame()


def agregar_por_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa múltiples compras del mismo ticker en una cartera.
    PPC_USD_PROM = promedio ponderado por cantidad.
    """
    if df.empty:
        return df
    grupos = []
    for (prop, cartera, ticker), g in df.groupby(['Propietario', 'Cartera', 'Ticker']):
        cant_total = g['Cantidad'].sum()
        inv_total  = (g['Cantidad'] * g['PPC_USD']).sum()
        ppc_prom   = inv_total / cant_total if cant_total > 0 else 0.0
        tipo       = g['Tipo'].iloc[0]
        grupos.append({
            'Propietario': prop,
            'Cartera':     cartera,
            'Ticker':      ticker,
            'Tipo':        tipo,
            'Cantidad':    int(cant_total),
            'PPC_USD':     round(ppc_prom, 4),
            'Inv_USD':     round(inv_total, 2),
        })
    return pd.DataFrame(grupos)


# ─── CÁLCULOS COMPLETOS ────────────────────────────────────────────────────────
def calcular_libro_mayor(
    df_posiciones: pd.DataFrame,
    precios_usd: dict,      # {ticker: precio_USD_actual}
    ratios: dict,           # {ticker: ratio_cedear}
    ccl: float,
) -> pd.DataFrame:
    """
    Calcula el Libro Mayor completo con todas las columnas.

    Lógica CEDEARs:
      - PPC_USD = precio pagado POR CEDEAR (no por acción subyacente)
      - Precio actual USD = precio_subyacente_USD / ratio
      - Precio ARS = precio_USD_cedear × CCL
      - Inversión ARS = Cantidad × PPC_USD × CCL
      - Valor actual ARS = Cantidad × Precio_ARS_actual

    Lógica Acciones locales (CEPU, YPFD, TGNO4, PAMP):
      - PPC_USD = precio en USD (cotización en dólares cable)
      - Precio actual USD = desde yfinance .BA / CCL
      - Todo igual al CEDEAR con ratio = 1
    """
    if df_posiciones.empty:
        return pd.DataFrame()

    rows = []
    for _, pos in df_posiciones.iterrows():
        ticker   = str(pos['Ticker']).upper().strip()
        cantidad = int(pos.get('Cantidad', 0))
        ppc_usd  = float(pos.get('PPC_USD', 0.0))
        tipo     = str(pos.get('Tipo', 'Cedears'))

        ratio       = float(ratios.get(ticker, 1.0))
        precio_usd  = float(precios_usd.get(ticker, 0.0))   # precio del subyacente USD

        # Precio del CEDEAR en USD = subyacente / ratio
        if ratio > 0 and precio_usd > 0:
            precio_cedear_usd = precio_usd / ratio
        else:
            precio_cedear_usd = 0.0

        # Precio del CEDEAR en ARS = precio_cedear_usd × CCL
        precio_cedear_ars = precio_cedear_usd * ccl

        # Inversión: cuánto pagaste en total
        inv_usd = cantidad * ppc_usd
        inv_ars = inv_usd * ccl

        # Valor actual
        valor_ars = cantidad * precio_cedear_ars
        valor_usd = cantidad * precio_cedear_usd

        # P&L
        pnl_ars = valor_ars - inv_ars
        pnl_usd = valor_usd - inv_usd
        pnl_pct = (pnl_ars / inv_ars) if inv_ars > 0 else 0.0

        rows.append({
            'Ticker':        ticker,
            'Tipo':          tipo,
            'Cantidad':      cantidad,
            'Ratio':         int(ratio),
            'PPC_USD':       round(ppc_usd, 4),
            'PPC_ARS':       round(ppc_usd * ccl, 2),
            'Px_USD_actual': round(precio_cedear_usd, 4),
            'Px_ARS_actual': round(precio_cedear_ars, 2),
            'Inv_USD':       round(inv_usd, 2),
            'Inv_ARS':       round(inv_ars, 0),
            'Valor_ARS':     round(valor_ars, 0),
            'Valor_USD':     round(valor_usd, 2),
            'PnL_ARS':       round(pnl_ars, 0),
            'PnL_USD':       round(pnl_usd, 2),
            'PnL_%':         round(pnl_pct * 100, 2),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        total_valor = df['Valor_ARS'].sum()
        df['Peso_%'] = (df['Valor_ARS'] / total_valor * 100).round(2) if total_valor > 0 else 0.0
    return df


# ─── RENDERIZADO EN STREAMLIT ─────────────────────────────────────────────────
def render_libro_mayor(
    ruta_excel: Path,
    ratios: dict,
    precios_usd: dict,
    ccl: float,
    cartera_filtro: str = None,
):
    """
    Renderiza el Libro Mayor completo con:
    - Importar desde Excel
    - Tabla editable para agregar/modificar operaciones
    - Tabla de resumen con cálculos correctos
    - Totales y métricas
    """
    st.markdown("### 📒 Libro Mayor de Operaciones")

    # ── Importar desde Excel ──────────────────────────────────────────────────
    col_imp1, col_imp2 = st.columns([2, 1])
    with col_imp1:
        archivo = st.file_uploader(
            "📂 Importar desde Excel (Maestra_Inversiones.xlsx):",
            type=["xlsx"],
            key="uploader_libro_mayor"
        )
    with col_imp2:
        st.markdown("<br>", unsafe_allow_html=True)
        usar_excel_local = st.button("📥 Cargar Excel guardado localmente", key="btn_cargar_local")

    # Cargar datos
    if archivo is not None:
        df_raw = pd.read_excel(archivo, sheet_name=0)
        df_raw.columns = [c.strip() for c in df_raw.columns]
        df_importado = pd.DataFrame({
            'Propietario': df_raw.get('Propietario', '').astype(str).str.strip(),
            'Cartera':     df_raw.get('Cartera', '').astype(str).str.strip(),
            'Ticker':      df_raw.get('Ticker', '').astype(str).str.strip().str.upper(),
            'Tipo':        df_raw.get('Tipo', 'Cedears').astype(str).str.strip(),
            'Cantidad':    pd.to_numeric(df_raw.get('Cantidad', 0), errors='coerce').fillna(0).astype(int),
            'PPC_USD':     df_raw.get('PPC_USD', 0).apply(parsear_ppc_usd),
            'Fecha':       pd.to_datetime(df_raw.get('FECHA_INICIAL', date.today()), errors='coerce').dt.strftime('%Y-%m-%d'),
            'Notas':       '',
        })
        st.session_state['libro_mayor_data'] = df_importado.to_dict('records')
        st.success(f"✅ {len(df_importado)} operaciones importadas desde Excel.")

    elif usar_excel_local:
        df_local = cargar_desde_excel(ruta_excel)
        if not df_local.empty:
            df_local['Fecha'] = df_local['Fecha'].astype(str)
            df_local['Notas'] = ''
            st.session_state['libro_mayor_data'] = df_local.to_dict('records')
            st.success(f"✅ {len(df_local)} operaciones cargadas desde Excel local.")
        else:
            st.warning("No se encontró el Excel local.")

    # ── Tabla editable ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ✏️ Tabla de operaciones (editable)")
    st.caption("Podés agregar filas, editar o eliminar. PPC siempre en USD por nominal.")

    # Datos por defecto si no hay nada cargado
    if 'libro_mayor_data' not in st.session_state:
        if ruta_excel.exists():
            df_init = cargar_desde_excel(ruta_excel)
            # Normalizar nombre de columna de fecha
            if 'FECHA_INICIAL' in df_init.columns and 'Fecha' not in df_init.columns:
                df_init = df_init.rename(columns={'FECHA_INICIAL': 'Fecha'})
            if 'Fecha' in df_init.columns:
                df_init['Fecha'] = df_init['Fecha'].astype(str)
            else:
                df_init['Fecha'] = str(date.today())
            df_init['Notas'] = ''
            if cartera_filtro and cartera_filtro != "-- Todas las carteras --":
                prop = cartera_filtro.split("|")[0].strip() if "|" in cartera_filtro else cartera_filtro
                cart = cartera_filtro.split("|")[1].strip() if "|" in cartera_filtro else ""
                df_init = df_init[df_init['Propietario'].str.contains(prop, case=False, na=False)]
                if cart:
                    df_init = df_init[df_init['Cartera'].str.contains(cart, case=False, na=False)]
            st.session_state['libro_mayor_data'] = df_init.to_dict('records')
        else:
            st.session_state['libro_mayor_data'] = []

    df_editable = pd.DataFrame(st.session_state['libro_mayor_data'])
    if df_editable.empty:
        df_editable = pd.DataFrame(columns=['Propietario','Cartera','Ticker','Tipo','Cantidad','PPC_USD','Fecha','Gastos_Operacion','Notas'])

    # ── Normalizar tipos para el editor ──────────────────────────────────────
    for col in ['Propietario','Cartera','Ticker','Tipo','Notas']:
        if col not in df_editable.columns:
            df_editable[col] = ''
        df_editable[col] = df_editable[col].astype(str)

    if 'Gastos_Operacion' not in df_editable.columns:
        df_editable['Gastos_Operacion'] = 0.0
    df_editable['Gastos_Operacion'] = pd.to_numeric(df_editable['Gastos_Operacion'], errors='coerce').fillna(0.0)

    if 'Cantidad' not in df_editable.columns:
        df_editable['Cantidad'] = 0
    df_editable['Cantidad'] = pd.to_numeric(df_editable['Cantidad'], errors='coerce').fillna(0).astype(int)

    if 'PPC_USD' not in df_editable.columns:
        df_editable['PPC_USD'] = 0.0
    df_editable['PPC_USD'] = pd.to_numeric(df_editable['PPC_USD'], errors='coerce').fillna(0.0)

    # Fecha → tipo date para DateColumn
    if 'Fecha' not in df_editable.columns:
        df_editable['Fecha'] = date.today()
    df_editable['Fecha'] = pd.to_datetime(df_editable['Fecha'], errors='coerce').dt.date
    df_editable['Fecha'] = df_editable['Fecha'].apply(lambda x: x if pd.notna(x) else date.today())

    st.caption(
        "✏️ **Fecha** usa selector de calendario. "
        "**PPC** en USD para CEDEARs (precio subyacente / ratio²), en ARS para activos locales. "
        "**Gastos_Operacion** en ARS (comisiones, derechos de mercado). "
        "Podés agregar filas nuevas o editar cualquier campo — luego **💾 Guardar**."
    )

    df_resultado = st.data_editor(
        df_editable.reset_index(drop=True),
        num_rows="dynamic", use_container_width=True,
        column_config={
            "Propietario":       st.column_config.TextColumn("Propietario", width="medium"),
            "Cartera":           st.column_config.TextColumn("Cartera", width="medium"),
            "Ticker":            st.column_config.TextColumn("Ticker", width="small"),
            "Tipo":              st.column_config.SelectboxColumn(
                                     "Tipo instrumento",
                                     options=[
                                         "CEDEAR", "ACCION_LOCAL", "BONO", "BONO_USD",
                                         "LETRA", "FCI", "ON", "ON_USD", "ETF", "OTRO"
                                     ],
                                     width="medium",
                                     help="CEDEAR: activo extranjero. ACCION_LOCAL/BONO/LETRA/FCI: ARS directo (sin CCL)."
                                 ),
            "Cantidad":          st.column_config.NumberColumn("Cantidad", min_value=0, step=1, width="small"),
            "PPC_USD":           st.column_config.NumberColumn(
                                     "PPC_USD",
                                     min_value=0.0, format="%.4f", width="medium",
                                     help="CEDEARs: precio subyacente / ratio². Locales: precio en ARS.",
                                 ),
            "Fecha":             st.column_config.DateColumn(
                                     "Fecha compra", format="DD/MM/YYYY", width="medium"
                                 ),
            "Gastos_Operacion":  st.column_config.NumberColumn(
                                     "Gastos ARS", format="$%,.0f", min_value=0.0, step=100.0,
                                     help="Comisiones + derechos de mercado en ARS.",
                                     width="medium",
                                 ),
            "Notas":             st.column_config.TextColumn("Notas", width="large"),
        },
        key="editor_libro_mayor",
        hide_index=True,
    )

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        if st.button("💾 Guardar cambios", type="primary", key="btn_guardar_libro"):
            # Normalizar fecha a string antes de guardar en session_state / Excel / CSV
            df_guardar = df_resultado.copy()
            df_guardar['Fecha'] = df_guardar['Fecha'].apply(
                lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)
            )
            st.session_state['libro_mayor_data'] = df_guardar.to_dict('records')

            # ── Guardar en Excel con backup automático ────────────────────────
            try:
                df_xl = df_guardar.copy()
                df_xl['PPC_USD'] = df_xl['PPC_USD'].apply(lambda x: f"{x:.4f}")
                if ruta_excel.exists():
                    import shutil
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    ruta_bak = ruta_excel.with_suffix(f".bak_{ts}.xlsx")
                    shutil.copy2(ruta_excel, ruta_bak)
                    baks = sorted(ruta_excel.parent.glob(f"{ruta_excel.stem}.bak_*.xlsx"))
                    for bak_old in baks[:-3]:
                        try: bak_old.unlink()
                        except Exception: pass
                df_xl.to_excel(ruta_excel, index=False)
            except Exception as e:
                st.warning(f"No se pudo guardar Excel: {e}")

            # ── Sincronizar también en Maestra_Transaccional.csv ─────────────
            try:
                import csv as _csv
                ruta_csv = ruta_excel.parent / "Maestra_Transaccional.csv"
                # Leer CSV existente y remover filas de esta cartera
                filas_orig = []
                if ruta_csv.exists():
                    with open(ruta_csv, encoding="utf-8") as fh:
                        filas_orig = list(_csv.reader(fh))
                header_csv = filas_orig[0] if filas_orig else [
                    "CARTERA","FECHA_COMPRA","TICKER","CANTIDAD","PPC_USD","PPC_ARS","TIPO"
                ]
                if cartera_filtro and cartera_filtro != "-- Todas las carteras --":
                    prop_filt = cartera_filtro.split("|")[0].strip() if "|" in cartera_filtro else cartera_filtro
                    cart_filt = cartera_filtro.split("|")[1].strip() if "|" in cartera_filtro else ""
                    filas_resto = [
                        r for r in filas_orig[1:]
                        if r and not (
                            prop_filt.lower() in r[0].lower()
                            and (not cart_filt or cart_filt.lower() in r[0].lower())
                        )
                    ]
                else:
                    filas_resto = filas_orig[1:]

                # Generar nuevas filas desde el editor
                from config import RATIOS_CEDEAR as _RATIOS
                nuevas = []
                for _, row in df_guardar[df_guardar['Cantidad'] > 0].iterrows():
                    ticker   = str(row.get('Ticker','')).upper().strip()
                    cartera  = f"{row.get('Propietario','')} | {row.get('Cartera','')}".strip(" |")
                    cantidad = int(row.get('Cantidad', 0))
                    ppc_usd  = float(row.get('PPC_USD', 0))
                    tipo     = str(row.get('Tipo','CEDEAR'))
                    fecha_s  = str(row.get('Fecha', ''))[:10]
                    ratio    = float(_RATIOS.get(ticker, 1.0))
                    from config import CCL_HISTORICO as _CCL_HIST
                    try:
                        import datetime as _dt
                        fd = _dt.date.fromisoformat(fecha_s)
                        ccl_hist = next((v for d, v in sorted(_CCL_HIST.items(), reverse=True) if _dt.date.fromisoformat(d) <= fd), ccl)
                    except Exception:
                        ccl_hist = ccl
                    ppc_ars  = round(ppc_usd * ccl_hist, 2)
                    nuevas.append([cartera, fecha_s, ticker, cantidad, round(ppc_usd, 6), ppc_ars, tipo])

                with open(ruta_csv, "w", newline="", encoding="utf-8") as fh:
                    wr = _csv.writer(fh)
                    wr.writerow(header_csv)
                    wr.writerows(filas_resto)
                    wr.writerows(nuevas)

                st.toast(f"✅ Guardado en Excel y CSV ({len(nuevas)} posiciones). Backup creado.", icon="💾")
            except Exception as e:
                st.toast("✅ Excel guardado (no se actualizó CSV).", icon="💾")
                st.warning(f"CSV no sincronizado: {e}")

    with col_g2:
        if st.button("🔄 Actualizar tabla", key="btn_actualizar_libro"):
            df_tmp = df_resultado.copy()
            df_tmp['Fecha'] = df_tmp['Fecha'].apply(
                lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)
            )
            st.session_state['libro_mayor_data'] = df_tmp.to_dict('records')
            st.rerun()
    with col_g3:
        if st.button("🗑️ Limpiar tabla", key="btn_limpiar_libro"):
            st.session_state['libro_mayor_data'] = []
            st.rerun()

    # ── Tabla de cálculos con P&L ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"#### 📊 Posición Neta — CCL: **${ccl:,.0f}** ARS/USD")

    df_calc_input = df_resultado[df_resultado['Cantidad'] > 0].copy()
    df_calc_input['PPC_USD'] = pd.to_numeric(df_calc_input['PPC_USD'], errors='coerce').fillna(0.0)
    df_calc_input['Ticker'] = df_calc_input['Ticker'].str.upper().str.strip()

    # Filtrar por cartera si aplica
    if cartera_filtro and cartera_filtro != "-- Todas las carteras --":
        prop = cartera_filtro.split("|")[0].strip() if "|" in cartera_filtro else cartera_filtro
        cart = cartera_filtro.split("|")[1].strip() if "|" in cartera_filtro else ""
        mask = df_calc_input['Propietario'].str.contains(prop, case=False, na=False)
        if cart:
            mask = mask & df_calc_input['Cartera'].str.contains(cart, case=False, na=False)
        df_calc_input = df_calc_input[mask]

    if df_calc_input.empty:
        st.info("Sin posiciones para mostrar. Cargá operaciones en la tabla de arriba.")
        return pd.DataFrame()

    # Agregar por ticker (promediar PPC de múltiples compras)
    df_agrupado = agregar_por_ticker(df_calc_input)

    # Calcular libro mayor
    df_libro = calcular_libro_mayor(df_agrupado, precios_usd, ratios, ccl)

    if df_libro.empty:
        st.warning("No se pudieron calcular los valores actuales.")
        return pd.DataFrame()

    # Colorización
    def color_pnl(val):
        try:
            v = float(val)
            if v > 0:  return 'color: #27AE60; font-weight: bold'
            if v < 0:  return 'color: #E74C3C; font-weight: bold'
        except (ValueError, TypeError): pass
        return ''

    def color_peso(val):
        try:
            v = float(val)
            if v > 18: return 'background-color: #FFF3CD'
        except (ValueError, TypeError): pass
        return ''

    st.dataframe(
        df_libro.style
            .format({
                'PPC_USD':       '${:,.4f}',
                'PPC_ARS':       '${:,.2f}',
                'Px_USD_actual': '${:,.4f}',
                'Px_ARS_actual': '${:,.2f}',
                'Inv_USD':       '${:,.2f}',
                'Inv_ARS':       '${:,.0f}',
                'Valor_ARS':     '${:,.0f}',
                'Valor_USD':     '${:,.2f}',
                'PnL_ARS':       '${:,.0f}',
                'PnL_USD':       '${:,.2f}',
                'PnL_%':         '{:+.2f}%',
                'Peso_%':        '{:.2f}%',
            })
            .map(color_pnl,  subset=['PnL_ARS', 'PnL_USD', 'PnL_%'])
            .map(color_peso, subset=['Peso_%']), use_container_width=True,
        hide_index=True,
        height=420,
    )

    # ── Totales ───────────────────────────────────────────────────────────────
    total_inv_ars  = df_libro['Inv_ARS'].sum()
    total_val_ars  = df_libro['Valor_ARS'].sum()
    total_pnl_ars  = df_libro['PnL_ARS'].sum()
    total_inv_usd  = df_libro['Inv_USD'].sum()
    total_val_usd  = df_libro['Valor_USD'].sum()
    total_pnl_usd  = df_libro['PnL_USD'].sum()
    pnl_pct_total  = (total_pnl_ars / total_inv_ars * 100) if total_inv_ars > 0 else 0.0

    st.markdown("---")
    t1, t2, t3, t4, t5, t6 = st.columns(6)
    t1.metric("💰 Invertido ARS",   f"${total_inv_ars:,.0f}")
    t2.metric("📊 Valor actual ARS", f"${total_val_ars:,.0f}")
    t3.metric("📈 P&L ARS",
              f"${total_pnl_ars:,.0f}",
              f"{pnl_pct_total:+.2f}%",
              delta_color="normal")
    t4.metric("💵 Invertido USD",    f"${total_inv_usd:,.0f}")
    t5.metric("📊 Valor actual USD", f"${total_val_usd:,.0f}")
    t6.metric("📈 P&L USD",
              f"${total_pnl_usd:,.2f}",
              delta_color="normal")

    # Alerta concentración
    sobreweight = df_libro[df_libro['Peso_%'] > 18]
    if not sobreweight.empty:
        st.warning(f"⚠️ Concentración >18%: {', '.join(sobreweight['Ticker'].tolist())} — revisá el rebalanceo")

    return df_libro
