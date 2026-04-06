"""Tests core/diagnostico_types.py — helpers y constantes S5."""
from core.diagnostico_types import (
    PISO_DEFENSIVO,
    RENDIMIENTO_MODELO_YTD_REF,
    Semaforo,
    UNIVERSO_RENTA_FIJA_AR,
    perfil_diagnostico_valido,
    perfil_motor_salida,
    semaforo_desde_score,
    tir_ref_por_ticker,
)


class TestSemaforoDesdeScore:
    def test_verde_umbral_80(self):
        assert semaforo_desde_score(80.0) == Semaforo.VERDE
        assert semaforo_desde_score(95.0) == Semaforo.VERDE

    def test_amarillo_rango_60_79(self):
        assert semaforo_desde_score(79.9) == Semaforo.AMARILLO
        assert semaforo_desde_score(60.0) == Semaforo.AMARILLO

    def test_rojo_bajo_60(self):
        assert semaforo_desde_score(59.9) == Semaforo.ROJO
        assert semaforo_desde_score(0.0) == Semaforo.ROJO


class TestPerfilMotorSalida:
    def test_arriesgado_a_agresivo(self):
        assert perfil_motor_salida("Arriesgado") == "Agresivo"

    def test_muy_arriesgado_a_agresivo(self):
        assert perfil_motor_salida("Muy arriesgado") == "Agresivo"

    def test_conservador_sin_cambio(self):
        assert perfil_motor_salida("Conservador") == "Conservador"
        assert perfil_motor_salida("Moderado") == "Moderado"


class TestPerfilDiagnosticoValido:
    def test_perfil_conocido(self):
        assert perfil_diagnostico_valido("Muy arriesgado") == "Muy arriesgado"
        assert perfil_diagnostico_valido("Conservador") in PISO_DEFENSIVO

    def test_desconocido_fallback_moderado(self):
        assert perfil_diagnostico_valido("Raro") == "Moderado"
        assert perfil_diagnostico_valido("") == "Moderado"


class TestUniversoRentaFijaAr:
    def test_claves_on_y_soberanos(self):
        assert "TLCTO" in UNIVERSO_RENTA_FIJA_AR
        assert "GD30" in UNIVERSO_RENTA_FIJA_AR
        assert UNIVERSO_RENTA_FIJA_AR["TLCTO"]["tipo"] == "ON"

    def test_tir_ref_por_ticker(self):
        assert tir_ref_por_ticker("tlcto") == 8.0
        assert tir_ref_por_ticker("GD35") == 9.1
        assert tir_ref_por_ticker("ZZZZ") is None

    def test_rendimiento_modelo_moderado(self):
        assert abs(RENDIMIENTO_MODELO_YTD_REF["Moderado"] - 0.0869) < 1e-9
