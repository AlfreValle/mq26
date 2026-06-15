"""
tests/test_flow_manager.py — Tests del FlowManager (Sprint 1)
Cubre: StepState, lógica de cada paso, siguiente_accion, resumen.
"""
from __future__ import annotations

import pytest

from core.flow_manager import STEPS, FlowManager, StepState


@pytest.fixture
def fm() -> FlowManager:
    return FlowManager()


# ─── Paso 1: Datos ────────────────────────────────────────────────────────────

class TestPaso1Datos:
    def test_pendiente_sin_contexto(self, fm):
        assert fm.get_step_state(1, {}) == StepState.PENDIENTE

    def test_completo_cuando_cobertura_suficiente(self, fm):
        assert fm.get_step_state(1, {"price_coverage_pct": 100.0}) == StepState.COMPLETO
        assert fm.get_step_state(1, {"price_coverage_pct": 95.0}) == StepState.COMPLETO

    def test_alerta_cuando_cobertura_insuficiente(self, fm):
        assert fm.get_step_state(1, {"price_coverage_pct": 80.0}) == StepState.ALERTA
        assert fm.get_step_state(1, {"price_coverage_pct": 0.1}) == StepState.ALERTA

    def test_override_manual_fuerza_completo(self, fm):
        assert fm.get_step_state(1, {"paso1_completo": True, "price_coverage_pct": 0}) == StepState.COMPLETO

    def test_umbral_exacto_es_completo(self, fm):
        assert fm.get_step_state(1, {"price_coverage_pct": 95.0}) == StepState.COMPLETO


# ─── Paso 2: Riesgo ───────────────────────────────────────────────────────────

class TestPaso2Riesgo:
    def _ctx_p1_ok(self, **kw):
        return {"price_coverage_pct": 100.0, **kw}

    def test_completo_sin_alertas(self, fm):
        ctx = self._ctx_p1_ok(n_concentration_alerts=0)
        assert fm.get_step_state(2, ctx) == StepState.COMPLETO

    def test_alerta_con_concentracion(self, fm):
        ctx = self._ctx_p1_ok(n_concentration_alerts=2)
        assert fm.get_step_state(2, ctx) == StepState.ALERTA

    def test_completo_cuando_revisado(self, fm):
        ctx = self._ctx_p1_ok(n_concentration_alerts=3, riesgo_revisado=True)
        assert fm.get_step_state(2, ctx) == StepState.COMPLETO

    def test_bloqueado_si_paso1_no_completo(self, fm):
        ctx = {"price_coverage_pct": 50.0, "n_concentration_alerts": 0}
        assert fm.get_step_state(2, ctx) == StepState.BLOQUEADO


# ─── Paso 3: Optimización ─────────────────────────────────────────────────────

class TestPaso3Optimizacion:
    def _ctx_p2_ok(self, **kw):
        return {"price_coverage_pct": 100.0, "n_concentration_alerts": 0, **kw}

    def test_completo_cuando_aprobada(self, fm):
        ctx = self._ctx_p2_ok(optimizacion_aprobada=True)
        assert fm.get_step_state(3, ctx) == StepState.COMPLETO

    def test_alerta_con_drift_alto(self, fm):
        ctx = self._ctx_p2_ok(max_drift_pct=10.0)
        assert fm.get_step_state(3, ctx) == StepState.ALERTA

    def test_pendiente_sin_drift(self, fm):
        ctx = self._ctx_p2_ok(max_drift_pct=0.0)
        assert fm.get_step_state(3, ctx) == StepState.PENDIENTE

    def test_pendiente_con_drift_bajo(self, fm):
        ctx = self._ctx_p2_ok(max_drift_pct=3.0)
        assert fm.get_step_state(3, ctx) == StepState.PENDIENTE


# ─── Paso 4: Decisión ─────────────────────────────────────────────────────────

class TestPaso4Decision:
    def test_bloqueado_sin_optimizacion(self, fm):
        assert fm.get_step_state(4, {}) == StepState.BLOQUEADO

    def test_alerta_con_ordenes_pendientes(self, fm):
        ctx = {"optimizacion_aprobada": True, "ordenes_pendientes": 3}
        assert fm.get_step_state(4, ctx) == StepState.ALERTA

    def test_pendiente_sin_ordenes(self, fm):
        ctx = {"optimizacion_aprobada": True, "ordenes_pendientes": 0}
        assert fm.get_step_state(4, ctx) == StepState.PENDIENTE


