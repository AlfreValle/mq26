"""Purga de cachés de mercado y CCL live vs fallback."""
from __future__ import annotations

from core.purga_caches import purgar_caches_mercado


def test_purgar_caches_mercado_retorna_conteos():
    out = purgar_caches_mercado()
    assert isinstance(out, dict)
    assert "fundamentales_json" in out
    assert "scores_pkl" in out
    assert all(isinstance(v, int) for v in out.values())


def test_borrar_glob_oserror_al_listar_no_propaga():
    """Listar un dir de nube/permisos no puede tirar el arranque."""
    from unittest.mock import MagicMock

    from core.purga_caches import _borrar_glob

    d = MagicMock()
    d.is_dir.return_value = True
    d.glob.side_effect = OSError("cloud lock")
    assert _borrar_glob(d, "*.pkl") == 0


def test_borrar_glob_oserror_en_is_dir_no_propaga():
    from unittest.mock import MagicMock

    from core.purga_caches import _borrar_glob

    d = MagicMock()
    d.is_dir.side_effect = OSError("permission denied")
    assert _borrar_glob(d, "*.pkl") == 0
