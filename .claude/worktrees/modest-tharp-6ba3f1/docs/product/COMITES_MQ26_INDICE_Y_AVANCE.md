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

## 2. Paralelo comités (mismo corte de tiempo, no bloquea el código)

Mientras UX cierra revisión visual / PR y **Implementación** mantiene CI, **Expertos** y **Marketing** pueden avanzar **sin** ser gate del merge de front. Objetivo: tener **insumos** listos para la **sala de convergencia** o para el siguiente sprint. **Cuando el sprint 1 UX (*Hacia mercado* 1) quede cerrado** (criterios en [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) **§3**), el **siguiente** en tabla es *Hacia mercado* **2** — **Excelencia C–D** según [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md); **sin Fase E** sin acta comercial. **Cuando el sprint 2 quede cerrado**, el siguiente es *Hacia mercado* **3**: cumplir [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) **antes** de un **tag mayor** (misma §3). **Tras sprint 3** → *Hacia mercado* **4** (**staging** + pre-lanzamiento: demo, copy, `DEPLOY_RAILWAY.md`) y **5** (**sala de convergencia** + acta: requisitos congelados, plan de mercado, Go/No-Go) — skill `comite-convergencia-lanzamiento-mq26`, **§3** [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md).

### Expertos Carteras AR — pasos en este corte

1. **Lista de release (in / out):** qué queda **dentro** del próximo tag o demo y qué queda **fuera** con riesgo asumido (referencia: [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) §4 y §9; **Fase E** fuera salvo acta comercial — [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md)).
2. **Riesgos residuales:** copiar o resumir en una nota lo relevante de **§8** del inventario (precios/RF/BYMA, heurísticas) para que Implementación y Marketing no “prometan” más que eso.
3. **Límites de copy / disclaimers:** una viñeta por rol crítico (p. ej. inversor: paridad, nominal, “último operado”) alineado a **§5** del inventario y a [`INVESTOR_UX_DECISIONES_30_MEJORAS.md`](./INVESTOR_UX_DECISIONES_30_MEJORAS.md) si aplica.
4. **Siguiente ID de prioridad:** encadenamiento completo en **§3** de [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) — tras 1 → 2 (Excelencia **C–D**); tras 2 → 3 + checklist antes de tag mayor; tras 3 → **4** (staging + pre-lanzamiento) → **5** (sala + acta según skill `comite-convergencia-lanzamiento-mq26`). Anotar en §10 de [`PENDIENTES`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) lo ejecutado por sprint (**no** Fase E sin gate comercial).

Marcar las viñetas en **Expertos — qué avanzó / qué sigue** (más abajo) cuando esté hecho.

### Marketing — pasos en este corte

1. **Borrador interno** (1 página o Notion): posicionamiento “qué es / qué no es” MQ26 **sin** promesas de rentabilidad ni claims no respaldados por Expertos (skill `comite-marketing-mq26`).
2. **Demo:** contrastar guión con [`GUIA_DEMO_10_USUARIOS.md`](../GUIA_DEMO_10_USUARIOS.md) y el **build** que vaya a mostrarse (pestañas, roles); anotar **gaps** (pantalla que el guión menciona y el build no tiene).
3. **Canales y fase:** definir si este corte es solo **interno/beta** o hay fecha pública; si no hay fecha, registrar “sin salida pública en este corte”.
4. **Dependencias:** lista corta de lo que **bloquea** mensaje final (p. ej. “pendiente confirmación Expertos sobre X”) para la convergencia.

Marcar las viñetas en **Marketing — qué avanzó / qué sigue** cuando esté hecho.

---

## Avance por iteración (plantilla viva)

*Completar al cerrar sprint o al preparar un release; una línea por comité.*

