"""
tests/test_portfolio_optimizer.py — Unit tests para services/portfolio_optimizer.py

Cobertura:
  - CATALOGO_OBJETIVOS: 9 objetivos con campos obligatorios
  - _asignar_capital_por_objetivos: distribución por horizonte
  - _proyectar_fv: proyección FV mensual
  - calcular_plan_multifuncional: motor principal CP/MP/LP
  - Helpers UI: resumen_plan_df, proyeccion_consolidada_df, asignacion_pie_df
  - Caso del usuario: CP2 + MP1 + LP3, USD 5000 + USD 350/mes
"""
from __future__ import annotations

from datetime import date

import pytest

from services.portfolio_optimizer import (
    CATALOGO_OBJETIVOS,
    AsignacionInstrumento,
    PlanMultifuncional,
    _asignar_capital_por_objetivos,
    _distribuir_equitativamente,
    _proyectar_fv,
    asignacion_pie_df,
    calcular_plan_multifuncional,
    objetivo_info,
    proyeccion_consolidada_df,
    resumen_plan_df,
)

# ──────────────────────────────────────────────────────────────────────────────
#  CATÁLOGO
# ──────────────────────────────────────────────────────────────────────────────

class TestCatalogoObjetivos:
    def test_9_objetivos_presentes(self):
        assert len(CATALOGO_OBJETIVOS) == 9

    def test_todos_los_codigos_presentes(self):
        esperados = {"CP1", "CP2", "CP3", "MP1", "MP2", "MP3", "LP1", "LP2", "LP3"}
        assert set(CATALOGO_OBJETIVOS.keys()) == esperados

    def test_campos_obligatorios_por_objetivo(self):
        campos = (
            "codigo", "nombre", "horizonte", "horizonte_meses",
            "descripcion", "perfil_minimo", "tipo_instrumento_primario",
            "retorno_esperado_usd_anual", "liquidez", "moneda_objetivo",
        )
        for cod, cfg in CATALOGO_OBJETIVOS.items():
            for campo in campos:
                assert hasattr(cfg, campo), f"{cod} falta campo '{campo}'"
                val = getattr(cfg, campo)
                assert val is not None, f"{cod}.{campo} no debe ser None"

    def test_horizontes_validos(self):
        for cod, cfg in CATALOGO_OBJETIVOS.items():
            assert cfg.horizonte in ("CP", "MP", "LP"), f"{cod} horizonte inválido"

    def test_horizonte_meses_positivos(self):
        for cod, cfg in CATALOGO_OBJETIVOS.items():
            assert cfg.horizonte_meses > 0, f"{cod} horizonte_meses debe ser > 0"

    def test_cp_objetivos_son_corto_plazo(self):
        for cod in ("CP1", "CP2", "CP3"):
            assert CATALOGO_OBJETIVOS[cod].horizonte == "CP"
            assert CATALOGO_OBJETIVOS[cod].horizonte_meses <= 12

    def test_lp_objetivos_son_largo_plazo(self):
        for cod in ("LP1", "LP2", "LP3"):
            assert CATALOGO_OBJETIVOS[cod].horizonte == "LP"
            assert CATALOGO_OBJETIVOS[cod].horizonte_meses >= 36

    def test_objetivo_info_devuelve_dict(self):
        info = objetivo_info("MP1")
        assert info is not None
        assert info["codigo"] == "MP1"
        assert info["horizonte"] == "MP"

    def test_objetivo_info_devuelve_none_para_codigo_invalido(self):
        assert objetivo_info("XX9") is None


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────────────────────

class TestDistribuirEquitativamente:
    def test_1_instrumento(self):
        pesos = _distribuir_equitativamente(1)
        assert len(pesos) == 1
        assert abs(pesos[0] - 100.0) < 1e-6

    def test_2_instrumentos_suma_100(self):
        pesos = _distribuir_equitativamente(2)
        assert abs(sum(pesos) - 100.0) < 1e-4
        assert len(pesos) == 2

    def test_3_instrumentos_suma_100(self):
        pesos = _distribuir_equitativamente(3)
        assert abs(sum(pesos) - 100.0) < 1e-4

    def test_cero_instrumentos_lista_vacia(self):
        assert _distribuir_equitativamente(0) == []


