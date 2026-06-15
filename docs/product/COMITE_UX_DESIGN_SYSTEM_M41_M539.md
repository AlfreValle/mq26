# MQ26 · Comité UX — Sistema de diseño (M41–M539)

Documento de **panel de diseño** (tokens, tipografía, color, motion, responsive, componentes financieros e identidad por vista). Complementa las **decisiones de producto** del inversor/estudio/asesor sin duplicarlas.

**Relación con otros docs**

- **Cursor (agente):** skill del proyecto [`.cursor/skills/comite-ux-mq26/SKILL.md`](../../.cursor/skills/comite-ux-mq26/SKILL.md) — cuándo aplicar guardas, disparadores y lectura de este documento.
- **Todos los comités (avance coordinado):** [COMITES_MQ26_INDICE_Y_AVANCE.md](COMITES_MQ26_INDICE_Y_AVANCE.md).
- Decisiones funcionales y de información: [INVESTOR_UX_DECISIONES_30_MEJORAS.md](INVESTOR_UX_DECISIONES_30_MEJORAS.md).
- Listado numerado M41–M539 (índice ejecutivo + anexo): [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](COMITE_UX_MEJORAS_LISTADO_M41_M539.md).

---

## Propósito

Separar claramente:

| Ámbito | Contenido |
|--------|-----------|
| **Producto / inversor** | Qué se muestra, en qué orden, qué motor alimenta cada bloque. |
| **Comité UX (este doc)** | Cómo se ve y se comporta la UI: escala tipográfica, tokens semánticos, breakpoints, animaciones accesibles, patrones de tabla y de tabs. |

El comité no redefine reglas de negocio ni prioriza features: solo asegura **coherencia visual**, **accesibilidad** y **mantenibilidad** (CSS centralizado, sin colores sueltos en Python).

---

## Tipografía del proyecto (restricción)

| Uso | Familia |
|-----|---------|
| Texto corrido | **Barlow Regular** |
| Subtítulos | **Barlow Semibold** |
| Títulos | **Barlow Semi Condensed Extrabold** |

Los archivos CSS actuales pueden importar otras fuentes para datos monoespaciados; el comité alinea la **UI retail** con Barlow donde la app lo declare explícitamente (variables `--font-*` y clases `mq-*`).

---

## Los cinco especialistas y su mandato

### Jiro Yamamoto — Tipografía (M41–M90)

**Problema:** tamaños arbitrarios (`0.72rem`, `0.8125rem`, `0.875rem`…) sin escala única; números financieros que no alinean en tablas.

**Mandato:**

- Escala modular de **6 niveles** (ratio **1.25**): `--text-xs` … `--text-2xl` en `:root`.
- **Tracking** por propósito (etiquetas, cuerpo, hero).
- **`font-variant-numeric: tabular-nums`** (y donde aplique `font-feature-settings` para datos) en tablas y métricas para alineación vertical correcta.

### Ingrid Svensson — Color y accesibilidad (M91–M140)

**Problema:** colores hardcodeados en Python (p. ej. `style=""` en tabs) dificultan tema claro, contraste y export print/PDF.

**Mandato:**

- Tokens semánticos: `--c-gain`, `--c-loss`, `--c-prio-*`, gradientes de semáforo, fondos de estado.
- Sustituir inline repetible por **clases** que lean `var(...)`.
- Definir reglas de **impresión** (`@media print`) para informes legibles en papel.

### Priya Nair — Responsive (M141–M200 y solapamiento M261–M270 con motion)

**Problema:** en mobile, columnas superpuestas y gráficos cortados.

**Mandato:**

- Breakpoints: **640px** (mobile), **1024px** (tablet), **1440px** (desktop amplio).
- Grillas a **1 columna** en mobile; contenedores con **altura mínima/máxima** razonable para charts.
- No duplicar animaciones: motion sigue las reglas de Marcus; responsive evita layout roto cuando hay `prefers-reduced-motion`.

### Marcus de Villiers — Animaciones (M201–M270)

**Problema:** la UI aparece “de golpe”; falta feedback en progreso y estados de alerta.

**Mandato:**

- Entrada: **fade-in** al cargar (~700ms), **stagger** de métricas (~60ms entre ítems).
- Barras de progreso con **relleno animado**; semáforo con **pulse** diferenciado (rojo más rápido que verde); **ripple** en botón primario.
- **Todas** las animaciones deben degradar con **`prefers-reduced-motion: reduce`** (desactivar o acortar).

### Carlos Mendoza — Componentes financieros e identidad de tabs (M271–M370, M471–M520)

**Problema:** tablas densas sin estados hover claros; señales MOD-23 y sectores sin vocabulario visual único; tabs del inversor genéricos.

**Mandato:**

- Tabla de posiciones: tabular nums, separadores, hover, color por cuartil de score donde aplique.
- Barras **duales** (objetivo vs stop en el mismo track), **chips** de sector, **badges** MOD-23 con color semántico.
- **Cuatro tabs inversor** con identidad de “capítulos”: Resumen (grid métricas), Salud (semáforo hero), Plan (sub-tabs con acento por eje), Rebalanceo (acciones en dos columnas).

---

## Índice M41–M539

