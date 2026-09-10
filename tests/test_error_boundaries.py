"""error_boundaries delega en el componente de mq26_ux (paleta real)."""
from __future__ import annotations

from ui.error_boundaries import error_block_html


def test_error_block_html_usa_clase_del_design_system():
    html = error_block_html("Fallo", "No se pudo cargar")
    assert "mq-error-boundary" in html
    assert 'role="alert"' in html
    assert "#b84a5f" not in html
    assert "Fallo" in html
    assert "No se pudo cargar" in html
