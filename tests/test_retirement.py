"""Tests para core/retirement_goal.py — Sprint 2 FIX-1"""
from __future__ import annotations

import numpy as np
import pytest
from core.retirement_goal import (
    _daily_to_monthly,
    calcular_aporte_necesario,
    simulate_retirement,
)


def test_aporte_cero_si_capital_ya_alcanza():
    aporte = calcular_aporte_necesario(200_000, 100_000, 20, 0.07)
    assert aporte == pytest.approx(0.0)


def test_aporte_positivo_con_objetivo_grande():
    aporte = calcular_aporte_necesario(10_000, 500_000, 20, 0.08)
    assert aporte > 0


def test_daily_to_monthly_agrupa_21_dias():
    r_diarios = np.full(42, 0.001)          # 42 días → 2 meses
    meses = _daily_to_monthly(r_diarios)
    assert len(meses) == 2
    assert meses[0] == pytest.approx((1.001 ** 21) - 1, rel=1e-5)


def test_daily_to_monthly_array_vacio_retorna_fallback():
    meses = _daily_to_monthly(np.array([]))
    assert len(meses) >= 1


def test_simulate_p50_positivo_con_retornos_razonables():
    """
    20 años acumulando USD 1000/mes + retiro USD 500/mes por 10 años.
    Con retornos ~8% anual el capital acumulado (~USD 590k) sostiene
    holgadamente el retiro. p50 debe ser positivo.
    """
    rng = np.random.default_rng(42)
    r_diarios = rng.normal(0.0004, 0.01, 252 * 20)
    result = simulate_retirement(
        aporte_mensual=1_000,
        n_meses_acum=240,      # 20 años acumulando
        retiro_mensual=500,
        n_meses_desacum=120,   # 10 años retirando
        retornos_diarios=r_diarios,
        n_sim=1000,
    )
    assert result["p50"] > 0, f"p50 debe ser positivo, got {result['p50']:.0f}"
    assert 0 <= result["prob_no_agotar"] <= 1
    assert result["p10"] <= result["p50"] <= result["p90"]


def test_simulate_prob_no_agotar_alta_con_buen_plan():
    rng = np.random.default_rng(42)
    r_diarios = rng.normal(0.0004, 0.01, 252 * 25)
    result = simulate_retirement(
        aporte_mensual=2_000,
        n_meses_acum=300,      # 25 años
        retiro_mensual=1_000,
        n_meses_desacum=120,
        retornos_diarios=r_diarios,
        n_sim=500,
    )
    assert result["prob_no_agotar"] > 0.7, "Con plan conservador, prob de no agotar debe ser alta"


def test_simulate_fallback_sin_datos():
    result = simulate_retirement(
        aporte_mensual=100, n_meses_acum=12,
        retiro_mensual=50,  n_meses_desacum=12,
        retornos_diarios=np.array([]),
        n_sim=100,
    )
    assert "p50" in result
    assert "prob_no_agotar" in result


def test_simulate_retiro_insostenible_reduce_prob():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0001, 0.005, 500)
    result = simulate_retirement(
        aporte_mensual=100,
        n_meses_acum=60,
        retiro_mensual=10_000,   # retiro muy alto vs lo acumulado
        n_meses_desacum=60,
        retornos_diarios=r,
        n_sim=200,
    )
    assert result["prob_no_agotar"] < 0.5
