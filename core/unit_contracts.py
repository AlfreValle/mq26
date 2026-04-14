"""
Contratos de unidades (peso/precio/moneda) para flujos de cartera.
"""
from __future__ import annotations

import pandas as pd


def es_instrumento_rf_usd_paridad(ticker: str, tipo: str | None = None) -> bool:
    """
    True si el instrumento trata PPC/precio como paridad % sobre nominal USD (ON/bono cable),
    alineado con `services.cartera_service._ppc_usd_es_paridad_rf_usd`.
    """
    from core.renta_fija_ar import get_meta

    tu = str(ticker or "").upper().strip()
    m = get_meta(tu)
    if m and str(m.get("moneda", "")).upper() == "USD":
        return True
    tp = str(tipo or "").upper().strip()
    return tp in ("ON_USD", "BONO_USD")


def etiqueta_unidad_operativa_ejecucion(ticker: str, tipo: str | None = None) -> str:
    """Etiqueta corta para tablas de órdenes (P2-RF-03)."""
    from core.renta_fija_ar import TIPOS_RF, get_meta

    tp = str(tipo or "").strip().upper()
    if not tp:
        m = get_meta(str(ticker).upper())
        tp = str(m.get("tipo", "") or "").upper() if m else ""
    if es_instrumento_rf_usd_paridad(ticker, tp):
        return "Nominales USD (VN)"
    if tp in TIPOS_RF:
        return "Nominales (RF)"
    return "Nominales / acciones"


def validar_escala_precio_vs_ppc_rf_usd(
    ticker: str,
    tipo: str | None,
    precio_ars: float,
    ppc_ars_ref: float | None,
) -> tuple[bool, str]:
    """
    Guardrail: detecta desalineación ~100× entre precio de mercado y PPC ARS en RF USD,
    misma heurística que `cartera_service.calcular_posicion_neta` (ratio 50–500 → ÷100).
    """
    if not es_instrumento_rf_usd_paridad(ticker, tipo):
        return True, ""
    if precio_ars <= 0:
        return False, "Precio ARS inválido o cero."
    if ppc_ars_ref is None:
        return True, ""
    ppc = float(ppc_ars_ref)
    if ppc <= 0:
        return True, ""
    ratio = precio_ars / ppc
    if 50.0 < ratio < 500.0:
        return False, (
            "Escala inconsistente: el precio parece cotizado por lote (p. ej. cada 100 nominales USD) "
            "frente al costo (PPC) en ARS por nominal. Revisá la fuente de precio."
        )
    if ratio > 0 and ratio < (1.0 / 500.0):
        return False, (
            "Escala inconsistente: el precio es demasiado bajo respecto al PPC (posible error de unidad)."
        )
    return True, ""


def validar_fila_orden_ejecucion(
    ticker: str,
    precio_ars: float,
    df_ag: pd.DataFrame | None,
) -> tuple[bool, str, str]:
    """
    Valida una fila de orden respecto a la posición en `df_ag` (si existe).

    Returns:
        (ok, mensaje_bloqueo_vacío_si_ok, etiqueta_unidad)
    """
    t = str(ticker).upper().strip()
    tipo: str | None = None
    ppc_ref: float | None = None
    if df_ag is not None and not df_ag.empty and "TICKER" in df_ag.columns:
        hit = df_ag[df_ag["TICKER"].astype(str).str.upper() == t]
        if not hit.empty:
            row = hit.iloc[0]
            if "TIPO" in row.index:
                raw_t = row["TIPO"]
                tipo = None if pd.isna(raw_t) else str(raw_t)
            else:
                tipo = None
            if "PPC_ARS" in row.index:
                ppc_ref = float(pd.to_numeric(row.get("PPC_ARS"), errors="coerce") or 0.0)
                if ppc_ref <= 0:
                    ppc_ref = None
    etiqueta = etiqueta_unidad_operativa_ejecucion(ticker, tipo)
    ok, msg = validar_escala_precio_vs_ppc_rf_usd(ticker, tipo, precio_ars, ppc_ref)
    return ok, msg, etiqueta


def enriquecer_ordenes_con_unidad(df: pd.DataFrame, df_ag: pd.DataFrame | None) -> pd.DataFrame:
    """Añade columna `unidad_operativa` para UI/export (idempotente si ya existe)."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "unidad_operativa" in out.columns:
        return out
    if "ticker" not in out.columns and "Ticker" in out.columns:
        tick_col = "Ticker"
    elif "ticker" in out.columns:
        tick_col = "ticker"
    else:
        out["unidad_operativa"] = ""
        return out
    precio_col = "precio_ars" if "precio_ars" in out.columns else ("Precio ARS" if "Precio ARS" in out.columns else None)
    labs = []
    for _, r in out.iterrows():
        px = float(pd.to_numeric(r.get(precio_col), errors="coerce") or 0.0) if precio_col else 0.0
        _, _, lab = validar_fila_orden_ejecucion(str(r[tick_col]), px, df_ag)
        labs.append(lab)
    out["unidad_operativa"] = labs
    return out


def validar_dataframe_ordenes_ejecucion(df: pd.DataFrame, df_ag: pd.DataFrame | None) -> tuple[bool, list[str]]:
    """
    Valida todas las filas con ticker + precio. Devuelve (todas_ok, mensajes por ticker).
    """
    if df is None or df.empty:
        return True, []
    tick_col = "ticker" if "ticker" in df.columns else ("Ticker" if "Ticker" in df.columns else None)
    precio_col = "precio_ars" if "precio_ars" in df.columns else ("Precio ARS" if "Precio ARS" in df.columns else None)
    if not tick_col or not precio_col:
        return True, []
    msgs: list[str] = []
    for _, r in df.iterrows():
        t = str(r[tick_col])
        px = float(pd.to_numeric(r.get(precio_col), errors="coerce") or 0.0)
        ok, msg, _ = validar_fila_orden_ejecucion(t, px, df_ag)
        if not ok and msg:
            msgs.append(f"{t}: {msg}")
    return len(msgs) == 0, msgs


def validar_contrato_unidades_posicion_neta(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Contrato esperado en posición neta:
    - PRECIO_ARS, PPC_ARS, VALOR_ARS, INV_ARS en ARS por unidad/posición.
    - PESO_PCT en fracción [0, 1].
    - MONEDA_PRECIO (si existe) normalizada.
    """
    out = df.copy()
    issues: list[str] = []
    if out.empty:
        out["CONTRATO_UNIDADES_OK"] = pd.Series(dtype=bool)
        return out, issues

    # Normalización básica de moneda informativa (si está disponible).
    if "MONEDA_PRECIO" in out.columns:
        out["MONEDA_PRECIO"] = (
            out["MONEDA_PRECIO"].astype(str).str.strip().str.upper().replace({"": "ARS"})
        )

    # PESO_PCT debe ser fracción, no porcentaje 0..100
    if "PESO_PCT" in out.columns:
        peso = pd.to_numeric(out["PESO_PCT"], errors="coerce").fillna(0.0)
        if (peso > 1.0 + 1e-9).any():
            issues.append("PESO_PCT fuera de contrato (esperado fracción 0..1).")
        if (peso < -1e-9).any():
            issues.append("PESO_PCT negativo fuera de contrato.")

    # Precios/costos en ARS no negativos.
    for col in ("PRECIO_ARS", "PPC_ARS", "VALOR_ARS", "INV_ARS"):
        if col in out.columns:
            vals = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
            if (vals < -1e-9).any():
                issues.append(f"{col} negativo fuera de contrato.")

    out["CONTRATO_UNIDADES_OK"] = len(issues) == 0
    return out, issues
