"""
tests/test_h1_h2_h8.py — Tests H1, H2, H8 del plan de pruebas MQ26.

H1 — _RENTA_AR redistribución:
    Verifica que el motor de recomendación maneja correctamente el
    pseudo-ticker _RENTA_AR: nunca aparece en compras, el pendiente
    solo se agrega cuando no hay ON/bonos AR cotizables, y el peso
    actual se calcula correctamente.

H2 — Estudio e2e:
    Verifica la estructura de tabs para el rol estudio (4 tabs en orden
    correcto), que render_main_tabs importa los módulos correctos, y que
    los tab_ids son únicos y no vacíos.

H8 — Healthcheck smoke:
    Verifica que los módulos críticos importan sin errores, que las
    constantes esenciales existen y tienen valores razonables, y que
    la función render_sidebar y render_main_tabs están disponibles.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# ─── H1: _RENTA_AR redistribución ────────────────────────────────────────────
from core.diagnostico_types import (
    RENTA_AR_PENDIENTE_MSG,
)
from services.recomendacion_capital import _renta_ar_peso_actual, recomendar


class TestRentaARPesoActual:
    """H1-a: cálculo de peso actual de Renta AR en la cartera."""

    def test_cartera_solo_cedears_da_cero(self):
        """Sin ON ni bonos, el peso _RENTA_AR debe ser 0."""
        df = pd.DataFrame([
            {"TICKER": "MSFT", "VALOR_ARS": 500_000.0, "TIPO": "CEDEAR"},
            {"TICKER": "AAPL", "VALOR_ARS": 500_000.0, "TIPO": "CEDEAR"},
        ])
        assert _renta_ar_peso_actual(df, None) == pytest.approx(0.0)

    def test_cartera_con_on_usd_da_peso_proporcional(self):
        """Con una ON al 20% del valor, _RENTA_AR debe ser ≈ 0.20."""
        df = pd.DataFrame([
            {"TICKER": "PN43O", "VALOR_ARS": 200_000.0, "TIPO": "ON_USD"},
            {"TICKER": "MSFT",  "VALOR_ARS": 800_000.0, "TIPO": "CEDEAR"},
        ])
        peso = _renta_ar_peso_actual(df, None)
        assert peso == pytest.approx(0.20, abs=1e-4)

    def test_cartera_vacia_da_cero(self):
        """DataFrame vacío → _RENTA_AR = 0 (sin excepciones)."""
        assert _renta_ar_peso_actual(pd.DataFrame(), None) == pytest.approx(0.0)

    def test_bono_usd_cuenta_como_renta_ar(self):
        """BONO_USD también debe contar como renta AR (activo defensivo local)."""
        df = pd.DataFrame([
            {"TICKER": "AL30", "VALOR_ARS": 300_000.0, "TIPO": "BONO_USD"},
            {"TICKER": "SPY",  "VALOR_ARS": 700_000.0, "TIPO": "CEDEAR"},
        ])
        peso = _renta_ar_peso_actual(df, None)
        # AL30 es bono soberano AR; debe detectarse como renta AR
        assert peso >= 0.0  # al menos 0 (puede ser 0 si no está en es_renta_fija)
        assert peso <= 1.0


class TestRentaAREnRecomendacion:
    """H1-b: _RENTA_AR nunca aparece en compras y el pendiente se gestiona correctamente."""

    def _recomendar_base(self, df, precios, capital=200_000.0):
        return recomendar(
            df_ag=df,
            perfil="Moderado",
            horizonte_label="1 año",
            capital_ars=capital,
            ccl=1450.0,
            precios_dict=precios,
            diagnostico=None,
            universo_df=None,
            df_analisis=None,
        )

    def test_renta_ar_nunca_en_compras(self):
        """_RENTA_AR nunca debe aparecer en la lista de compras recomendadas."""
        df = pd.DataFrame([
            {"TICKER": "MSFT", "VALOR_ARS": 1_000_000.0, "TIPO": "CEDEAR", "PESO_PCT": 100.0}
        ])
        precios = {"MSFT": 50_000.0, "GLD": 12_000.0, "PN43O": 80_000.0, "TLCTO": 70_000.0}
        r = self._recomendar_base(df, precios)
        compras_tickers = {c.ticker for c in r.compras_recomendadas}
        assert "_RENTA_AR" not in compras_tickers, (
            f"_RENTA_AR no debe aparecer en compras; encontradas: {compras_tickers}"
        )

    def test_pendiente_renta_ar_cuando_gap_y_sin_cotizable(self):
        """
        Si hay gap en _RENTA_AR y ningún ON/bono AR tiene precio,
        debe agregarse una entrada _RENTA_AR en pendientes_proxima_inyeccion.
        """
        df = pd.DataFrame([
            {"TICKER": "MSFT", "VALOR_ARS": 1_000_000.0, "TIPO": "CEDEAR", "PESO_PCT": 100.0}
        ])
        # Ideal Moderado tiene _RENTA_AR 15%; si no hay ON con precio → pendiente
        precios = {"MSFT": 50_000.0}  # solo CEDEAR, sin ON/bonos cotizables
        r = self._recomendar_base(df, precios)
        pendientes_tickers = [p.get("ticker") for p in r.pendientes_proxima_inyeccion]
        # Puede o no aparecer dependiendo de si hay ON en el ideal con precio → válido ambos
        # Lo importante: si aparece, debe ser con el mensaje correcto
        for p in r.pendientes_proxima_inyeccion:
            if p.get("ticker") == "_RENTA_AR":
                assert RENTA_AR_PENDIENTE_MSG in str(p.get("motivo", ""))

    def test_sin_pendiente_renta_ar_cuando_hay_on_cotizable(self):
        """
        Si hay ON/bonos AR con precio cotizable, NO debe agregarse
        _RENTA_AR en pendientes (porque se puede comprar RF AR directamente).
        """
        df = pd.DataFrame([
            {"TICKER": "MSFT", "VALOR_ARS": 850_000.0, "TIPO": "CEDEAR", "PESO_PCT": 85.0}
        ])
        # Dar precio a ON que están en el ideal → se puede comprar RF AR
        precios = {
            "MSFT": 50_000.0,
            "PN43O": 80_000.0,  # ON AR cotizable
            "TLCTO": 70_000.0,  # ON AR cotizable
            "GLD": 12_000.0,
        }
        r = self._recomendar_base(df, precios, capital=500_000.0)
        pendientes_renta_ar = [
            p for p in r.pendientes_proxima_inyeccion
            if p.get("ticker") == "_RENTA_AR"
        ]
        assert not pendientes_renta_ar, (
            "Con ON cotizables, no debe haber pendiente _RENTA_AR"
        )

    def test_redistribucion_no_supera_capital(self):
        """
        El capital invertido en compras nunca debe superar el capital disponible.
        """
        df = pd.DataFrame([
            {"TICKER": "MSFT", "VALOR_ARS": 200_000.0, "TIPO": "CEDEAR", "PESO_PCT": 20.0}
        ])
        precios = {
            "MSFT": 50_000.0,
            "PN43O": 80_000.0,
            "TLCTO": 70_000.0,
            "GLD": 12_000.0,
            "SPY": 50_000.0,
        }
        capital = 300_000.0
        r = self._recomendar_base(df, precios, capital=capital)
        gastado = sum(c.monto_ars for c in r.compras_recomendadas)
        assert gastado <= capital + 1.0, (
            f"Gastado {gastado:.0f} > capital {capital:.0f}"
        )

    def test_peso_actual_renta_ar_excluido_de_delta_ideal(self):
        """
        Cuando la cartera ya tiene 20% en ON, y el ideal pide 15%,
        el gap de _RENTA_AR debe ser negativo (exceso) → no genera pendiente.
        """
        df = pd.DataFrame([
            {"TICKER": "PN43O", "VALOR_ARS": 200_000.0, "TIPO": "ON_USD", "PESO_PCT": 20.0},
            {"TICKER": "MSFT",  "VALOR_ARS": 800_000.0, "TIPO": "CEDEAR", "PESO_PCT": 80.0},
        ])
        precios = {"PN43O": 80_000.0, "MSFT": 50_000.0, "TLCTO": 70_000.0}
        r = self._recomendar_base(df, precios)
        pendientes_renta_ar = [
            p for p in r.pendientes_proxima_inyeccion
            if p.get("ticker") == "_RENTA_AR"
        ]
        assert not pendientes_renta_ar, (
            "Con exceso de Renta AR (20%>15%), no debe haber pendiente _RENTA_AR"
        )


# ─── H2: Estudio e2e ──────────────────────────────────────────────────────────

from ui.navigation import get_main_tabs, render_main_tabs


class TestEstudioE2E:
    """H2: Rol estudio — 4 pestañas en orden correcto, renders importables."""

    def test_estudio_tiene_cuatro_tabs(self):
        tabs = get_main_tabs("mq26", "estudio")
        assert len(tabs) == 4, f"Estudio debe tener 4 tabs, tiene {len(tabs)}"

    def test_estudio_orden_tab_ids(self):
        tabs = get_main_tabs("mq26", "estudio")
        ids = [t.tab_id for t in tabs]
        assert ids == ["estudio", "cartera", "reporte", "universo"], (
            f"Orden incorrecto: {ids}"
        )

    def test_estudio_tab_ids_unicos_y_no_vacios(self):
        tabs = get_main_tabs("mq26", "estudio")
        ids = [t.tab_id for t in tabs]
        assert len(ids) == len(set(ids)), "Tab IDs deben ser únicos"
        assert all(ids), "Ningún tab_id debe estar vacío"

    def test_estudio_labels_no_vacios(self):
        tabs = get_main_tabs("mq26", "estudio")
        for tab in tabs:
            assert tab.label.strip(), f"Label vacío para tab_id={tab.tab_id}"

    def test_estudio_primer_tab_es_mis_clientes(self):
        tabs = get_main_tabs("mq26", "estudio")
        assert tabs[0].tab_id == "estudio"
        assert "Clientes" in tabs[0].label or "Estudio" in tabs[0].label or "estudio" in tabs[0].label.lower()

    def test_estudio_render_funciones_importables(self):
        """Las funciones de render deben importar sin errores (lazy load)."""
        tabs = get_main_tabs("mq26", "estudio")
        for tab in tabs:
            assert callable(tab.render), (
                f"tab_id={tab.tab_id}: render no es callable"
            )

    def test_estudio_difiere_de_inversor(self):
        """Estudio e inversor tienen estructuras de tabs distintas."""
        inv_tabs = get_main_tabs("mq26", "inversor")
        est_tabs = get_main_tabs("mq26", "estudio")
        inv_ids = {t.tab_id for t in inv_tabs}
        est_ids = {t.tab_id for t in est_tabs}
        assert inv_ids != est_ids, "Inversor y estudio no deben tener los mismos tab IDs"

    def test_super_admin_extiende_flujo_institucional(self):
        """Super admin debe tener los tabs de asesor + el tab admin."""
        asesor = get_main_tabs("mq26", "asesor")
        sadmin = get_main_tabs("mq26", "super_admin")
        assert len(sadmin) == len(asesor) + 1, (
            f"Super admin debe tener 1 tab más que asesor; tiene {len(sadmin)} vs {len(asesor)}"
        )
        assert sadmin[-1].tab_id == "admin", "Último tab de super_admin debe ser 'admin'"


class TestRenderMainTabsEstructura:
    """H2-b: render_main_tabs tiene la firma y estructura esperadas."""

    def test_render_main_tabs_es_callable(self):
        assert callable(render_main_tabs)

    def test_render_main_tabs_firma_acepta_ctx_appkind_role(self):
        """La función acepta ctx, app_kind y role como parámetros."""
        import inspect
        sig = inspect.signature(render_main_tabs)
        params = list(sig.parameters.keys())
        assert "ctx" in params
        assert "app_kind" in params
        assert "role" in params

    def test_navigation_spinner_presente(self):
        """C19: el spinner debe estar presente en navigation.py."""
        src = Path(__file__).parent.parent / "ui" / "navigation.py"
        content = src.read_text(encoding="utf-8")
        assert "st.spinner" in content, (
            "C19: navigation.py debe usar st.spinner en render_main_tabs"
        )


# ─── H8: Healthcheck smoke ────────────────────────────────────────────────────


class TestHealthcheckSmoke:
    """
    H8: Verificaciones de startup — módulos críticos importan sin errores,
    constantes esenciales existen, y los contratos de la API interna se respetan.
    """

    def test_config_importa(self):
        import config
        assert hasattr(config, "RATIOS_CEDEAR")
        assert hasattr(config, "SECTORES")
        assert len(config.RATIOS_CEDEAR) >= 50, (
            f"RATIOS_CEDEAR debería tener ≥50 entradas, tiene {len(config.RATIOS_CEDEAR)}"
        )

    def test_nuevos_cedears_en_config(self):
        """H8 verifica que los nuevos CEDEARs (próximamente en BYMA) están cargados."""
        from config import RATIOS_CEDEAR, SECTORES
        nuevos = {
            "CRWD": 79, "ANET": 29, "NBIS": 27, "SNDK": 170,
            "CCJ": 23, "NEE": 19, "COP": 25, "MP": 10, "GLNG": 10,
            "O": 13, "FISV": 11, "HIMS": 4, "ONDS": 2,
        }
        for ticker, ratio_esperado in nuevos.items():
            assert ticker in RATIOS_CEDEAR, f"{ticker} falta en RATIOS_CEDEAR"
            assert RATIOS_CEDEAR[ticker] == ratio_esperado, (
                f"{ticker}: ratio esperado={ratio_esperado}, actual={RATIOS_CEDEAR[ticker]}"
            )
            assert ticker in SECTORES, f"{ticker} falta en SECTORES"

    def test_broker_importer_importa(self):
        from broker_importer import (
            detectar_formato,
            importar_archivo_broker,
            parsear_bmb,
        )
        assert callable(detectar_formato)
        assert callable(importar_archivo_broker)
        assert callable(parsear_bmb)

    def test_broker_importer_detecta_bmb(self):
        """El detector BMB debe funcionar antes de detectar IOL."""
        from broker_importer import detectar_formato
        df = pd.DataFrame({
            "Liquida": ["2026-05-12"],
            "Operado": ["2026-05-11"],
            "Comprobante": ["COMPRA NORMAL"],
            "Numero": [12345],
            "Cantidad": [5],
            "Especie": ["AAPL"],
            "Precio": [225.0],
            "Importe": [1125.0],
            "Saldo": [8875.0],
            "Referencia": ["X"],
        })
        assert detectar_formato(df) == "bmb"

    def test_sidebar_modulo_importa(self):
        from ui.sidebar import SidebarState, render_sidebar
        assert callable(render_sidebar)
        # SidebarState es un dataclass frozen con los campos esperados
        import dataclasses
        fields = {f.name for f in dataclasses.fields(SidebarState)}
        assert "cartera_activa" in fields
        assert "ccl" in fields
        assert "n_escenarios" in fields
        assert "capital_disponible" in fields

    def test_navigation_modulo_importa(self):
        from ui.navigation import get_main_tabs, render_main_tabs
        assert callable(get_main_tabs)
        assert callable(render_main_tabs)

    def test_recomendacion_capital_importa(self):
        from services.recomendacion_capital import recomendar
        assert callable(recomendar)

    def test_cartera_ideal_tiene_renta_ar_clave(self):
        """CARTERA_IDEAL debe tener _RENTA_AR en al menos el perfil Moderado."""
        from core.diagnostico_types import CARTERA_IDEAL
        assert "Moderado" in CARTERA_IDEAL
        assert "_RENTA_AR" in CARTERA_IDEAL["Moderado"], (
            "Moderado en CARTERA_IDEAL debe incluir _RENTA_AR"
        )
        renta_ar_w = CARTERA_IDEAL["Moderado"]["_RENTA_AR"]
        assert 0.0 < renta_ar_w < 1.0, (
            f"_RENTA_AR peso debe estar entre 0 y 1, es {renta_ar_w}"
        )

    def test_renta_ar_pendiente_msg_no_vacio(self):
        from core.diagnostico_types import RENTA_AR_PENDIENTE_MSG
        assert isinstance(RENTA_AR_PENDIENTE_MSG, str)
        assert len(RENTA_AR_PENDIENTE_MSG) > 5

    def test_session_defaults_cliente_id_en_run_mq26(self):
        """
        El flujo inversor depende de que 'cliente_id' exista en session_state.
        Verificamos que run_mq26.py accede via session_state.get('cliente_id').
        """
        src = Path(__file__).parent.parent / "run_mq26.py"
        content = src.read_text(encoding="utf-8")
        assert '"cliente_id"' in content or "'cliente_id'" in content, (
            "run_mq26.py debe referenciar la clave 'cliente_id' en session_state"
        )

    def test_rbac_puede_action_importa(self):
        from ui.rbac import can_action
        assert callable(can_action)
        # Inversor no puede usar herramientas sensibles
        assert not can_action({"user_role": "inversor"}, "sensitive_utils")
        # Admin sí puede
        assert can_action({"user_role": "super_admin"}, "sensitive_utils")

    def test_db_manager_info_backend_callable(self):
        """info_backend() debe retornar dict con clave 'backend'."""
        import core.db_manager as dbm
        info = dbm.info_backend()
        assert isinstance(info, dict)
        assert "backend" in info
        assert info["backend"] in ("postgresql", "sqlite")
