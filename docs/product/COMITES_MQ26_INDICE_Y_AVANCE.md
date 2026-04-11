# MQ26 — Índice de comités y avance coordinado

**Propósito:** un solo lugar para ver **los cinco roles** (cuatro comités de dominio + **convergencia** como orquestación), sus skills, documentos clave y **cómo avanzar** cada iteración sin duplicar el inventario de producto (`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`).

**Convergencia** no sustituye a los demás: cierra la mesa cuando hay que alinear **requisitos + salida al mercado** (`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`). **Orden de sprints:** misma referencia (*Lista de sprints hacia el lanzamiento*): **gate P0–P2** en equipo; si `PENDIENTES` §9 está verde, la cadena mínima son **5 sprints** (*Hacia mercado* 1–5); si no, fundaciones P0/P1/P2 antes.

---

## Mapa rápido

| Rol | Skill (`.cursor/skills/`) | Documento guía principal |
|-----|---------------------------|---------------------------|
| Expertos Carteras AR | `comite-expertos-carteras-ar` | `PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`, `EXCELENCIA_INDUSTRIAL_FASES.md` |
| UX MQ26 | `comite-ux-mq26` | `COMITE_UX_DESIGN_SYSTEM_M41_M539.md` |
| Implementación | `comite-implementacion-mq26` | `DEPLOY_RAILWAY.md`, CI, runbooks |
| Marketing | `comite-marketing-mq26` | `COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`, `GUIA_DEMO_10_USUARIOS.md` |
| **Convergencia / lanzamiento** | `comite-convergencia-lanzamiento-mq26` | `COMITE_CONVERGENCIA_Y_LANZAMIENTO.md` |

---

## Cómo “avanzan” todos en la misma dirección

1. **Paralelo (cada sprint):** cada comité mueve su checklist de **Avance por iteración** (abajo) sin bloquear a los otros.
2. **Hito de release o salida al mercado:** convocar **Convergencia** con insumos listos (checklist de entrada en `COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`).
3. **Salida única:** acta con requisitos congelados + plan de mercado + Go/No-Go (plantilla en skill `comite-convergencia-lanzamiento-mq26`).

---

## Avance por iteración (plantilla viva)

*Completar al cerrar sprint o al preparar un release; una línea por comité.*

### Expertos — qué avanzó / qué sigue
- [ ] 1–2 ítems del inventario tocados o cerrados (ID en nota de PR o aquí).
- [ ] Riesgos residuales explícitos para el próximo corte.
- [ ] Siguiente prioridad acordada (referencia a `PENDIENTES` por ID).

### UX — qué avanzó / qué sigue
- [x] **Sprint *Hacia mercado* 1 (código listo para cierre):** admin + **Estudio** sin `style=""` (torre, chips R/A/V, hero acciones, separadores, spacer PDF) + workflow; `assets/style.css`. Trazabilidad **M** → plantilla PR más abajo. *Decisión: opción B (tercer micro-bloque Estudio).*
- [ ] Pantallas críticas vistas en oscuro + claro (revisión humana pendiente).
- [ ] Siguiente bloque UX: `ui/mq26_ux.py` inline residual u otra pestaña / rango M del anexo.

#### Plantilla — descripción PR (P3 incremental · IDs M)

Copiar y pegar en GitHub (ajustar rutas de tests si el PR no incluye todos los archivos):

```markdown
## Sprint 1 UX — *Hacia mercado* (P3 incremental)

**Norma:** [COMITE_UX_DESIGN_SYSTEM_M41_M539.md — § P3 incremental](./COMITE_UX_DESIGN_SYSTEM_M41_M539.md) · anexo [COMITE_UX_MEJORAS_LISTADO_M41_M539.md](./COMITE_UX_MEJORAS_LISTADO_M41_M539.md)

### IDs M tocados

| Rango / ID | Cobertura en este PR |
|------------|----------------------|
| **M43–M45** | Jerarquía de sección: `mq-admin-panel-h2`, `mq-estudio-page-h2`, kickers torre (`mq-estudio-torre-kicker`). |
| **M46–M47** | Etiquetas en mayúsculas / captions densos (kickers torre, labels tarjeta compacta). |
| **M48** | `font-variant-numeric: tabular-nums` en scores torre y hero (`mq-estudio-torre-card__score`, `mq-estudio-hero-score`). |
| **M50–M51** | Pesos coherentes en chips R/A/V (`mq-estudio-chip--rojo|amarillo|verde`). |
| **M52** | Truncado con ellipsis en nombres (`mq-estudio-torre-card__nombre`). |
| **M91–M97** | Color semántico (semáforo tarjeta, `data-mq-sem`, chips urgencia / OK). |
| **M42** (parcial) | Banner y pasos workflow (`mq-wf-banner`, `mq-wf-step` + vars `--mq-wf-*`). |

### Archivos

`assets/style.css` · `ui/tab_admin.py` · `ui/tab_estudio.py` · `ui/workflow_header.py` · `docs/product/COMITES_MQ26_INDICE_Y_AVANCE.md`

### Tests sugeridos

`pytest tests/test_sprint3.py tests/test_plan_pruebas_mq26_ui.py tests/test_mq26_ux_design_system.py tests/test_workflow_header.py tests/test_flujo_asesor.py`
```

