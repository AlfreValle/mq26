"""
Test de integración de flujos por rol (estudio + asesor) con 3 clientes.

Automatiza la prueba funcional manual: crea 3 clientes con perfiles
contrastantes en una BD temporal aislada y ejercita el MISMO motor que las
tabs de estudio/asesor (alta → posición neta → diagnóstico → recomendación).

Offline y determinista: precios fallback del sistema + CCL fijo, sin red.
Asserts sobre invariantes de negocio (no valores mágicos que cambian con los
precios de referencia). Cubre el camino que ningún test end-to-end tocaba.
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

CCL = 1500.0  # config.CCL_FALLBACK — sin red


# ─── BD temporal aislada (nunca toca la productiva) ──────────────────────────

@pytest.fixture()
def dbm_temp(monkeypatch, tmp_path):
    import core.db_manager as dbm

    eng = create_engine(f"sqlite:///{tmp_path / 'roles_test.db'}", future=True)
    dbm.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbm, "engine", eng)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=eng, future=True))
    return dbm


@pytest.fixture()
def precios():
    from services.cartera_service import PRECIOS_FALLBACK_ARS

    return {k.upper(): float(v) for k, v in PRECIOS_FALLBACK_ARS.items()}


# Carteras por perfil (ON_USD: PPC_USD = paridad %, CANTIDAD = nominales).
CARTERAS = {
    "Conservador": [
        ("PN43O", 200, 103.0, "ON_USD"), ("TLCTO", 180, 102.5, "ON_USD"),
        ("KO", 8, 18.0, "CEDEAR"), ("JNJ", 5, 14.0, "CEDEAR"), ("PG", 6, 16.0, "CEDEAR"),
    ],
    "Moderado": [
        ("SPY", 6, 45.0, "CEDEAR"), ("MSFT", 4, 28.0, "CEDEAR"), ("KO", 5, 18.0, "CEDEAR"),
        ("GLD", 4, 12.0, "CEDEAR"), ("PN43O", 120, 103.0, "ON_USD"),
    ],
    "Arriesgado": [
        ("NVDA", 6, 9.0, "CEDEAR"), ("MELI", 3, 18.0, "CEDEAR"), ("AMZN", 5, 2.5, "CEDEAR"),
        ("META", 4, 30.0, "CEDEAR"), ("PLTR", 8, 5.0, "CEDEAR"),
    ],
}


def _df_ag(cartera):
    return pd.DataFrame([
        {
            "TICKER": tk, "CANTIDAD_TOTAL": float(c), "PPC_USD_PROM": float(p),
            "INV_USD_TOTAL": float(c) * float(p), "TIPO": tipo, "FECHA_COMPRA": "2025-09-15",
        }
        for tk, c, p, tipo in cartera
    ])


def _diagnostico(perfil, horizonte, precios):
    from services.cartera_service import calcular_posicion_neta, metricas_resumen
    from services.diagnostico_cartera import diagnosticar

    df = calcular_posicion_neta(_df_ag(CARTERAS[perfil]), precios, CCL)
    diag = diagnosticar(
        df_ag=df, perfil=perfil, horizonte_label=horizonte,
        metricas=metricas_resumen(df), ccl=CCL, universo_df=None,
        senales_salida=None, cliente_nombre=f"Test {perfil}",
    )
    return df, diag


# ─── ROL ESTUDIO: alta y listado de clientes ─────────────────────────────────

class TestRolEstudio:
    def test_alta_tres_clientes_visibles(self, dbm_temp):
        clientes = [
            ("Ana Conservadora", "Conservador", "+5 años"),
            ("Marta Moderada", "Moderado", "3 años"),
            ("Joaquín Arriesgado", "Arriesgado", "1 año"),
        ]
        ids = [
            dbm_temp.registrar_cliente(
                nombre=n, perfil_riesgo=p, horizonte_label=h, tenant_id="default",
            )
            for n, p, h in clientes
        ]
        assert all(isinstance(i, int) and i > 0 for i in ids)
        assert len(set(ids)) == 3  # ids únicos
        df = dbm_temp.obtener_clientes_df(tenant_id="default")
        assert len(df) == 3

    def test_alta_idempotente(self, dbm_temp):
        # registrar_cliente es idempotente por (nombre, tenant)
        a = dbm_temp.registrar_cliente(nombre="Dup", perfil_riesgo="Moderado", tenant_id="default")
        b = dbm_temp.registrar_cliente(nombre="Dup", perfil_riesgo="Moderado", tenant_id="default")
        assert a == b
        assert len(dbm_temp.obtener_clientes_df(tenant_id="default")) == 1


# ─── ROL ASESOR: motor de diagnóstico + recomendación por perfil ─────────────

class TestRolAsesorDiagnostico:
    @pytest.mark.parametrize("perfil,horizonte", [
        ("Conservador", "+5 años"), ("Moderado", "3 años"), ("Arriesgado", "1 año"),
    ])
    def test_diagnostico_valido(self, perfil, horizonte, precios):
        df, diag = _diagnostico(perfil, horizonte, precios)
        assert 0 <= diag.score_total <= 100
        assert getattr(diag, "semaforo", None) is not None
        assert diag.valor_cartera_usd > 0
        assert diag.n_posiciones == 5
        assert not diag.modo_fallback  # hay cartera real, no degradado

    def test_defensivo_escala_con_renta_fija(self, precios):
        # Invariante de negocio: más ONs → más % defensivo.
        # Ana (2 ONs grandes) > Marta (1 ON) > Joaquín (0 ONs).
        _, ana = _diagnostico("Conservador", "+5 años", precios)
        _, marta = _diagnostico("Moderado", "3 años", precios)
        _, joaco = _diagnostico("Arriesgado", "1 año", precios)
        assert ana.pct_defensivo_actual > marta.pct_defensivo_actual
        assert marta.pct_defensivo_actual > joaco.pct_defensivo_actual
        assert joaco.pct_defensivo_actual == pytest.approx(0.0, abs=0.02)

    def test_conservador_bien_armado_supera_a_desbalanceado(self, precios):
        # Ana cumple su objetivo defensivo (60%); Marta no (25% vs 50% req).
        _, ana = _diagnostico("Conservador", "+5 años", precios)
        _, marta = _diagnostico("Moderado", "3 años", precios)
        assert ana.score_total > marta.score_total
        assert ana.pct_defensivo_actual >= ana.pct_defensivo_requerido - 0.05

    def test_observaciones_presentes(self, precios):
        _, diag = _diagnostico("Moderado", "3 años", precios)
        assert diag.observaciones  # el motor siempre explica
        assert all(getattr(o, "titulo", "") for o in diag.observaciones)


class TestRolAsesorRecomendacion:
    @pytest.mark.parametrize("perfil,horizonte", [
        ("Conservador", "+5 años"), ("Moderado", "3 años"), ("Arriesgado", "1 año"),
    ])
    def test_recomienda_con_justificacion(self, perfil, horizonte, precios):
        from services.recomendacion_capital import recomendar

        df, diag = _diagnostico(perfil, horizonte, precios)
        rr = recomendar(
            df_ag=df, perfil=perfil, horizonte_label=horizonte,
            capital_ars=500_000.0, ccl=CCL, precios_dict=precios,
            diagnostico=diag, universo_df=None, cliente_nombre=f"Test {perfil}",
        )
        compras = list(getattr(rr, "compras_recomendadas", []) or [])
        assert compras, "con capital y cartera real debe sugerir algo"
        # Cada sugerencia es accionable y explicada
        for it in compras:
            assert getattr(it, "ticker", "")
            assert float(getattr(it, "monto_ars", 0)) > 0
            assert str(getattr(it, "justificacion", "")).strip()
        # No gasta más que el capital disponible
        usado = sum(float(getattr(it, "monto_ars", 0)) for it in compras)
        assert usado <= 500_000.0 * 1.02  # margen por redondeo de unidades

    def test_capital_cero_no_rompe(self, precios):
        from services.recomendacion_capital import recomendar

        df, diag = _diagnostico("Moderado", "3 años", precios)
        rr = recomendar(
            df_ag=df, perfil="Moderado", horizonte_label="3 años",
            capital_ars=0.0, ccl=CCL, precios_dict=precios,
            diagnostico=diag, universo_df=None,
        )
        assert rr is not None
        assert float(getattr(rr, "capital_remanente_ars", 0)) == 0.0

    def test_desbalanceado_recibe_renta_fija(self, precios):
        # Marta tiene 25% RF (req 50%): el motor debe sugerir al menos 1 RF.
        from core.renta_fija_ar import es_renta_fija
        from services.recomendacion_capital import recomendar

        df, diag = _diagnostico("Moderado", "3 años", precios)
        rr = recomendar(
            df_ag=df, perfil="Moderado", horizonte_label="3 años",
            capital_ars=500_000.0, ccl=CCL, precios_dict=precios,
            diagnostico=diag, universo_df=None,
        )
        tickers = [str(getattr(it, "ticker", "")).upper() for it in rr.compras_recomendadas]
        assert any(es_renta_fija(t) for t in tickers), \
            f"cartera con déficit RF debería recibir RF; sugirió {tickers}"
