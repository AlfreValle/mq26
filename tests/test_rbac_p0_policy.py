"""
P0-RBAC-02 — Tests deny/allow por rol sobre ``can_action`` (``ui/rbac.py``).

Matriz acordada (rol en filas, acción en columnas; ✓ = permitido, ✗ = denegado):

                    write   read   sensitive_utils   panel_admin_write
  (vacío / anon)      ✗      ✗          ✗                  ✗
  inversor            ✗      ✓          ✗                  ✗
  viewer              ✗      ✓          ✗                  ✗
  estudio             ✓      ✓          ✗                  ✗
  asesor              ✓      ✓          ✗                  ✗
  admin               ✓      ✓          ✓                  ✗
  super_admin         ✓      ✓          ✓                  ✓

Fuente única de verdad: ``ui/rbac.ACTION_POLICY``. Si cambia la política, actualizar
esta matriz y los expected parametrizados abajo.
"""
from __future__ import annotations

import pytest

from ui.rbac import ACTION_POLICY, can_action

# (user_role, action, expected)
_MATRIX: list[tuple[str | None, str, bool]] = []

for _role in ("", "inversor", "viewer", "estudio", "asesor", "admin", "super_admin"):
    ctx = {"user_role": _role} if _role else {}
    for _action, _allowed_roles in ACTION_POLICY.items():
        _rnorm = (_role or "").strip().lower()
        _expect = _rnorm in {x.strip().lower() for x in _allowed_roles}
        _MATRIX.append((_role, _action, _expect))


@pytest.mark.parametrize("user_role,action,expected", _MATRIX)
def test_can_action_matrix_p0_rbac(user_role: str | None, action: str, expected: bool) -> None:
    ctx = {"user_role": user_role} if user_role else {}
    assert can_action(ctx, action) is expected


def test_unknown_action_deny_by_default() -> None:
    assert can_action({"user_role": "super_admin"}, "accion_inventada_xyz") is False
    assert can_action({"user_role": "super_admin"}, "accion_inventada_xyz", default=True) is True


def test_role_normalization_case_insensitive() -> None:
    assert can_action({"user_role": "SUPER_ADMIN"}, "panel_admin_write") is True
    assert can_action({"user_role": "Estudio"}, "write") is True


def test_write_explicit_denies_from_pendientes() -> None:
    """Casos nombrados en P0-RBAC-02 (viewer / contraste con estudio y asesor)."""
    assert can_action({"user_role": "viewer"}, "write") is False
    assert can_action({"user_role": "estudio"}, "write") is True
    assert can_action({"user_role": "asesor"}, "write") is True


def test_panel_admin_write_only_super_admin() -> None:
    for bad in ("viewer", "inversor", "estudio", "asesor", "admin", ""):
        assert can_action({"user_role": bad}, "panel_admin_write") is False, bad
    assert can_action({"user_role": "super_admin"}, "panel_admin_write") is True


# ─── #11: admin entra sin elegir cliente ─────────────────────────────────────

def test_entra_sin_cliente_solo_admin() -> None:
    from ui.rbac import entra_sin_cliente

    # Admin/super_admin entran directo (sin cliente); el resto pasa por el selector.
    assert entra_sin_cliente("super_admin") is True
    assert entra_sin_cliente("admin") is True
    assert entra_sin_cliente("SUPER_ADMIN") is True  # case-insensitive
    for r in ("inversor", "estudio", "asesor", "viewer", "", None):
        assert entra_sin_cliente(r) is False, r


def test_entra_sin_cliente_forzar_selector_obliga_a_elegir() -> None:
    from ui.rbac import entra_sin_cliente

    # "🔄 Cambiar cliente" fuerza el selector incluso para el admin.
    assert entra_sin_cliente("super_admin", forzar_selector=True) is False
    assert entra_sin_cliente("admin", forzar_selector=True) is False
    # Para no-admin es indistinto: nunca entran directo.
    assert entra_sin_cliente("asesor", forzar_selector=False) is False
