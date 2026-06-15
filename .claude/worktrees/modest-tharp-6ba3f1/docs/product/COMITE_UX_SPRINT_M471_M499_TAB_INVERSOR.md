# Sprint UX · M471–M499 — Tab Inversor (cierre)

**Anexo operativo** del [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](./COMITE_UX_MEJORAS_LISTADO_M41_M539.md). Objetivo: bajar el bloque **M471–M499** (“Tabs inversor / cierre”) a tareas concretas en **`assets/style.css`**, **`assets/style_retail_light.css`** (paridad tema) y **`ui/tab_inversor.py`**, sin reescribir lógica de motores ni orden funcional de contenido ([guardas](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md#guardas-de-implementación-no-negociables)).

---

## Nota de producto: cuatro “capítulos” vs cinco tabs

El listado M471–M483 habla de Resumen / Salud / Plan / Rebalanceo. En código, **`render_tab_inversor`** expone **cinco** tabs principales:

| Tab en UI | Etiqueta actual | Relación con M471–M483 |
|-----------|-----------------|-------------------------|
| 1 | 📋 Resumen | **M471–M474** |
| 2 | 📊 RF · RV | *No está en M471–M483*; tratar como **sub-capitulo de mix/KPIs** (mismo criterio de grid + jerarquía que Resumen donde aplique) |
| 3 | ❤️ Salud y alineación | **M475–M477** |
| 4 | 🎯 Plan y simulaciones | **M478–M480** (sub-tabs internos `plan_s1`–`plan_s3`) |
| 5 | ⚖️ Rebalanceo y oportunidades | **M481–M483** |

Los ítems **M484–M499** son **cross-cutting** (estilo de tabs, clases, print, tests).

---

## Tabla de tareas por ID

| ID | Tarea concreta | Dónde | Criterio de hecho |
|----|----------------|-------|-------------------|
| **M471** | Grid de métricas del **Resumen** con identidad visual única (cuatro `st.metric` alineados, espaciado consistente). | `tab_inversor.py` (`tab_res`); CSS clase contenedora si el DOM de Streamlit lo permite sin hacks frágiles. | Métricas legibles en 360px+; sin solapamiento; números con intención tabular donde corresponda (`tabular-nums` vía token/clase). |
| **M472** | Jerarquía tipográfica: título de sección → caption → “Tus posiciones”. | `tab_res`: tras migrar H2 a `mq-inv-*`, revisar `#### Tus posiciones` vs tokens `--text-*` / `mq-font-*`. | Orden visual claro; título > subtítulo > tabla. |
| **M473** | KPIs explícitos (labels de `st.metric` coherentes con glosario). | `tab_res` + copy en `help=` si hace falta. | Mismos términos que glosario inversor; sin duplicar números confusos. |
| **M474** | *Sparklines*: hoy el Resumen no muestra mini-series; **no inventar datos**. Marcar como *defer* o sustituir por “tendencia solo donde ya exista chart” (p. ej. enlazar a Plan). | Documentar decisión en PR; opcional enlace UI “Ver evolución en Plan”. | No fake charts; o sparkline real alimentada por motor existente. |
| **M475** | **Salud:** bloque “hero” del semáforo (columna con `semaforo_html`) con layout estable. | `tab_salud`: `h1,h2,h3` columns; envolver con clase si se puede; `mq-hub-lead` → definir en CSS o reemplazar por `mq-label`. | Semáforo + título + botón Actualizar sin saltos raríos en mobile (`@media` ≤640). |
| **M476** | Cards de riesgo: métricas RF/RV/objetivo en **tres columnas** + expanders. | `tab_salud` `k1,k2,k3`; opcional clase `mq-inv-kpi-box` por bloque. | Alineación y contraste AA en oscuro/claro. |
| **M477** | “Tendencia”: barra `st.progress` + caption; coherencia con puntaje. | `tab_salud` | Progress y texto refieren al mismo score; `prefers-reduced-motion` respeta CSS global. |
| **M478** | Sub-tabs Plan **“1 · 2 · 3”** con navegación clara (activo vs inactivo). | `st.tabs` en `tab_plan`; CSS `[data-baseweb="tab"]` bajo scope si se añade wrapper estable. | Indicador de tab activo visible; foco teclado usable. |
| **M479** | Objetivos: lista prioridades + tablas mix ideal/actual. | `plan_s1` | Tipografía y tablas con mismas reglas que resto inversor. |
| **M480** | Escenarios: bloque proyección + charts. | `plan_s3` → `_render_proyeccion_y_pie_inversor` | Altura mínima de charts; sin overflow horizontal roto en mobile. |
| **M481** | Rebalanceo: columnas de acciones / targets. | `tab_reb` + `_render_posiciones_con_targets` | Tabla o cards con columnas alineadas; chips legibles. |
| **M482** | Lista de órdenes / mensajes de copy. | `copy_rebalanceo_humano`, bloques markdown | Lista ordenada visualmente; no solo muro de texto. |
| **M483** | Totales / efectivo: barras tipo `mq-inv-totals-bar` donde ya hay totales en ARS. | `tab_reb` expander efectivo | Misma familia tipográfica y tokens que KPI globales. |
| **M484** | Tabs principales estilo “libro” (borde inferior, capítulo). | CSS global cuidadoso para `[data-testid="stTabs"]` **dentro del main** o clase envolvente inyectada una sola vez si se adopta patrón seguro. | Tabs distinguibles de default Streamlit sin romper otras vistas. |
| **M485** | Estado activo del tab. | Mismo bloque CSS + contraste foco | Tab seleccionado obvio en claro y oscuro. |
| **M486** | Iconos en labels (emojis en strings de tabs): mantener; no duplicar iconografía en CSS. | `st.tabs([...])` | Sin regresión de copy. |
| **M487** | Badges: prioridades en `obs_card_html` / filas — ya pasan por `mq26_ux`. | `tab_salud` expander observaciones | Colores desde tokens (`--c-prio-*`). |
| **M488** | Responsive: stack en mobile para columnas densas de Salud y Plan. | `style.css` `@media (max-width: 640px)` selectores específicos | Sin scroll horizontal accidental en bloques clave. |
| **M489** | Sustituir `style=""` repetible por clases `mq-*` / `mq-inv-*`. | `tab_inversor.py` por secciones | Diff acotado; sin cambiar datos. |
| **M490** | Eliminar inline **crítico** (títulos, bloques que bloquean tema claro). | Priorizar `_render_selector_perfil_cards`, bloques `div style=` en rebalanceo. | Menos hex sueltos en Python. |
| **M491** | Smoke: `tests/test_plan_pruebas_mq26_ui.py` o navegación existente que toque inversor. | `tests/` | CI verde. |
| **M492–M493** | Paridad dark / light. | `style_retail_light.css` + revisión manual | Mismos componentes legibles en ambos temas. |
| **M494** | Print: `@media print` ocultar sidebar/controles; métricas legibles. | `style.css` | PDF/impresión usable para resumen. |
| **M495** | Documentar clases nuevas en comentario corto al final de bloque CSS o en este archivo. | CSS / este doc | PR describible. |
| **M496** | Regresión Streamlit: no usar APIs experimentales; probar rerun en tabs. | Manual + pytest | Sin errores en consola. |
| **M497** | Performance: evitar `st.rerun` innecesario; no duplicar `plotly_chart` keys. | Revisión ligera | Sin degradación medible en interacción tab. |
| **M498** | i18n números: separadores miles consistentes (`formato_montos` / locale). | Donde se formatee en f-strings | Misma regla que resto app. |
| **M499** | Revisión visual final checklist (oscuro, claro, 375px). | QA manual | Firmado en descripción PR. |

---

## Orden sugerido (3–8 ítems por PR)

1. **Fundaciones:** M489 + M490 (inline → clases) en cabecera “Mi cartera” y labels repetidos; M475 (definir `.mq-hub-lead` o unificar con `.mq-label`).
2. **Resumen:** M471–M473 + M488 parcial en `tab_res`.
3. **Salud + Plan:** M475–M480 + M487.
4. **Rebalanceo + cross:** M481–M483 + M484–M486 + M492–M494.
5. **Cierre:** M491, M496–M499.

---

## Archivos involucrados

| Archivo | Rol |
|---------|-----|
| [ui/tab_inversor.py](../../ui/tab_inversor.py) | Contenido de los cinco tabs y sub-tabs Plan. |
| [assets/style.css](../../assets/style.css) | Tokens, `mq-inv-*`, `mq-metric-row`, print, tabs. |
| [assets/style_retail_light.css](../../assets/style_retail_light.css) | Paridad tema claro. |
| [ui/mq26_ux.py](../../ui/mq26_ux.py) | HTML compartido (semáforo, barras, observaciones). |
| [tests/test_plan_pruebas_mq26_ui.py](../../tests/test_plan_pruebas_mq26_ui.py) (u otros smoke UI) | Regresión mínima. |

---

---

## Estado de implementación (código)

| IDs | Qué se hizo |
|-----|-------------|
| **M471–M473** | Ancla `mq-inv-resumen-kpi-hook` + reglas CSS en `style.css` (separador bajo la fila de métricas, `tabular-nums` en valores); `h4.mq-inv-resumen-positions-head`; caption bajo KPIs alineado a glosario. |
| **M478** | Ancla `mq-inv-plan-subtabs-anchor` + estilo secundario para sub-tabs Plan (más compacto, borde punteado). |
| **M484–M486** | Ancla `mq-inv-inner-tabs-anchor` antes de los cinco tabs; estilo “capítulo” con `> [data-testid="stTabs"]` para no aplicar a tabs anidados; responsive ≤640px para botones. |

*Última actualización: alineado a `render_tab_inversor` con cinco tabs principales y tres sub-tabs en Plan.*