El inventario completo por código **M41 … M539** está en [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](COMITE_UX_MEJORAS_LISTADO_M41_M539.md), con una línea por mejora y agrupación por responsable. Si en el futuro se incorpora un anexo externo de ~72KB con redacción extendida, puede sustituir o ampliar ese archivo sin cambiar el rol del comité.

---

## Guardas de implementación (no negociables)

1. **Lógica Python:** los **cuatro tabs** del inversor y sus funciones **no se reescriben** en este sprint de diseño. Solo se reemplazan estilos inline repetibles por clases `mq-*` y se amplía CSS compartido.
2. **Entornos divergentes:** si `ui/tab_inversor.py` quedó **degradado** (p. ej. merge o sprint anterior que sobrescribió una versión completa), **restaurar la versión correcta** (p. ej. V3/local) **antes** de aplicar solo CSS/clases.
3. **Servicios de dominio:** no se modifican motores de scoring, cartera, reportes, etc., salvo una tarea explícita aparte.

---

## Mapeo técnico (archivos del sprint)

| Área | Archivos típicos |
|------|------------------|
| Tokens y componentes globales | [assets/style.css](../../assets/style.css) |
| Tema claro | [assets/style_retail_light.css](../../assets/style_retail_light.css) |
| Helpers HTML reutilizables | [ui/mq26_ux.py](../../ui/mq26_ux.py) |
| Inversor (inline → clases) | [ui/tab_inversor.py](../../ui/tab_inversor.py) |
| Resumen cartera | [ui/tab_cartera.py](../../ui/tab_cartera.py) |
| Torre estudio | [ui/tab_estudio.py](../../ui/tab_estudio.py) |

**Verificación:** `pytest tests/` completo; revisión visual **oscuro + claro**.

**Estado reciente (implementación parcial alineada al comité):** en [assets/style.css](../../assets/style.css) hay utilidades `mq-inv-*` (bienvenida, cards, pasos, KPI, barra de totales) y `mq-motion-page-fade` con `@media (prefers-reduced-motion: reduce)`. [assets/style_retail_light.css](../../assets/style_retail_light.css) define paridad de tokens semánticos (`--c-gain`, `--c-loss`, prioridades, gradientes) y, desde **P3-UX-02**, tipografía modular (`--text-*`) y breakpoints (`--bp-sm/md/lg`) en `:root`. [ui/mq26_ux.py](../../ui/mq26_ux.py) refactoriza semáforo, barra hero, barra defensiva y `plotly_chart_layout_base` (Barlow + color de eje según tema) hacia clases/tokens; [ui/tab_inversor.py](../../ui/tab_inversor.py) migra bloques desde `style=""` a clases; el resto de inline y otras pestañas puede seguir el mismo patrón por sprint.

---

## Proceso de aplicación (resumen)

1. Congelar versión correcta de tabs (especialmente `tab_inversor.py`).
2. Alinear tokens en `:root` y reglas por breakpoint / print.
3. Sustituir `style=""` por clases en tabs priorizados; reutilizar `mq26_ux` donde exista.
4. Validar accesibilidad básica (contraste, reduced motion) y regresión de tests.

---

## P3 incremental (por sprint, sin inflar alcance)

Tras el cierre **v1** de **P3-UX-02** (tokens, breakpoints, refactor priorizado en `mq26_ux` / CSS), el anexo [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](COMITE_UX_MEJORAS_LISTADO_M41_M539.md) queda como **backlog visual incremental**, no como un único mega-entregable.

| Regla | Qué significa |
|--------|----------------|
| **Un bloque por sprint** | Elegir un rango **Mxx–Myy** del mismo “responsable” en el listado **o** un solo archivo UI (p. ej. una pestaña) y migrar solo lo que afecte ese archivo + `assets/style*.css` / `ui/mq26_ux.py`. |
| **Tamaño razonable** | Orden de magnitud: **3–8 ítems M** cerrados en código, **o** una pestaña pasando de `style=""` inline a clases `mq-*` / tokens donde aplique. |
| **Guardas** | Respetar [Guardas de implementación](#guardas-de-implementación-no-negociables): no reescribir lógica de tabs ni motores; solo estilo y accesibilidad. |
| **Fuera de alcance** | Features nuevas de producto, rediseño total de navegación, scoring/cartera/reportes, o “terminar los ~500 ítems” en un solo PR. |
| **Definición de hecho** | Cambios visuales aplicados; `pytest` verde en tests UX existentes (`tests/test_mq26_ux_*.py`); si se tocó tema, chequeo rápido **oscuro + claro**. |
| **Trazabilidad** | En la nota del sprint o descripción del PR: listar **IDs M** tocados para cruzar con el anexo. |
| **Ejemplo bloque M471–M499** | Desglose por tab y archivo: [COMITE_UX_SPRINT_M471_M499_TAB_INVERSOR.md](./COMITE_UX_SPRINT_M471_M499_TAB_INVERSOR.md). |

**Relación con Excelencia / Pendientes:** el inventario comité describe **P3-UX-02 v1** como cerrado y el refinamiento M41–M539 como trabajo **por sprints**; esta sección es la referencia operativa para no desviar el alcance.

---

*Documento de comité UX; actualizar cuando cambie la matriz M41–M539 o los archivos de implementación de referencia.*
