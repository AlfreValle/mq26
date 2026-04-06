from core.historical_cache import (
    historico_cache_clear,
    historico_cache_get,
    historico_cache_key,
    historico_cache_set,
)


def test_cache_key_cambia_si_cambia_universo():
    a = historico_cache_key(["B", "A"], "1y", align_calendar_strict=True, relax_alignment_if_short=True, min_filas=30)
    b = historico_cache_key(["A", "C"], "1y", align_calendar_strict=True, relax_alignment_if_short=True, min_filas=30)
    assert a != b


def test_cache_hit_devuelve_copia():
    historico_cache_clear()
    import pandas as pd

    k = historico_cache_key(["X"], "1y", align_calendar_strict=True, relax_alignment_if_short=False, min_filas=10)
    df = pd.DataFrame({"X": [1.0, 2.0]})
    historico_cache_set(k, df)
    g = historico_cache_get(k)
    assert g is not None
    assert g["X"].tolist() == [1.0, 2.0]
    g.loc[0, "X"] = 99.0
    g2 = historico_cache_get(k)
    assert float(g2.iloc[0]["X"]) == 1.0