# ─── Paso 5: Reporte ──────────────────────────────────────────────────────────

class TestPaso5Reporte:
    def test_completo_con_reporte(self, fm):
        assert fm.get_step_state(5, {"ultimo_reporte_generado": True}) == StepState.COMPLETO

    def test_pendiente_sin_reporte(self, fm):
        assert fm.get_step_state(5, {"ultimo_reporte_generado": False}) == StepState.PENDIENTE

    def test_pendiente_sin_contexto(self, fm):
        assert fm.get_step_state(5, {}) == StepState.PENDIENTE


# ─── siguiente_accion ─────────────────────────────────────────────────────────

class TestSiguienteAccion:
    def test_verde_cuando_todo_ok(self, fm):
        ctx = {
            "price_coverage_pct": 100.0, "n_concentration_alerts": 0,
            "optimizacion_aprobada": True, "ordenes_pendientes": 0,
            "ultimo_reporte_generado": True,
        }
        msg, color = fm.siguiente_accion(ctx)
        assert color == "green"
        assert "orden" in msg.lower() or "completo" in msg.lower()

    def test_rojo_cuando_cobertura_baja(self, fm):
        _, color = fm.siguiente_accion({"price_coverage_pct": 50.0})
        assert color == "red"

    def test_rojo_cuando_concentracion_alta(self, fm):
        ctx = {"price_coverage_pct": 100.0, "n_concentration_alerts": 2}
        _, color = fm.siguiente_accion(ctx)
        assert color == "red"

    def test_prioridad_paso1_sobre_paso2(self, fm):
        """Cobertura baja debe reportarse antes que concentración alta."""
        ctx = {"price_coverage_pct": 50.0, "n_concentration_alerts": 5}
        msg, _ = fm.siguiente_accion(ctx)
        assert "precio" in msg.lower() or "ticker" in msg.lower() or "datos" in msg.lower()


# ─── resumen ──────────────────────────────────────────────────────────────────

class TestResumen:
    def test_contiene_todos_los_pasos(self, fm):
        r = fm.resumen({})
        for n in range(1, 6):
            assert n in r

    def test_contiene_siguiente_accion(self, fm):
        r = fm.resumen({})
        assert "siguiente_accion" in r
        assert "mensaje" in r["siguiente_accion"]
        assert "color" in r["siguiente_accion"]

    def test_campos_por_paso(self, fm):
        r = fm.resumen({"price_coverage_pct": 100.0})
        paso1 = r[1]
        for key in ("name", "description", "criterio", "state", "label", "color", "icon"):
            assert key in paso1


# ─── pasos_completados ────────────────────────────────────────────────────────

class TestPasosCompletados:
    def test_cero_sin_contexto(self, fm):
        assert fm.pasos_completados({}) == 0

    def test_pasos_con_cobertura_completa(self, fm):
        # Con 100% cobertura y sin alertas (default 0): paso 1 y 2 son COMPLETO
        assert fm.pasos_completados({"price_coverage_pct": 100.0}) == 2

    def test_cinco_contexto_completo(self, fm):
        ctx = {
            "price_coverage_pct": 100.0,
            "n_concentration_alerts": 0,
            "optimizacion_aprobada": True,
            "ordenes_aprobadas": True,
            "ordenes_pendientes": 0,
            "ultimo_reporte_generado": True,
        }
        assert fm.pasos_completados(ctx) == 5


# ─── StepState propiedades ────────────────────────────────────────────────────

class TestStepState:
    def test_colores_definidos(self):
        for state in StepState:
            assert isinstance(state.color, str)

    def test_icons_definidos(self):
        for state in StepState:
            assert isinstance(state.icon, str)

    def test_labels_definidos(self):
        for state in StepState:
            assert isinstance(state.label, str)


# ─── STEPS metadata ───────────────────────────────────────────────────────────

class TestStepsMeta:
    def test_cinco_pasos_definidos(self):
        assert len(STEPS) == 5

    def test_numeracion_correcta(self):
        assert set(STEPS.keys()) == {1, 2, 3, 4, 5}

    def test_campos_presentes(self):
        for meta in STEPS.values():
            assert meta.name
            assert meta.description
            assert meta.criterio
