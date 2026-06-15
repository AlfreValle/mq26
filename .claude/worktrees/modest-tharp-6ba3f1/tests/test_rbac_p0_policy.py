"""
P0-RBAC-02 — Tests deny/allow por rol sobre ``can_action`` (``ui/rbac.py``).

Matriz acordada (rol en filas, acción en columnas; ✓ = permitido, ✗ = denegado):

                    write   read   sensitive_utils   panel_admin_write
  (vacío / anon)      ✗      ✗          ✗                  ✗
  inversor            ✗      ✓          ✗                  ✗
  viewer              ✗      ✓          ✗                  ✗
  estudio             ✓      ✓          ✗                  ✗
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

for _role in ("", "inversor", "viewer", "estudio", "admin", "super_admin"):
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
    """Casos nombrados en P0-RBAC-02 (viewer / contraste con estudio y admin)."""
    assert can_action({"user_role": "viewer"}, "write") is False
    assert can_action({"user_role": "estudio"}, "write") is True
    assert can_action({"user_role": "admin"}, "write") is True


def test_panel_admin_write_only_super_admin() -> None:
    for bad in ("viewer", "inversor", "estudio", "admin", ""):
        assert can_action({"user_role": bad}, "panel_admin_write") is False, bad
    assert can_action({"user_role": "super_admin"}, "panel_admin_write") is True
