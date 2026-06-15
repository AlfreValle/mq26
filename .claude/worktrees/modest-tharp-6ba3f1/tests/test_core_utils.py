"""
tests/test_core_utils.py — Tests de módulos core sin cobertura (Sprint 17+27)
Cubre: constants.py, audit.py, app_context.py.
Sin red ni yfinance.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# ─── constants.py ─────────────────────────────────────────────────────────────

class TestConstants:
    def test_tipos_instrumento_es_lista(self):
        from core.constants import TIPOS_INSTRUMENTO
        assert isinstance(TIPOS_INSTRUMENTO, list)
        assert len(TIPOS_INSTRUMENTO) > 0
        assert "CEDEAR" in TIPOS_INSTRUMENTO

    def test_horizontes_inversion_es_lista(self):
        from core.constants import HORIZONTES_INVERSION
        assert isinstance(HORIZONTES_INVERSION, list)
        assert "1 año" in HORIZONTES_INVERSION

    def test_horizonte_a_dias_coherente(self):
        from core.constants import HORIZONTE_A_DIAS, HORIZONTES_INVERSION
        for h in HORIZONTES_INVERSION:
            if h in HORIZONTE_A_DIAS:
                assert HORIZONTE_A_DIAS[h] > 0

    def test_horizontes_dias_ordenados(self):
        from core.constants import HORIZONTE_A_DIAS
        valores = list(HORIZONTE_A_DIAS.values())
        assert valores == sorted(valores)

    def test_tipos_alerta_es_lista(self):
        from core.constants import TIPOS_ALERTA
        assert isinstance(TIPOS_ALERTA, list)
        assert "AUDITORIA" in TIPOS_ALERTA

    def test_colores_es_dict(self):
        from core.constants import COLORES
        assert isinstance(COLORES, dict)
        assert "verde" in COLORES and "rojo" in COLORES

    def test_mensajes_es_dict(self):
        from core.constants import MENSAJES
        assert isinstance(MENSAJES, dict)
        assert "sin_datos" in MENSAJES

    def test_mensajes_son_strings(self):
        from core.constants import MENSAJES
        for k, v in MENSAJES.items():
            assert isinstance(v, str), f"MENSAJES['{k}'] no es str"

    def test_tipos_instrumento_contiene_claves(self):
        from core.constants import TIPOS_INSTRUMENTO
        for t in ("BONO", "ETF", "FCI", "ACCION"):
            assert t in TIPOS_INSTRUMENTO

    def test_tipos_instrumento_todos_strings_no_vacios(self):
        from core.constants import TIPOS_INSTRUMENTO
        for t in TIPOS_INSTRUMENTO:
            assert isinstance(t, str) and len(t) > 0

    def test_horizontes_al_menos_cinco(self):
        from core.constants import HORIZONTES_INVERSION
        assert len(HORIZONTES_INVERSION) >= 5

    def test_horizonte_un_anio_365_dias(self):
        from core.constants import HORIZONTE_A_DIAS
        assert HORIZONTE_A_DIAS.get("1 año") == 365

    def test_mas_cinco_anios_mayor_tres_anios(self):
        from core.constants import HORIZONTE_A_DIAS
        assert HORIZONTE_A_DIAS["+5 años"] > HORIZONTE_A_DIAS["3 años"]

    def test_tipos_alerta_todos_mayusculas(self):
        from core.constants import TIPOS_ALERTA
        for t in TIPOS_ALERTA:
            assert isinstance(t, str)
            assert t == t.upper()

    def test_colores_valores_hex_seis_digitos(self):
        from core.constants import COLORES
        patron = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for k, v in COLORES.items():
            assert patron.match(v), f"COLORES['{k}']={v!r} no es #RRGGBB"

    def test_mensajes_cliente_requerido_y_guardado_ok(self):
        from core.constants import MENSAJES
        assert "cliente_requerido" in MENSAJES
        assert len(MENSAJES["cliente_requerido"]) > 0
        assert "guardado_ok" in MENSAJES
        assert len(MENSAJES["guardado_ok"]) > 0


# ─── audit.py ─────────────────────────────────────────────────────────────────

class TestAuditModule:
    def test_registrar_accion_no_lanza_sin_bd(self):
        from core.audit import registrar_accion
        with patch("core.db_manager.registrar_alerta_log",
                   side_effect=Exception("BD no disponible")):
            try:
                registrar_accion("TEST_ACCION", "detalle test")
            except Exception as e:
                pytest.fail(f"registrar_accion lanzó: {e}")

    def test_registrar_login_exitoso(self):
        from core.audit import registrar_login
        with patch("core.db_manager.registrar_alerta_log", return_value=None) as mock_log:
            registrar_login("mq26", exito=True, usuario="alfredo")
        mock_log.assert_called_once()
        kw = mock_log.call_args.kwargs
        assert kw["tipo_alerta"] == "ACCESO"
        assert "LOGIN_EXITOSO" in kw["mensaje"]

    def test_registrar_login_fallido(self):
        from core.audit import registrar_login
        with patch("core.db_manager.registrar_alerta_log", return_value=None) as mock_log:
            registrar_login("mq26", exito=False)
        mock_log.assert_called_once()
        kw = mock_log.call_args.kwargs
        assert "LOGIN_FALLIDO" in kw["mensaje"]

    def test_registrar_eliminacion(self):
        from core.audit import registrar_eliminacion
        with patch("core.db_manager.registrar_alerta_log", return_value=None):
            registrar_eliminacion("OBJETIVO", 42, cliente_id=5)

    def test_registrar_eliminacion_mensaje_incluye_entidad(self):
        from core.audit import registrar_eliminacion
        with patch("core.db_manager.registrar_alerta_log", return_value=None) as mock_log:
            registrar_eliminacion("OBJETIVO", 42, cliente_id=3)
        kw = mock_log.call_args.kwargs
        assert "ELIMINAR_OBJETIVO" in kw["mensaje"]

    def test_registrar_modificacion(self):
        from core.audit import registrar_modificacion
        with patch("core.db_manager.registrar_alerta_log", return_value=None):
            registrar_modificacion("CLIENTE", 1, {"perfil": "Agresivo"})

    def test_registrar_backup(self):
        from core.audit import registrar_backup
        with patch("core.db_manager.registrar_alerta_log", return_value=None):
            registrar_backup("/backup/path.db", "abc123def456ghi789")

    def test_registrar_backup_trunca_hash_en_mensaje(self):
        from core.audit import registrar_backup
        hash_largo = "abc123def456ghi789jkl012mno345pqr678"
        with patch("core.db_manager.registrar_alerta_log", return_value=None) as mock_log:
            registrar_backup("/ruta/backup.db", hash_largo)
        kw = mock_log.call_args.kwargs
        mensaje = kw["mensaje"]
        assert hash_largo[:16] in mensaje
        assert hash_largo not in mensaje

    def test_registrar_accion_con_ticker(self):
        from core.audit import registrar_accion
        with patch("core.db_manager.registrar_alerta_log", return_value=None):
            registrar_accion("COMPRA", ticker="AAPL", detalle="10 nominales")

    def test_registrar_accion_todos_los_parametros(self):
        from core.audit import registrar_accion
        with patch("core.db_manager.registrar_alerta_log", return_value=None) as mock_log:
            registrar_accion(
                accion="GUARDAR_CARTERA",
                detalle="10 posiciones",
                cliente_id=5,
                ticker="MSFT",
                tipo_alerta="AUDITORIA",
                usuario="alfredo",
            )
        mock_log.assert_called_once()
        kw = mock_log.call_args.kwargs
        assert kw["tipo_alerta"] == "AUDITORIA"
        assert "GUARDAR_CARTERA" in kw["mensaje"]
        assert "MSFT" in kw["mensaje"]
        assert kw["ticker"] == "MSFT"


# ─── app_context.py ───────────────────────────────────────────────────────────

class TestAppContext:
    def test_crea_con_defaults(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert ctx.ccl == 1500.0
        assert ctx.cliente_perfil == "Moderado"
        assert ctx.tenant_id == "default"

    def test_acceso_dict_style(self):
        from core.app_context import AppContext
        ctx = AppContext(ccl=1465.0)
        assert ctx["ccl"] == 1465.0

    def test_in_operator(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert "ccl" in ctx
        assert "campo_inexistente_xyz" not in ctx

    def test_get_con_default(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert ctx.get("ccl") == 1500.0
        assert ctx.get("campo_no_existe", "default_val") == "default_val"

    def test_to_dict_retorna_dict(self):
        from core.app_context import AppContext
        ctx = AppContext(ccl=1465.0, tenant_id="test@mail.com")
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d.get("ccl") == 1465.0

    def test_df_ag_es_dataframe_por_defecto(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert isinstance(ctx.df_ag, pd.DataFrame)
        assert ctx.df_ag.empty

    def test_tickers_cartera_es_lista_por_defecto(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert isinstance(ctx.tickers_cartera, list)
        assert len(ctx.tickers_cartera) == 0

    def test_cliente_id_none_por_defecto(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert ctx.cliente_id is None

    def test_asignacion_personalizada(self):
        from core.app_context import AppContext
        ctx = AppContext(
            ccl=1500.0,
            tenant_id="alfredo@mail.com",
            cliente_nombre="Alfredo Vallejos",
            cliente_perfil="Agresivo",
        )
        assert ctx.tenant_id == "alfredo@mail.com"
        assert ctx.cliente_nombre == "Alfredo Vallejos"
        assert ctx.cliente_perfil == "Agresivo"

    def test_asignacion_horizonte_dias(self):
        from core.app_context import AppContext
        ctx = AppContext(ccl=1465.0, horizonte_dias=365, tenant_id="t@test.com")
        assert ctx.horizonte_dias == 365
        assert ctx.ccl == 1465.0

    def test_cliente_id_entero(self):
        from core.app_context import AppContext
        ctx = AppContext(cliente_id=42)
        assert ctx.cliente_id == 42

    def test_tickers_cartera_asignables(self):
        from core.app_context import AppContext
        ctx = AppContext(tickers_cartera=["AAPL", "MSFT", "KO"])
        assert ctx.tickers_cartera == ["AAPL", "MSFT", "KO"]

    def test_df_ag_con_filas(self):
        from core.app_context import AppContext
        df = pd.DataFrame({"TICKER": ["AAPL"], "VALOR_ARS": [190_000.0]})
        ctx = AppContext(df_ag=df)
        assert len(ctx.df_ag) == 1

    def test_precios_dict_vacio_por_defecto(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert isinstance(ctx.precios_dict, dict)
        assert len(ctx.precios_dict) == 0

    def test_metricas_dict_por_defecto(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert isinstance(ctx.metricas, dict)
        assert len(ctx.metricas) == 0

    def test_base_dir_es_path(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert isinstance(ctx.BASE_DIR, Path)

    def test_getitem_lanza_attributeerror_campo_inexistente(self):
        from core.app_context import AppContext
        ctx = AppContext()
        with pytest.raises(AttributeError):
            _ = ctx["campo_que_no_existe"]

    def test_getitem_cliente_nombre(self):
        from core.app_context import AppContext
        ctx = AppContext(cliente_nombre="Test")
        assert ctx["cliente_nombre"] == "Test"

    def test_get_sin_default_none_si_no_existe(self):
        from core.app_context import AppContext
        ctx = AppContext()
        assert ctx.get("campo_inexistente") is None

    def test_to_dict_con_dataframe_no_lanza(self):
        from core.app_context import AppContext
        df = pd.DataFrame({"A": [1, 2]})
        ctx = AppContext(df_ag=df)
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert len(d["df_ag"]) == 2
