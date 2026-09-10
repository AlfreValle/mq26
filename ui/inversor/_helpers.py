"""ui/inversor/_helpers.py — helpers compartidos entre secciones del tier IN.

Extraídos de ui/tab_inversor.py (Fase 2.1). Acá vive todo lo que usan dos o más
secciones (primera cartera, plata nueva, posiciones, orquestador): resolución de
precios, diagnóstico cacheado, mix RF, identificación de tickers y constantes de
edición. Sin lógica de render.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date

import pandas as pd
import streamlit as st

from core.diagnostico_types import (
    CARTERA_IDEAL,
    UNIVERSO_RENTA_FIJA_AR,
    etiqueta_fuente_precio,
    perfil_motor_salida,
)
from core.logging_config import get_logger
from core.renta_fija_ar import es_fila_renta_fija_ar

_log = get_logger(__name__)

_TIPOS_EDICION_PRIMERA_CARTERA = [
    "CEDEAR",
    "ACCION_LOCAL",
    "BONO",
    "LETRA",
    "FCI",
    "ETF",
    "ON",
    "ON_USD",
    "BONO_USD",
    "OTRO",
]


def _log_degradacion(ctx: dict, evento: str, exc: Exception | None = None, **extra) -> None:
    payload = {"evento": evento, **extra}
    if exc is not None:
        _log.warning("degradacion_tab_inversor: %s | error=%s", payload, exc, exc_info=True)
    else:
        _log.warning("degradacion_tab_inversor: %s", payload)
    st.session_state["inv_degradado_ui"] = True


def _tickers_semilla_precios(ctx: dict) -> list[str]:
    """Anclas nombradas del ideal (SPY/QQQ). Sin análisis ni catálogo RF entero."""
    _ = ctx  # la semilla es estructural, no depende del libro cargado
    need: set[str] = set()
    for _pesos in CARTERA_IDEAL.values():
        for k in _pesos or {}:
            ks = str(k).strip().upper()
            if ks and not ks.startswith("_"):
                need.add(ks)
    return sorted(need)


def _precios_para_recomendar(ctx: dict) -> dict:
    """
    Precios **ARS por cuotaparte** para armar/recomendar cartera.

    No pega a Yahoo acá: un `yf.download` del análisis/universo traba el clic
    (SSL/timeout). Las ONs salen por catálogo×CCL; el RV elegido se cotiza
    después, en un lote chico, dentro de `generar_primera_cartera`.
    """
    from services.cartera_service import resolver_precios

    ccl = float(ctx.get("ccl") or 0.0)
    universo_df = ctx.get("universo_df")
    tickers_list = _tickers_semilla_precios(ctx)
    resolved = resolver_precios(
        tickers_list, {}, ccl, universo_df, permitir_hard=False
    )
    return {str(k).upper(): float(v) for k, v in resolved.items() if float(v or 0) > 0}


def _ctx_hash_inversor(ctx: dict) -> str:
    df_ag = ctx.get("df_ag")
    ccl = round(float(ctx.get("ccl") or 0), 4)
    cartera = str(ctx.get("cartera_activa", ""))
    _plan = st.session_state.get("inv_mix_plan")
    _mix_part = ""
    if isinstance(_plan, dict) and _plan.get("rf") is not None:
        _mix_part = f"|mix={round(float(_plan['rf']), 4)}"
    if df_ag is None or df_ag.empty:
        return hashlib.md5(f"empty|{ccl}|{cartera}{_mix_part}".encode()).hexdigest()
    try:
        h = str(pd.util.hash_pandas_object(df_ag, index=False).sum())
    except Exception:
        h = str(len(df_ag)) + str(df_ag["TICKER"].tolist())
    return hashlib.md5(f"{h}|{ccl}|{cartera}{_mix_part}".encode()).hexdigest()


def _senales_precalculadas(ctx: dict) -> list[dict] | None:
    df_ag = ctx.get("df_ag")
    if df_ag is None or df_ag.empty:
        return None
    df_analisis = ctx.get("df_analisis")
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    score_map: dict = {}
    rsi_map: dict = {}
    if df_analisis is not None and not df_analisis.empty:
        if "TICKER" in df_analisis.columns and "PUNTAJE_TECNICO" in df_analisis.columns:
            score_map = df_analisis.set_index("TICKER")["PUNTAJE_TECNICO"].to_dict()
        if "RSI" in df_analisis.columns:
            rsi_map = df_analisis.set_index("TICKER")["RSI"].to_dict()
    from services.motor_salida import evaluar_salida

    out: list[dict] = []
    for _, row in df_ag.iterrows():
        ticker = str(row.get("TICKER", ""))
        ppc_ars = float(pd.to_numeric(row.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
        px_ars = float(pd.to_numeric(row.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
        rsi_val = float(rsi_map.get(ticker, 50.0) or 50.0)
        score_v = float(score_map.get(ticker, 5.0) or 5.0)
        fecha_c = row.get("FECHA_COMPRA", date(2020, 1, 1))
        if not isinstance(fecha_c, date):
            try:
                fecha_c = pd.to_datetime(str(fecha_c)).date()
            except Exception:
                fecha_c = date(2020, 1, 1)
        if ppc_ars <= 0 or px_ars <= 0:
            continue
        out.append(
            evaluar_salida(
                ticker=ticker,
                ppc_usd=ppc_ars,
                px_usd_actual=px_ars,
                rsi=rsi_val,
                score_actual=score_v,
                score_semana_anterior=score_v,
                fecha_compra=fecha_c,
                perfil=perfil_ms,
            )
        )
    return out if out else None


def _mix_rf_desde_filas_primera(filas: list[dict]) -> float:
    total = 0.0
    rf = 0.0
    for f in filas:
        v = float(f.get("PPC_ARS") or 0) * float(f.get("CANTIDAD") or 0)
        if v <= 0:
            continue
        total += v
        row = pd.Series({"TICKER": f.get("TICKER", ""), "TIPO": f.get("TIPO", "")})
        if es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
            rf += v
    return float(rf / total) if total > 1e-9 else 0.0


def _mix_objetivo_desde_sesion(df_ag: pd.DataFrame | None, universo_df) -> float | None:
    """Objetivo RF del armado reciente, si sigue alineado con la cartera actual."""
    from services.diagnostico_cartera import pct_renta_fija_cartera

    plan = st.session_state.get("inv_mix_plan")
    if not isinstance(plan, dict):
        return None
    try:
        ts = float(plan.get("ts") or 0)
        cand = float(plan["rf"])
    except (KeyError, TypeError, ValueError):
        return None
    if time.time() - ts > 90.0 * 86400.0:
        return None
    if df_ag is None or df_ag.empty:
        return cand
    try:
        pr = float(pct_renta_fija_cartera(df_ag, universo_df))
    except Exception:
        return cand
    if abs(cand - pr) > 0.22:
        return None
    return cand


def _get_diagnostico_cached(ctx: dict) -> object:
    h = _ctx_hash_inversor(ctx)
    now = time.monotonic()
    cache = st.session_state.get("inv_diagnostico") or {}
    ttl = 300.0
    if (
        cache.get("hash") == h
        and cache.get("result") is not None
        and (now - float(cache.get("ts", 0))) < ttl
    ):
        return cache["result"]
    from services.diagnostico_cartera import diagnosticar

    df_ag = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
    metricas = ctx.get("metricas") or {}
    senales = _senales_precalculadas(ctx)
    mix_o = _mix_objetivo_desde_sesion(df_ag, ctx.get("universo_df"))
    res = diagnosticar(
        df_ag=df_ag,
        perfil=str(ctx.get("cliente_perfil", "Moderado")),
        horizonte_label=_horizonte_ui(ctx),
        metricas=metricas,
        ccl=float(ctx.get("ccl") or 0.0),
        universo_df=ctx.get("universo_df"),
        senales_salida=senales,
        cliente_nombre=str(ctx.get("cliente_nombre", "")),
        mix_objetivo_rf=mix_o,
    )
    st.session_state["inv_diagnostico"] = {"hash": h, "ts": now, "result": res}
    st.session_state.pop("diagnostico_cache", None)
    return res


def _market_stress_optional() -> dict | None:
    try:
        import yfinance as yf

        vix_h = yf.Ticker("^VIX").history(period="5d")
        vix = float(vix_h["Close"].iloc[-1]) if len(vix_h) > 0 else None
        spy = yf.Ticker("SPY").history(period="30d")["Close"].dropna()
        dd = None
        if len(spy) >= 2:
            dd = float(spy.iloc[-1] / spy.iloc[0] - 1.0)
        return {"vix": vix, "spy_drawdown_30d": dd}
    except Exception:
        return None


def _horizonte_ui(ctx: dict) -> str:
    return str(
        ctx.get("cliente_horizonte_label")
        or ctx.get("horizonte_label")
        or "1 año",
    )


def _ticker_desde_fila_pos(row: pd.Series) -> str:
    """Ticker robusto (evita columnas alternativas y valores corruptos)."""
    for key in ("TICKER", "Ticker", "ticker", "ACTIVO", "Activo"):
        if key not in row.index:
            continue
        v = row.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "nat", "<na>"):
            continue
        if s in ("0", "0.0", "0.00"):
            continue
        return s.upper().strip()
    return ""


def _nombre_universo_para_ticker(ticker: str, udf: pd.DataFrame | None) -> str:
    if not ticker or udf is None or udf.empty or "TICKER" not in udf.columns:
        return ""
    tu = str(ticker).strip().upper()
    m = udf[udf["TICKER"].astype(str).str.strip().str.upper() == tu]
    if m.empty:
        return ""
    for col in ("NOMBRE", "DENOMINACION", "Nombre", "nombre", "DESCRIPCION", "descripcion"):
        if col not in m.columns:
            continue
        val = m.iloc[0].get(col)
        if val is not None and str(val).strip():
            return str(val).strip()[:72]
    return ""


def _nombre_criollo(ticker: str, udf: pd.DataFrame | None, item=None) -> str:
    """Nombre comercial: item → universo → catálogo RF. Vacío si solo hay ticker."""
    tu = str(ticker or "").strip().upper()
    if not tu:
        return ""
    if item is not None:
        n = str(getattr(item, "nombre_legible", "") or "").strip()
        if n and n.upper() != tu:
            return n[:72]
    nom = _nombre_universo_para_ticker(tu, udf)
    if nom and nom.upper() != tu:
        return nom
    try:
        from core.renta_fija_ar import descripcion_legible

        d = str(descripcion_legible(tu) or "").strip()
        if d and d.upper() != tu:
            return d[:72]
    except Exception:
        pass
    return ""


def _etiqueta_fuente_precio(codigo: str) -> str:
    return etiqueta_fuente_precio(codigo)


def _fila_editor_canasta(
    ticker: str,
    *,
    unidades: int,
    precio_ars: float,
    tipo: str,
    notas: str,
    nombre: str = "",
    fuente: str = "",
) -> dict:
    return {
        "Ticker": ticker,
        "Nombre": nombre,
        "Unidades": int(unidades),
        "Precio_ARS": float(precio_ars),
        "Fuente": fuente,
        "TIPO": tipo,
        "Notas": notas,
    }


def _column_config_editor_canasta() -> dict:
    return {
        "Ticker": st.column_config.TextColumn("Ticker", help="Código BYMA", width="small"),
        "Nombre": st.column_config.TextColumn(
            "Nombre",
            disabled=True,
            width="medium",
            help="Nombre comercial del instrumento.",
        ),
        "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1, width="small"),
        "Precio_ARS": st.column_config.NumberColumn(
            "Precio ARS c/u",
            min_value=0.0,
            format="%.2f",
            help="Pesos por cuotaparte en BYMA.",
        ),
        "Fuente": st.column_config.TextColumn(
            "Fuente",
            disabled=True,
            width="medium",
            help="De dónde salió el precio de esta fila.",
        ),
        "TIPO": st.column_config.SelectboxColumn(
            "Tipo",
            options=_TIPOS_EDICION_PRIMERA_CARTERA,
            width="small",
        ),
        "Notas": st.column_config.TextColumn("Notas (solo guía)", width="large"),
    }


def _cartera_resuelta_primera_cartera(ctx: dict) -> str:
    """
    Libro donde persistir compras sugeridas: **el mismo** que la cartera activa en contexto.

    Antes se reemplazaba «(sin datos)» por «Cartera principal», y las compras quedaban en
    otro `CARTERA` que el filtro del inversor no mostraba (no se veía la acumulación).
    Si no hay nombre activo, se usa «Cliente | Cartera principal» como fallback.
    """
    raw = str(ctx.get("cartera_activa") or "").strip()
    nombre = str(ctx.get("cliente_nombre", "")).split("|")[0].strip() or "Cliente"
    if not raw:
        return f"{nombre} | Cartera principal"
    return raw


def _flag_plan_explicado(ctx: dict) -> bool:
    """Feature flag A08: plan explicado activable por tenant sin deploy."""
    try:
        from core.feature_flags import get_flag

        return get_flag("plan_explicado", ctx.get("tenant_id"))
    except Exception:
        return True


_TIPOS_INVALIDOS_EDICION = frozenset({"NAN", "NONE", "", "COMPRA", "VENTA"})


def _tipo_universo_ticker(ticker: str, udf: pd.DataFrame | None) -> str:
    """Tipo canónico: maestro (RF manda) → universo_df → CEDEAR solo si no es RF."""
    tu = str(ticker or "").strip().upper()
    if not tu:
        return "CEDEAR"
    try:
        from core.instrument_master import get_master, normalizar_tipo

        t_m = normalizar_tipo(get_master(udf).tipo(tu))
        if t_m:
            return t_m
    except Exception:
        pass
    try:
        from core.renta_fija_ar import es_renta_fija, get_meta

        if es_renta_fija(tu):
            meta = get_meta(tu) or {}
            t_rf = str(meta.get("tipo") or "ON_USD").strip().upper()
            return t_rf or "ON_USD"
    except Exception:
        pass
    if udf is not None and not udf.empty and "TICKER" in udf.columns:
        m = udf[udf["TICKER"].astype(str).str.strip().str.upper() == tu]
        if not m.empty:
            t = str(m.iloc[0].get("TIPO", "") or "").strip().upper()
            if t in ("ACCION", "ACCIÓN"):
                return "ACCION_LOCAL"
            if t:
                return t
    return "CEDEAR"


def _ppc_usd_desde_precio_ars(
    ticker: str,
    precio_ars: float,
    ccl: float,
    tipo: str = "",
) -> float:
    """PPC_USD para persistir el libro. Delega al helper canónico."""
    from core.pricing_utils import ppc_usd_desde_precio_ars

    return ppc_usd_desde_precio_ars(precio_ars, ticker, ccl, tipo=tipo)


def _tipo_persistencia_fila(
    ticker: str,
    tipo_editor: str,
    udf: pd.DataFrame | None,
) -> str:
    """RF siempre por maestro; RV respeta el editor si el tipo es válido."""
    from core.renta_fija_ar import es_renta_fija

    maestro = _tipo_universo_ticker(ticker, udf)
    te = str(tipo_editor or "").strip().upper()
    if es_renta_fija(ticker):
        return maestro or te or "ON_USD"
    if te in _TIPOS_INVALIDOS_EDICION or te not in _TIPOS_EDICION_PRIMERA_CARTERA:
        return maestro or "CEDEAR"
    return te


def _filas_maestra_desde_editor(
    edited: pd.DataFrame | None,
    ccl: float,
    udf: pd.DataFrame | None = None,
) -> tuple[list[dict], list[dict]]:
    """Parte el data_editor en filas que entran al libro vs. las que no se anotan."""
    entra: list[dict] = []
    excluidas: list[dict] = []
    if edited is None or getattr(edited, "empty", True):
        return entra, excluidas
    from core.unit_contracts import es_instrumento_rf_usd_paridad

    ccl_f = float(ccl or 0.0)
    for _, row in edited.iterrows():
        tick = str(row.get("Ticker", "")).strip().upper()
        if not tick:
            continue
        uv = pd.to_numeric(row.get("Unidades", 0), errors="coerce")
        u = int(uv) if pd.notna(uv) else 0
        pxv = pd.to_numeric(row.get("Precio_ARS", 0), errors="coerce")
        px = float(pxv) if pd.notna(pxv) else 0.0
        ti = _tipo_persistencia_fila(
            tick, str(row.get("TIPO", "") or ""), udf
        )
        if u <= 0 or px <= 0:
            excluidas.append(
                {
                    "TICKER": tick,
                    "TIPO": ti,
                    "motivo": "sin unidades" if u <= 0 else "sin cotización",
                    "Unidades": u,
                    "Precio_ARS": px,
                }
            )
            continue
        ppc_usd = _ppc_usd_desde_precio_ars(tick, px, ccl_f, ti)
        if es_instrumento_rf_usd_paridad(tick, ti) and ccl_f > 0 and ppc_usd > 0:
            from core.pricing_utils import precio_ars_desde_ppc_usd

            # ARS por 1 VN: mismo contrato que carga_activos / agregar_cartera.
            ppc_ars = precio_ars_desde_ppc_usd(tick, ti, ppc_usd, ccl_f)
        else:
            ppc_ars = round(px, 4)
        entra.append(
            {
                "FECHA_COMPRA": date.today(),
                "TICKER": tick,
                "CANTIDAD": u,
                "PPC_USD": ppc_usd,
                "PPC_ARS": ppc_ars,
                "TIPO": ti,
                "LAMINA_VN": float("nan"),
            }
        )
    return entra, excluidas


def _html_pills_ruta_decision(rr) -> str:
    """Pills de trazabilidad: ruta de score + constructor (Sprint B)."""
    from ui.mq26_ux import html_pills_fuente

    ruta = str(getattr(rr, "ruta_score", "") or "")
    ctor = str(getattr(rr, "constructor_ideal", "") or "")
    fp = str(getattr(rr, "fingerprint_decision", "") or "")
    hz = str(getattr(rr, "horizonte_label", "") or "")
    if ruta == "scanner_60_20_20":
        ruta_item: tuple[str, str] = ("Scanner 60/20/20", "neutral")
    else:
        ruta_item = ("Score estático", "ghost")
    if ctor == "cartera_optima":
        ctor_item: tuple[str, str] = ("Canasta dinámica", "ok")
    elif ctor == "cartera_ideal_fallback":
        ctor_item = ("Semilla de perfil (fallback)", "warn")
    else:
        ctor_item = (ctor or "Sin constructor", "ghost")
    items: list[tuple[str, str]] = [ruta_item, ctor_item]
    if hz:
        items.append((f"Horizonte {hz}", "ghost"))
    hint = f"decisión {fp}" if fp else ""
    return html_pills_fuente(*items, hint=hint)
