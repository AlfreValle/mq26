"""
services/diagnostico_cartera.py — Motor de Diagnóstico de Cartera (S5)

Evalúa 4 dimensiones y produce un DiagnosticoResult con semáforo,
observaciones en lenguaje humano y cifras concretas.

SIN imports de streamlit. SIN llamadas a yfinance.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from core.diagnostico_types import (
    AJUSTE_HORIZONTE_CORTO,
    BENCHMARK_RENDIMIENTO,
    CATEGORIAS_DEFENSIVAS,
    CLASIFICACION_ACTIVOS,
    CategoriaActivo,
    DiagnosticoResult,
    LIMITE_CONCENTRACION,
    ObservacionDiagnostico,
    PISO_DEFENSIVO,
    PrioridadAccion,
    Semaforo,
    perfil_diagnostico_valido,
    semaforo_desde_score,
)

_BONO_PREFIJOS = ("AL", "GD", "TX", "PR")


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _trunc_text(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _ticker_u(row: pd.Series) -> str:
    return str(row.get("TICKER", "") or "").strip().upper()


def _ticker_col_universo(universo_df: pd.DataFrame | None) -> str | None:
    if universo_df is None or universo_df.empty:
        return None
    if "TICKER" in universo_df.columns:
        return "TICKER"
    if "Ticker" in universo_df.columns:
        return "Ticker"
    return None


def _lookup_tipo_universo(ticker: str, universo_df: pd.DataFrame | None) -> str:
    col = _ticker_col_universo(universo_df)
    if col is None:
        return ""
    tu = ticker.upper()
    m = universo_df[universo_df[col].astype(str).str.upper() == tu]
    if m.empty:
        return ""
    return str(m.iloc[0].get("TIPO", "") or "")


def _es_prefijo_bono_arg(ticker: str) -> bool:
    t = ticker.upper()
    return any(t.startswith(p) for p in _BONO_PREFIJOS)


def _es_defensivo_fila(
    row: pd.Series,
    universo_df: pd.DataFrame | None,
) -> bool:
    ticker = _ticker_u(row)
    tipo_row = str(row.get("TIPO", "") or "").upper()
    tipo_u = _lookup_tipo_universo(ticker, universo_df).upper()
    for _liq in ("LETRA", "LECAP", "LEDE"):
        if tipo_row == _liq or tipo_u == _liq:
            return False

    tipos_renta_ar = {"ON", "ON_USD"}
    if tipo_row.upper() in tipos_renta_ar or tipo_u.upper() in tipos_renta_ar:
        return True
    if _es_prefijo_bono_arg(ticker):
        return True

    cat = CLASIFICACION_ACTIVOS.get(ticker, CategoriaActivo.OTRO)
    return cat in CATEGORIAS_DEFENSIVAS


def _fraccion_peso(row: pd.Series) -> float:
    w = row.get("PESO_PCT", 0.0)
    try:
        f = float(w)
    except (TypeError, ValueError):
        f = 0.0
    if f > 1.0 + 1e-6:
        return f / 100.0
    return max(0.0, f)


def _pct_defensivo_actual(df_ag: pd.DataFrame, universo_df: pd.DataFrame | None) -> float:
    if df_ag is None or df_ag.empty:
        return 0.0
    if "VALOR_ARS" in df_ag.columns:
        vt = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum())
        if vt > 0:
            acc = 0.0
            for _, row in df_ag.iterrows():
                va = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
                if _es_defensivo_fila(row, universo_df):
                    acc += va
            return acc / vt
    total = 0.0
    acc = 0.0
    for _, row in df_ag.iterrows():
        w = _fraccion_peso(row)
        total += w
        if _es_defensivo_fila(row, universo_df):
            acc += w
    return acc / total if total > 1e-12 else 0.0


def _piso_defensivo_requerido(perfil: str, horizonte_label: str) -> float:
    p = PISO_DEFENSIVO.get(perfil, PISO_DEFENSIVO["Moderado"])
    h = str(horizonte_label or "").strip()
    if h in AJUSTE_HORIZONTE_CORTO:
        p = min(1.0, p + 0.10)
    return p


def _score_dim_cobertura(pct_actual: float, piso_req: float) -> float:
    if piso_req <= 0:
        return 100.0
    r = pct_actual / piso_req
    return _clip(min(r, 1.0) * 100.0, 0.0, 100.0)


def _score_dim_concentracion(
    df_ag: pd.DataFrame,
    limite_fraccion: float,
) -> tuple[float, list[tuple[str, float]]]:
    if df_ag is None or df_ag.empty:
        return 100.0, []
    excedentes: list[tuple[str, float]] = []
    for _, row in df_ag.iterrows():
        t = _ticker_u(row)
        w = _fraccion_peso(row)
        if w > limite_fraccion + 1e-9:
            excedentes.append((t, w))
    pen = min(75, 25 * len(excedentes))
    return float(_clip(100.0 - pen, 0.0, 100.0)), excedentes


def _score_dim_rendimiento(
    pnl_frac_usd: float,
    perfil: str,
    df_ag: pd.DataFrame,
) -> tuple[float, float]:
    ben = BENCHMARK_RENDIMIENTO.get(perfil, BENCHMARK_RENDIMIENTO["Moderado"])
    dias = 365
    if df_ag is not None and not df_ag.empty and "FECHA_COMPRA" in df_ag.columns:
        try:
            fechas = pd.to_datetime(df_ag["FECHA_COMPRA"], errors="coerce").dropna()
            if not fechas.empty:
                first = fechas.min().date()
                dias = max(1, (date.today() - first).days)
        except Exception:
            dias = 365
    bench_frac = ben * (dias / 365.0)
    diff = float(pnl_frac_usd) - bench_frac
    if diff >= 0.05:
        sc = 100.0
    elif diff >= 0.0:
        sc = 75.0
    elif diff >= -0.10:
        sc = 50.0
    elif diff >= -0.20:
        sc = 25.0
    else:
        sc = 0.0
    return sc, bench_frac


def _conteo_senales(senales_salida: list[dict[str, Any]] | None) -> tuple[int, int, float]:
    if not senales_salida:
        return 0, 0, 100.0
    n_alta = 0
    n_media = 0
    for s in senales_salida:
        pr = s.get("prioridad", 0)
        try:
            pr_i = int(pr) if not isinstance(pr, str) else 0
        except (TypeError, ValueError):
            pr_i = 0
        if pr_i >= 3:
            n_alta += 1
        elif pr_i == 2:
            n_media += 1
    sc = max(0.0, 100.0 - n_alta * 30.0 - n_media * 10.0)
    return n_alta, n_media, sc


def _prioridad_ord(p: PrioridadAccion) -> int:
    order = {
        PrioridadAccion.CRITICA: 0,
        PrioridadAccion.ALTA: 1,
        PrioridadAccion.MEDIA: 2,
        PrioridadAccion.BAJA: 3,
        PrioridadAccion.NINGUNA: 4,
    }
    return order.get(p, 4)


def diagnosticar(
    df_ag: pd.DataFrame,
    perfil: str,
    horizonte_label: str,
    metricas: dict,
    ccl: float,
    universo_df: pd.DataFrame | None = None,
    senales_salida: list[dict[str, Any]] | None = None,
    cliente_nombre: str = "",
) -> DiagnosticoResult:
    """
    Produce DiagnosticoResult. `senales_salida` debe ser lista de dicts retornados por
    `evaluar_salida` por posición; si es None, la dimensión 4 no penaliza.

    Convención de conteo: `prioridad` numérica del dict — 3 = ALTA, 2 = MEDIA (como motor_salida).
    """
    fecha_iso = date.today().isoformat()
    perfil_n = perfil_diagnostico_valido(perfil)
    modo_fallback = False
    ccl_f = float(ccl or 0.0)

    if df_ag is None:
        df_ag = pd.DataFrame()

    if df_ag.empty:
        modo_fallback = True
        obs = ObservacionDiagnostico(
            dimension="cobertura_defensiva",
            icono="🔴",
            titulo="Sin posiciones en cartera",
            texto_corto=_trunc_text(
                "No hay activos cargados: agregá posiciones para obtener un diagnóstico completo.",
                120,
            ),
            cifra_clave="0 posiciones",
            accion_sugerida="Importá o cargá tu cartera desde el libro mayor.",
            prioridad=PrioridadAccion.ALTA,
            score_dimension=0.0,
        )
        d1 = d2 = d3 = 0.0
        if senales_salida is None:
            n_alta = n_media = 0
            d4 = 100.0
        else:
            n_alta, n_media, d4 = _conteo_senales(senales_salida)
        stotal = _clip(0.35 * d1 + 0.25 * d2 + 0.20 * d3 + 0.20 * d4, 0.0, 100.0)
        sem = semaforo_desde_score(stotal)
        return DiagnosticoResult(
            cliente_nombre=cliente_nombre or "",
            perfil=perfil_n,
            horizonte_label=str(horizonte_label or ""),
            fecha_diagnostico=fecha_iso,
            score_total=stotal,
            semaforo=sem,
            score_cobertura_defensiva=d1,
            score_concentracion=d2,
            score_rendimiento=d3,
            score_senales_salida=d4,
            observaciones=[obs],
            pct_defensivo_actual=0.0,
            pct_defensivo_requerido=_piso_defensivo_requerido(perfil_n, horizonte_label),
            titulo_semaforo="Tu cartera aún no tiene datos suficientes",
            resumen_ejecutivo=_trunc_text(
                "No se encontraron posiciones. El semáforo refleja un diagnóstico limitado hasta que cargues tu cartera.",
                500,
            ),
            valor_cartera_usd=0.0,
            n_posiciones=0,
            modo_fallback=modo_fallback,
            n_senales_salida_altas=n_alta,
            n_senales_salida_medias=n_media,
        )

    if senales_salida is None:
        n_alta, n_media, d4 = 0, 0, 100.0
    else:
        n_alta, n_media, d4 = _conteo_senales(senales_salida)
    d4 = _clip(d4, 0.0, 100.0)

    limite = LIMITE_CONCENTRACION.get(perfil_n, LIMITE_CONCENTRACION["Moderado"])
    pct_def = _pct_defensivo_actual(df_ag, universo_df)
    piso = _piso_defensivo_requerido(perfil_n, horizonte_label)
    d1 = _clip(_score_dim_cobertura(pct_def, piso), 0.0, 100.0)

    d2, excedentes = _score_dim_concentracion(df_ag, limite)
    d2 = _clip(d2, 0.0, 100.0)

    if not metricas:
        modo_fallback = True
    pnl_frac = float(metricas.get("pnl_pct_total_usd", 0.0) or 0.0)
    d3, bench_frac = _score_dim_rendimiento(pnl_frac, perfil_n, df_ag)
    d3 = _clip(d3, 0.0, 100.0)

    d1 = _clip(d1, 0.0, 100.0)
    stotal = _clip(0.35 * d1 + 0.25 * d2 + 0.20 * d3 + 0.20 * d4, 0.0, 100.0)
    sem = semaforo_desde_score(stotal)

    total_valor = float(metricas.get("total_valor", 0.0) or 0.0)
    if total_valor <= 0 and "VALOR_ARS" in df_ag.columns:
        total_valor = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum())
    valor_usd = total_valor / ccl_f if ccl_f > 0 else 0.0

    deficit_usd = max(0.0, (piso - pct_def) * valor_usd)

    max_t, max_w = "", 0.0
    for _, row in df_ag.iterrows():
        w = _fraccion_peso(row)
        if w > max_w:
            max_w = w
            max_t = _ticker_u(row)

    observaciones: list[ObservacionDiagnostico] = []

    if pct_def + 1e-9 < piso:
        gap_pct = (piso - pct_def) * 100.0
        pri = PrioridadAccion.CRITICA if gap_pct > 15 else PrioridadAccion.ALTA
        observaciones.append(
            ObservacionDiagnostico(
                dimension="cobertura_defensiva",
                icono="⚠️" if pri == PrioridadAccion.ALTA else "🔴",
                titulo="Cobertura defensiva insuficiente",
                texto_corto=_trunc_text(
                    f"Tenés {pct_def*100:.0f}% defensivo; tu perfil requiere {piso*100:.0f}%.",
                    120,
                ),
                cifra_clave=f"{pct_def*100:.0f}% actual vs {piso*100:.0f}% requerido",
                accion_sugerida=_trunc_text(
                    f"Sumá USD {deficit_usd:,.0f} en anclas (GLD, INCOME, renta corta) en próximas compras.",
                    120,
                ),
                prioridad=pri,
                score_dimension=d1,
            )
        )

    for t_ex, w_ex in excedentes[:3]:
        imp = w_ex * 0.20 * 100.0
        observaciones.append(
            ObservacionDiagnostico(
                dimension="concentracion",
                icono="⚠️",
                titulo=f"Concentración elevada en {t_ex}",
                texto_corto=_trunc_text(
                    f"{t_ex} representa {w_ex*100:.0f}% de la cartera (límite {limite*100:.0f}%).",
                    120,
                ),
                cifra_clave=f"{w_ex*100:.0f}% del total; si {t_ex} cae 20% ≈ -{imp:.1f}% cartera",
                accion_sugerida=_trunc_text("Diversificá con nuevas compras en otros sectores o reducí peso.", 120),
                prioridad=PrioridadAccion.ALTA,
                score_dimension=d2,
            )
        )

    if d3 < 75.0:
        observaciones.append(
            ObservacionDiagnostico(
                dimension="rendimiento",
                icono="⚠️",
                titulo="Rendimiento acumulado en USD bajo el benchmark esperado",
                texto_corto=_trunc_text(
                    f"Retorno USD {pnl_frac*100:.1f}% vs referencia {bench_frac*100:.1f}% al período.",
                    120,
                ),
                cifra_clave=f"{pnl_frac*100:.1f}% cartera vs {bench_frac*100:.1f}% referencia",
                accion_sugerida=_trunc_text(
                    "Revisá asignación y costos; evitá realizar pérdidas por impulso.",
                    120,
                ),
                prioridad=PrioridadAccion.MEDIA,
                score_dimension=d3,
            )
        )

    if n_alta > 0:
        observaciones.append(
            ObservacionDiagnostico(
                dimension="senales",
                icono="🔴",
                titulo="Señales de salida prioritarias",
                texto_corto=_trunc_text(
                    f"{n_alta} posición(es) con alerta ALTA en el motor de salida.",
                    120,
                ),
                cifra_clave=f"{n_alta} alta(s), {n_media} media(s)",
                accion_sugerida="Revisá objetivos y stops en la grilla de posición neta.",
                prioridad=PrioridadAccion.CRITICA,
                score_dimension=d4,
            )
        )
    elif n_media > 0:
        observaciones.append(
            ObservacionDiagnostico(
                dimension="senales",
                icono="🟠",
                titulo="Señales de revisión",
                texto_corto=_trunc_text(
                    f"{n_media} posición(es) con alerta media (RSI o score).",
                    120,
                ),
                cifra_clave=f"0 altas, {n_media} medias",
                accion_sugerida="Monitoreá en la próxima semana.",
                prioridad=PrioridadAccion.MEDIA,
                score_dimension=d4,
            )
        )

    if not observaciones:
        observaciones.append(
            ObservacionDiagnostico(
                dimension="cobertura_defensiva",
                icono="✅",
                titulo="Cartera alineada a los parámetros principales",
                texto_corto=_trunc_text(
                    "No se detectaron problemas graves en cobertura, concentración ni señales.",
                    120,
                ),
                cifra_clave=f"Score global {stotal:.0f}/100",
                accion_sugerida="Mantené disciplina y revisá en la próxima inyección de capital.",
                prioridad=PrioridadAccion.NINGUNA,
                score_dimension=stotal,
            )
        )

    observaciones.sort(key=lambda o: _prioridad_ord(o.prioridad))
    observaciones = observaciones[:6]

    n_ajustes = sum(1 for o in observaciones if o.prioridad != PrioridadAccion.NINGUNA)
    if sem == Semaforo.VERDE:
        titulo_sem = f"Tu cartera está bien con {n_ajustes} ajuste(s) recomendado(s)"
    elif sem == Semaforo.AMARILLO:
        titulo_sem = "Tu cartera necesita algunos ajustes para alinearla al perfil"
    else:
        titulo_sem = "Tu cartera requiere atención prioritaria"

    resumen = _trunc_text(
        f"Score {stotal:.0f}/100 ({sem.value}). Defensivo {pct_def*100:.0f}% sobre piso {piso*100:.0f}%. "
        f"{'Hay ' + str(len(excedentes)) + ' activo(s) sobre el límite de concentración. ' if excedentes else ''}"
        f"P&L USD acumulado {pnl_frac*100:.1f}%.",
        500,
    )

    return DiagnosticoResult(
        cliente_nombre=cliente_nombre or "",
        perfil=perfil_n,
        horizonte_label=str(horizonte_label or ""),
        fecha_diagnostico=fecha_iso,
        score_total=stotal,
        semaforo=sem,
        score_cobertura_defensiva=d1,
        score_concentracion=d2,
        score_rendimiento=d3,
        score_senales_salida=d4,
        observaciones=observaciones,
        pct_defensivo_actual=pct_def,
        pct_defensivo_requerido=piso,
        deficit_defensivo_usd=deficit_usd,
        activo_mas_concentrado=max_t,
        pct_concentracion_max=max_w * 100.0,
        rendimiento_ytd_usd_pct=pnl_frac * 100.0,
        benchmark_ytd_pct=bench_frac * 100.0,
        n_senales_salida_altas=n_alta,
        n_senales_salida_medias=n_media,
        titulo_semaforo=titulo_sem,
        resumen_ejecutivo=resumen,
        valor_cartera_usd=valor_usd,
        n_posiciones=len(df_ag),
        modo_fallback=modo_fallback,
    )
