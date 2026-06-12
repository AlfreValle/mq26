"""Tests Pilar 3 — services/recomendador_explicable.py: plan de acción auditable."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import services.recomendador_explicable as rx

# ─── Dobles ───────────────────────────────────────────────────────────────────

class PrioFake(Enum):
    CRITICA = "critica"
    MEDIA = "media"


class CatFake(Enum):
    RENTA_FIJA = "renta_fija"
    CEDEAR = "cedear"


@dataclass
class ItemFake:
    orden: int = 1
    ticker: str = "AAPL"
    nombre_legible: str = "Apple Inc"
    categoria: CatFake = CatFake.CEDEAR
    unidades: int = 5
    precio_ars_estimado: float = 30_000.0
    monto_ars: float = 150_000.0
    monto_usd: float = 103.0
    justificacion: str = "Acerca a cartera ideal: peso objetivo +2.1 pp en AAPL"
    impacto_en_balance: str = "Renta variable ↑ por compra en AAPL"
    prioridad: PrioFake = PrioFake.MEDIA
    es_activo_nuevo: bool = True


@dataclass
class RRFake:
    compras_recomendadas: list = field(default_factory=lambda: [ItemFake()])
    alerta_mercado: bool = False
    mensaje_alerta: str = ""


def _senal(senal: str = "🔴 SALIR", n_disp: int = 2) -> dict:
    return {
        "ticker": "MSFT",
        "senal": senal,
        "pnl_pct": 42.5,
        "disparadores": [
            {"tipo": "🎯 OBJETIVO ALCANZADO", "detalle": "+42.5% vs target +40%", "prioridad": "ALTA"},
            {"tipo": "📈 RSI SOBRECOMPRADO", "detalle": "RSI = 78 > 75", "prioridad": "MEDIA"},
        ][:n_disp],
    }


class _RecordFake:
    def __init__(self, *, live: bool, stale: bool):
        class _Src:
            def __init__(self, live):
                self.is_live = live
                self.value = "live_byma" if live else "fallback_bd"
        self.source = _Src(live)
        self.stale = stale
        self.timestamp = datetime(2026, 6, 12, 10, 0)


# ─── Compras ──────────────────────────────────────────────────────────────────

class TestExplicarCompras:
    def test_traduce_item_completo(self):
        recs = rx.explicar_compras(RRFake())
        assert len(recs) == 1
        r = recs[0]
        assert r.accion == "COMPRAR"
        assert r.ticker == "AAPL"
        assert r.monto_ars == 150_000.0
        assert r.prioridad == "MEDIA"
        assert r.motor == "recomendacion_capital"

    def test_motivos_atomicos_con_origen(self):
        r = rx.explicar_compras(RRFake())[0]
        textos = [m.texto for m in r.motivos]
        assert any("cartera ideal" in t for t in textos)
        assert any("Renta variable" in t for t in textos)
        assert any("Activo nuevo" in t for t in textos)
        assert all(m.origen == "motor_capital" for m in r.motivos)

    def test_ficha_disponible_para_rv(self):
        r = rx.explicar_compras(RRFake())[0]
        assert r.tiene_ficha  # AAPL es RV del maestro

    def test_rr_vacio(self):
        assert rx.explicar_compras(RRFake(compras_recomendadas=[])) == []


class TestConfianza:
    def test_precio_live_alta(self):
        recs = rx.explicar_compras(
            RRFake(), precio_records={"AAPL": _RecordFake(live=True, stale=False)}
        )
        assert recs[0].confianza == rx.CONFIANZA_ALTA
        assert not recs[0].advertencias

    def test_precio_stale_baja_con_advertencia(self):
        recs = rx.explicar_compras(
            RRFake(), precio_records={"AAPL": _RecordFake(live=False, stale=True)}
        )
        assert recs[0].confianza == rx.CONFIANZA_BAJA
        assert any("frescura" in a for a in recs[0].advertencias)

    def test_sin_record_media(self):
        recs = rx.explicar_compras(RRFake(), precio_records={})
        assert recs[0].confianza == rx.CONFIANZA_MEDIA


# ─── Señales de salida ────────────────────────────────────────────────────────

class TestExplicarSalidas:
    def test_salir_es_vender_critica(self):
        recs = rx.explicar_senales_salida([_senal("🔴 SALIR")])
        assert len(recs) == 1
        r = recs[0]
        assert r.accion == "VENDER"
        assert r.prioridad == "CRITICA"
        assert "+42.5%" in r.tesis
        assert "2 disparador" in r.tesis

    def test_disparadores_son_motivos(self):
        r = rx.explicar_senales_salida([_senal()])[0]
        assert len(r.motivos) == 2
        assert any("OBJETIVO ALCANZADO" in m.texto for m in r.motivos)
        assert all(m.origen == "motor_salida" for m in r.motivos)

    def test_atencion_es_revisar(self):
        r = rx.explicar_senales_salida([_senal("🟡 ATENCIÓN", n_disp=1)])[0]
        assert r.accion == "REVISAR"
        assert r.prioridad == "MEDIA"

    def test_en_camino_no_genera_accion(self):
        assert rx.explicar_senales_salida([_senal("⚪ EN CAMINO")]) == []

    def test_none_ok(self):
        assert rx.explicar_senales_salida(None) == []


# ─── Plan completo ────────────────────────────────────────────────────────────

class TestPlanAccion:
    def test_plan_combina_ambos_motores(self):
        plan = rx.construir_plan_accion(
            perfil="Moderado",
            rr=RRFake(),
            senales=[_senal()],
            capital_ars=500_000.0,
        )
        assert plan.n_acciones == 2
        assert "1 compra(s)" in plan.resumen
        assert "1 posición(es) a revisar" in plan.resumen
        assert "1 con salida sugerida" in plan.resumen

    def test_plan_vacio_dice_alineada(self):
        plan = rx.construir_plan_accion(perfil="Moderado")
        assert plan.n_acciones == 0
        assert "alineada" in plan.resumen

    def test_alerta_mercado_en_resumen(self):
        plan = rx.construir_plan_accion(
            perfil="Moderado",
            rr=RRFake(alerta_mercado=True, mensaje_alerta="VIX alto: entrada escalonada."),
        )
        assert plan.alerta_mercado == "VIX alto: entrada escalonada."
        assert "VIX alto" in plan.resumen

    def test_precios_viejos_avisa_en_resumen(self):
        plan = rx.construir_plan_accion(
            perfil="Moderado",
            rr=RRFake(),
            precio_records={"AAPL": _RecordFake(live=False, stale=True)},
        )
        assert "precios viejos" in plan.resumen

    def test_serializable(self):
        import json

        plan = rx.construir_plan_accion(perfil="Moderado", rr=RRFake(), senales=[_senal()])
        assert json.dumps(plan.to_dict())


# ─── Audit trail ──────────────────────────────────────────────────────────────

class TestAuditoria:
    def test_auditar_persiste_payload_completo(self, monkeypatch):
        capturado = {}

        def _fake_registrar(**kwargs):
            capturado.update(kwargs)
            return 77

        import services.audit_trail as at

        monkeypatch.setattr(at, "registrar_recomendacion_evento", _fake_registrar)
        plan = rx.construir_plan_accion(perfil="Moderado", rr=RRFake(), capital_ars=100_000.0)
        rid = rx.auditar_plan(plan, ctx={"cliente_nombre": "Test", "login_user": "alfredo"})
        assert rid == 77
        assert capturado["evento"] == "PLAN_ACCION_EXPLICADO"
        assert capturado["filas"] == 1
        assert capturado["payload"]["comprar"][0]["ticker"] == "AAPL"
        assert capturado["payload"]["comprar"][0]["motivos"]  # motivos viajan al audit

    def test_auditar_nunca_rompe(self, monkeypatch):
        import services.audit_trail as at

        def _boom(**kwargs):
            raise RuntimeError("BD caída")

        monkeypatch.setattr(at, "registrar_recomendacion_evento", _boom)
        plan = rx.construir_plan_accion(perfil="Moderado")
        assert rx.auditar_plan(plan) is None
