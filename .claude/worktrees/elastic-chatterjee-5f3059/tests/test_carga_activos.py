"""Smoke y lógica ligera para ui/carga_activos y renta fija."""
import importlib.util
from datetime import date

import pandas as pd


def test_carga_activos_importa_sin_crash():
    import ui.carga_activos as m

    assert callable(getattr(m, "render_carga_activos", None))
    assert callable(getattr(m, "aplicar_vaciar_cartera", None))


def test_broker_to_maestra_rows_venta_negativa():
    from ui.carga_activos import _broker_to_maestra_rows

    df = pd.DataFrame([
        {"Tipo_Op": "COMPRA", "TICKER": "A", "CANTIDAD": 10, "Precio_ARS": 1000.0, "Fecha": date(2026, 1, 1)},
        {"Tipo_Op": "VENTA", "TICKER": "A", "CANTIDAD": 3, "Precio_ARS": 1100.0, "Fecha": date(2026, 2, 1)},
    ])
    ctx = {"cartera_activa": "Test | Libro", "ccl": 1000.0}
    solo_c = _broker_to_maestra_rows(df, ctx, incluir_ventas=False)
    assert len(solo_c) == 1
    assert solo_c[0]["CANTIDAD"] == 10
    mix = _broker_to_maestra_rows(df, ctx, incluir_ventas=True)
    assert len(mix) == 2
    assert mix[1]["CANTIDAD"] == -3


def test_tir_efectiva_menor_paridad_mayor_rendimiento():
    from core.renta_fija_ar import tir_al_precio

    assert tir_al_precio("TLCTO", 95.0) > tir_al_precio("TLCTO", 105.0)


def test_valor_nominal_a_ars_escala_con_ccl():
    from core.renta_fija_ar import valor_nominal_a_ars

    assert valor_nominal_a_ars(1000, 100.0, 1150) == 1_150_000.0


def test_instrumentos_rf_tienen_campos_obligatorios():
    from core.renta_fija_ar import INSTRUMENTOS_RF

    for _t, meta in INSTRUMENTOS_RF.items():
        assert meta.get("emisor")
        assert meta.get("tipo")
        assert meta.get("vencimiento")
        assert meta.get("tir_ref") is not None


def test_carga_cedear_no_importa_streamlit_en_logica():
    src = importlib.util.find_spec("core.renta_fija_ar").origin  # type: ignore[attr-defined]
    with open(src, encoding="utf-8") as f:
        body = f.read()
    assert "import streamlit" not in body


def test_broker_importar_archivo_csv_vacio_no_crash():
    import io

    import pandas as pd

    from broker_importer import ImportBrokerResult, importar_archivo_broker

    class _F:
        name = "x.csv"
        _data = b"CARTERA,x\n"

        def read(self):
            return self._data

        def seek(self, n):
            pass

    res = importar_archivo_broker(_F(), "P", "C", ccl=1000.0)
    assert isinstance(res, ImportBrokerResult)
    assert isinstance(res.df, pd.DataFrame)
    assert res.df.empty
