"""
core/notificaciones.py — Notificaciones centralizadas para DSS Alfredo (DS-A8)
Unifica st.toast, st.success, st.error y el log en alertas_log.
"""
from __future__ import annotations

from core.logging_config import get_logger

_log = get_logger(__name__)


class NotificadorDSS:
    """
    Centraliza todos los mensajes de éxito/error del DSS.

    Uso:
        notif = NotificadorDSS(cliente_id=5)
        notif.exito("Transacción guardada correctamente")
        notif.error("No se pudo guardar: campo vacío")
        notif.alerta("Presupuesto de Alimentos al 92% de uso")
    """

    def __init__(self, cliente_id: int | None = None, dbm=None):
        self.cliente_id = cliente_id
        self.dbm        = dbm

    def _log_en_bd(self, tipo: str, mensaje: str) -> None:
        if self.dbm:
            try:
                self.dbm.registrar_alerta_log(
                    tipo_alerta=tipo, mensaje=mensaje[:400], enviada=False
                )
            except Exception:
                pass

    def exito(self, mensaje: str, toast: bool = True, icono: str = "✅") -> None:
        """Muestra mensaje de éxito via st.toast y/o st.success."""
        import streamlit as st
        _log.info("EXITO: %s", mensaje)
        if toast:
            st.toast(f"{icono} {mensaje}", icon="✅")
        else:
            st.success(f"{icono} {mensaje}")
        self._log_en_bd("AUDITORIA", f"OK: {mensaje}")

    def error(self, mensaje: str, toast: bool = False, icono: str = "❌") -> None:
        """Muestra mensaje de error."""
        import streamlit as st
        _log.error("ERROR DSS: %s", mensaje)
        if toast:
            st.toast(f"{icono} {mensaje}", icon="🔴")
        else:
            st.error(f"{icono} {mensaje}")
        self._log_en_bd("AUDITORIA", f"ERROR: {mensaje}")

    def alerta(self, mensaje: str, toast: bool = False, icono: str = "⚠️") -> None:
        """Muestra alerta/advertencia."""
        import streamlit as st
        _log.warning("ALERTA DSS: %s", mensaje)
        if toast:
            st.toast(f"{icono} {mensaje}", icon="⚠️")
        else:
            st.warning(f"{icono} {mensaje}")
        self._log_en_bd("PRESUPUESTO_DESVIO", f"ALERTA: {mensaje}")

    def info(self, mensaje: str, icono: str = "ℹ️") -> None:
        """Muestra mensaje informativo."""
        import streamlit as st
        st.info(f"{icono} {mensaje}")

    def presupuesto_desvio(self, categoria: str, pct_uso: float, monto_real: float, presupuestado: float) -> None:
        """Alerta específica de desvío de presupuesto."""
        import streamlit as st
        color  = "#E53935" if pct_uso >= 100 else "#F57F17"
        icono  = "🔴" if pct_uso >= 100 else "🟡"
        msj    = (
            f"**{categoria}** — {icono} {pct_uso:.0f}% del presupuesto usado "
            f"(${monto_real:,.0f} de ${presupuestado:,.0f})"
        )
        st.markdown(
            f"<div style='background:rgba(255,0,0,0.05);border-left:4px solid {color};"
            f"padding:10px 14px;border-radius:0 8px 8px 0;margin:4px 0'>{msj}</div>",
            unsafe_allow_html=True,
        )
        self._log_en_bd("PRESUPUESTO_DESVIO", f"{categoria}: {pct_uso:.0f}% uso")


def notificar_exito(mensaje: str, dbm=None, cliente_id: int = None) -> None:
    """Función convenience para éxito sin instanciar."""
    NotificadorDSS(cliente_id=cliente_id, dbm=dbm).exito(mensaje)


def notificar_error(mensaje: str, dbm=None, cliente_id: int = None) -> None:
    """Función convenience para error sin instanciar."""
    NotificadorDSS(cliente_id=cliente_id, dbm=dbm).error(mensaje)