#### Revisión visual manual — sprint 1 UX (comité UX, paridad temas)

**Entorno:** `python run_mq26.py` (o el entrypoint que usen). En sidebar: **☀️ Modo claro** — con toggle **activado** = tema claro (`style_retail_light.css`); **desactivado** = tema oscuro (`style.css`). Repetir **toda** la tabla en ambos modos.

**Roles / rutas**

| Qué mirar | Rol / condición | Dónde |
|-----------|-----------------|--------|
| Título panel admin | `super_admin` | Pestaña que renderiza `render_tab_admin` (p. ej. **Admin** / panel administración) — título **🛠 Panel de administración** con clase `mq-admin-panel-h2`. |
| Estudio: h2, torre, chips, hero, tarjetas | `asesor` o quien tenga tab **Estudio** | **Estudio** → “Mis clientes”; torre (*Torre de control*, chips R/A/V si hay rojos/amarillos, tabla, **Acciones rápidas** con emoji/score); expander **Vista en tarjetas (compacta)**. |
| Workflow header | Cualquier rol **≠ inversor** | Tras login, **arriba del bloque de tabs principal**: banner “**Siguiente:**” (`mq-wf-banner`) y pasos 1–5 (`mq-wf-step`) si no es vista compacta. |

**Por cada modo (oscuro y claro), revisar**

- [ ] **Contraste:** texto del banner y de los pasos legible; bordes de tarjetas torre visibles sin “fantasma”.
- [ ] **Tipografía:** títulos coherentes (Barlow; sin saltos raros de tamaño respecto al resto de la app).
- [ ] **Layout:** banner en una línea o wrap aceptable; pasos en grid de 5 columnas sin solapamiento (ancho ≥ ~1024px ideal; probar también ventana estrecha si aplica).
- [ ] **Semáforo / PnL / chips:** borde izquierdo de la tarjeta resumen y colores de chips R/A/V coherentes; filas **Acciones rápidas** (score bajo emoji) legibles.
- [ ] **Accesibilidad rápida:** si el SO tiene “reducir movimiento”, comprobar que la app no depende de animación para entender el estado (opcional).

**Cierre:** cuando todo esté OK en **ambos** temas, marcar arriba la viñeta *Pantallas críticas vistas en oscuro + claro* y anotar fecha / responsable aquí o en el PR: ____________________

### Implementación — qué avanzó / qué sigue
- [x] `pytest tests/` verde en rama de trabajo (regresión reciente corregida).
- [ ] Runbook o incidentes: actualización si aplica.
- [ ] Riesgo técnico conocido para el próximo release.

### Marketing — qué avanzó / qué sigue
- [ ] Mensajes y canales alineados al alcance real (sin promesas de retorno).
- [ ] Materiales o demo actualizados respecto del build.
- [ ] Dependencias con Expertos/Implementación anotadas.

### Convergencia — cuándo convocar
- [ ] ¿Hay fecha o intención de salida al mercado? Si sí: preparar sala según `COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`.
- [x] Esta iteración: **no convoca sala formal**; avance sprint 1 UX + gate técnico local.

---

## Registro de última sesión de convergencia (opcional)

| Fecha | Release / hito | Veredicto | Enlace acta / PR |
|-------|----------------|-----------|------------------|
| 2026-04-11 | Sprint *Hacia mercado* 1 (UX admin) + suite `pytest` verde | Avance; **convergencia formal** cuando haya fecha comercial | `mq-admin-panel-h2`; fixes tests previos |

---

*Actualizar este archivo cuando cambie el modelo de gobierno o al cerrar una convergencia importante.*