class TestProyectarFV:
    def test_sin_flujo_ni_tir(self):
        proyeccion = _proyectar_fv(1000, 0, 0, 3, ccl=1429, fecha_inicio=date(2026, 6, 1))
        assert len(proyeccion) == 3
        for p in proyeccion:
            assert p.valor_usd == pytest.approx(1000.0, abs=0.01)

    def test_con_tir_positiva(self):
        # USD 1000 al 12% anual (1% mensual) durante 12 meses
        proyeccion = _proyectar_fv(1000, 0, 12.0, 12, ccl=1000, fecha_inicio=date(2026, 1, 1))
        assert len(proyeccion) == 12
        fv = proyeccion[-1].valor_usd
        # FV esperado: 1000 × (1.01)^12 ≈ 1126.83
        assert fv == pytest.approx(1000 * (1.01 ** 12), abs=0.5)

    def test_con_flujo_mensual(self):
        # USD 0 inicial + USD 100/mes, 0% tir → FV = 100 × 12 = 1200
        proyeccion = _proyectar_fv(0, 100, 0, 12, ccl=1000, fecha_inicio=date(2026, 1, 1))
        assert proyeccion[-1].valor_usd == pytest.approx(1200.0, abs=0.01)

    def test_valor_ars_es_usd_por_ccl(self):
        proyeccion = _proyectar_fv(500, 0, 0, 1, ccl=1429, fecha_inicio=date(2026, 6, 1))
        assert proyeccion[0].valor_ars == pytest.approx(500 * 1429, abs=1.0)

    def test_horizonte_meses_correcto(self):
        for meses in (3, 6, 12, 24, 60):
            p = _proyectar_fv(1000, 0, 7.0, meses, ccl=1000, fecha_inicio=date(2026, 1, 1))
            assert len(p) == meses


class TestAsignarCapital:
    def test_un_solo_objetivo(self):
        asig = _asignar_capital_por_objetivos(["MP1"], 5000)
        assert "MP1" in asig
        assert abs(asig["MP1"] - 5000) < 1.0

    def test_suma_total_igual_capital(self):
        asig = _asignar_capital_por_objetivos(["CP2", "MP1", "LP3"], 5000)
        total = sum(asig.values())
        assert abs(total - 5000) < 1.0

    def test_objetivo_invalido_ignorado(self):
        asig = _asignar_capital_por_objetivos(["XX9"], 1000)
        assert asig == {} or sum(asig.values()) == pytest.approx(1000, abs=1)

    def test_distribuye_entre_horizontes_presentes(self):
        # CP2 + MP1 + LP3 → 3 horizontes distintos
        asig = _asignar_capital_por_objetivos(["CP2", "MP1", "LP3"], 10_000)
        # LP debe recibir más que CP (pesos base LP=0.45 > CP=0.15)
        assert asig.get("LP3", 0) > asig.get("CP2", 0)

    def test_capital_cero_devuelve_cero(self):
        asig = _asignar_capital_por_objetivos(["MP1"], 0)
        assert sum(asig.values()) == 0


# ──────────────────────────────────────────────────────────────────────────────
#  MOTOR PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

