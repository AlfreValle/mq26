"""
core/rf_panel_taxonomy.py — Familias tipo panel BYMA/BAVSA para alinear datos y UI con MQ26.

Mapeo declarativo hacia tipos operativos en renta_fija_ar / columna TIPO del libro.
Ingest CSV/API puede rellenar `familia_panel` + `tipo_mq26` sin reescribir reglas de cartera.
"""
from __future__ import annotations

from enum import Enum


class FamiliaPanelRF(str, Enum):
    """Taxonomía educativa / datos — no reemplaza la clasificación binaria RF del motor."""

    TASA_FIJA_ARS = "tasa_fija_ars"
    BONCER_CER = "boncer_cer"
    HARD_USD_NY = "hard_usd_ny"
    HARD_USD_LOCAL = "hard_usd_local"
    BOPREAL = "bopreal"
    DOLAR_LINKED = "dolar_linked"
    DUAL = "dual"
    TAMAR_CORTO = "tamar_corto"
    LETRA_LECAP = "letra_lecap"


# Sugerencia de TIPO en df_ag / universo (subset de TIPOS_RF + alias soberanos).
FAMILIA_A_TIPO_MQ26: dict[FamiliaPanelRF, str] = {
    FamiliaPanelRF.TASA_FIJA_ARS: "BONO",
    FamiliaPanelRF.BONCER_CER: "BONCER",
    FamiliaPanelRF.HARD_USD_NY: "BONO_USD",
    FamiliaPanelRF.HARD_USD_LOCAL: "BONO_USD",
    FamiliaPanelRF.BOPREAL: "BOPREAL",
    FamiliaPanelRF.DOLAR_LINKED: "USD_LINKED",
    FamiliaPanelRF.DUAL: "DUAL",
    FamiliaPanelRF.TAMAR_CORTO: "BONO",
    FamiliaPanelRF.LETRA_LECAP: "LECAP",
}


def familia_desde_prefijos(ticker: str) -> FamiliaPanelRF | None:
    """
    Heurística por prefijo (MVP); completar con tabla maestra al ingestir panel.
    """
    t = str(ticker or "").strip().upper()
    if not t:
        return None
    if t.startswith("BPY") or t.startswith("BPB"):
        return FamiliaPanelRF.BOPREAL
    if t.startswith("TAM"):
        return FamiliaPanelRF.TAMAR_CORTO
    if t.startswith("S") and len(t) >= 2 and t[1].isdigit():
        return FamiliaPanelRF.LETRA_LECAP
    if t.startswith(("AL", "GD", "AE", "TX")):
        return FamiliaPanelRF.HARD_USD_LOCAL
    return None
