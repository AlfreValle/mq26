"""
tests/test_ctx_builder.py — Tests de core/ctx_builder.py (Sprint 29)
build_ctx solo usa pandas, Path y AppContext; sin red ni streamlit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


def _kwargs_minimos():
    """
    Invariante: kwargs suficientes para que build_ctx devuelva AppContext sin lanzar;
    valores mínimos son tipos válidos esperados por AppContext.
    """
    return dict(
        tenant_id="default",
        df_ag=pd.DataFrame(),
        tickers_cartera=[],
        precios_dict={},
        ccl=1465.0,
        cartera_activa="Test",
        prop_nombre="Test",
        df_clientes=pd.DataFrame(),
        df_analisis=pd.DataFrame(),
        metricas={},
        df_trans=pd.DataFrame(),
        cliente_id=None,
        cliente_nombre="Test",
        cliente_perfil="Moderado",
        horizonte_label="1 año",
        RISK_FREE_RATE=0.043,
        PESO_MAX_CARTERA=0.25,
        N_SIM_DEFAULT=5000,
        RUTA_ANALISIS="",
        horizonte_dias=365,
        capital_nuevo=0.0,
        BASE_DIR=Path("."),
        engine_data=None,
        RiskEngine=None,
        cached_historico=None,
        dbm=None,
        cs=None,
        m23svc=None,
        ejsvc=None,
        rpt=None,
        bt=None,
        ab=None,
        lm=None,
        bi=None,
        gr=None,
        mc=None,
        _boton_exportar=None,
        asignar_sector=None,
    )


class TestBuildCtx:
    def test_retorna_app_context(self):
        from core.app_context import AppContext
        from core.ctx_builder import build_ctx

        ctx = build_ctx(**_kwargs_minimos())
        assert isinstance(ctx, AppContext)

    def test_ccl_preservado(self):
        from core.ctx_builder import build_ctx

        kwargs = _kwargs_minimos()
        kwargs["ccl"] = 1500.0
        ctx = build_ctx(**kwargs)
        assert ctx.ccl == 1500.0

    def test_tenant_id_preservado(self):
        from core.ctx_builder import build_ctx

        kwargs = _kwargs_minimos()
        kwargs["tenant_id"] = "alfredo@mail.com"
        ctx = build_ctx(**kwargs)
        assert ctx.tenant_id == "alfredo@mail.com"

    def test_cliente_id_preservado(self):
        from core.ctx_builder import build_ctx

        kwargs = _kwargs_minimos()
        kwargs["cliente_id"] = 42
        ctx = build_ctx(**kwargs)
        assert ctx.cliente_id == 42

    def test_tickers_preservados(self):
        from core.ctx_builder import build_ctx

        kwargs = _kwargs_minimos()
        kwargs["tickers_cartera"] = ["AAPL", "MSFT"]
        ctx = build_ctx(**kwargs)
        assert ctx.tickers_cartera == ["AAPL", "MSFT"]

    def test_acceso_dict_style(self):
        from core.ctx_builder import build_ctx

        ctx = build_ctx(**_kwargs_minimos())
        assert ctx["ccl"] == 1465.0

    def test_contains_funciona(self):
        from core.ctx_builder import build_ctx

        ctx = build_ctx(**_kwargs_minimos())
        assert "ccl" in ctx
        assert "campo_inexistente" not in ctx

    def test_get_con_default(self):
        from core.ctx_builder import build_ctx

        ctx = build_ctx(**_kwargs_minimos())
        assert ctx.get("cliente_id") is None
        assert ctx.get("campo_raro", "fallback") == "fallback"

    def test_df_ag_asignable(self):
        from core.ctx_builder import build_ctx

        kwargs = _kwargs_minimos()
        df = pd.DataFrame({"TICKER": ["AAPL"], "VALOR_ARS": [190_000.0]})
        kwargs["df_ag"] = df
        ctx = build_ctx(**kwargs)
        assert len(ctx.df_ag) == 1

    def test_no_lanza_con_kwargs_minimos(self):
        from core.ctx_builder import build_ctx

        try:
            build_ctx(**_kwargs_minimos())
        except Exception as e:  # pragma: no cover
            pytest.fail(f"build_ctx lanzó con kwargs mínimos: {e}")