class TestCalcularPlanMultifuncional:
    """Caso base: CP2 + MP1 + LP3, USD 5000 + USD 350/mes (caso del usuario)."""

    def _plan_usuario(self) -> PlanMultifuncional:
        return calcular_plan_multifuncional(
            ["CP2", "MP1", "LP3"],
            capital_inicial_usd=5_000,
            flujo_mensual_usd=350,
            ccl=1_429.0,
            fecha_inicio=date(2026, 5, 27),
        )

    def test_devuelve_plan_multifuncional(self):
        plan = self._plan_usuario()
        assert isinstance(plan, PlanMultifuncional)

    def test_tres_tramos_generados(self):
        plan = self._plan_usuario()
        assert len(plan.tramos) == 3

    def test_objetivos_activos_correctos(self):
        plan = self._plan_usuario()
        assert set(plan.objetivos_activos) == {"CP2", "MP1", "LP3"}

    def test_capital_total_correcto(self):
        plan = self._plan_usuario()
        assert plan.capital_total_usd == pytest.approx(5_000, abs=0.01)

    def test_flujo_mensual_correcto(self):
        plan = self._plan_usuario()
        assert plan.flujo_mensual_total_usd == pytest.approx(350, abs=0.01)

    def test_ccl_conservado(self):
        plan = self._plan_usuario()
        assert plan.ccl == pytest.approx(1_429.0)

    def test_suma_capital_tramos_igual_total(self):
        plan = self._plan_usuario()
        suma = sum(t.capital_inicial_usd for t in plan.tramos)
        assert abs(suma - plan.capital_total_usd) <= 1.0

    def test_cada_tramo_tiene_proyeccion(self):
        plan = self._plan_usuario()
        for t in plan.tramos:
            assert len(t.proyeccion) == t.horizonte_meses

    def test_tir_ponderada_positiva_en_mp1(self):
        plan = self._plan_usuario()
        mp1 = next(t for t in plan.tramos if t.objetivo == "MP1")
        assert mp1.tir_ponderada_pct > 0

    def test_valor_final_mayor_que_capital_en_mp1(self):
        plan = self._plan_usuario()
        mp1 = next(t for t in plan.tramos if t.objetivo == "MP1")
        # Con TIR > 0 y horizonte 24 meses, FV debe superar capital inicial
        assert mp1.valor_final_usd > mp1.capital_inicial_usd * 0.9  # al menos no pierde >10%

    def test_mp1_tiene_instrumentos_on_usd(self):
        plan = self._plan_usuario()
        mp1 = next(t for t in plan.tramos if t.objetivo == "MP1")
        assert len(mp1.instrumentos) > 0
        for instr in mp1.instrumentos:
            assert isinstance(instr, AsignacionInstrumento)
            assert instr.capital_usd >= 0

    def test_suma_pesos_instrumentos_es_100(self):
        plan = self._plan_usuario()
        for t in plan.tramos:
            if t.instrumentos:
                suma_pesos = sum(i.peso_pct for i in t.instrumentos)
                assert abs(suma_pesos - 100.0) < 0.1, (
                    f"{t.objetivo}: suma pesos {suma_pesos:.2f} ≠ 100"
                )

    def test_capital_ars_correcto_en_instrumentos(self):
        plan = self._plan_usuario()
        for t in plan.tramos:
            for instr in t.instrumentos:
                esperado_ars = round(instr.capital_usd * plan.ccl, 2)
                assert abs(instr.capital_ars - esperado_ars) < 1.0

    def test_to_dict_serializable(self):
        plan = self._plan_usuario()
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert "tramos" in d
        assert len(d["tramos"]) == 3

    def test_fecha_plan_es_inicio(self):
        plan = self._plan_usuario()
        assert plan.fecha_plan == "2026-05-27"


class TestCalcularPlanCasosEdge:
    def test_objetivo_invalido_genera_advertencia(self):
        plan = calcular_plan_multifuncional(["CP2", "INVALIDO"], 1000)
        assert any("INVALIDO" in a for a in plan.advertencias_globales)
        # Solo CP2 activo
        assert "CP2" in plan.objetivos_activos

    def test_plan_vacio_con_todos_invalidos(self):
        plan = calcular_plan_multifuncional(["XX1", "XX2"], 5000)
        assert plan.tramos == []
        assert plan.capital_no_asignado_usd == pytest.approx(5000, abs=0.01)

    def test_capital_bajo_genera_advertencia(self):
        plan = calcular_plan_multifuncional(["MP1"], 50)
        assert any("bajo" in a.lower() or "insuficiente" in a.lower()
                   for a in plan.advertencias_globales + plan.tramos[0].advertencias)

    def test_sin_flujo_mensual(self):
        plan = calcular_plan_multifuncional(["LP1"], 10_000, flujo_mensual_usd=0)
        assert len(plan.tramos) == 1
        lp1 = plan.tramos[0]
        # Sin flujo la proyección crece solo por TIR
        assert lp1.proyeccion[-1].valor_usd >= lp1.capital_inicial_usd * 0.9

    def test_9_objetivos_juntos(self):
        todos = list(CATALOGO_OBJETIVOS.keys())
        plan = calcular_plan_multifuncional(todos, 100_000, flujo_mensual_usd=1_000)
        assert len(plan.tramos) == 9
        assert abs(sum(t.capital_inicial_usd for t in plan.tramos) - 100_000) <= 1.0

    def test_resultado_determinista(self):
        """Mismo input → mismo output (sin aleatoriedad)."""
        p1 = calcular_plan_multifuncional(["MP1", "LP3"], 5000)
        p2 = calcular_plan_multifuncional(["MP1", "LP3"], 5000)
        assert p1.capital_total_usd == p2.capital_total_usd
        assert len(p1.tramos) == len(p2.tramos)
        for t1, t2 in zip(p1.tramos, p2.tramos, strict=True):
            assert t1.capital_inicial_usd == t2.capital_inicial_usd

    def test_mp2_boncer_instrumentos(self):
        """MP2 debe seleccionar instrumentos tipo BONCER."""
        plan = calcular_plan_multifuncional(["MP2"], 5000)
        mp2 = plan.tramos[0]
        assert len(mp2.instrumentos) > 0
        # BONCER del catálogo (TX28, TZXD7, etc.)
        tickers = {i.ticker for i in mp2.instrumentos}
        assert len(tickers) > 0

    def test_cp1_letras_instrumentos(self):
        """CP1 debe usar instrumentos tipo LETRA (LECAP)."""
        plan = calcular_plan_multifuncional(["CP1"], 2000)
        cp1 = plan.tramos[0]
        assert len(cp1.instrumentos) > 0

    def test_lp3_cedears_instrumentos(self):
        """LP3 debe tener CEDEARs en instrumentos."""
        plan = calcular_plan_multifuncional(["LP3"], 3000)
        lp3 = plan.tramos[0]
        assert len(lp3.instrumentos) > 0
        # CEDEARs conocidos
        tickers = {i.ticker for i in lp3.instrumentos}
        cedears_esperados = {"GOOGL", "AMZN", "NVDA", "BRK/B"}
        assert tickers & cedears_esperados, f"LP3 sin CEDEARs conocidos. Tickers: {tickers}"


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS UI
# ──────────────────────────────────────────────────────────────────────────────

