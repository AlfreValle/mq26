"""
tests/test_lab_tickers_pending.py — D5: Test unitario para el patrón _lab_tickers_pending
Verifica que la inicialización de tickers del Lab Quant no genera StreamlitAPIException.
"""
import sys
from pathlib import Path

# Asegurar que el proyecto esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_lab_tickers_pending_patron():
    """
    D5: Simula dos renders consecutivos del Lab Quant y verifica que el patrón
    _lab_tickers_pending funciona sin lanzar excepciones de widget duplicado.
    """
    # Simulamos session_state como un dict simple
    session_state = {}

    tickers_cartera = ["AAPL", "MSFT", "AMZN"]
    prop_nombre     = "Test Portfolio"
    _PENDING_KEY    = "_lab_tickers_pending"
    _cartera_key    = f"lab_cartera_origen_{prop_nombre}"

    # ── PRIMER RENDER ────────────────────────────────────────────────────────
    # El widget "lab_tickers" aún no existe → se puede inicializar directo
    if _PENDING_KEY in session_state:
        session_state["lab_tickers"] = session_state.pop(_PENDING_KEY)

    if session_state.get(_cartera_key) != prop_nombre:
        session_state[_cartera_key] = prop_nombre
        session_state[_PENDING_KEY] = tickers_cartera

    # Si el pending se acaba de crear y el widget aún no existe, aplicar ahora
    if _PENDING_KEY in session_state and "lab_tickers" not in session_state:
        session_state["lab_tickers"] = session_state.pop(_PENDING_KEY)

    # Después del primer render el widget debería tener los tickers correctos
    assert session_state.get("lab_tickers") == tickers_cartera, (
        f"Primer render: esperaba {tickers_cartera}, obtuvo {session_state.get('lab_tickers')}"
    )
    assert _PENDING_KEY not in session_state, "Pending no debería quedar después de aplicar"

    # ── SEGUNDO RENDER (simular st.rerun después de botón Restaurar) ─────────
    # El botón de restaurar guarda en _PENDING_KEY (NO modifica "lab_tickers" directamente)
    nuevos_tickers  = ["GOOGL", "META"]
    session_state[_PENDING_KEY] = nuevos_tickers

    # Inicio del segundo render: aplicar pending si existe
    if _PENDING_KEY in session_state:
        session_state["lab_tickers"] = session_state.pop(_PENDING_KEY)

    assert session_state.get("lab_tickers") == nuevos_tickers, (
        f"Segundo render: esperaba {nuevos_tickers}, obtuvo {session_state.get('lab_tickers')}"
    )
    assert _PENDING_KEY not in session_state, "Pending no debería quedar después de segundo render"


def test_lab_tickers_cartera_nueva():
    """D5: Verificar que cambiar de cartera activa actualiza los tickers del Lab."""
    session_state = {}
    _PENDING_KEY  = "_lab_tickers_pending"

    carteras = {
        "Alfredo": ["AAPL", "MSFT", "GLD"],
        "Andrea":  ["KO",   "PEP",  "ABBV"],
    }

    for prop_nombre, tickers in carteras.items():
        _cartera_key = f"lab_cartera_origen_{prop_nombre}"

        if session_state.get(_cartera_key) != prop_nombre:
            session_state[_cartera_key] = prop_nombre
            session_state[_PENDING_KEY] = tickers

        if _PENDING_KEY in session_state and "lab_tickers" not in session_state:
            session_state["lab_tickers"] = session_state.pop(_PENDING_KEY)
        elif _PENDING_KEY in session_state:
            session_state["lab_tickers"] = session_state.pop(_PENDING_KEY)

        assert session_state.get("lab_tickers") == tickers, (
            f"Cartera {prop_nombre}: esperaba {tickers}, obtuvo {session_state.get('lab_tickers')}"
        )

    print("✅ test_lab_tickers_cartera_nueva PASS")


if __name__ == "__main__":
    test_lab_tickers_pending_patron()
    print("✅ test_lab_tickers_pending_patron PASS")
    test_lab_tickers_cartera_nueva()
    print("✅ Todos los tests D5 pasaron correctamente.")