### Expertos — qué avanzó / qué sigue
- **Próximo release (inventario [`PENDIENTES`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) §9):** entra lo ya **P0–P2 Done** (RBAC/tenant, SSOT/observabilidad/admin, RF/BYMA/trazabilidades acordadas en §4) más **P3** acumulable en la rama (p. ej. cierre sprint 1 UX + checklist [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) antes de tag mayor). **Fuera / no comunicar:** **Fase E** (API broker, multi-moneda real, chat) sin gate comercial explícito ([`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md)); nada de promesa de retorno ni claims sin respaldo en build + doc BYMA (§7).
- **Riesgo residual (§8):** heurísticas de escala RF/BYMA en tickers extremos (mitigado con UI **P2-RF-04** + logs); tests que tocan **red** deben ir aislados/marcados; **M41–M539** como refinamiento visual por sprints, no como “pantalla perfecta” en un solo corte.
- [ ] Equipo: validar o ajustar las dos líneas anteriores y anotar **siguiente ID** de [`PENDIENTES` §10](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) a ejecutar tras este release.

### UX — qué avanzó / qué sigue
- [x] **Sprint *Hacia mercado* 1 (código listo para cierre):** admin + **Estudio** sin `style=""` (torre, chips R/A/V, hero acciones, separadores, spacer PDF) + workflow; `assets/style.css`. Trazabilidad **M** → plantilla PR más abajo. *Decisión: opción B (tercer micro-bloque Estudio).*
- [ ] Pantallas críticas vistas en oscuro + claro (revisión humana pendiente).
- [ ] Siguiente bloque UX: `ui/mq26_ux.py` inline residual u otra pestaña / rango M del anexo (puede convivir con trabajo **Excelencia C–D** del sprint *Hacia mercado* 2; ver [`COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`](./COMITE_CONVERGENCIA_Y_LANZAMIENTO.md) §3).

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

**Condición:** usar este bloque cuando haya **intención de demo o salida**; hasta entonces puede quedar como borrador interno. El copy debe coincidir con lo que **Expertos** fija en [`PENDIENTES`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) (§4–§9, §8 riesgos) y con el **build** que confirme **Implementación** (skill `comite-marketing-mq26`).

#### Borrador de mensaje (acotado; sin promesas de retorno)

*Máximo tres ideas; ajustar redacción final con Expertos antes de cualquier canal público.*

1. **Qué es:** MQ26 concentra en un solo lugar cartera, diagnóstico, riesgo, reportes y flujos por rol (cuando el entorno los tenga activos), con foco en **claridad de unidades, fuente de precio y trazabilidad** — herramienta de trabajo, no promesa de resultado.
2. **Honestidad operativa:** si un dato es ilustrativo, benchmark o depende de proveedores (p. ej. BYMA / fallback), la app y la demo deben **mostrarlo**; no se afirma rentabilidad futura ni “mejor que” el mercado.
3. **Demo:** guión y audiencias alineados a [`GUIA_DEMO_10_USUARIOS.md`](../GUIA_DEMO_10_USUARIOS.md); solo mostrar pantallas que existan en el **build** acordado (incl. Estudio / Admin / workflow si el rol lo permite).

**No decir (lista corta):** retorno esperado, garantías, “asesoría personalizada” sustitutiva de un profesional licenciado, funciones de **Fase E** ([`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md)) si no están desplegadas y aprobadas por Expertos.

- [ ] Expertos + Implementación: **OK** al borrador de las tres viñetas (o versión sustituida en PR/nota).
- [ ] Canales y materiales actualizados respecto del build real (sin adelantar salida pública sin fecha).
- [ ] Dependencias explícitas anotadas (qué falta desplegar o validar antes de comunicar).

### Convergencia — cuándo convocar
- [ ] ¿Hay fecha o intención de salida al mercado? Si sí: preparar sala según `COMITE_CONVERGENCIA_Y_LANZAMIENTO.md`.
- [x] Esta iteración: **no convoca sala formal**; avance sprint 1 UX + gate técnico local.
- [ ] **Encadenamiento 1 → 2:** con sprint 1 UX **cerrado** (§3 `COMITE_CONVERGENCIA`), marcar inicio explícito de *Hacia mercado* **2** (Excelencia C–D; sin Fase E sin acta comercial) en acta breve o PR.
- [ ] **Encadenamiento 2 → 3:** con sprint 2 **cerrado**, marcar inicio de *Hacia mercado* **3** y dejar **[`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) verde** antes del **tag mayor** (§3).
- [ ] **Encadenamiento 3 → 4:** con sprint 3 **cerrado**, staging con build candidato + pre-lanzamiento (demo, mensajes, límites de copy) según §3 y fila *Hacia mercado* 4 de `COMITE_CONVERGENCIA`.
- [ ] **Encadenamiento 4 → 5 / sala:** convocatoria **sala de convergencia** con acta (**requisitos congelados**, **plan de mercado**, **Go/No-Go**) según skill **`comite-convergencia-lanzamiento-mq26`**; registrar en el *Registro* de abajo o en ticket de release.

---

## Registro de última sesión de convergencia (opcional)

| Fecha | Release / hito | Veredicto | Enlace acta / PR |
|-------|----------------|-----------|------------------|
| 2026-04-11 | Sprint *Hacia mercado* 1 (UX admin) + suite `pytest` verde | Avance; **convergencia formal** cuando haya fecha comercial | `mq-admin-panel-h2`; fixes tests previos |
| (pendiente) | Cierre sprint 1 UX → arranque **sprint 2** (*Hacia mercado* 2, Excelencia C–D) | Plan documentado en `COMITE_CONVERGENCIA` §3; Fase E fuera sin gate comercial | Marcar checklist UX + checkbox encadenamiento arriba |
| (pendiente) | Cierre sprint 2 → **sprint 3** (*Hacia mercado* 3) + tag mayor | `CHECKLIST_P3_QA01_RELEASE.md` completo antes del tag; §3 `COMITE_CONVERGENCIA` | Enlace al PR de release o nota de checklist |
| (pendiente) | Sprint **4** — staging + pre-lanzamiento (*Hacia mercado* 4) | Build candidato staging; `GUIA_DEMO_10_USUARIOS.md`; guión Marketing + límites Expertos | URL staging / nota de validación |
| (pendiente) | Sprint **5** — sala convergencia + acta (*Hacia mercado* 5) | Requisitos congelados + plan mercado + Go/No-Go; skill `comite-convergencia-lanzamiento-mq26` | Acta o enlace al documento de sesión |

---

*Actualizar este archivo cuando cambie el modelo de gobierno o al cerrar una convergencia importante.*