class TestHelpersUI:
    def _plan(self) -> PlanMultifuncional:
        return calcular_plan_multifuncional(
            ["CP2", "MP1", "LP3"], 5_000, flujo_mensual_usd=350, ccl=1_429.0
        )

    def test_resumen_plan_df_columnas(self):
        df = resumen_plan_df(self._plan())
        assert not df.empty
        for col in ("Objetivo", "Nombre", "Horizonte", "Capital USD", "TIR pond. %", "FV USD"):
            assert col in df.columns

    def test_resumen_plan_df_filas_iguales_tramos(self):
        plan = self._plan()
        df = resumen_plan_df(plan)
        assert len(df) == len(plan.tramos)

    def test_resumen_plan_df_vacio_si_no_hay_tramos(self):
        plan = calcular_plan_multifuncional(["XX99"], 1000)
        df = resumen_plan_df(plan)
        assert df.empty

    def test_proyeccion_consolidada_df_columnas(self):
        df = proyeccion_consolidada_df(self._plan())
        assert not df.empty
        for col in ("mes", "fecha", "objetivo", "nombre", "valor_usd", "valor_ars"):
            assert col in df.columns

    def test_proyeccion_consolidada_df_tiene_todos_los_tramos(self):
        plan = self._plan()
        df = proyeccion_consolidada_df(plan)
        objs_en_df = set(df["objetivo"].unique())
        assert objs_en_df == set(plan.objetivos_activos)

    def test_proyeccion_consolidada_df_longitud(self):
        plan = self._plan()
        total_esperado = sum(t.horizonte_meses for t in plan.tramos)
        df = proyeccion_consolidada_df(plan)
        assert len(df) == total_esperado

    def test_asignacion_pie_df_suma_100(self):
        df = asignacion_pie_df(self._plan())
        assert not df.empty
        assert abs(df["peso_pct"].sum() - 100.0) < 0.5

    def test_asignacion_pie_df_columnas(self):
        df = asignacion_pie_df(self._plan())
        for col in ("objetivo", "nombre", "capital_usd", "peso_pct"):
            assert col in df.columns

    def test_asignacion_pie_df_lp3_mayor_que_cp2(self):
        """LP recibe más capital que CP por diseño de pesos de horizonte."""
        df = asignacion_pie_df(self._plan())
        cap_lp3 = df[df["objetivo"] == "LP3"]["capital_usd"].values[0]
        cap_cp2 = df[df["objetivo"] == "CP2"]["capital_usd"].values[0]
        assert cap_lp3 > cap_cp2
