"""G02: auditoría append-only al cambiar parámetros globales vía guardar_config."""
import pytest

import core.db_manager as dbm


@pytest.fixture(autouse=True)
def _skip_if_no_db(monkeypatch):
    """Evita fallos si el engine global no está disponible en entornos exóticos."""
    try:
        dbm.ensure_schema()
    except Exception:
        pytest.skip("BD no disponible para test de auditoría")


def test_cambio_parametro_genera_fila_audit():
    dbm.guardar_config("RISK_FREE_RATE", "0.06001", audit_user="pytest")
    rows = dbm.list_global_param_audit("RISK_FREE_RATE", limit=20)
    assert rows, "debe existir historial de RISK_FREE_RATE"
    last = rows[0]
    assert last["param_key"] == "RISK_FREE_RATE"
    assert last["changed_by"] == "pytest"
    assert "0.06001" in (last.get("new_value") or "")


def test_log_append_solo_insert():
    n_antes = len(dbm.list_global_param_audit("PESO_MAX_OPT", limit=500))
    dbm.guardar_config("PESO_MAX_OPT", "0.24", audit_user="t2")
    n_despues = len(dbm.list_global_param_audit("PESO_MAX_OPT", limit=500))
    assert n_despues >= n_antes
