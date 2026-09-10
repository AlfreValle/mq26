"""
ui/deeplinks.py — A12: Sistema de deeplinks avanzados para MQ26.

Sprint 5 — A12:
  Permite navegar directamente a un tab, cliente y cartera específicos
  mediante parámetros de URL. Compatible con Streamlit 1.30+.

  Formato de URL:
    ?tab=cartera&cliente=123&cartera=Mi%20Cartera
    ?tab=diagnostico&cliente=42
    ?tab=torre_control

  Parámetros soportados:
    tab          — nombre o alias del tab destino
    cliente      — cliente_id (int) o nombre (str, lookup parcial)
    cartera      — nombre de la cartera (exacto o parcial)
    cartera_id   — ID numérico de la cartera
    modo         — "fifo" | "ppc" (modo de valuación)
    debug        — "1" para forzar modo debug en el request

  API:
    parse_deeplink() → DeeplinkParams         ← lee de st.query_params
    apply_deeplink(params, ctx) → ApplyResult ← aplica al session_state
    build_deeplink(tab, *, cliente_id, cartera, ...) → str ← construye URL
    render_deeplink_status()                   ← muestra badge si activo
    mark_deeplink_applied(tab)                 ← evita re-aplicar en reruns
    is_deeplink_applied(tab) → bool

  Diseño:
    - Solo se aplica UNA VEZ por rerun (guarded con session_state).
    - El tab destino de ``apply_deeplink`` se consume en ``ui.navigation.render_main_tabs``
      vía ``consume_deeplink_tab()`` y activa ``st.segmented_control`` (A9/C18).
    - No lanza excepciones: errores en DeeplinkResult.errors.
    - Compatible con DEEPLINKS_AVANZADOS feature flag.
    - Sin dependencia circular: importa core/session_schema desde función.
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)

# Alias de tabs: nombre amigable → tab_id interno
_TAB_ALIASES: dict[str, str] = {
    # nombres canónicos (tab_id de ui.navigation)
    "cartera":          "cartera",
    "mercado":          "mercado",
    "universo":         "universo",
    "optimizacion":     "optimizacion",
    "riesgo":           "riesgo",
    "retiro":           "retiro",
    "ejecucion":        "ejecucion",
    "reporte":          "reporte",
    "reportes":         "reporte",
    "admin":            "admin",
    "administracion":   "admin",
    "estudio":          "estudio",
    "mi_cartera":       "mi_cartera",
    "plan_objetivos":   "plan_objetivos",
    "perlas":           "perlas",
    "diagnostico":      "diagnostico",
    "torre_control":    "estudio",
    "torre":            "estudio",
    # aliases en inglés
    "portfolio":        "cartera",
    "optimize":         "optimizacion",
    "control_tower":    "estudio",
    "reports":          "reporte",
    "retirement":       "retiro",
    "market":           "mercado",
    # aliases cortos
    "cart":             "cartera",
    "diag":             "diagnostico",
    "opt":              "optimizacion",
}

# Parámetros válidos de deeplink
_VALID_PARAMS = {"tab", "cliente", "cartera", "cartera_id", "modo", "debug"}


# ─── Tipos de datos ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeeplinkParams:
    """Parámetros extraídos de la URL."""
    tab:        str | None          # tab destino resuelto
    cliente_id: int | None          # cliente_id numérico (si se pudo resolver)
    cliente_raw: str                # valor crudo del parámetro ?cliente=
    cartera:    str                 # nombre de cartera (crudo)
    cartera_id: int | None          # ID numérico de cartera
    modo_fifo:  bool | None         # True=FIFO, False=PPC, None=sin cambio
    debug:      bool
    raw:        dict[str, str] = field(compare=False)   # params originales

    @property
    def has_any(self) -> bool:
        """True si hay al menos un parámetro de deeplink."""
        return bool(
            self.tab or self.cliente_raw or self.cartera
            or self.cartera_id is not None
            or self.modo_fifo is not None
        )

    @property
    def has_tab(self) -> bool:
        return bool(self.tab)

    @property
    def has_cliente(self) -> bool:
        return bool(self.cliente_raw)

    @property
    def has_cartera(self) -> bool:
        return bool(self.cartera) or self.cartera_id is not None


@dataclass
class ApplyResult:
    """Resultado de aplicar un deeplink al session_state."""
    applied:      bool = False
    tab_resolved: str  = ""
    errors:       list[str] = field(default_factory=list)
    warnings:     list[str] = field(default_factory=list)
    changes:      list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.applied and not self.errors

    def add_change(self, msg: str) -> None:
        self.changes.append(msg)
        _LOG.debug("deeplink change: %s", msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        _LOG.warning("deeplink error: %s", msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        _LOG.debug("deeplink warning: %s", msg)


# ─── Parseo de URL ─────────────────────────────────────────────────────────────

def parse_deeplink() -> DeeplinkParams:
    """
    Lee los query params de Streamlit y retorna DeeplinkParams.
    No modifica el session_state.
    """
    try:
        import streamlit as st
        raw: dict[str, str] = dict(st.query_params)
    except Exception:
        raw = {}

    # Tab
    tab_raw = raw.get("tab", "").strip().lower()
    tab = _TAB_ALIASES.get(tab_raw) if tab_raw else None

    # Cliente — puede ser int o string
    cliente_raw = raw.get("cliente", "").strip()
    cliente_id: int | None = None
    if cliente_raw:
        try:
            cliente_id = int(cliente_raw)
        except ValueError:
            pass  # se tratará como búsqueda por nombre

    # Cartera
    cartera = raw.get("cartera", "").strip()

    # cartera_id
    cartera_id: int | None = None
    cartera_id_raw = raw.get("cartera_id", "").strip()
    if cartera_id_raw:
        try:
            cartera_id = int(cartera_id_raw)
        except ValueError:
            pass

    # Modo
    modo_raw = raw.get("modo", "").strip().lower()
    modo_fifo: bool | None = None
    if modo_raw == "fifo":
        modo_fifo = True
    elif modo_raw == "ppc":
        modo_fifo = False

    # Debug
    debug = raw.get("debug", "").strip() == "1"

    return DeeplinkParams(
        tab=tab,
        cliente_id=cliente_id,
        cliente_raw=cliente_raw,
        cartera=cartera,
        cartera_id=cartera_id,
        modo_fifo=modo_fifo,
        debug=debug,
        raw=raw,
    )


# ─── Aplicación al session_state ──────────────────────────────────────────────

def apply_deeplink(
    params: DeeplinkParams,
    ctx: Any = None,
    *,
    df_clientes: Any = None,
) -> ApplyResult:
    """
    Aplica los parámetros del deeplink al session_state.
    Solo se aplica si no fue aplicado antes en este rerun (idempotente).

    Args:
        params:      parámetros parseados con parse_deeplink().
        ctx:         AppContext (opcional, para lookup de clientes).
        df_clientes: DataFrame de clientes (alternativa a ctx).

    Returns:
        ApplyResult con el resultado de la aplicación.
    """
    result = ApplyResult()

    if not params.has_any:
        return result

    # Guard: solo aplicar una vez por tab_id
    tab_key = params.tab or "_none"
    if is_deeplink_applied(tab_key):
        _LOG.debug("deeplink ya aplicado para tab=%s, skip", tab_key)
        return result

    try:
        from core.session_schema import K, set_ss
    except ImportError:
        result.add_error("core.session_schema no disponible")
        return result

    # ── Tab ──────────────────────────────────────────────────────────────────
    if params.tab:
        # El tab destino se comunica via session_state para que run_mq26.py lo consuma
        set_ss("_mq26_deeplink_tab", params.tab)
        result.add_change(f"tab → {params.tab}")
        result.tab_resolved = params.tab

    # ── Cliente ──────────────────────────────────────────────────────────────
    if params.has_cliente:
        _apply_cliente(params, ctx, df_clientes, result)

    # ── Cartera ──────────────────────────────────────────────────────────────
    if params.has_cartera:
        _apply_cartera(params, result)

    # ── Modo FIFO/PPC ────────────────────────────────────────────────────────
    if params.modo_fifo is not None:
        set_ss(K.MODO_FIFO, params.modo_fifo)
        result.add_change(f"modo_fifo → {params.modo_fifo}")

    # ── Marcar como aplicado ─────────────────────────────────────────────────
    mark_deeplink_applied(tab_key)
    result.applied = True

    _LOG.info(
        "deeplink applied: tab=%s cliente=%s cartera=%s changes=%d errors=%d",
        params.tab, params.cliente_raw, params.cartera,
        len(result.changes), len(result.errors),
    )
    return result


def _columna_id_clientes(df: Any) -> str | None:
    """Columna de id en el df scoped (db_clientes usa ID; otros usan cliente_id)."""
    if df is None:
        return None
    cols = getattr(df, "columns", [])
    for c in ("cliente_id", "ID", "id"):
        if c in cols:
            return c
    return str(cols[0]) if len(cols) else None


def _nombre_fila_cliente(row: Any) -> str:
    for c in ("Nombre", "nombre", "cliente_nombre", "razon_social"):
        try:
            if c in row.index:
                val = row[c]
                if val is not None and str(val).strip():
                    return str(val)
        except Exception:
            continue
    return ""


def _apply_cliente(
    params: DeeplinkParams,
    ctx: Any,
    df_clientes: Any,
    result: ApplyResult,
) -> None:
    """Aplica el cliente del deeplink al session_state."""
    try:
        import pandas as pd

        from core.session_schema import K, set_ss

        # Obtener df_clientes desde ctx si no se pasó directamente
        df = df_clientes
        if df is None and ctx is not None:
            df = getattr(ctx, "df_clientes", None)

        if params.cliente_id is not None:
            # Fail-closed: sin df scoped no hay allowlist que consultar.
            if df is None or getattr(df, "empty", True):
                result.add_warning(
                    "df_clientes no disponible: no se aplica cliente_id del deeplink"
                )
                return
            col_id = _columna_id_clientes(df)
            if col_id is None:
                result.add_warning("df_clientes sin columna de id: no se aplica cliente_id")
                return
            ids = pd.to_numeric(df[col_id], errors="coerce")
            match = df.loc[ids == int(params.cliente_id)]
            if match.empty:
                result.add_warning(
                    f"cliente_id={params.cliente_id} no encontrado en df_clientes"
                )
                return
            nombre = _nombre_fila_cliente(match.iloc[0])
            set_ss(K.CLIENTE_ID, params.cliente_id)
            if nombre:
                set_ss(K.CLIENTE_NOMBRE, nombre)
            result.add_change(f"cliente_id → {params.cliente_id} ({nombre})")
            return

        elif params.cliente_raw:
            # Buscar por nombre parcial
            if df is not None and not df.empty:
                nombre_lower = params.cliente_raw.lower()
                for col in ("nombre", "cliente_nombre", "Nombre", "razon_social"):
                    if col in df.columns:
                        mask = df[col].astype(str).str.lower().str.contains(
                            nombre_lower, na=False
                        )
                        matches = df[mask]
                        if not matches.empty:
                            row = matches.iloc[0]
                            col_id = _columna_id_clientes(df) or df.columns[0]
                            cid = int(row[col_id])
                            nombre = str(row.get(col, params.cliente_raw))
                            set_ss(K.CLIENTE_ID, cid)
                            set_ss(K.CLIENTE_NOMBRE, nombre)
                            result.add_change(f"cliente → {nombre} (id={cid})")
                            return
                result.add_warning(f"cliente={params.cliente_raw!r} no encontrado")
            else:
                result.add_warning("df_clientes no disponible para lookup por nombre")

    except Exception as e:
        result.add_error(f"_apply_cliente: {e}")


def _apply_cartera(params: DeeplinkParams, result: ApplyResult) -> None:
    """Aplica la cartera del deeplink al session_state."""
    try:
        from core.session_schema import K, set_ss
        if params.cartera:
            set_ss(K.CARTERA_ACTIVA, params.cartera)
            result.add_change(f"cartera_activa → {params.cartera!r}")
    except Exception as e:
        result.add_error(f"_apply_cartera: {e}")


# ─── Guard de re-aplicación ────────────────────────────────────────────────────

def mark_deeplink_applied(tab: str) -> None:
    """Marca el deeplink de tab como ya aplicado en esta sesión."""
    try:
        from core.session_schema import K, set_ss
        key = f"{K.DEEPLINK_OK_PFX}{tab}"
        set_ss(key, True)
    except Exception:
        pass


def is_deeplink_applied(tab: str) -> bool:
    """True si el deeplink para tab ya fue aplicado."""
    try:
        from core.session_schema import K, get_ss
        key = f"{K.DEEPLINK_OK_PFX}{tab}"
        return bool(get_ss(key, False))
    except Exception:
        return False


def reset_deeplink_guard(tab: str | None = None) -> None:
    """
    Limpia el guard de deeplink.
    Si tab=None limpia todos los guards de deeplink.
    Útil en tests o al cerrar sesión.
    """
    try:
        import streamlit as st

        from core.session_schema import K
        prefix = K.DEEPLINK_OK_PFX
        if tab is not None:
            key = f"{prefix}{tab}"
            st.session_state.pop(key, None)
        else:
            keys = [k for k in list(st.session_state.keys()) if k.startswith(prefix)]
            for k in keys:
                del st.session_state[k]
    except Exception:
        pass


# ─── Constructor de URLs ───────────────────────────────────────────────────────

def build_deeplink(
    tab: str = "",
    *,
    cliente_id: int | None = None,
    cartera: str = "",
    cartera_id: int | None = None,
    modo: str = "",
    base_url: str = "",
    debug: bool = False,
) -> str:
    """
    Construye una URL de deeplink con los parámetros dados.

    Args:
        tab:        nombre del tab destino (alias o nombre canónico).
        cliente_id: ID del cliente.
        cartera:    nombre de la cartera.
        cartera_id: ID numérico de la cartera.
        modo:       "fifo" | "ppc".
        base_url:   URL base (sin query string); por defecto cadena vacía.
        debug:      añadir ?debug=1.

    Returns:
        URL con query string codificado.
    """
    params: dict[str, str] = {}
    if tab:
        params["tab"] = tab.lower()
    if cliente_id is not None:
        params["cliente"] = str(cliente_id)
    if cartera:
        params["cartera"] = cartera
    if cartera_id is not None:
        params["cartera_id"] = str(cartera_id)
    if modo in ("fifo", "ppc"):
        params["modo"] = modo
    if debug:
        params["debug"] = "1"

    if not params:
        return base_url or "?"

    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    sep = "?" if "?" not in (base_url or "") else "&"
    return f"{base_url}{sep}{qs}" if base_url else f"?{qs}"


# ─── UI helper ────────────────────────────────────────────────────────────────

def render_deeplink_status(params: DeeplinkParams | None = None) -> None:
    """
    Renderiza un badge informativo si hay parámetros de deeplink activos.
    Solo visible en modo debug o si hay errores.
    """
    try:
        import streamlit as st

        from core.feature_flags import is_enabled

        if not is_enabled("DEEPLINKS_AVANZADOS"):
            return

        if params is None:
            params = parse_deeplink()

        if not params.has_any:
            return

        debug_mode = st.session_state.get("_mq26_debug", False) or params.debug
        if not debug_mode:
            return

        parts = []
        if params.tab:
            parts.append(f"tab=**{params.tab}**")
        if params.cliente_raw:
            parts.append(f"cliente=**{params.cliente_raw}**")
        if params.cartera:
            parts.append(f"cartera=**{params.cartera}**")

        st.info(f"🔗 Deeplink activo: {' · '.join(parts)}", icon=None)

    except Exception:
        pass


def get_pending_deeplink_tab() -> str:
    """
    Retorna el tab_id pendiente de deeplink (si hay uno).
    Llamado desde run_mq26.py para hacer el scroll/rerun al tab correcto.
    """
    try:
        from core.session_schema import get_ss
        return str(get_ss("_mq26_deeplink_tab", "") or "")
    except Exception:
        return ""


def consume_deeplink_tab() -> str:
    """
    Retorna y limpia el tab pendiente de deeplink.
    Llamar una sola vez al inicio del run.
    """
    try:
        import streamlit as st
        tab = str(st.session_state.pop("_mq26_deeplink_tab", "") or "")
        return tab
    except Exception:
        return ""
