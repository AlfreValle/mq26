"""Tests Pilar 4 — services/salud_datos.py: monitor de salud de datos."""
from __future__ import annotations

from datetime import date, datetime

import services.salud_datos as sd


class _SrcFake:
    def __init__(self, value: str, live: bool):
        self.value = value
        self.is_live = live


class _RecFake:
    def __init__(self, src: str = "live_byma", live: bool = True, stale: bool = False):
        self.source = _SrcFake(src, live)
        self.stale = stale
        self.timestamp = datetime(2026, 6, 12, 10, 0)


class TestChequeoCclSpot:
    def test_ccl_live_ok(self):
        ch = sd._chequeo_ccl_spot(1452.3)
        assert ch.estado == sd.OK

    def test_ccl_fallback_avisa(self):
        from config import CCL_FALLBACK

        ch = sd._chequeo_ccl_spot(float(CCL_FALLBACK))
        assert ch.estado == sd.AVISO
        assert ch.valor["es_fallback"]

    def test_ccl_cero_critico(self):
        assert sd._chequeo_ccl_spot(0).estado == sd.CRITICO


class TestChequeoSerieCcl:
    def test_al_dia_ok(self, monkeypatch):
        import core.pricing_utils as pu

        monkeypatch.setattr(pu, "CCL_HISTORICO", {"2026-05": 1450.0, "2026-06": 1460.0})
        ch = sd._chequeo_serie_ccl(hoy=date(2026, 6, 12))
        assert ch.estado == sd.OK

    def test_tres_meses_atraso_avisa(self, monkeypatch):
        import core.pricing_utils as pu

        monkeypatch.setattr(pu, "CCL_HISTORICO", {"2026-03": 1465.0})
        ch = sd._chequeo_serie_ccl(hoy=date(2026, 6, 12))
        assert ch.estado == sd.AVISO
        assert ch.valor["meses_atraso"] == 3

    def test_cinco_meses_critico(self, monkeypatch):
        import core.pricing_utils as pu

        monkeypatch.setattr(pu, "CCL_HISTORICO", {"2026-01": 1420.0})
        ch = sd._chequeo_serie_ccl(hoy=date(2026, 6, 12))
        assert ch.estado == sd.CRITICO


class TestChequeoCatalogoRf:
    def test_paridades_frescas_ok(self, monkeypatch):
        import core.renta_fija_ar as rf

        monkeypatch.setattr(rf, "INSTRUMENTOS_RF", {
            "XX1O": {"activo": True, "fecha_ref": "2026-06-01"},
        })
        ch = sd._chequeo_catalogo_rf(hoy=date(2026, 6, 12))
        assert ch.estado == sd.OK

    def test_paridad_vieja_critico(self, monkeypatch):
        import core.renta_fija_ar as rf

        monkeypatch.setattr(rf, "INSTRUMENTOS_RF", {
            "XX1O": {"activo": True, "fecha_ref": "2026-01-15"},
            "XX2O": {"activo": False, "fecha_ref": "2020-01-01"},  # inactivo no cuenta
        })
        ch = sd._chequeo_catalogo_rf(hoy=date(2026, 6, 12))
        assert ch.estado == sd.CRITICO
        assert ch.valor["instrumentos_activos"] == 1


class TestChequeoPrecios:
    def test_todo_live_ok(self):
        recs = {"A": _RecFake(), "B": _RecFake()}
        chs = sd._chequeo_precios(recs)
        assert all(c.estado == sd.OK for c in chs)

    def test_missing_critico(self):
        recs = {"A": _RecFake("missing", live=False)}
        cob = next(c for c in sd._chequeo_precios(recs) if c.nombre == "Cobertura de precios")
        assert cob.estado == sd.CRITICO

    def test_mucho_fallback_avisa(self):
        recs = {"A": _RecFake("fallback_bd", live=False), "B": _RecFake("fallback_bd", live=False)}
        cob = next(c for c in sd._chequeo_precios(recs) if c.nombre == "Cobertura de precios")
        assert cob.estado == sd.AVISO

    def test_stale_masivo_critico(self):
        recs = {
            "A": _RecFake("fallback_bd", live=False, stale=True),
            "B": _RecFake(),
        }
        fr = next(c for c in sd._chequeo_precios(recs) if c.nombre == "Frescura de precios")
        assert fr.estado == sd.CRITICO  # 50% stale > 30%

    def test_sin_records_avisa(self):
        chs = sd._chequeo_precios(None)
        assert chs[0].estado == sd.AVISO


class TestSnapshot:
    def test_snapshot_nunca_lanza_y_agrega_todo(self, monkeypatch):
        # Cache y auditoría rotos no tumban el monitor
        monkeypatch.setattr(
            sd, "_chequeo_fundamentals_cache",
            lambda: sd.ChequeoSalud("Caché de fundamentals", sd.AVISO, "x", {}),
        )
        monkeypatch.setattr(
            sd, "_chequeo_auditoria",
            lambda: sd.ChequeoSalud("Audit trail", sd.OK, "x", {}),
        )
        s = sd.snapshot_salud_datos(ccl=1450.0, precio_records={"A": _RecFake()})
        nombres = {c.nombre for c in s.chequeos}
        assert {"CCL spot", "Serie CCL histórica", "Catálogo RF",
                "Cobertura de precios", "Frescura de precios"} <= nombres

    def test_semaforo_global_es_el_peor(self):
        s = sd.SaludDatos(generado_utc="x", chequeos=[
            sd.ChequeoSalud("a", sd.OK, "", {}),
            sd.ChequeoSalud("b", sd.CRITICO, "", {}),
            sd.ChequeoSalud("c", sd.AVISO, "", {}),
        ])
        assert s.semaforo_global == sd.CRITICO

    def test_serializable(self, monkeypatch):
        import json

        monkeypatch.setattr(
            sd, "_chequeo_auditoria",
            lambda: sd.ChequeoSalud("Audit trail", sd.OK, "x", {}),
        )
        s = sd.snapshot_salud_datos(ccl=1450.0)
        assert json.dumps(s.to_dict())
