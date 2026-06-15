"""tests/test_investor_hub_snapshot.py — P3-EXC-01 / Fase C: contrato hub inversor."""
from services.investor_hub_snapshot import build_investor_hub_snapshot


def test_hub_incluye_ruleset_cold_start_y_patrimonio_override():
    class _P:
        value = "alta"

    class _O:
        titulo = "Concentración"
        cifra_clave = "18%"
        prioridad = _P()

    class _Sem:
        value = "amarillo"

    class _D:
        score_total = 65.0
        semaforo = _Sem()
        titulo_semaforo = "Estado"
        resumen_ejecutivo = "Resumen"
        pct_defensivo_actual = 0.3
        pct_defensivo_requerido = 0.35
        valor_cartera_usd = 100.0
        n_posiciones = 2
        rendimiento_ytd_usd_pct = 1.0
        modo_fallback = True
        observaciones = [_O()]
        ruleset_version = "2026.04.test"
        perfil = "Moderado"
        horizonte_label = "Largo"

    snap = build_investor_hub_snapshot(
        _D(),
        {"total_valor": 99.0},
        1400.0,
        valor_total_ars=250_000.0,
    )
    assert snap["ruleset_version"] == "2026.04.test"
    assert snap["cold_start"] is True
    assert snap["patrimonio_total_ars"] == 250_000.0
    assert snap["semaforo"] == "amarillo"
    assert snap["alignment_score_pct"] == 65.0
    assert len(snap["acciones_top"]) == 1
    assert snap["acciones_top"][0]["titulo"] == "Concentración"
    assert snap["acciones_top"][0]["prioridad"] == "alta"
    assert snap["acciones_top"][0]["cifra"] == "18%"


def test_hub_semaforo_default_amarillo_sin_objeto():
    class _D:
        score_total = 50.0
        semaforo = None
        titulo_semaforo = ""
        resumen_ejecutivo = ""
        pct_defensivo_actual = 0.5
        pct_defensivo_requerido = 0.5
        valor_cartera_usd = 0.0
        n_posiciones = 0
        rendimiento_ytd_usd_pct = 0.0
        modo_fallback = False
        observaciones = []
        ruleset_version = ""
        perfil = ""
        horizonte_label = ""

    snap = build_investor_hub_snapshot(_D(), {}, 1000.0)
    assert snap["semaforo"] == "amarillo"
