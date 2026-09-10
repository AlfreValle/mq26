"""
core/domain_ctx.py — A3: Contextos por dominio (sub-contextos tipados).

Sprint 5 — A3:
  Descompone el monolítico AppContext en sub-contextos cohesivos por dominio.
  Cada DomainCtx es un dataclass inmutable con solo los campos que necesita.
  Se extrae desde AppContext sin copiar datos (vistas lightweight).

  Dominios:
    ClienteCtx  — identidad y perfil del cliente activo
    CarteraCtx  — posiciones, precios, métricas del portafolio
    MarketCtx   — macro, CCL, datos de análisis y señales
    TenantCtx   — tenant, clientes visibles, permisos
    SessionCtx  — rol, estado de autenticación, configuración UI

  API:
    from_app_ctx(ctx) → DomainBundle   (extrae todos los sub-contextos)
    ClienteCtx.from_app(ctx) → ClienteCtx
    CarteraCtx.from_app(ctx) → CarteraCtx
    MarketCtx.from_app(ctx)  → MarketCtx
    TenantCtx.from_app(ctx)  → TenantCtx
    SessionCtx.from_session() → SessionCtx   (lee de st.session_state)

  Diseño:
    - Inmutables (frozen=True): no mutan después de construcción.
    - Tipados: sin campos Any donde sea posible.
    - Constructores .from_app() / .from_session() son los únicos puntos de entrada.
    - Compatibles con forward refs (sin imports circulares).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# ─── ClienteCtx ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClienteCtx:
    """Identidad y perfil del cliente activo."""
    cliente_id:       int | None
    nombre:           str
    perfil:           str          # "Conservador" | "Moderado" | ...
    horizonte_label:  str          # "1 año" | "3 años" | ...
    horizonte_dias:   int          # derivado de horizonte_label

    @property
    def tiene_cliente(self) -> bool:
        return self.cliente_id is not None and bool(self.nombre)

    @classmethod
    def from_app(cls, ctx: Any) -> ClienteCtx:
        return cls(
            cliente_id      = getattr(ctx, "cliente_id",      None),
            nombre          = str(getattr(ctx, "cliente_nombre", "") or ""),
            perfil          = str(getattr(ctx, "cliente_perfil",  "Moderado") or "Moderado"),
            horizonte_label = str(getattr(ctx, "horizonte_label", "1 año") or "1 año"),
            horizonte_dias  = int(getattr(ctx, "horizonte_dias",  365) or 365),
        )

    @classmethod
    def from_session(cls) -> ClienteCtx:
        from core.session_schema import K, get_ss
        hl = str(get_ss(K.CLIENTE_HORIZONTE, "1 año") or "1 año")
        return cls(
            cliente_id      = get_ss(K.CLIENTE_ID),
            nombre          = str(get_ss(K.CLIENTE_NOMBRE, "") or ""),
            perfil          = str(get_ss(K.CLIENTE_PERFIL, "Moderado") or "Moderado"),
            horizonte_label = hl,
            horizonte_dias  = _horizonte_to_dias(hl),
        )

    @classmethod
    def empty(cls) -> ClienteCtx:
        return cls(
            cliente_id=None, nombre="", perfil="Moderado",
            horizonte_label="1 año", horizonte_dias=365,
        )


# ─── CarteraCtx ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CarteraCtx:
    """Estado del portafolio activo: posiciones, precios y métricas."""
    cartera_activa:   str
    prop_nombre:      str          # propietario / label de la cartera
    df_ag:            pd.DataFrame = field(compare=False)
    df_trans:         pd.DataFrame = field(compare=False)
    precios_dict:     dict[str, float] = field(compare=False)
    tickers:          tuple[str, ...]
    metricas:         dict[str, Any]   = field(compare=False)
    modo_fifo:        bool

    @property
    def tiene_posiciones(self) -> bool:
        return not self.df_ag.empty

    @property
    def n_posiciones(self) -> int:
        return len(self.df_ag) if not self.df_ag.empty else 0

    @property
    def valor_total_ars(self) -> float:
        if self.df_ag.empty or "VALOR_ARS" not in self.df_ag.columns:
            return 0.0
        return float(
            pd.to_numeric(self.df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()
        )

    @classmethod
    def from_app(cls, ctx: Any) -> CarteraCtx:
        df_ag   = getattr(ctx, "df_ag",   pd.DataFrame())
        df_t    = getattr(ctx, "df_trans", pd.DataFrame())
        tickers = tuple(getattr(ctx, "tickers_cartera", []) or [])
        return cls(
            cartera_activa = str(getattr(ctx, "cartera_activa", "") or ""),
            prop_nombre    = str(getattr(ctx, "prop_nombre",    "") or ""),
            df_ag          = df_ag if isinstance(df_ag, pd.DataFrame) else pd.DataFrame(),
            df_trans       = df_t  if isinstance(df_t,  pd.DataFrame) else pd.DataFrame(),
            precios_dict   = dict(getattr(ctx, "precios_dict", {}) or {}),
            tickers        = tickers,
            metricas       = dict(getattr(ctx, "metricas",     {}) or {}),
            modo_fifo      = bool(getattr(ctx, "modo_fifo",    False)),
        )

    @classmethod
    def empty(cls) -> CarteraCtx:
        return cls(
            cartera_activa="", prop_nombre="",
            df_ag=pd.DataFrame(), df_trans=pd.DataFrame(),
            precios_dict={}, tickers=(), metricas={}, modo_fifo=False,
        )


# ─── MarketCtx ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MarketCtx:
    """Datos de mercado: CCL, análisis cuantitativo, historial."""
    ccl:            float
    df_analisis:    pd.DataFrame = field(compare=False)
    risk_free_rate: float
    capital_nuevo:  float
    n_sim:          int
    recesion_riesgo: bool

    @property
    def ccl_valido(self) -> bool:
        return 100.0 <= self.ccl <= 20_000.0

    @classmethod
    def from_app(cls, ctx: Any) -> MarketCtx:
        from core.session_schema import K, get_ss
        df_an = getattr(ctx, "df_analisis", pd.DataFrame())
        return cls(
            ccl             = float(getattr(ctx, "ccl",             1_500.0) or 1_500.0),
            df_analisis     = df_an if isinstance(df_an, pd.DataFrame) else pd.DataFrame(),
            risk_free_rate  = float(getattr(ctx, "RISK_FREE_RATE",  0.06) or 0.06),
            capital_nuevo   = float(getattr(ctx, "capital_nuevo",   0.0)  or 0.0),
            n_sim           = int(getattr(ctx, "N_SIM_DEFAULT",    5000) or 5000),
            recesion_riesgo = bool(get_ss(K.RECESION_RIESGO, False)),
        )

    @classmethod
    def empty(cls) -> MarketCtx:
        return cls(
            ccl=1_500.0, df_analisis=pd.DataFrame(),
            risk_free_rate=0.06, capital_nuevo=0.0,
            n_sim=5000, recesion_riesgo=False,
        )


# ─── TenantCtx ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TenantCtx:
    """Aislamiento multi-tenant: tenant_id y clientes visibles."""
    tenant_id:         str
    df_clientes:       pd.DataFrame = field(compare=False)
    allowed_cliente_ids: tuple[int, ...] | None  # None = sin restricción

    @property
    def n_clientes(self) -> int:
        return len(self.df_clientes) if not self.df_clientes.empty else 0

    def cliente_permitido(self, cliente_id: int) -> bool:
        if self.allowed_cliente_ids is None:
            return True
        return cliente_id in self.allowed_cliente_ids

    @classmethod
    def from_app(cls, ctx: Any) -> TenantCtx:
        from core.session_schema import K, get_ss
        df_cli = getattr(ctx, "df_clientes", pd.DataFrame())
        app_id = str(getattr(ctx, "app_id", None) or get_ss("app_id", None) or "mq26")
        allowed = get_ss(K.allowed_clientes_key(app_id), None)
        if allowed is None:
            allowed_ids = None
        else:
            allowed_ids = tuple(int(i) for i in allowed)
        return cls(
            tenant_id           = str(getattr(ctx, "tenant_id", "default") or "default"),
            df_clientes         = df_cli if isinstance(df_cli, pd.DataFrame) else pd.DataFrame(),
            allowed_cliente_ids = allowed_ids,
        )

    @classmethod
    def empty(cls, tenant_id: str = "default") -> TenantCtx:
        return cls(tenant_id=tenant_id, df_clientes=pd.DataFrame(), allowed_cliente_ids=None)


# ─── SessionCtx ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionCtx:
    """Estado de la sesión: rol, autenticación, preferencias UI."""
    role:            str       # "inversor" | "estudio" | "admin" | ...
    authenticated:   bool
    light_mode:      bool
    login_user:      str
    capital_inyectado: float
    mc_n_escenarios:   int

    @property
    def is_admin_like(self) -> bool:
        return self.role in ("super_admin", "admin")

    @property
    def is_estudio(self) -> bool:
        return self.role == "estudio"

    @property
    def is_inversor(self) -> bool:
        return self.role == "inversor"

    @classmethod
    def from_session(cls) -> SessionCtx:
        from core.session_schema import K, get_ss
        auth = bool(
            get_ss(K.AUTH, False)
            or (get_ss(K.AUTH_STATUS) is True)
        )
        return cls(
            role             = str(get_ss(K.USER_ROLE, "viewer") or "viewer"),
            authenticated    = auth,
            light_mode       = bool(get_ss(K.LIGHT_MODE, False)),
            login_user       = str(get_ss(K.LOGIN_USER, "") or ""),
            capital_inyectado= float(get_ss(K.CAPITAL_INYECTADO, 0.0) or 0.0),
            mc_n_escenarios  = int(get_ss(K.MC_N_ESCENARIOS, 3000) or 3000),
        )

    @classmethod
    def empty(cls) -> SessionCtx:
        return cls(
            role="viewer", authenticated=False, light_mode=False,
            login_user="", capital_inyectado=0.0, mc_n_escenarios=3000,
        )


# ─── DomainBundle ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DomainBundle:
    """Colección de todos los sub-contextos para un request."""
    cliente:  ClienteCtx
    cartera:  CarteraCtx
    market:   MarketCtx
    tenant:   TenantCtx
    session:  SessionCtx

    @classmethod
    def from_app_ctx(cls, ctx: Any) -> DomainBundle:
        """Construye el bundle completo desde un AppContext."""
        return cls(
            cliente = ClienteCtx.from_app(ctx),
            cartera = CarteraCtx.from_app(ctx),
            market  = MarketCtx.from_app(ctx),
            tenant  = TenantCtx.from_app(ctx),
            session = SessionCtx.from_session(),
        )

    @classmethod
    def empty(cls) -> DomainBundle:
        return cls(
            cliente = ClienteCtx.empty(),
            cartera = CarteraCtx.empty(),
            market  = MarketCtx.empty(),
            tenant  = TenantCtx.empty(),
            session = SessionCtx.empty(),
        )


# ─── Convenience shortcut ──────────────────────────────────────────────────────

def from_app_ctx(ctx: Any) -> DomainBundle:
    """Alias de DomainBundle.from_app_ctx(ctx)."""
    return DomainBundle.from_app_ctx(ctx)


# ─── Helper privado ────────────────────────────────────────────────────────────

def _horizonte_to_dias(label: str) -> int:
    _MAP = {
        "1 mes":   30,
        "3 meses": 90,
        "6 meses": 180,
        "1 año":   365,
        "3 años":  1095,
        "+5 años": 1825,
    }
    return _MAP.get((label or "").strip(), 365)
