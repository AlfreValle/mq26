"""
core/app_context.py — Contexto tipado de la aplicación MQ26 (MQ-A1)
Reemplaza el dict `ctx` plano por un dataclass con type hints completos.
Elimina errores silenciosos por claves faltantes y habilita autocompletado IDE.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class AppContext:
    """
    Contexto compartido entre todos los tabs de MQ26.
    Construido una sola vez por frame en core/ctx_builder.py y pasado a render_tab_*().
    """
    # ── Estado de cartera ────────────────────────────────────────────────────
    df_ag:           pd.DataFrame = field(default_factory=pd.DataFrame)
    tickers_cartera: list[str]    = field(default_factory=list)
    precios_dict:    dict[str, float] = field(default_factory=dict)
    ccl:             float            = 1500.0
    cartera_activa:  str              = ""
    prop_nombre:     str              = ""
    df_clientes:     pd.DataFrame     = field(default_factory=pd.DataFrame)
    df_analisis:     pd.DataFrame     = field(default_factory=pd.DataFrame)
    metricas:        dict[str, Any]   = field(default_factory=dict)
    df_trans:        pd.DataFrame     = field(default_factory=pd.DataFrame)

    # ── Cliente activo ───────────────────────────────────────────────────────
    cliente_id:      int | None = None
    cliente_nombre:  str           = ""
    cliente_perfil:  str           = "Moderado"
    horizonte_label: str           = "1 año"

    # ── Config financiero ────────────────────────────────────────────────────
    RISK_FREE_RATE:   float = 0.06
    PESO_MAX_CARTERA: float = 0.25
    N_SIM_DEFAULT:    int   = 5000
    RUTA_ANALISIS:    str   = ""
    horizonte_dias:   int   = 365
    capital_nuevo:    float = 0.0

    # ── Rutas ────────────────────────────────────────────────────────────────
    BASE_DIR: Path = field(default_factory=Path)

    # ── Motores / engines (Any para evitar imports circulares) ───────────────
    engine_data:      Any = None
    RiskEngine:       Any = None
    cached_historico: Any = None

    # ── Servicios ────────────────────────────────────────────────────────────
    dbm:     Any = None
    cs:      Any = None
    m23svc:  Any = None
    ejsvc:   Any = None
    rpt:     Any = None
    bt:      Any = None
    ab:      Any = None
    lm:      Any = None
    bi:      Any = None
    gr:      Any = None
    mc:      Any = None

    # ── Multi-tenant (Sprint 5) ─────────────────────────────────────────────
    tenant_id: str = "default"

    # ── Helpers ──────────────────────────────────────────────────────────────
    _boton_exportar: Callable | None = None
    asignar_sector:  Callable | None = None

    def to_dict(self) -> dict[str, Any]:
        """Compatibilidad retroactiva: devuelve un dict plano para tabs que usan ctx['key']."""
        import dataclasses
        return dataclasses.asdict(self)

    def get(self, key: str, default: Any = None) -> Any:
        """Acceso tipo dict para compatibilidad con código legado."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Permite usar ctx['key'] además de ctx.key."""
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        """Permite usar 'key' in ctx."""
        return hasattr(self, key)
