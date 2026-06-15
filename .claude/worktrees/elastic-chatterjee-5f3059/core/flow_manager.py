"""
core/flow_manager.py — FlowManager: estado inteligente del workflow (Sprint 1)
MQ26-DSS | Sin dependencias de Streamlit ni de UI.

Implementa el modelo de navegación orientada a tareas de Bloomberg PORT:
el sistema detecta el estado de cada paso y propone la siguiente acción,
en lugar de dejar al usuario navegar libremente entre tabs.

Los 5 pasos del flujo principal:
    1. Datos        — cobertura de precios >= 95%
    2. Riesgo       — sin alertas de concentración sin revisar
    3. Optimización — drift vs óptimo < 5% o asesor aprueba
    4. Decisión     — órdenes aprobadas o rechazadas explícitamente
    5. Reporte      — PDF generado y enviado al cliente

Uso:
    fm = FlowManager()
    ctx = {"price_coverage_pct": 98, "n_concentration_alerts": 0, ...}
    state = fm.get_step_state(1, ctx)      # StepState.COMPLETO
    msg, color = fm.siguiente_accion(ctx)  # ("Cartera en orden", "green")
    summary = fm.resumen(ctx)              # dict con estado de todos los pasos
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

# ─── Estado de paso ───────────────────────────────────────────────────────────

class StepState(Enum):
    COMPLETO  = "completo"   # criterio de aceptación cumplido
    PENDIENTE = "pendiente"  # aún no iniciado o sin información suficiente
    ALERTA    = "alerta"     # requiere atención del asesor antes de continuar
    BLOQUEADO = "bloqueado"  # prerequisito no completado

    @property
    def color(self) -> str:
        return {
            "completo":  "green",
            "pendiente": "gray",
            "alerta":    "red",
            "bloqueado": "lightgray",
        }[self.value]

    @property
    def icon(self) -> str:
        return {
            "completo":  "✅",
            "pendiente": "⏳",
            "alerta":    "🔴",
            "bloqueado": "🔒",
        }[self.value]

    @property
    def label(self) -> str:
        return {
            "completo":  "Completo",
            "pendiente": "Pendiente",
            "alerta":    "Atención requerida",
            "bloqueado": "Bloqueado",
        }[self.value]


# ─── Metadatos de paso ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StepMeta:
    number:      int
    name:        str
    description: str
    criterio:    str    # criterio de aceptación en lenguaje natural


STEPS: dict[int, StepMeta] = {
    1: StepMeta(1, "Datos",        "Ingesta y calidad de precios",
                "Cobertura de precios >= 95% y sin tickers MISSING"),
    2: StepMeta(2, "Riesgo",       "Análisis de riesgo y exposición",
                "Sin alertas de concentración crítica sin revisar"),
    3: StepMeta(3, "Optimización", "Optimización de portafolio",
                "Asesor aprueba o descarta la cartera óptima"),
    4: StepMeta(4, "Decisión",     "Órdenes de rebalanceo",
                "Órdenes aprobadas o rechazadas explícitamente"),
    5: StepMeta(5, "Reporte",      "Generación de reporte PDF",
                "PDF generado y enviado al cliente"),
}


# ─── FlowManager ─────────────────────────────────────────────────────────────

class FlowManager:
    """
    Calcula el estado de cada paso del flujo en función del contexto actual
    de la sesión. No tiene estado interno — es una función pura sobre ctx.

    Claves esperadas en ctx (todas opcionales con defaults seguros):
        price_coverage_pct      float   — % tickers con precio válido
        n_concentration_alerts  int     — alertas de concentración sin revisar
        max_drift_pct           float   — drift máximo vs cartera óptima (%)
        optimizacion_aprobada   bool    — asesor confirmó la optimización
        ordenes_pendientes      int     — órdenes sin aprobar/rechazar
        ultimo_reporte_generado bool    — PDF generado en el período actual
        paso1_completo          bool    — override manual del paso 1
    """

    # Umbrales configurables
    COBERTURA_MIN_PCT:   float = 95.0
    DRIFT_ALERTA_PCT:    float = 5.0
    CONC_MAX_POR_SECTOR: float = 0.40  # 40% máximo por sector

    def get_step_state(self, step: int, ctx: dict[str, Any]) -> StepState:
        """Estado calculado de un paso dado el contexto actual."""
        if step == 1:
            return self._estado_paso1(ctx)
        if step == 2:
            # Paso 2 requiere paso 1 completo
            if self._estado_paso1(ctx) == StepState.BLOQUEADO:
                return StepState.BLOQUEADO
            return self._estado_paso2(ctx)
        if step == 3:
            if self._estado_paso2(ctx) == StepState.BLOQUEADO:
                return StepState.BLOQUEADO
            return self._estado_paso3(ctx)
        if step == 4:
            return self._estado_paso4(ctx)
        if step == 5:
            return self._estado_paso5(ctx)
        return StepState.PENDIENTE

    def siguiente_accion(self, ctx: dict[str, Any]) -> tuple[str, str]:
        """
        Retorna (mensaje, color) para mostrar en el header de la app.
        Prioriza la alerta más urgente encontrando el primer paso con ALERTA.
        """
        mensajes = {
            1: ("Hay tickers sin precio — revisar cobertura de datos", "red"),
            2: ("Concentración de riesgo elevada — revisar exposición", "red"),
            3: ("Cartera desviada del óptimo — evaluar rebalanceo", "orange"),
            4: ("Órdenes pendientes de aprobación", "orange"),
            5: ("Reporte del período no generado", "gray"),
        }
        for step in range(1, 6):
            state = self.get_step_state(step, ctx)
            if state == StepState.ALERTA:
                return mensajes[step]
        return ("Cartera en orden — todos los pasos completados", "green")

    def resumen(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Dict con el estado completo de todos los pasos para renderizado UI."""
        out = {}
        for n, meta in STEPS.items():
            state = self.get_step_state(n, ctx)
            out[n] = {
                "name":        meta.name,
                "description": meta.description,
                "criterio":    meta.criterio,
                "state":       state.value,
                "label":       state.label,
                "color":       state.color,
                "icon":        state.icon,
            }
        siguiente, color = self.siguiente_accion(ctx)
        out["siguiente_accion"] = {"mensaje": siguiente, "color": color}
        return out

    def pasos_completados(self, ctx: dict[str, Any]) -> int:
        """Número de pasos en estado COMPLETO."""
        return sum(
            1 for n in STEPS
            if self.get_step_state(n, ctx) == StepState.COMPLETO
        )

    # ── Lógica de cada paso ───────────────────────────────────────────────────

    def _estado_paso1(self, ctx: dict[str, Any]) -> StepState:
        if ctx.get("paso1_completo"):
            return StepState.COMPLETO
        cob = float(ctx.get("price_coverage_pct", 0))
        if cob == 0:
            return StepState.PENDIENTE
        return StepState.COMPLETO if cob >= self.COBERTURA_MIN_PCT else StepState.ALERTA

    def _estado_paso2(self, ctx: dict[str, Any]) -> StepState:
        if self._estado_paso1(ctx) not in (StepState.COMPLETO,):
            return StepState.BLOQUEADO
        alertas_conc  = int(ctx.get("n_concentration_alerts", 0))
        alertas_mod23 = int(ctx.get("n_mod23_alertas", 0))   # S7: MOD-23
        revisado      = bool(ctx.get("riesgo_revisado", False))
        total_alertas = alertas_conc + alertas_mod23
        if total_alertas == 0 or revisado:
            return StepState.COMPLETO
        return StepState.ALERTA

    def _estado_paso3(self, ctx: dict[str, Any]) -> StepState:
        aprobada = bool(ctx.get("optimizacion_aprobada", False))
        if aprobada:
            return StepState.COMPLETO
        drift = float(ctx.get("max_drift_pct", 0))
        if drift == 0:
            return StepState.PENDIENTE
        return StepState.ALERTA if drift > self.DRIFT_ALERTA_PCT else StepState.PENDIENTE

    def _estado_paso4(self, ctx: dict[str, Any]) -> StepState:
        if not ctx.get("optimizacion_aprobada"):
            return StepState.BLOQUEADO
        if ctx.get("ordenes_aprobadas"):
            return StepState.COMPLETO
        ordenes = int(ctx.get("ordenes_pendientes", 0))
        if ordenes == 0:
            return StepState.PENDIENTE
        return StepState.ALERTA

    def _estado_paso5(self, ctx: dict[str, Any]) -> StepState:
        generado  = bool(ctx.get("ultimo_reporte_generado", False))
        vencim    = int(ctx.get("n_vencimientos_proximos", 0))   # S9
        if generado:
            return StepState.COMPLETO
        if vencim > 0:
            return StepState.ALERTA   # hay objetivos por vencer
        return StepState.PENDIENTE
