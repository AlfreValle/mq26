"""
services/recomendacion_capital.py — Motor de Recomendación de Capital Nuevo (S5)

Dado capital disponible, propone compras (ticker + unidades enteras) priorizadas.

SIN streamlit. SIN yfinance (precios vía precios_dict; estrés vía market_stress inyectado).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from core.diagnostico_types import (
    CARTERA_IDEAL,
    CLASIFICACION_ACTIVOS,
    CategoriaActivo,
    ItemRecomendacion,
    LIMITE_CONCENTRACION,
    PrioridadAccion,
    RENTA_AR_PENDIENTE_MSG,
    RecomendacionResult,
    perfil_diagnostico_valido,
)
from core.perfil_allocation import target_rv_efectivo
from core.renta_fija_ar import es_renta_fija
from services.diagnostico_cartera import _pct_rf_actual, _piso_defensivo_requerido
from services.favoritos_mes import aplicar_prioridad_favoritos, load_favoritos_mes


def _pct_defensivo_from_df(df_ag: pd.DataFrame, universo_df: pd.DataFrame | None) -> float:
    """Fracción renta fija (campo histórico pct_defensivo_*)."""
    return _pct_rf_actual(df_ag, universo_df)


def _renta_ar_peso_actual(df_ag: pd.DataFrame, universo_df: pd.DataFrame | None) -> float:
    if df_ag is None or df_ag.empty:
        return 0.0
    if "VALOR_ARS" not in df_ag.columns:
        return 0.0
    vt = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum())
    if vt <= 0:
        return 0.0
    acc = 0.0
    for _, row in df_ag.iterrows():
        tipo = str(row.get("TIPO", "") or "").upper()
        tu = tipo
        if universo_df is not None and not universo_df.empty and "TICKER" in universo_df.columns:
            m = universo_df[universo_df["TICKER"].astype(str).str.upper() == _ticker_u(row)]
            if not m.empty:
                tu = str(m.iloc[0].get("TIPO", "") or "").upper()
        if tu in ("ON", "ON_USD") or tipo in ("ON", "ON_USD"):
            va = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
            acc += va
    return acc / vt


def _ticker_u(row: pd.Series) -> str:
    return str(row.get("TICKER", "") or "").strip().upper()


def _nombre_legible(ticker: str, universo_df: pd.DataFrame | None) -> str:
    if universo_df is None or universo_df.empty or "TICKER" not in universo_df.columns:
        return ticker
    tu = ticker.upper()
    m = universo_df[universo_df["TICKER"].astype(str).str.upper() == tu]
    if m.empty:
        return ticker
    for col in ("NOMBRE", "DENOMINACION", "Nombre", "nombre"):
        if col in m.columns:
            v = m.iloc[0].get(col)
            if v and str(v).strip():
                return str(v).strip()[:80]
    return ticker


def _mod23_score_100(ticker: str, df_analisis: pd.DataFrame | None) -> float:
    if df_analisis is None or df_analisis.empty or "TICKER" not in df_analisis.columns:
        return 0.0
    m = df_analisis[df_analisis["TICKER"].astype(str).str.upper() == ticker.upper()]
    if m.empty or "PUNTAJE_TECNICO" not in m.columns:
        return 0.0
    try:
        p = float(m.iloc[0]["PUNTAJE_TECNICO"])
    except (TypeError, ValueError):
        return 0.0
    return p * 10.0


def _es_compra_defensiva(ticker: str) -> bool:
    """Prioridad “core” para cubrir déficit RF: instrumentos de renta fija cotizables."""
    return es_renta_fija(ticker)


def _alerta_mercado(market_stress: dict[str, Any] | None) -> tuple[bool, str]:
    if not market_stress:
        return False, ""
    vix = market_stress.get("vix")
    dd = market_stress.get("spy_drawdown_30d")
    if vix is not None and float(vix) > 30:
        return True, "Mercado en tensión (VIX elevado) — considerá esperar o invertir con cautela."
    if dd is not None and float(dd) <= -0.15:
        return True, "Mercado en tensión (fuerte caída reciente) — considerá esperar."
    return False, ""


def recomendar(
    df_ag: pd.DataFrame,
    perfil: str,
    horizonte_label: str,
    capital_ars: float,
    ccl: float,
    precios_dict: dict[str, float],
    diagnostico: Any | None,
    universo_df: pd.DataFrame | None = None,
    *,
    df_analisis: pd.DataFrame | None = None,
    market_stress: dict[str, Any] | None = None,
    cliente_nombre: str = "",
    favoritos_mes: dict[str, Any] | None = None,
) -> RecomendacionResult:
    fecha = date.today().isoformat()
    perfil_n = perfil_diagnostico_valido(perfil)
    ccl_f = max(float(ccl or 0.0), 1e-9)
    cap = max(0.0, float(capital_ars or 0.0))
    capital_usd = cap / ccl_f

    alerta, msg_alerta = _alerta_mercado(market_stress)
    if alerta:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=cap,
            capital_disponible_usd=capital_usd,
            ccl=ccl_f,
            fecha_recomendacion=fecha,
            alerta_mercado=True,
            mensaje_alerta=msg_alerta,
            resumen_recomendacion=_trunc(msg_alerta, 200),
            pct_defensivo_pre=_pct_defensivo_from_df(df_ag, universo_df),
        )

    if cap <= 0:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=0.0,
            capital_disponible_usd=0.0,
            ccl=ccl_f,
            fecha_recomendacion=fecha,
            pct_defensivo_pre=_pct_defensivo_from_df(df_ag, universo_df),
            resumen_recomendacion="Ingresá un capital mayor a cero para obtener sugerencias.",
        )

    if df_ag is None:
        df_ag = pd.DataFrame()

    fav_doc = load_favoritos_mes() if favoritos_mes is None else favoritos_mes
    fav_rf = list(fav_doc.get("rf") or [])
    fav_rv = list(fav_doc.get("rv") or [])

    ideal = CARTERA_IDEAL.get(perfil_n, CARTERA_IDEAL["Moderado"])
    total_valor = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()) if not df_ag.empty else 0.0

    peso_actual: dict[str, float] = {}
    tickers_hold: set[str] = set()
    if not df_ag.empty and total_valor > 0:
        for _, row in df_ag.iterrows():
            t = _ticker_u(row)
            tickers_hold.add(t)
            va = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
            peso_actual[t] = peso_actual.get(t, 0.0) + va / total_valor

    renta_ar_act = _renta_ar_peso_actual(df_ag, universo_df)
    peso_actual["_RENTA_AR"] = renta_ar_act

    piso = _piso_defensivo_requerido(perfil_n, horizonte_label)
    if diagnostico is not None:
        pct_def_pre = float(
            getattr(diagnostico, "pct_defensivo_actual", _pct_defensivo_from_df(df_ag, universo_df))
        )
    else:
        pct_def_pre = _pct_defensivo_from_df(df_ag, universo_df)
    deficit_def = pct_def_pre + 1e-9 < piso
    target_rv_goal = target_rv_efectivo(perfil_n, horizonte_label)

    limite = LIMITE_CONCENTRACION.get(perfil_n, 0.25)
    concentrado = ""
    max_p = 0.0
    for t, w in peso_actual.items():
        if t.startswith("_"):
            continue
        if w > max_p:
            max_p = w
            concentrado = t
    hay_concentracion = max_p > limite + 1e-6 and concentrado

    pendientes: list[dict[str, Any]] = []
    delta_ideal: dict[str, float] = {}
    for tk, ideal_w in ideal.items():
        if tk == "_RENTA_AR":
            act = renta_ar_act
            d = float(ideal_w) - act
            if d > 1e-6:
                pendientes.append({
                    "ticker": "_RENTA_AR",
                    "precio_ars": 0.0,
                    "falta_ars": 0.0,
                    "motivo": RENTA_AR_PENDIENTE_MSG,
                })
            continue
        act = peso_actual.get(tk.upper(), 0.0)
        d = float(ideal_w) - act
        if d > 1e-6:
            delta_ideal[tk.upper()] = d

    candidatos: list[tuple[str, PrioridadAccion, float]] = []

    def _add_tier(prio: PrioridadAccion, tickers: list[str], deltas: dict[str, float]) -> None:
        for t in tickers:
            if t in delta_ideal and deltas.get(t, delta_ideal[t]) > 1e-9:
                candidatos.append((t, prio, deltas.get(t, delta_ideal[t])))

    if deficit_def:
        defs = sorted(
            [t for t in delta_ideal if _es_compra_defensiva(t)],
            key=lambda x: (-delta_ideal[x], precios_dict.get(x, 1e18) or 1e18),
        )
        defs = aplicar_prioridad_favoritos(defs, fav_rf)
        _add_tier(PrioridadAccion.CRITICA, defs, delta_ideal)

    if hay_concentracion:
        seen_t = {t for t, _, _ in candidatos}
        diluir = sorted(
            [t for t in delta_ideal if t != concentrado],
            key=lambda x: (-delta_ideal[x], precios_dict.get(x, 1e18) or 1e18),
        )
        for t in diluir:
            if t not in seen_t:
                candidatos.append((t, PrioridadAccion.ALTA, delta_ideal[t]))
                seen_t.add(t)

    rest_keys = [t for t in delta_ideal if t not in {c[0] for c in candidatos}]
    if target_rv_goal >= 0.55:
        rest_ideal = sorted(
            rest_keys,
            key=lambda x: (-_mod23_score_100(x, df_analisis), -delta_ideal[x]),
        )
    else:
        rest_ideal = sorted(
            rest_keys,
            key=lambda x: (-delta_ideal[x], -_mod23_score_100(x, df_analisis)),
        )
    rest_ideal = aplicar_prioridad_favoritos(rest_ideal, fav_rv)
    for t in rest_ideal:
        candidatos.append((t, PrioridadAccion.MEDIA, delta_ideal[t]))

    ideal_keys = {k.upper() for k in ideal if k != "_RENTA_AR"}
    if df_analisis is not None and not df_analisis.empty:
        for _, row in df_analisis.iterrows():
            t = str(row.get("TICKER", "")).upper()
            if not t or t in tickers_hold or t in ideal_keys:
                continue
            sc = _mod23_score_100(t, df_analisis)
            if sc > 75.0 and t not in {c[0] for c in candidatos}:
                if float(precios_dict.get(t, 0.0) or precios_dict.get(t.upper(), 0.0) or 0.0) > 0:
                    candidatos.append((t, PrioridadAccion.BAJA, 0.05))

    compras: list[ItemRecomendacion] = []
    capital_restante = cap
    orden = 0
    valor_post = total_valor + cap
    escala_valor = total_valor if total_valor > 1e-6 else max(cap, 1.0)

    for t, prio, delt in candidatos:
        if capital_restante <= 0:
            break
        if t == "_RENTA_AR":
            continue
        precio = float(precios_dict.get(t, precios_dict.get(t.upper(), 0.0)) or 0.0)
        if precio <= 0:
            continue
        need_ars = delt * escala_valor
        capital_para = min(capital_restante, need_ars)
        unidades = int(capital_para // precio)
        if unidades < 1:
            falta = precio - capital_para
            pendientes.append({
                "ticker": t,
                "precio_ars": precio,
                "falta_ars": max(0.0, falta),
                "motivo": "Precio unitario mayor al capital asignado o disponible",
            })
            continue
        monto_real = unidades * precio
        if monto_real > capital_restante:
            unidades = int(capital_restante // precio)
            if unidades < 1:
                pendientes.append({
                    "ticker": t,
                    "precio_ars": precio,
                    "falta_ars": precio - capital_restante,
                    "motivo": "Capital remanente insuficiente para 1 unidad",
                })
                continue
            monto_real = unidades * precio
        capital_restante -= monto_real
        orden += 1
        cat = CLASIFICACION_ACTIVOS.get(t, CategoriaActivo.OTRO)
        jus = _trunc(
            f"Acerca a cartera ideal: peso objetivo +{delt*100:.1f} pp en {t}.", 150,
        )
        compras.append(
            ItemRecomendacion(
                orden=orden,
                ticker=t,
                nombre_legible=_nombre_legible(t, universo_df),
                categoria=cat,
                unidades=unidades,
                precio_ars_estimado=precio,
                monto_ars=monto_real,
                monto_usd=monto_real / ccl_f,
                justificacion=jus,
                impacto_en_balance=_impacto_str(t, _es_compra_defensiva(t)),
                prioridad=prio,
                es_activo_nuevo=t not in tickers_hold,
            )
        )

    monto_rf_compras = sum(i.monto_ars for i in compras if es_renta_fija(i.ticker))
    valor_rf_pre = pct_def_pre * total_valor
    pct_post = (valor_rf_pre + monto_rf_compras) / valor_post if valor_post > 0 else pct_def_pre

    delta_bal = f"Renta fija: {pct_def_pre*100:.0f}% → {pct_post*100:.0f}% | concentración vía líneas nuevas"[:200]

    resumen = _trunc(
        f"Con ${cap:,.0f} ARS podés ejecutar {len(compras)} compra(s). RF proyectada ~{pct_post*100:.0f}%.",
        200,
    )

    return RecomendacionResult(
        cliente_nombre=cliente_nombre,
        perfil=perfil_n,
        capital_disponible_ars=cap,
        capital_disponible_usd=capital_usd,
        ccl=ccl_f,
        fecha_recomendacion=fecha,
        compras_recomendadas=compras,
        pendientes_proxima_inyeccion=pendientes,
        capital_usado_ars=cap - capital_restante,
        capital_remanente_ars=capital_restante,
        n_compras=len(compras),
        pct_defensivo_post=pct_post,
        pct_defensivo_pre=pct_def_pre,
        delta_balance=delta_bal,
        resumen_recomendacion=resumen,
    )


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _impacto_str(ticker: str, core_rf: bool) -> str:
    if core_rf:
        return f"Renta fija ↑ por compra en {ticker}"
    return f"Renta variable / diversificación ↑ en {ticker}"
