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
    """
    Verifica que los gates de seguridad (disabled=not can_sensitive) existen.

    Tras el refactor B10+C3, la lógica del sidebar se desaclopó a ui/sidebar.py.
    El gate se calcula en run_mq26.py (_mq26_can_sensitive_utils) y se pasa
    como parámetro can_sensitive a render_sidebar(), que aplica disabled= en cada widget.
    """
    # run_mq26.py aún define el gate y lo pasa a render_sidebar
    src_main = _read("run_mq26.py")
    assert "_mq26_can_sensitive_utils" in src_main, (
        "run_mq26.py debe definir _mq26_can_sensitive_utils"
    )
    assert "can_sensitive=_mq26_can_sensitive_utils" in src_main, (
        "run_mq26.py debe pasar can_sensitive a render_sidebar"
    )

    # ui/sidebar.py aplica el gate en todos los widgets sensibles
    src_sb = _read("ui/sidebar.py")
    checks = [
        "disabled=not can_sensitive",           # gate genérico (varios widgets)
        'key="btn_regen_csv"',                  # botón sincronización
        'key="editor_fallback_sb"',             # editor de precios fallback
        'key="btn_aplicar_fb"',                 # aplicar precios
        'key="btn_guardar_cap"',                # guardar capital
        'key="btn_tg_guardar"',                 # guardar credenciales Telegram
        'key="btn_tg_probar"',                  # probar conexión Telegram
    ]
    for frag in checks:
        assert frag in src_sb, f"Falta gate/widget sensible en ui/sidebar.py: {frag}"


def test_navigation_matrix_por_rol_y_entrypoint():
    # app_main (app): inversor 4 tabs
    app_inv = get_main_tabs("app", "inversor")
    assert len(app_inv) == 4
    assert [t.tab_id for t in app_inv] == ["cartera", "como_va", "ejecucion", "reporte"]

    # app_main (app): asesor/admin flujo institucional 6
    app_ases = get_main_tabs("app", "asesor")
    assert len(app_ases) == 6
    assert app_ases[0].tab_id == "cartera"

    # run_mq26: inversor — 3 tabs (Mi Cartera + Plan de Objetivos + Perlas)
    mq_inv = get_main_tabs("mq26", "inversor")
    assert len(mq_inv) == 3
    assert mq_inv[0].tab_id == "mi_cartera"
    assert mq_inv[1].tab_id == "plan_objetivos"
    assert mq_inv[2].tab_id == "perlas"

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
