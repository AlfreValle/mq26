"""
data_engine.py — Motor de Datos
Master Quant 26 | Estrategia Capitales
Carga transaccional, universo de activos, precios en tiempo real e históricos.
"""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    CCL_FACTOR_GGAL,
    CCL_FALLBACK,
    RUTA_ANALISIS,
    RUTA_MAESTRA,
    RUTA_TRANSAC,
    RUTA_UNIVERSO,
    SECTORES,
    UNIVERSO_BASE,
)
from core.pricing_utils import ccl_historico_por_fecha, obtener_ratio as ratio_desde_universo_o_config


# ─── UTILIDADES ───────────────────────────────────────────────────────────────
def limpiar_ppc(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    v = str(val).lower().replace("usd","").replace("$","").replace("u$s","").replace(" ","")
    if "." in v and "," in v:
        v = v.replace(".", "").replace(",", ".") if v.index(".") < v.index(",") else v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try: return float(v)
    except (ValueError, TypeError): return 0.0

def parse_ratio(valor) -> float:
    """Parsea el ratio de un CEDEAR desde distintos formatos ('20', '20:1', 20.0)."""
    try: return float(str(valor).split(":")[0].strip())
    except (ValueError, TypeError): return 1.0

def asignar_sector(ticker: str) -> str:
    return SECTORES.get(ticker.upper(), "Otros")


def alinear_panel_precios_cierre(
    data: pd.DataFrame,
    *,
    strict_inner: bool = True,
    ffill_limit: int = 2,
) -> pd.DataFrame:
    """
    Alineación calendario NY / BYMA (C03).

    Por defecto solo conserva fechas donde **todos** los activos tienen cierre no-NaN,
    evitando ffill agresivo que mezcla sesiones distintas.

    Si strict_inner=False: ffill acotado por columna y luego dropna(how='any').
    """
    if data.empty or data.shape[1] == 0:
        return data
    df = data.sort_index()
    if strict_inner:
        return df.dropna(how="any")
    df = df.ffill(limit=ffill_limit).bfill(limit=ffill_limit)
    return df.dropna(how="any")


def ticker_yahoo(ticker: str, universo_df=None) -> str:
    t = ticker.upper().strip()
    traducciones = {"BRKB":"BRK-B","BRK/B":"BRK-B","YPFD":"YPF",
                    "CEPU":"CEPU.BA","TGNO4":"TGNO4.BA","PAMP":"PAM","DISN":"DIS"}
    if universo_df is not None and not universo_df.empty:
        row = universo_df[universo_df["Ticker"].str.upper() == t]
        if not row.empty and "Tipo" in row.columns:
            if "Local" in str(row["Tipo"].iloc[0]):
                return f"{t}.BA"
    return traducciones.get(t, t)

def obtener_ccl() -> float:
    """F4: Delega en market_connector.obtener_ccl_mep() — función única, sin duplicado."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services"))
        from market_connector import obtener_ccl_mep as _get_ccl
        return _get_ccl()
    except Exception:
        # Fallback directo si market_connector no está disponible
        try:
            ba  = yf.Ticker("GGAL.BA").history(period="2d")["Close"].dropna().iloc[-1]
            adr = yf.Ticker("GGAL").history(period="2d")["Close"].dropna().iloc[-1]
            if adr > 0:
                return round((ba / adr) * CCL_FACTOR_GGAL, 2)
        except Exception:
            pass
        return CCL_FALLBACK

# ─── DATA ENGINE ──────────────────────────────────────────────────────────────
class DataEngine:
    """Motor de datos puro — sin dependencias de UI. Lanza excepciones nativas."""

    def __init__(self):
        self.universo_df = pd.DataFrame()
        self._cargar_universo()

    def _cargar_universo(self):
        try:
            if RUTA_UNIVERSO.exists():
                df = pd.read_excel(RUTA_UNIVERSO)
                df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
                df["Ratio"] = df["Ratio"].apply(parse_ratio)
                self.universo_df = df
        except Exception as e:
            raise RuntimeError(f"Error cargando universo: {e}") from e

    def cargar_transaccional(self) -> pd.DataFrame:
        if RUTA_TRANSAC.exists():
            df = pd.read_csv(RUTA_TRANSAC, encoding="utf-8-sig")
            if "FECHA_COMPRA" in df.columns:
                df["FECHA_COMPRA"] = pd.to_datetime(df["FECHA_COMPRA"], errors="coerce").dt.date
            for col in ["PPC_USD","PPC_ARS"]:
                if col in df.columns: df[col] = df[col].apply(limpiar_ppc)
            if "LAMINA_VN" not in df.columns:
                df["LAMINA_VN"] = float("nan")
            else:
                df["LAMINA_VN"] = pd.to_numeric(df["LAMINA_VN"], errors="coerce")
            # Validación D3: informar filas problemáticas sin crashear
            self._validacion_csv = self._validar_csv(df)
            return df
        return self._migrar_desde_maestra()

    def _validar_csv(self, df: pd.DataFrame) -> dict:
        """
        MQ2-A10: Validación vectorizada del CSV transaccional (~20x más rápida que bucle fila-fila).
        Agrega validación de coherencia temporal (MQ2-S6): fechas anteriores a 2010 o futuras.
        """
        import datetime as _dt

        if df.empty:
            return {"total": 0, "validas": 0, "invalidas": 0, "detalle": []}

        _df = df.copy().reset_index(drop=True)
        hoy = _dt.date.today()

        # Vectorize columns
        cant_s = pd.to_numeric(_df.get("CANTIDAD", 0), errors="coerce").fillna(0)
        ppc_s  = pd.to_numeric(_df.get("PPC_USD", 0),  errors="coerce").fillna(0)
        tick_s = _df.get("TICKER", pd.Series([""] * len(_df))).astype(str).str.strip()

        # Fechas: parsear vectorizadamente
        fecha_s = pd.to_datetime(_df.get("FECHA_COMPRA", pd.NaT), errors="coerce")
        _min_fecha = pd.Timestamp("2010-01-01")
        _max_fecha = pd.Timestamp(hoy) + pd.Timedelta(days=1)

        mask_cant    = cant_s == 0
        mask_ppc     = ppc_s <= 0
        mask_ticker  = tick_s.isin(["", "nan", "NaN", "none"])
        mask_futura  = fecha_s > _max_fecha
        mask_antigua = fecha_s < _min_fecha
        mask_fecha_inv = fecha_s.isna()

        mask_any = mask_cant | mask_ppc | mask_ticker | mask_futura | mask_antigua | mask_fecha_inv
        idx_problemas = _df.index[mask_any].tolist()

        problemas = []
        for i in idx_problemas[:20]:
            msgs = []
            if mask_cant.iloc[i]:     msgs.append("CANTIDAD = 0")
            if mask_ppc.iloc[i]:      msgs.append("PPC_USD <= 0")
            if mask_ticker.iloc[i]:   msgs.append("TICKER vacío")
            if mask_fecha_inv.iloc[i]:msgs.append("FECHA inválida")
            elif mask_futura.iloc[i]: msgs.append(f"FECHA futura ({fecha_s.iloc[i].date()})")
            elif mask_antigua.iloc[i]:msgs.append(f"FECHA anterior a 2010 ({fecha_s.iloc[i].date()})")
            problemas.append({
                "fila": i + 2,
                "ticker": str(tick_s.iloc[i]),
                "problemas": ", ".join(msgs),
            })

        total_inv = int(mask_any.sum())
        return {
            "total":    len(_df),
            "validas":  len(_df) - total_inv,
            "invalidas": total_inv,
            "detalle":  problemas,
        }

    def _migrar_desde_maestra(self) -> pd.DataFrame:
        """Migra Maestra_Inversiones.xlsx al CSV transaccional (primera ejecución)."""
        if not RUTA_MAESTRA.exists():
            return pd.DataFrame(columns=[
                "CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD",
                "PPC_USD", "PPC_ARS", "TIPO", "LAMINA_VN",
            ])
        df = pd.read_excel(RUTA_MAESTRA)
        df.columns = [c.strip() for c in df.columns]
        prop  = df.get("Propietario", pd.Series([""] * len(df))).astype(str)
        cart  = df.get("Cartera",     pd.Series([""] * len(df))).astype(str)
        _lam  = df.get("LAMINA_VN", df.get("Lamina", pd.Series([float("nan")] * len(df))))
        trans = pd.DataFrame({
            "CARTERA":      prop + " | " + cart,
            "FECHA_COMPRA": pd.to_datetime(df.get("FECHA_INICIAL",""), errors="coerce").dt.date,
            "TICKER":       df.get("Ticker", df.get("TICKER","")).astype(str).str.strip().str.upper(),
            "CANTIDAD":     pd.to_numeric(df.get("Cantidad", df.get("CANTIDAD",0)), errors="coerce").fillna(0),
            "PPC_USD":      df.get("PPC_USD", 0).apply(limpiar_ppc),
            "PPC_ARS":      0.0,
            "TIPO":         df.get("Tipo", "CEDEAR"),
            "LAMINA_VN":    pd.to_numeric(_lam, errors="coerce"),
        })
        trans = trans[trans["CANTIDAD"] != 0].reset_index(drop=True)
        trans.to_csv(RUTA_TRANSAC, index=False)
        return trans

    def guardar_transaccional(self, df: pd.DataFrame):
        df = df.dropna(subset=["TICKER"])
        df = df[df["CANTIDAD"] != 0]
        df.to_csv(RUTA_TRANSAC, index=False)

    def cargar_analisis(self) -> pd.DataFrame:
        if RUTA_ANALISIS.exists():
            df = pd.read_excel(RUTA_ANALISIS)
            df.columns = [c.upper().strip() for c in df.columns]
            df["TICKER"] = df["TICKER"].astype(str).str.strip().str.upper()
            return df
        return pd.DataFrame(columns=["TICKER","PUNTAJE_TECNICO","ESTADO"])

    def agregar_cartera(self, df_trans: pd.DataFrame, cartera: str) -> pd.DataFrame:
        from core.pricing_utils import es_instrumento_local_ars

        df_c = df_trans[df_trans["CARTERA"] == cartera].copy()
        if df_c.empty: return pd.DataFrame()
        df_c["TICKER"] = df_c["TICKER"].str.upper().str.strip()

        rows = []
        for ticker_key, g in df_c.groupby("TICKER"):
            cant_neta     = g["CANTIDAD"].sum()
            buys          = g[g["CANTIDAD"] > 0]
            cant_comprada = buys["CANTIDAD"].sum()
            tipo_instr    = str(g["TIPO"].iloc[0]) if "TIPO" in g.columns else "CEDEAR"
            es_local      = es_instrumento_local_ars(str(ticker_key), tipo_instr)
            _lam_s = pd.to_numeric(g.get("LAMINA_VN", pd.Series(dtype=float)), errors="coerce").dropna()
            lamina_vn = float(_lam_s.iloc[0]) if not _lam_s.empty else float("nan")

            inv_comprada  = (buys["CANTIDAD"] * buys["PPC_USD"]).sum()
            ppc_prom      = inv_comprada / cant_comprada if cant_comprada > 0 else 0.0
            ratio         = 1.0 if es_local else float(self.obtener_ratio(str(ticker_key)))

            inv_ars_hist = 0.0
            if not buys.empty and "FECHA_COMPRA" in buys.columns:
                for _, row in buys.iterrows():
                    cant_r = float(row["CANTIDAD"])
                    if es_local:
                        # Instrumento local ARS: usar PPC_ARS directo si está disponible,
                        # o PPC_USD como precio en ARS (convención para locales).
                        ppc_ars_r = float(row.get("PPC_ARS", 0) or 0)
                        if ppc_ars_r > 0:
                            inv_ars_hist += cant_r * ppc_ars_r
                        else:
                            # fallback: PPC_USD interpretado como precio ARS
                            inv_ars_hist += cant_r * float(row["PPC_USD"])
                    else:
                        # CEDEAR: fórmula estándar con CCL histórico y ratio
                        fecha_key = str(row.get("FECHA_COMPRA", ""))[:7]
                        ccl_hist  = ccl_historico_por_fecha(fecha_key, fallback=1350.0)
                        inv_ars_hist += cant_r * float(row["PPC_USD"]) * ccl_hist * ratio

            rows.append({
                "TICKER":            ticker_key,
                "CANTIDAD_TOTAL":    cant_neta,
                "PPC_USD_PROM":      ppc_prom,
                "INV_USD_TOTAL":     inv_comprada,
                "INV_ARS_HISTORICO": inv_ars_hist,
                "TIPO":              tipo_instr,
                "ES_LOCAL":          es_local,
                "LAMINA_VN":         lamina_vn,
            })

        if not rows:
            return pd.DataFrame()

        df_result = pd.DataFrame(rows)
        # Solo retornar tickers con posición neta positiva
        return df_result[df_result["CANTIDAD_TOTAL"] > 0].reset_index(drop=True)

    def calcular_ppc_fifo(self, transacciones_ticker: pd.DataFrame) -> float:
        """
        B11: Calcula el PPC según criterio FIFO (primeras compras = primeras ventas).
        Estándar contable impositivo en Argentina.
        Retorna el PPC promedio de las unidades que quedan en cartera.
        """
        if transacciones_ticker.empty:
            return 0.0

        df = transacciones_ticker.sort_values("FECHA_COMPRA").copy()
        compras = []  # lista de (cant, ppc_usd)

        for _, row in df.iterrows():
            cant  = float(row.get("CANTIDAD", 0))
            ppc   = float(row.get("PPC_USD", 0))
            if cant > 0:
                compras.append([cant, ppc])
            elif cant < 0:
                # Venta: consumir compras más antiguas primero (FIFO)
                cant_venta = abs(cant)
                while cant_venta > 0 and compras:
                    if compras[0][0] <= cant_venta:
                        cant_venta -= compras[0][0]
                        compras.pop(0)
                    else:
                        compras[0][0] -= cant_venta
                        cant_venta = 0

        if not compras:
            return 0.0

        total_cant = sum(c[0] for c in compras)
        total_inv  = sum(c[0] * c[1] for c in compras)
        return total_inv / total_cant if total_cant > 0 else 0.0

    def agregar_cartera_fifo(self, df_trans: pd.DataFrame, cartera: str) -> pd.DataFrame:
        """
        B11: Versión FIFO de agregar_cartera.
        Usa calcular_ppc_fifo() en lugar del promedio ponderado simple.
        """
        from core.pricing_utils import es_instrumento_local_ars

        df_c = df_trans[df_trans["CARTERA"] == cartera].copy()
        if df_c.empty:
            return pd.DataFrame()
        df_c["TICKER"] = df_c["TICKER"].str.upper().str.strip()

        rows = []
        for ticker_key, g in df_c.groupby("TICKER"):
            cant_neta = g["CANTIDAD"].sum()
            if cant_neta <= 0:
                continue
            ppc_fifo  = self.calcular_ppc_fifo(g)
            cant_comp = g[g["CANTIDAD"] > 0]["CANTIDAD"].sum()
            inv_comp  = (g[g["CANTIDAD"] > 0]["CANTIDAD"] * g[g["CANTIDAD"] > 0]["PPC_USD"]).sum()
            tipo_instr = str(g["TIPO"].iloc[0]) if "TIPO" in g.columns else "CEDEAR"
            es_local = es_instrumento_local_ars(str(ticker_key), tipo_instr)
            ratio = 1.0 if es_local else float(self.obtener_ratio(str(ticker_key)))
            _lam_s = pd.to_numeric(g.get("LAMINA_VN", pd.Series(dtype=float)), errors="coerce").dropna()
            lamina_vn = float(_lam_s.iloc[0]) if not _lam_s.empty else float("nan")

            inv_ars_hist = 0.0
            buys = g[g["CANTIDAD"] > 0]
            if not buys.empty and "FECHA_COMPRA" in buys.columns:
                for _, row in buys.iterrows():
                    fecha_key = str(row.get("FECHA_COMPRA", ""))[:7]
                    ccl_hist  = ccl_historico_por_fecha(fecha_key, fallback=1350.0)
                    inv_ars_hist += float(row["CANTIDAD"]) * float(row["PPC_USD"]) * ccl_hist * ratio

            rows.append({
                "TICKER":            ticker_key,
                "CANTIDAD_TOTAL":    cant_neta,
                "PPC_USD_PROM":      ppc_fifo,
                "INV_USD_TOTAL":     inv_comp,
                "INV_ARS_HISTORICO": inv_ars_hist,
                "TIPO":              tipo_instr,
                "ES_LOCAL":          es_local,
                "LAMINA_VN":         lamina_vn,
            })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).reset_index(drop=True)

    def detectar_posibles_splits(
        self,
        df_cartera: pd.DataFrame,
        precios_actuales: dict,
        umbral_pct: float = 0.50,
    ) -> list:
        """
        D4: Detecta posibles splits de acciones comparando el PPC histórico (USD subyacente)
        con el precio actual ajustado. Si la diferencia supera el umbral (50%), alerta al asesor.

        Retorna lista de dicts con {ticker, ppc_usd, px_actual, ratio_cambio, alerta}.
        """
        alertas = []
        if df_cartera.empty or not precios_actuales:
            return alertas

        for _, row in df_cartera.iterrows():
            ticker = str(row.get("TICKER", "")).upper().strip()
            if not ticker:
                continue

            ppc_usd_raw = float(row.get("PPC_USD_PROM", 0) or 0)
            ratio = float(self.obtener_ratio(ticker))
            # PPC_USD almacenado = subyacente_USD / ratio²  →  × ratio² recupera el subyacente.
            # px_usd_actual = (px_ars / ccl) × ratio  también es subyacente → misma escala.
            ppc_usd_sub = ppc_usd_raw * ratio * ratio  # subyacente_USD al momento de compra

            if ppc_usd_sub <= 0:
                continue

            px_ars  = float(precios_actuales.get(ticker, 0) or 0)
            # MQ2-A5: usar CCL histórico real en vez del 1500 hardcodeado
            try:
                import datetime as _dt

                from core.pricing_utils import ccl_historico_por_fecha
                ccl_est = ccl_historico_por_fecha(_dt.date.today().strftime("%Y-%m"))
            except Exception:
                ccl_est = 1465.0

            px_usd_actual = (px_ars / ccl_est) * ratio if ccl_est > 0 else 0

            if px_usd_actual <= 0 or ppc_usd_sub <= 0:
                continue

            ratio_cambio = px_usd_actual / ppc_usd_sub

            # Si el precio actual es < 40% o > 250% del PPC → posible split/reverse split
            if ratio_cambio < (1 - umbral_pct) or ratio_cambio > (1 + 1.5):
                tipo = "SPLIT" if ratio_cambio < 0.5 else "REVERSE SPLIT" if ratio_cambio > 2.0 else "ANOMALÍA"
                alertas.append({
                    "ticker":         ticker,
                    "ppc_usd":        round(ppc_usd_sub, 2),
                    "px_actual_usd":  round(px_usd_actual, 2),
                    "ratio_cambio":   round(ratio_cambio, 3),
                    "tipo_alerta":    tipo,
                    "alerta": (
                        f"⚠️ {tipo} posible en {ticker}: "
                        f"PPC USD ${ppc_usd_sub:.2f} vs Px actual ${px_usd_actual:.2f} "
                        f"({ratio_cambio:.1f}x)"
                    ),
                })

        return alertas

    def obtener_ratio(self, ticker: str) -> float:
        """Delega en pricing_utils (misma regla Excel vs config)."""
        return ratio_desde_universo_o_config(ticker, self.universo_df)

    def obtener_precios_cartera(self, tickers: list[str], ccl: float) -> dict[str, float]:
        """
        Descarga precios de cartera en BATCH (F1): una sola llamada HTTP para todos los tickers.
        Speedup 5-10x respecto al loop ticker-por-ticker.
        """
        if not tickers:
            return {}
        if ccl <= 0:
            ccl = CCL_FALLBACK

        # Construir listas de tickers para BA y US
        ratios_map: dict[str, float] = {t: self.obtener_ratio(t) for t in tickers}
        tickers_ba = [f"{t}.BA" for t in tickers]
        tickers_us = [ticker_yahoo(t, self.universo_df) for t in tickers]
        all_tickers = list(set(tickers_ba + tickers_us))

        try:
            raw = yf.download(all_tickers, period="2d", auto_adjust=True, progress=False)
            if "Close" in raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex) else True:
                if isinstance(raw.columns, pd.MultiIndex):
                    close_data = raw["Close"]
                else:
                    close_data = raw
            last_prices: dict[str, float] = {}
            for col in close_data.columns:
                s = close_data[col].dropna()
                if not s.empty:
                    last_prices[str(col)] = float(s.iloc[-1])
        except Exception:
            last_prices = {}

        precios: dict[str, float] = {}
        for t in tickers:
            ratio = ratios_map[t]
            t_yf  = ticker_yahoo(t, self.universo_df)
            p_ba  = last_prices.get(f"{t}.BA", 0.0)
            p_us  = last_prices.get(t_yf, 0.0)
            p_teo = (p_us * ccl) / ratio if ratio > 0 and p_us > 0 else 0.0
            # Priorizar cotización BYMA (.BA): es la referencia de "precio actual"
            # del certificado en pesos. El teórico NY×CCL/ratio depende del ratio y
            # suele desviarse si el Excel trae ratio=1 por error o no está el universo.
            if p_ba > 0:
                if p_teo > 0 and (p_ba < 0.2 * p_teo or p_ba > 5.0 * p_teo):
                    precios[t] = round(p_teo, 2)
                else:
                    precios[t] = round(p_ba, 2)
            elif p_teo > 0:
                precios[t] = round(p_teo, 2)
            else:
                precios[t] = 0.0
        return precios

    def descargar_historico(
        self,
        tickers: list[str],
        period: str = "1y",
        *,
        align_calendar_strict: bool = True,
        relax_alignment_if_short: bool = True,
        min_filas: int = 30,
    ) -> pd.DataFrame:
        """
        Descarga histórico de precios ajustados.

        align_calendar_strict=True (C03): intersección de fechas con precio en todos
        los tickers; evita mezclar cierres NY vs BYMA mediante ffill infinito.
        Si el panel queda con menos de min_filas y relax_alignment_if_short=True,
        reintenta con ffill acotado (fallback documentado en SOURCES.md).
        """
        tickers_yf = list({ticker_yahoo(t, self.universo_df) for t in tickers})
        tickers_yf = list(set(tickers_yf + ["SPY"]))
        from core.historical_cache import (
            historico_cache_get,
            historico_cache_key,
            historico_cache_set,
        )

        _ck = historico_cache_key(
            tickers_yf,
            period,
            align_calendar_strict=align_calendar_strict,
            relax_alignment_if_short=relax_alignment_if_short,
            min_filas=min_filas,
        )
        _hit = historico_cache_get(_ck)
        if _hit is not None:
            return _hit
        try:
            data = yf.download(tickers_yf, period=period, progress=False)["Close"]
            if isinstance(data, pd.Series):
                data = data.to_frame(name=tickers_yf[0])
            if "BRK-B" in data.columns:
                data = data.rename(columns={"BRK-B": "BRKB"})
            if align_calendar_strict:
                aligned = alinear_panel_precios_cierre(data, strict_inner=True)
                if relax_alignment_if_short and len(aligned) < min_filas:
                    aligned = alinear_panel_precios_cierre(
                        data, strict_inner=False, ffill_limit=3
                    )
                out = aligned.dropna(how="all")
            else:
                data = data.ffill().bfill()
                out = data.dropna(how="all")
            historico_cache_set(_ck, out)
            return out
        except Exception as e:
            raise RuntimeError(f"Error descargando histórico: {e}") from e

    def escaneo_universo(self) -> tuple[pd.DataFrame, dict]:
        tickers = self.universo_df["Ticker"].dropna().unique().tolist() if \
                  not self.universo_df.empty else UNIVERSO_BASE
        tickers_yf = [ticker_yahoo(t, self.universo_df) for t in tickers]
        tickers_yf = list(dict.fromkeys(tickers_yf))
        data = yf.download(tickers_yf, period="1y", progress=False)["Close"]
        if isinstance(data, pd.Series): data = data.to_frame()
        data = data.ffill().bfill()
        rend = data.pct_change().dropna()
        detalles, metricas = {}, {}
        ticker_map = dict(zip(tickers_yf, tickers))
        for col in data.columns:
            t_by = ticker_map.get(col, col)
            s = data[col].dropna()
            if len(s) < 150: continue
            px  = float(s.iloc[-1])
            sma = float(s.rolling(150).mean().iloc[-1])
            d   = s.diff()
            g   = d.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean().iloc[-1]
            l   = (-d.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean().iloc[-1]
            rsi = round(100 - 100 / (1 + g / l), 1) if l > 0 else 50.0
            sh  = round(float(rend[col].mean() * 252) /
                        float(rend[col].std() * (252**0.5)), 2) if rend[col].std() > 0 else 0.0
            detalles[t_by] = {"RSI": rsi, "SMA150": px > sma, "Sharpe": sh, "Precio": px}
            if px > sma and rsi < 75: metricas[t_by] = sh
        top = sorted(metricas, key=metricas.get, reverse=True)[:15]
        data_byma = data.rename(columns=ticker_map)
        cols_top = [t for t in top if t in data_byma.columns]
        return data_byma[cols_top].dropna(how="all"), detalles
