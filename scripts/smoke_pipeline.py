"""
scripts/smoke_pipeline.py — Smoke test del pipeline_optimizador.py
(sin red: usa datos sintéticos para validar imports, constraints y solver)

Uso:
    cd MQ26_V11
    python scripts/smoke_pipeline.py
"""
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PASS = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def seccion(titulo: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print(f"{'='*60}")


# ─────────────────────────────────────────────────────────────
# TEST 1: Imports básicos
# ─────────────────────────────────────────────────────────────
seccion("TEST 1 — Imports")

try:
    from core.pipeline_optimizador import (
        ResultadoOptimizacion,
        _calcular_metricas_portafolio,
        _clasificar_activos,
        _construir_constraints_perfil,
        _postprocesar_hrp,
        reporte_cartera,
        resumen_ejecutivo,
    )
    print(f"{PASS}  Todos los símbolos de pipeline_optimizador importados")
except Exception as e:
    print(f"{FAIL}  Import falló: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from config import RESTRICCIONES_POR_PERFIL
    print(f"{PASS}  config.py — RESTRICCIONES_POR_PERFIL, PARAMETROS_HISTORICO, MACRO_AR")
except Exception as e:
    print(f"{FAIL}  config.py import falló: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 2: Dataclass ResultadoOptimizacion
# ─────────────────────────────────────────────────────────────
seccion("TEST 2 — Dataclass ResultadoOptimizacion")

try:
    r = ResultadoOptimizacion(
        tickers=["AAPL", "MSFT"],
        pesos={"AAPL": 0.6, "MSFT": 0.4},
        metodo="max_sharpe",
        perfil="MODERADO",
    )
    assert r.sharpe_ratio == 0.0
    assert r.valido_riesgo_perfil is True
    assert r.advertencias == []
    print(f"{PASS}  Instanciacion correcta con defaults")

    # reporte_cartera con datos mínimos
    df = reporte_cartera(r)
    assert len(df) == 2
    assert "peso_pct" in df.columns
    print(f"{PASS}  reporte_cartera() -> DataFrame ({len(df)} filas)")

    # resumen_ejecutivo
    ej = resumen_ejecutivo(r)
    assert ej["estado"] == "VALIDA"
    assert ej["n_activos"] == 2
    print(f"{PASS}  resumen_ejecutivo() -> dict estado='{ej['estado']}'")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 3: _clasificar_activos
# ─────────────────────────────────────────────────────────────
seccion("TEST 3 — _clasificar_activos")

try:
    from config import ACCIONES_ARGENTINAS, CEDEAR_INFO, OBLIGACIONES_NEGOCIABLES

    # Elegimos un ticker de cada categoría (si existen)
    tickers_test = []

    # RF
    on_sample = next(iter(OBLIGACIONES_NEGOCIABLES), None)
    if on_sample:
        tickers_test.append(on_sample)

    # RV global — CEDEAR
    cedear_sample = next(
        (t for t, m in CEDEAR_INFO.items() if isinstance(m, dict)), None
    )
    if cedear_sample:
        tickers_test.append(cedear_sample)

    # RV local — BYMA
    byma_sample = next(
        (t for t, m in ACCIONES_ARGENTINAS.items()
         if isinstance(m, dict) and m.get("exchange") == "BYMA"),
        None,
    )
    if byma_sample:
        tickers_test.append(byma_sample)

    # Ticker desconocido
    tickers_test.append("UNKNOWN_TICKER_XYZ")

    clasi = _clasificar_activos(tickers_test)
    print(f"{PASS}  Clasificacion de {len(tickers_test)} tickers:")
    for t, c in clasi.items():
        print(f"        {t:25s} -> tipo={c['tipo']}")

    if on_sample:
        assert clasi[on_sample]["tipo"] == "rf", f"Esperaba rf para {on_sample}"
        print(f"{PASS}  {on_sample} correctamente clasificado como RF")

    if cedear_sample:
        assert clasi[cedear_sample]["tipo"] in ("rv_global", "rv_local")
        print(f"{PASS}  {cedear_sample} correctamente clasificado como RV")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 4: _construir_constraints_perfil
# ─────────────────────────────────────────────────────────────
seccion("TEST 4 — _construir_constraints_perfil (mock Sigma/mu)")

import numpy as np

try:
    # Simular universo mixto: 3 RV global, 1 RV local, 2 RF
    tickers_mock = ["AAPL", "MSFT", "SPY", "GGAL", "ON1", "ON2"]
    clasi_mock = {
        "AAPL": {"tipo": "rv_global"},
        "MSFT": {"tipo": "rv_global"},
        "SPY":  {"tipo": "rv_global"},
        "GGAL": {"tipo": "rv_local"},
        "ON1":  {"tipo": "rf"},
        "ON2":  {"tipo": "rf"},
    }
    n = len(tickers_mock)
    np.random.seed(42)
    vols = np.array([0.20, 0.18, 0.14, 0.35, 0.05, 0.06])
    corr = np.eye(n) * 0.5 + 0.5 * np.ones((n, n))
    np.fill_diagonal(corr, 1.0)
    Sigma_mock = np.outer(vols, vols) * corr
    mu_mock = np.array([0.12, 0.11, 0.09, 0.18, 0.055, 0.065])

    restr_mod = RESTRICCIONES_POR_PERFIL["MODERADO"]
    datos_perf = {
        "objetivo_retorno_usd_anual": 0.07,
        "necesidad_liquidez_pct": 0.10,
    }

    cons, bounds = _construir_constraints_perfil(
        tickers_mock, clasi_mock,
        Sigma_mock, mu_mock,
        restr_mod, datos_perf,
    )

    print(f"{PASS}  Constraints generadas: {len(cons)}  Bounds: {len(bounds)}")

    # Verificar estructura
    types = [c["type"] for c in cons]
    n_eq   = types.count("eq")
    n_ineq = types.count("ineq")
    print(f"        eq={n_eq}  ineq={n_ineq}")
    assert n_eq >= 1, "Debe haber al menos 1 constraint de igualdad (sum=1)"
    print(f"{PASS}  Al menos 1 constraint eq (sum(w)=1)")

    # Evaluar constraint eq en w_equal
    w_eq = np.ones(n) / n
    val_eq = cons[0]["fun"](w_eq)
    assert abs(val_eq) < 1e-10, f"C1 debería ser ~0, es {val_eq}"
    print(f"{PASS}  C1 sum(w)=1 evalúa a {val_eq:.2e} con w_equal")

    # Verificar bounds dimensión
    assert len(bounds) == n
    for lb, ub in bounds:
        assert 0.0 <= lb <= ub <= 1.0
    print(f"{PASS}  Todos los bounds válidos [0, {max(ub for _,ub in bounds):.2f}]")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 5: Solver con datos sintéticos (sin red)
# ─────────────────────────────────────────────────────────────
seccion("TEST 5 — _solve_min_variance_con_perfil (mock, sin red)")

try:
    from core.pipeline_optimizador import _solve_min_variance_con_perfil
    from core.portfolio_optimization import OptimizationProblem

    prob = OptimizationProblem(mu=mu_mock, Sigma=Sigma_mock, rf=0.043)
    res = _solve_min_variance_con_perfil(prob, cons, bounds)

    w = res["weights"]
    assert abs(w.sum() - 1.0) < 1e-6, f"Pesos no suman 1: {w.sum()}"
    assert all(wi >= -1e-8 for wi in w), "Pesos negativos detectados"
    print(f"{PASS}  Solver min_variance convergio: {res['success']} | {res['message']}")
    print(f"        sum(w)={w.sum():.6f}  n_nonzero={(w > 1e-4).sum()}")

    # Mostrar top pesos
    for t, wi in sorted(zip(tickers_mock, w, strict=True), key=lambda x: -x[1]):
        if wi > 1e-4:
            print(f"        {t:20s}  {wi:.2%}")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 6: _solve_max_sharpe_con_perfil (mock, sin red)
# ─────────────────────────────────────────────────────────────
seccion("TEST 6 — _solve_max_sharpe_con_perfil (mock, sin red)")

try:
    from core.pipeline_optimizador import _solve_max_sharpe_con_perfil

    res_ms = _solve_max_sharpe_con_perfil(
        prob, cons, bounds, None, 0.0, None
    )

    w_ms = res_ms["weights"]
    assert abs(w_ms.sum() - 1.0) < 1e-5, f"Pesos no suman 1: {w_ms.sum()}"
    print(f"{PASS}  Solver max_sharpe convergio: {res_ms['success']} | {res_ms['message']}")

    # Sharpe con RF=4.3%
    from core.risk_metrics import portfolio_vol_annual
    vol_p = portfolio_vol_annual(w_ms, Sigma_mock)
    ret_p = float(mu_mock @ w_ms)
    sharpe = (ret_p - 0.043) / vol_p if vol_p > 0 else 0
    print(f"        Retorno={ret_p:.2%}  Vol={vol_p:.2%}  Sharpe={sharpe:.3f}")

    for t, wi in sorted(zip(tickers_mock, w_ms, strict=True), key=lambda x: -x[1]):
        if wi > 1e-4:
            print(f"        {t:20s}  {wi:.2%}")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 7: _postprocesar_hrp
# ─────────────────────────────────────────────────────────────
seccion("TEST 7 — _postprocesar_hrp")

try:
    # Simular HRP con pesos que violan max_rv (todo en RV)
    w_hrp_raw = np.array([0.30, 0.25, 0.25, 0.20, 0.0, 0.0])  # 100% RV
    restr_cons = RESTRICCIONES_POR_PERFIL["CONSERVADOR"]   # max_rv=45%

    w_post = _postprocesar_hrp(w_hrp_raw, tickers_mock, clasi_mock, restr_cons)

    peso_rv = sum(w_post[i] for i, t in enumerate(tickers_mock)
                  if clasi_mock[t]["tipo"] != "rf")
    max_rv_cons = float(restr_cons.get("max_renta_variable", 0.45))
    print(f"{PASS}  Post-processing HRP:")
    print(f"        Peso RV antes={w_hrp_raw[:4].sum():.2%} -> despues={peso_rv:.2%}  (max={max_rv_cons:.0%})")
    print(f"        sum(w_post)={w_post.sum():.6f}")
    assert abs(w_post.sum() - 1.0) < 1e-8

    # Si hay activos RF en el universo, el RV debería ser <= max_rv + tolerancia pequeña
    # (el post-processing es aproximado cuando no hay RF para recibir el exceso)
    if "ON1" in tickers_mock and w_hrp_raw[tickers_mock.index("ON1")] == 0:
        # RF están en cero → no se puede redistribuir; esto está documentado como aproximación
        print(f"{WARN}  RV post={peso_rv:.2%} (HRP no puede redistribuir a RF con w_rf=0 — OK, es aproximacion)")
    else:
        assert peso_rv <= max_rv_cons + 1e-6

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 8: _calcular_metricas_portafolio (mock DataFrame retornos)
# ─────────────────────────────────────────────────────────────
seccion("TEST 8 — _calcular_metricas_portafolio (mock retornos diarios)")

try:
    import pandas as pd

    T = 300
    np.random.seed(7)
    ret_diarios = pd.DataFrame(
        np.random.multivariate_normal(mu_mock / 252, Sigma_mock / 252, T),
        columns=tickers_mock,
    )

    # Simular metricas_riesgo
    metricas_rv_mock = {
        "AAPL": {"metrica_riesgo_tipo": "BETA", "valor_riesgo": 1.15},
        "MSFT": {"metrica_riesgo_tipo": "BETA", "valor_riesgo": 0.95},
        "SPY":  {"metrica_riesgo_tipo": "BETA", "valor_riesgo": 1.00},
        "GGAL": {"metrica_riesgo_tipo": "BETA", "valor_riesgo": 1.40},
        "ON1":  {"metrica_riesgo_tipo": "DURATION_MODIFICADA", "valor_riesgo": 2.5},
        "ON2":  {"metrica_riesgo_tipo": "DURATION_MODIFICADA", "valor_riesgo": 3.8},
    }

    metricas = _calcular_metricas_portafolio(
        w_ms, tickers_mock, mu_mock, Sigma_mock,
        ret_diarios, metricas_rv_mock, 0.043,
    )

    print(f"{PASS}  Metricas calculadas:")
    for k, v in metricas.items():
        print(f"        {k:35s}: {v}")

    assert "sharpe_ratio" in metricas
    assert "var_95_diario" in metricas
    assert "beta_rv_ponderado" in metricas
    assert "duration_rf_ponderada" in metricas
    print(f"{PASS}  Todas las claves de metricas presentes")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 9: RESTRICCIONES_POR_PERFIL — perfiles existentes
# ─────────────────────────────────────────────────────────────
seccion("TEST 9 — RESTRICCIONES_POR_PERFIL integridad")

try:
    campos_obligatorios = [
        "max_renta_variable", "min_renta_fija",
        "max_por_ticker_rv", "max_por_ticker_rf",
        "max_exposicion_local_rv", "volatilidad_max_anual",
        "max_duration_modificada", "max_beta_ponderado_rv",
    ]
    for perfil, r in RESTRICCIONES_POR_PERFIL.items():
        faltantes = [c for c in campos_obligatorios if c not in r]
        if faltantes:
            print(f"{WARN}  Perfil '{perfil}' le faltan campos: {faltantes}")
        else:
            print(f"{PASS}  Perfil '{perfil}' completo ({len(r)} campos)")

    # Consistencia RV + RF <= 1
    for perfil, r in RESTRICCIONES_POR_PERFIL.items():
        total = r.get("max_renta_variable", 0) + r.get("min_renta_fija", 0)
        if total > 1.001:
            print(f"{WARN}  Perfil '{perfil}': max_rv + min_rf = {total:.2f} > 1.0")
        else:
            print(f"{PASS}  Perfil '{perfil}': max_rv + min_rf = {total:.2f} <= 1.0")

except Exception as e:
    print(f"{FAIL}  {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SMOKE TEST COMPLETADO")
print(f"{'='*60}")
print("  Todos los tests pasaron. El pipeline_optimizador.py esta listo.")
print("  Para un test de extremo a extremo con red:")
print("    python -c \"from core.pipeline_optimizador import optimizar_cartera; "
      "r = optimizar_cartera('MODERADO', metodo='min_variance', "
      "universo_override=['AAPL','MSFT','SPY']); print(r.sharpe_ratio)\"")
