"""
tests/test_motor_salida.py — Tests del motor de salida (Sprint 11)
Cubre: evaluar_salida, kelly_sizing, estimar_prob_exito.
Sin yfinance — funciones 100% puras.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")

FECHA_COMPRA_BASE = date(2023, 1, 1)


# ─── kelly_sizing ─────────────────────────────────────────────────

class TestKellySizing:
    def test_importa_sin_error(self):
        from services.motor_salida import kelly_sizing
        assert callable(kelly_sizing)

    def test_retorna_claves_requeridas(self):
        from services.motor_salida import kelly_sizing
        r = kelly_sizing(0.6, 35.0, 15.0, 1_000_000.0)
        for k in ("kelly_completo_pct", "kelly_fraccionado_pct",
                  "kelly_aplicado_pct", "capital_sugerido_ars",
                  "prob_exito", "ratio_ganancia_perdida", "interpretacion"):
            assert k in r

    def test_kelly_aplicado_nunca_negativo(self):
        from services.motor_salida import kelly_sizing
        # Apuesta desfavorable: kelly_completo < 0 → kelly_aplicado = 0
        r = kelly_sizing(0.20, 5.0, 50.0, 1_000_000.0)
        assert r["kelly_aplicado_pct"] >= 0.0

    def test_kelly_aplicado_no_supera_max_posicion(self):
        from services.motor_salida import kelly_sizing
        r = kelly_sizing(0.99, 100.0, 1.0, 1_000_000.0, max_posicion_pct=20.0)
        assert r["kelly_aplicado_pct"] <= 20.0

    def test_capital_sugerido_coherente_con_kelly_aplicado(self):
        from services.motor_salida import kelly_sizing
        capital = 2_000_000.0
        r = kelly_sizing(0.60, 35.0, 15.0, capital)
        esperado = capital * (r["kelly_aplicado_pct"] / 100)
        # Tolerancia relativa 0.1% — capital_sugerido_ars usa valor sin redondear
        # mientras kelly_aplicado_pct está redondeado a 2 decimales
        assert abs(r["capital_sugerido_ars"] - esperado) < capital * 0.001

    def test_prob_exito_en_rango_correcto(self):
        from services.motor_salida import kelly_sizing
        r = kelly_sizing(0.60, 35.0, 15.0, 1_000_000.0)
        assert 0.01 <= r["prob_exito"] <= 0.99

    def test_interpretacion_favorable_cuando_kelly_positivo(self):
        from services.motor_salida import kelly_sizing
        r = kelly_sizing(0.70, 40.0, 15.0, 1_000_000.0)
        if r["kelly_completo_pct"] > 0:
            assert ("favorable" in r["interpretacion"].lower() or
                    "asignar" in r["interpretacion"].lower())

    def test_interpretacion_desfavorable_cuando_kelly_negativo(self):
        from services.motor_salida import kelly_sizing
        r = kelly_sizing(0.10, 5.0, 50.0, 1_000_000.0)
        if r["kelly_completo_pct"] < 0:
            assert ("desfavorable" in r["interpretacion"].lower() or
                    "no operar" in r["interpretacion"].lower())

    def test_fraccion_kelly_reduce_capital(self):
        from services.motor_salida import kelly_sizing
        r_full   = kelly_sizing(0.60, 35.0, 15.0, 1_000_000.0, fraccion_kelly=1.0)
        r_cuarto = kelly_sizing(0.60, 35.0, 15.0, 1_000_000.0, fraccion_kelly=0.25)
        assert r_cuarto["kelly_aplicado_pct"] <= r_full["kelly_aplicado_pct"]

    def test_stop_cero_no_lanza(self):
        from services.motor_salida import kelly_sizing
        # stop_pct=0 usa b=1.0 por defecto — no debe lanzar ZeroDivisionError
        r = kelly_sizing(0.60, 35.0, 0.0, 1_000_000.0)
        assert "kelly_aplicado_pct" in r


# ─── estimar_prob_exito ───────────────────────────────────────────

class TestEstimarProbExito:
    def test_importa_sin_error(self):
        from services.motor_salida import estimar_prob_exito
        assert callable(estimar_prob_exito)

    def test_retorna_float_en_rango(self):
        from services.motor_salida import estimar_prob_exito
        for score in [0, 25, 50, 75, 100]:
            for rsi in [10, 30, 45, 60, 80]:
                p = estimar_prob_exito(score, rsi)
                assert 0.20 <= p <= 0.80, f"Fuera de rango: score={score}, rsi={rsi}, p={p}"

    def test_score_alto_da_prob_mayor(self):
        from services.motor_salida import estimar_prob_exito
        p_alto = estimar_prob_exito(90, 45)
        p_bajo = estimar_prob_exito(10, 45)
        assert p_alto > p_bajo

    def test_rsi_sobrevendido_aumenta_prob(self):
        from services.motor_salida import estimar_prob_exito
        p_sv  = estimar_prob_exito(50, 25)   # sobrevendido: RSI < 30
        p_neu = estimar_prob_exito(50, 50)   # neutro
        assert p_sv >= p_neu

    def test_rsi_sobrecomprado_reduce_prob(self):
        from services.motor_salida import estimar_prob_exito
        p_sc  = estimar_prob_exito(50, 80)   # sobrecomprado: RSI > 75
        p_neu = estimar_prob_exito(50, 50)   # neutro
        assert p_sc <= p_neu

    def test_zona_compra_ideal_aumenta_prob(self):
        from services.motor_salida import estimar_prob_exito
        p_ideal  = estimar_prob_exito(50, 45)   # 35 <= RSI <= 55
        p_neutro = estimar_prob_exito(50, 65)   # fuera de zona ideal
        assert p_ideal >= p_neutro

    def test_clampeado_a_maximo_080(self):
        from services.motor_salida import estimar_prob_exito
        p = estimar_prob_exito(100, 25)   # máximo posible
        assert p <= 0.80

    def test_clampeado_a_minimo_020(self):
        from services.motor_salida import estimar_prob_exito
        p = estimar_prob_exito(0, 85)    # mínimo posible
        assert p >= 0.20

    def test_orden_rsi_sobrevendido_ideal_sobrecomprado(self):
        from services.motor_salida import estimar_prob_exito

        p_sobrevendido = estimar_prob_exito(50, 25)
        p_ideal = estimar_prob_exito(50, 45)
        p_sobrecomprado = estimar_prob_exito(50, 80)
        assert p_sobrevendido >= p_ideal >= p_sobrecomprado


# ─── evaluar_salida ───────────────────────────────────────────────

class TestEvaluarSalida:
    def test_importa_sin_error(self):
        from services.motor_salida import evaluar_salida
        assert callable(evaluar_salida)

    def test_ppc_cero_retorna_neutro(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 0.0, 150.0, 50.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        assert r["progreso_pct"] == 0.0
        assert r["precio_target"] == 0.0
        assert "senal" in r
        assert "quality_flags" in r
        assert "ppc_invalido" in r["quality_flags"]

    def test_retorna_claves_requeridas(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 100.0, 120.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        for k in ("senal", "prioridad", "progreso_pct", "precio_target",
                  "precio_stop", "trailing_stop", "disparadores_activos",
                  "target_pct", "stop_pct"):
            assert k in r, f"Clave faltante: {k}"

    def test_progreso_positivo_cuando_precio_sube(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("MSFT", 100.0, 130.0, 50.0, 6.0, 6.0, FECHA_COMPRA_BASE)
        assert r["progreso_pct"] > 0

    def test_progreso_negativo_cuando_precio_baja(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("KO", 100.0, 80.0, 60.0, 5.0, 5.0, FECHA_COMPRA_BASE)
        assert r["progreso_pct"] < 0

    def test_progreso_pct_en_rango_amplio(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 100.0, 50.0, 70.0, 3.0, 4.0, FECHA_COMPRA_BASE)
        assert -100.0 <= r["progreso_pct"] <= 200.0

    def test_precio_target_mayor_que_ppc(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 100.0, 110.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        assert r["precio_target"] > 100.0

    def test_precio_stop_menor_que_ppc(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 100.0, 110.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        assert r["precio_stop"] < 100.0

    def test_override_target_se_aplica(self):
        from services.motor_salida import evaluar_salida
        r_std = evaluar_salida("AAPL", 100.0, 110.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        r_ov  = evaluar_salida("AAPL", 100.0, 110.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE,
                               override_target_pct=50.0)
        assert r_ov["precio_target"] != r_std["precio_target"]

    def test_senal_es_string(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("COST", 50.0, 60.0, 42.0, 8.0, 7.5, FECHA_COMPRA_BASE)
        assert isinstance(r["senal"], str)

    def test_disparadores_activos_es_lista(self):
        from services.motor_salida import evaluar_salida
        r = evaluar_salida("AAPL", 100.0, 200.0, 50.0, 9.0, 8.0, FECHA_COMPRA_BASE)
        assert isinstance(r["disparadores_activos"], list)

    def test_objetivo_alcanzado_activa_disparador(self):
        from services.motor_salida import evaluar_salida
        # precio > target activa al menos un disparador
        r = evaluar_salida("AAPL", 100.0, 200.0, 50.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        assert len(r["disparadores_activos"]) >= 1

    def test_perfil_agresivo_distinto_a_conservador(self):
        from services.motor_salida import evaluar_salida
        r_ag = evaluar_salida("AAPL", 100.0, 120.0, 45.0, 7.0, 7.0,
                              FECHA_COMPRA_BASE, perfil="Agresivo")
        r_co = evaluar_salida("AAPL", 100.0, 120.0, 45.0, 7.0, 7.0,
                              FECHA_COMPRA_BASE, perfil="Conservador")
        # Target distinto según perfil
        assert r_ag["target_pct"] != r_co["target_pct"]

    def test_stop_loss_activa_disparador(self):
        from services.motor_salida import evaluar_salida

        r = evaluar_salida("AAPL", 100.0, 60.0, 80.0, 2.0, 3.0, FECHA_COMPRA_BASE)
        assert len(r["disparadores_activos"]) >= 1

    def test_override_stop_modifica_precio_stop(self):
        from services.motor_salida import evaluar_salida

        r_std = evaluar_salida("AAPL", 100.0, 110.0, 45.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        r_ov = evaluar_salida(
            "AAPL",
            100.0,
            110.0,
            45.0,
            7.0,
            7.0,
            FECHA_COMPRA_BASE,
            override_stop_pct=-25.0,
        )
        assert r_std["precio_stop"] != r_ov["precio_stop"]

    def test_rsi_negativo_no_lanza(self):
        from services.motor_salida import evaluar_salida

        r = evaluar_salida("AAPL", 100.0, 110.0, -10.0, 7.0, 7.0, FECHA_COMPRA_BASE)
        assert "senal" in r
