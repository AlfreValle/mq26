"""Suite de integración por rol en entrypoints críticos."""
from __future__ import annotations

from pathlib import Path

from ui.navigation import get_main_tabs


ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


def test_app_main_define_gate_sensible_por_rol():
    src = _read("app_main.py")
    assert "from ui.rbac import can_action as _can_action_rbac" in src
    assert '_can_sensitive_utils = _can_action_rbac({"user_role": _app_role_sidebar}, "sensitive_utils")' in src


def test_app_main_botones_sensibles_bloqueados_para_no_admin():
    src = _read("app_main.py")
    checks = [
        'st.button("🔄 Regenerar posiciones desde Excel", key="btn_regen_csv", disabled=not _can_manage_data)',
        'st.button("🗑️ Resetear todo (punto cero)", key="btn_reset_confirm", disabled=not _can_manage_data)',
        'st.button("✅ Sí, borrar", key="btn_reset_si", type="primary", disabled=not _can_manage_data)',
        'st.button("💾 Aplicar precios", key="btn_aplicar_fb", disabled=not _can_sensitive_utils)',
        'st.button("🔔 Probar conexión", disabled=not _can_sensitive_utils)',
    ]
    for frag in checks:
        assert frag in src, f"Falta gate sensible en app_main: {frag}"


def test_run_mq26_define_gate_sensible_por_rol():
    src = _read("run_mq26.py")
    assert "from ui.rbac import can_action as _can_action_rbac" in src
    assert '_mq26_can_sensitive_utils = _can_action_rbac({"user_role": _mq26_role}, "sensitive_utils")' in src


def test_run_mq26_utilidades_sensibles_en_deny_by_default():
    src = _read("run_mq26.py")
    checks = [
        'disabled=_bloqueado or (not _mq26_can_sensitive_utils)',
        'key="editor_fallback_sb", hide_index=True, disabled=not _mq26_can_sensitive_utils',
        'st.button("💾 Aplicar precios", key="btn_aplicar_fb", disabled=not _mq26_can_sensitive_utils)',
        'st.button("💾 Guardar capital", key="btn_guardar_cap", disabled=not _mq26_can_sensitive_utils)',
        'st.button("💾 Guardar credenciales", key="btn_tg_guardar", disabled=not _mq26_can_sensitive_utils)',
        'st.button("🔔 Probar conexión", key="btn_tg_probar", disabled=not _mq26_can_sensitive_utils)',
    ]
    for frag in checks:
        assert frag in src, f"Falta gate sensible en run_mq26: {frag}"


def test_navigation_matrix_por_rol_y_entrypoint():
    # app_main (app): inversor 4 tabs
    app_inv = get_main_tabs("app", "inversor")
    assert len(app_inv) == 4
    assert [t.tab_id for t in app_inv] == ["cartera", "como_va", "ejecucion", "reporte"]

    # app_main (app): estudio/admin flujo institucional 6
    app_est = get_main_tabs("app", "estudio")
    assert len(app_est) == 6
    assert app_est[0].tab_id == "cartera"

    # run_mq26: inversor experiencia compacta 1 tab
    mq_inv = get_main_tabs("mq26", "inversor")
    assert len(mq_inv) == 1
    assert mq_inv[0].tab_id == "mi_cartera"

    # run_mq26: estudio 4 tabs torre
    mq_est = get_main_tabs("mq26", "estudio")
    assert len(mq_est) == 4
    assert [t.tab_id for t in mq_est] == ["estudio", "cartera", "reporte", "universo"]


def test_run_mq26_usa_render_main_tabs_ssot_p1_nav01():
    """P1-NAV-01: run_mq26 no duplica st.tabs por rol; usa navigation SSOT."""
    src = _read("run_mq26.py")
    assert 'from ui.navigation import render_main_tabs' in src
    assert 'render_main_tabs(ctx, app_kind="mq26", role=_mq26_role)' in src
    assert "st.tabs([" not in src
