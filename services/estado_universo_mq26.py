"""
Resumen de conteos para estado de situacion: BYMA Open Data + listas del motor.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def resumen_estado_universo_mq26(
    *,
    max_scan_cedears: int = 80,
    max_scan_merval: int = 40,
    max_scan_on: int = 60,
    max_scan_bonos: int = 30,
) -> dict[str, Any]:
    from services.byma_market_data import _fetch_tipo, fetch_universo_rv_byma
    from services.scoring_engine import (
        UNIVERSO_BONOS_USD,
        UNIVERSO_CEDEARS,
        UNIVERSO_MERVAL,
        _tickers_rv_segmento_desde_byma,
        universo_ons_tickers,
    )

    out: dict[str, Any] = {
        "max_scan_cedears": max_scan_cedears,
        "max_scan_merval": max_scan_merval,
        "max_scan_on": max_scan_on,
        "max_scan_bonos": max_scan_bonos,
    }

    try:
        df = fetch_universo_rv_byma()
    except Exception:
        df = pd.DataFrame()
    if df is not None and not df.empty and "Tipo" in df.columns:
        t = df["Tipo"].astype(str).str.upper().str.strip()
        out["mq26_universo_cedears"] = int((t == "CEDEAR").sum())
        out["mq26_universo_acciones"] = int((t == "ACCION_LOCAL").sum())
    else:
        out["mq26_universo_cedears"] = 0
        out["mq26_universo_acciones"] = 0

    for ep, key in (
        ("cedears", "byma_filas_cedears"),
        ("equities", "byma_filas_equities"),
        ("corporate-bonds", "byma_filas_on"),
        ("government-bonds", "byma_filas_bonos_soberanos"),
        ("lebac-notes", "byma_filas_letras"),
    ):
        try:
            rows = _fetch_tipo(ep)
            out[key] = len(rows) if isinstance(rows, list) else 0
        except Exception:
            out[key] = -1

    ced = _tickers_rv_segmento_desde_byma("cedears", max_scan_cedears)
    out["scan_cedears_tickets"] = len(ced) if ced else min(max_scan_cedears, len(UNIVERSO_CEDEARS))
    mer = _tickers_rv_segmento_desde_byma("merval", max_scan_merval)
    out["scan_merval_tickets"] = len(mer) if mer else min(max_scan_merval, len(UNIVERSO_MERVAL))

    on_list = sorted(universo_ons_tickers())
    out["motor_catalogo_on"] = len(on_list)
    out["scan_on_tickets"] = min(max_scan_on, len(on_list))
    out["motor_lista_bonos"] = len(UNIVERSO_BONOS_USD)
    out["scan_bonos_tickets"] = min(max_scan_bonos, len(UNIVERSO_BONOS_USD))
    return out


def dataframe_estado_universo(res: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"Concepto": "Universo RV MQ26 - CEDEARs (tras reglas motor)", "Cantidad": res.get("mq26_universo_cedears", 0), "Detalle": "Listado BYMA `cedears` consolidado en `fetch_universo_rv_byma`"},
        {"Concepto": "Universo RV MQ26 - Acciones Argentina", "Cantidad": res.get("mq26_universo_acciones", 0), "Detalle": "Listado BYMA `equities` + filtro moneda en instrumentos locales"},
        {"Concepto": "BYMA Open Data - filas panel CEDEARs (crudo)", "Cantidad": res.get("byma_filas_cedears", 0), "Detalle": "POST `cedears` (puede coincidir con universo CEDEAR)"},
        {"Concepto": "BYMA Open Data - filas panel Acciones", "Cantidad": res.get("byma_filas_equities", 0), "Detalle": "POST `equities` (el motor puede excluir filas no ARS)"},
        {"Concepto": "Scoring tecnico - CEDEARs analizados (tope)", "Cantidad": res.get("scan_cedears_tickets", 0), "Detalle": f"Max. {res.get('max_scan_cedears', 80)} - BYMA o fallback `UNIVERSO_CEDEARS`"},
        {"Concepto": "Scoring tecnico - Acciones Merval analizadas (tope)", "Cantidad": res.get("scan_merval_tickets", 0), "Detalle": f"Max. {res.get('max_scan_merval', 40)} - BYMA o fallback `UNIVERSO_MERVAL`"},
        {"Concepto": "Catalogo motor - Obligaciones negociables (ON USD)", "Cantidad": res.get("motor_catalogo_on", 0), "Detalle": "`universo_ons_tickers()` + catalogo RF activo"},
        {"Concepto": "Scoring RF - ON analizadas (tope)", "Cantidad": res.get("scan_on_tickets", 0), "Detalle": f"Max. {res.get('max_scan_on', 60)} instrumentos del catalogo ON"},
        {"Concepto": "BYMA Open Data - Oblig. negociables (filas panel)", "Cantidad": res.get("byma_filas_on", 0), "Detalle": "POST `corporate-bonds`"},
        {"Concepto": "Lista motor - Bonos soberanos USD (scoring)", "Cantidad": res.get("motor_lista_bonos", 0), "Detalle": "`UNIVERSO_BONOS_USD`"},
        {"Concepto": "Scoring RF - Bonos analizados (tope)", "Cantidad": res.get("scan_bonos_tickets", 0), "Detalle": f"Max. {res.get('max_scan_bonos', 30)}"},
        {"Concepto": "BYMA Open Data - Bonos soberanos (filas panel)", "Cantidad": res.get("byma_filas_bonos_soberanos", 0), "Detalle": "POST `government-bonds`"},
        {"Concepto": "BYMA Open Data - Letras (filas panel)", "Cantidad": res.get("byma_filas_letras", 0), "Detalle": "POST `lebac-notes`"},
    ]
    return pd.DataFrame(rows)
