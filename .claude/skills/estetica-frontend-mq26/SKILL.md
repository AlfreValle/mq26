---
name: estetica-frontend-mq26
description: Diseña y revisa la UI de MQ26 con su design system real (paleta WCAG, tokens CSS, componentes mq26_ux, temas por rol). Usar al crear/ajustar pantallas Streamlit, tocar HTML/CSS, o cuando el usuario hable de estética, layout, contraste, redundancia visual o consistencia de fronts.
---

# Estética de frontend MQ26

MQ26 tiene un design system propio (no improvisar colores ni HTML suelto).
Antes de tocar UI, usá estas piezas — todo lo visual sale de acá.

## Fuentes de verdad (leer antes de diseñar)

- **`ui/color_palette.py`** — `PALETTE` (dataclass congelada) + helpers:
  `semaforo_color(score)`, `color_recomendacion()`, `color_rsi()`, `color_score()`,
  `badge_html()`. Los colores están auditados WCAG AA/AAA — NO inventar hex.
- **`assets/style.css`** — variables `:root` (usar SIEMPRE en vez de hex crudos):
  - Fondos: `--c-bg` `--c-surface` `--c-surface-2/3` `--c-surface-elevated`
  - Texto: `--c-text` `--c-text-2` `--c-text-3` (jerarquía, no usar gris arbitrario)
  - Acento: `--c-accent` (#4f8ef7 azul acero) `--c-accent-2/3/muted/glow`
  - Semáforo: `--c-green/yellow/red` + `-muted/-glow`
  - Prioridades: `--c-prio-critica/alta/media/baja`
  - Tipografía: `--font-ui` (Inter), `--font-mono` (JetBrains), `--text-xs…2xl`,
    `--fw-*`, `--tracking-*`, `--leading-*` (escala modular 1.25)
  - Espaciado: `--space-0…20`, `--gap-sm/md/lg/xl`; radios `--r-sm/md/lg/pill`;
    sombras `--shadow-sm/md/lg`; animaciones `--ease*` `--dur-*`; breakpoints `--bp-*`
- **`ui/mq26_ux.py`** — componentes reutilizables. REUSAR, no recrear:
  `metric_card_html`, `semaforo_html`, `obs_card_html`, `topline_html`,
  `defensive_bar_html`, `hero_alignment_bar_html`, `fig_torta_ideal`,
  `plotly_chart_layout_base`, `dataframe_auto_height`, `render_breadcrumb`,
  `get_tooltip` (tooltips de métricas: Sharpe, Sortino, Kelly, CVaR…).
- **`ui/mq26_theme.py`** — bundle CSS (`build_theme_css_bundle`), tema retail
  claro activable con env `MQ26_RETAIL_LIGHT=1`.
- **`docs/product/COMITE_UX_DESIGN_SYSTEM_M41_M539.md`** — el marco completo.

## Reglas de estilo (no negociables)

1. **Colores solo del sistema**: variables CSS `--c-*` o `PALETTE`. Cero hex sueltos
   en HTML inline nuevo.
2. **Texto con jerarquía**: `--c-text` (principal) → `--c-text-2` (secundario) →
   `--c-text-3` (sutil). Contraste mínimo AA (PALETTE ya lo garantiza).
3. **Clases con prefijo**: `mq-` global, `mq-inv-*` inversor, `mq-estudio-*`
   estudio, `mq26-metric-card`, `mq-pill*`, `mq-sem-*`. Una clase nueva sigue el
   prefijo del dominio.
4. **Tablas con altura responsiva**: `dataframe_auto_height(df)`, no alturas fijas.
5. **Plotly**: `plotly_chart_layout_base()` para fondo transparente + fuente del tema.
6. **Rol/tier**: inversor = retail (clase `.mq-inversor`, métricas grandes);
   asesor/estudio/admin = profesional. No mezclar densidades.
7. **Mobile**: la app declara breakpoints; las columnas deben apilar <768px
   (ver `css_hub_responsive_block`).

## Antipatrones a corregir (los que ya aparecieron en review)

- **Vista duplicada del mismo dato** (ej. dos `st.dataframe` de la misma lista):
  consolidar en una vista rica + selector, no repetir la tabla.
- HTML inline con hex hardcodeado en vez de variable CSS.
- Altura fija en dataframes (rompe en pantallas chicas).
- Texto gris arbitrario sin nivel de jerarquía.
- Emojis como única señal de estado sin texto (accesibilidad).

## Flujo al ajustar UI

1. Identificar el componente/dominio y su prefijo de clase.
2. Reusar componente de `mq26_ux` si existe; si no, crearlo ahí (no inline en la tab).
3. Colores/espaciado solo con tokens.
4. Verificar contraste (PALETTE) y apilado mobile.
5. Smoke con el mock de Streamlit (ver tests/test_plan_pruebas_mq26_ui.py) + ruff.
6. Commit `feat(ui)`/`fix(ui)` enfocado.
