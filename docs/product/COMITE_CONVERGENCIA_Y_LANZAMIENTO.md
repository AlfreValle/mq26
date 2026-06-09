# MQ26 — Convergencia de comités y plan de lanzamiento

Este documento articula **cómo conversan** entre sí los comités del proyecto cuando el producto está **listo para salir al mercado** (o en un **hito previo explícito**): no sustituye al inventario de prioridades en `PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`; define el **ritmo conjunto**, los **insumos** y las **salidas** de una reunión de alineación.

**Índice maestro y avance por iteración (todos los comités):** [COMITES_MQ26_INDICE_Y_AVANCE.md](./COMITES_MQ26_INDICE_Y_AVANCE.md).

**Encadenar sprints *Hacia mercado* (orden en tabla):** [§3](#3-encadenamiento-del-plan-siguiente-sprint-en-la-tabla) — **1 → 2** (cierre UX → Excelencia C–D; sin Fase E sin acta comercial); **2 → 3** — [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) **antes** de un **tag mayor**; **3 → 4 → 5** — **staging** + **pre-lanzamiento**, luego **sala de convergencia** con **acta** (requisitos congelados, plan de mercado, Go/No-Go) según la skill **`comite-convergencia-lanzamiento-mq26`** (`.cursor/skills/comite-convergencia-lanzamiento-mq26/SKILL.md`).

---

## Lista de sprints hacia el lanzamiento (orden sugerido)

**Fuente normativa del orden de prioridades:** [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) (sección **10 · Orden de ejecución sugerido**) y [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md).  
**Regla:** esta tabla traduce ese orden a **unidades de sprint** para coordinar comités; no reemplaza el inventario por ID. Cuando un ítem ya figure **cerrado** en `PENDIENTES`, el sprint correspondiente se **salta** o se dedica al **siguiente residual** de la misma fila (roles §5, dominios §6, deuda §8).

**Duración:** asumir sprint de **1–2 semanas** según el equipo; si la cadena se acorta (más capacidad), **mantener el orden relativo**, no invertir dependencias (p. ej. QA release antes de cerrar riesgos de producto acordados).

### Gate en equipo: ¿P0–P2 cerrados en esta rama / entorno?

Antes de asignar numeración, el equipo confirma (acta breve, ticket o fila en [`COMITES_MQ26_INDICE_Y_AVANCE.md`](./COMITES_MQ26_INDICE_Y_AVANCE.md)):

- [ ] **P0** alineado a [`PENDIENTES`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) §9 *P0 Done* y a la rama desplegada.
- [ ] **P1** alineado a §9 *P1 Done* (o explícitamente excluido del release con riesgo asumido).
- [ ] **P2** alineado a §9 *P2 Done* (mismo criterio de exclusión explícita si algo queda fuera).

**Si las tres casillas están marcadas:** **no** se ejecutan los sprints de **fundación** de la tabla siguiente (filas con “Fundación” en el nombre); el **primer** sprint de trabajo hacia mercado es el que en la columna *Hacia mercado (si P0–P2 OK)* lleva el número **1** (antes “Sprint 4 global”). En total son **5 sprints** hasta la convergencia formal.

**Si alguna casilla no aplica:** ejecutar primero solo las filas **Fundación P0 / P1 / P2** que correspondan a deuda real (revisar §4 y §9 del inventario); luego continuar por la columna *Hacia mercado* en orden 1→5.

| Orden global | Hacia mercado (si P0–P2 OK) | Sprint | Objetivo (qué debe quedar listo) | Comités protagonistas | Referencia inventario / docs |
|--------------|-----------------------------|--------|-----------------------------------|------------------------|------------------------------|
| 1 | — | **Fundación P0** (condicional) | Cierre **P0** residual: RBAC deny, checklist P0, tenant — solo si el gate no está verde. | Expertos, Implementación | `PENDIENTES` §4 P0, `CHECKLIST_P0_DONE_SEGURIDAD.md` |
| 2 | — | **Fundación P1** (condicional) | **P1:** navegación SSOT, `log_degradacion`, tests observabilidad, admin auditable — solo si falta respecto de §9. | Expertos, Implementación | `PENDIENTES` §4 P1 |
| 3 | — | **Fundación P2** (condicional) | **P2** restante o seguimiento (RF, BYMA, ingestas): solo lo abierto en inventario; sin parches de escala fuera de marco. | Expertos, Implementación | `PENDIENTES` §4 P2, `BYMA_*` |
| 4 | **1** | **Hacia mercado — UX incremental** | **P3-UX:** un **bloque** M41–M539 o una pestaña (no mega-PR); paridad oscuro/claro en lo tocado. | UX, Expertos (alcance) | `COMITE_UX_DESIGN_SYSTEM_M41_M539.md` § P3 incremental, `COMITE_UX_MEJORAS_LISTADO_M41_M539.md` |
| 5 | **2** | **Hacia mercado — Excelencia C–D** | Filas vivas de `EXCELENCIA_INDUSTRIAL_FASES.md` (hub, motores, admin/DevOps); Fase **D** como soporte; **no** sustituir prioridad P0/P2. | Expertos, Implementación | `EXCELENCIA_INDUSTRIAL_FASES.md`, `PENDIENTES` §4 P3-EXC-01 |
| 6 | **3** | **Hacia mercado — QA release mayor** | `CHECKLIST_P3_QA01_RELEASE.md`: pytest, revisión visual, criterios de tag/release. | Implementación, UX | `CHECKLIST_P3_QA01_RELEASE.md`, CI |
| 7 | **4** | **Hacia mercado — Pre-lanzamiento** | Build candidato en staging; **Marketing** borrador de mensajes/canales; **Expertos** límites de copy. | Marketing, Expertos, Implementación, UX | `GUIA_DEMO_10_USUARIOS.md`, `DEPLOY_RAILWAY.md` |
| 8 | **5** | **Hacia mercado — Convergencia formal** | [Agenda “todos en la mesa”](#agenda-tipo-todos-en-la-mesa-orden-sugerido); requisitos congelados, plan de mercado, **Go/No-Go**. | Los cuatro + acta | Skill `comite-convergencia-lanzamiento-mq26` |

**Resumen:** con inventario **v1.33** y §9 en verde para P0–P2 en el entorno del equipo, la **cadena mínima** hacia el mercado son **5 sprints** (columna *Hacia mercado* 1–5). Los **tres** sprints de fundación son **opcionales** y solo se nombran en planificación si hay deuda abierta respecto de §9.

**Fuera de esta cadena hasta decisión explícita:** **Fase E** (API broker, multi-moneda real, chat) — ver tabla *Criterio de apertura comercial* en `EXCELENCIA_INDUSTRIAL_FASES.md`; no asignar sprint de ingeniería sin acta comercial.

**Mantenimiento:** al cambiar el orden global en `PENDIENTES` §10, actualizar esta tabla en el mismo PR o inmediatamente después.

---

## 3. Encadenamiento del plan (siguiente sprint en la tabla)

**Reglas (orden de la columna *Hacia mercado*):**

1. Al cerrar el sprint **1**, el equipo **avanza al 2** (fila **“Hacia mercado — Excelencia C–D”**), sin reordenar la cadena salvo **acta** o PR de gobierno que lo justifique.
2. Al cerrar el sprint **2**, el equipo **avanza al 3** (fila **“Hacia mercado — QA release mayor”**). **Antes de cortar un tag mayor** de release, debe quedar **cumplido** el checklist [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md) (tests como en CI, revisión visual claro/oscuro, criterios del propio documento). Si el checklist no está verde, **no** se etiqueta el release salvo **excepción** explícita aprobada y documentada en acta o ticket.
3. Al cerrar el sprint **3**, el equipo **avanza al 4** (*Hacia mercado — Pre-lanzamiento*): **build candidato en staging**, alineación con [`DEPLOY_RAILWAY.md`](../DEPLOY_RAILWAY.md) (o entorno equivalente), **Marketing** (borrador mensajes/canales) y **Expertos** (límites de copy); **Implementación** y **UX** confirman lo que se ve en staging frente al tag.
4. Tras el **4**, el equipo ejecuta el **5** (*Hacia mercado — Convergencia formal*): **sala de convergencia** con los cuatro comités + acta, siguiendo la agenda de [“todos en la mesa”](#agenda-tipo-todos-en-la-mesa-orden-sugerido) y el formato de acta de la skill **`comite-convergencia-lanzamiento-mq26`** (`.cursor/skills/comite-convergencia-lanzamiento-mq26/SKILL.md`). **Salidas mínimas del acta:** requisitos **congelados**, **plan de mercado**, **Go / No-Go** (detalle en la sección **Salidas obligatorias** más abajo en este mismo documento).

### Cierre del sprint 1 UX (*Hacia mercado* 1)

“Cerrado a ojos del equipo” implica como **mínimo**:

- **UX:** checklist acordada en [`COMITES_MQ26_INDICE_Y_AVANCE.md`](./COMITES_MQ26_INDICE_Y_AVANCE.md) (revisión visual en oscuro + claro de lo tocado en el sprint; paridad con design system P3 incremental).
- **Implementación:** build/CI alineados a lo que se considera base del cierre (sin prometer en demo más de lo desplegado).
- **Traza:** fecha, responsable o enlace a PR/acta breve en el índice de comités o en el ticket de sprint.

### Arranque del sprint 2 (*Hacia mercado* 2): Excelencia C–D

- **Alcance:** fases **C** y **D** de [`EXCELENCIA_INDUSTRIAL_FASES.md`](./EXCELENCIA_INDUSTRIAL_FASES.md) — hub inversor y motores (C); admin, DevOps y deuda arquitectónica como **soporte** (D), sin sustituir **P0** / **P2** salvo bloqueo operativo explícito (misma norma que en ese documento).
- **Inventario accionable:** bloque **P3-EXC-01** y filas vivas de la tabla por fase en el mismo archivo; coordinación con [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) §4 y §10.
- **Fase E:** **no** forma parte de este sprint. Integraciones **API broker**, **multi-moneda real** y **chat** siguen fuera de planificación de ingeniería y de mensaje comercial **hasta** cumplir el **gate comercial** (acta / minuta explícita — tabla *Criterio de apertura comercial* en `EXCELENCIA_INDUSTRIAL_FASES.md`).

### Cierre del sprint 2 (Excelencia C–D)

Criterio orientativo de “cerrado” para encadenar: residual acordado con Expertos (P3-EXC / `PENDIENTES` §10) **cerrado o explícitamente fuera** del alcance del próximo tag; CI estable en la rama candidata; sin arrastrar Fase E al alcance del tag.

### Arranque del sprint 3 (*Hacia mercado* 3): QA release mayor

- **Objetivo:** misma fila de la tabla (*QA release mayor*): alinear **pytest**, revisión visual y **criterios de tag/release** con [`CHECKLIST_P3_QA01_RELEASE.md`](./CHECKLIST_P3_QA01_RELEASE.md).
- **Gate de etiquetado:** el checklist anterior es la **barra mínima** antes de un **tag mayor**; Implementación y UX son protagonistas; Expertos validan que el alcance del tag coincide con lo comunicable.

### Cierre del sprint 3 (QA release mayor)

Orientativo: checklist **P3-QA-01** verde; **tag mayor** aplicado o identificado como candidato; rama/build que se promoverá a staging para el sprint 4.

### Arranque del sprint 4 (*Hacia mercado* 4): staging + pre-lanzamiento

- **Contenido:** misma fila de la tabla — staging con build candidato; guión de demo alineado a [`GUIA_DEMO_10_USUARIOS.md`](../GUIA_DEMO_10_USUARIOS.md); borrador de **Marketing** y **límites de copy** de **Expertos** sin adelantar Fase E ni promesas no respaldadas.
- **Objetivo:** dejar listos los **insumos** para la sala del sprint **5** (nadie promete en canales públicos hasta cerrar acta si así lo definió el equipo).

### Arranque del sprint 5 (*Hacia mercado* 5): sala de convergencia + acta

- **Qué es:** reunión **“todos en la mesa”** (orden sugerido en la agenda de este documento); orquestación y plantilla de acta en la skill **`comite-convergencia-lanzamiento-mq26`**.
- **Acta (mínimo):** **requisitos congelados** para el lanzamiento; **plan de mercado** (canales, fechas, responsables, mensajes clave); **Go / No-Go** (o Go con condiciones). Registrar enlace o cuerpo en [`COMITES_MQ26_INDICE_Y_AVANCE.md`](./COMITES_MQ26_INDICE_Y_AVANCE.md) (*Registro de última sesión*) o en el ticket de release.

### Fin de la cadena *Hacia mercado* 1–5

Tras el sprint **5** y el veredicto **Go** (según acta), el equipo ejecuta el **día D** operativo (despliegue, comunicación acordada) sin sustituir la skill ni este documento para decisiones nuevas de alcance: cambios mayores vuelven a **PENDIENTES** §10 y, si aplica, a un nuevo ciclo de sprints.

---

## Los cuatro comités (roles)

| Comité | Enfoque | Skill en Cursor (proyecto) |
|--------|---------|----------------------------|
| **Expertos Carteras AR** | Qué ofrece el producto, riesgo, motor, roadmap P0–P3, confianza del inversor | `comite-expertos-carteras-ar` |
| **UX MQ26** | Cómo se ve y se comporta la UI (tokens, Barlow, accesibilidad, M41–M539) | `comite-ux-mq26` |
| **Implementación** | Entrega técnica: alcance cerrado, calidad, CI, despliegue, observabilidad, “listo para producción” | `comite-implementacion-mq26` |
| **Marketing** | Mensaje al mercado, canales, narrativa, sin promesas de rentabilidad; plan de lanzamiento comunicacional | `comite-marketing-mq26` |

**Orquestación de la reunión única:** cuando los cuatro ángulos deben cerrar juntos, usar la skill **`comite-convergencia-lanzamiento-mq26`** (agenda y salidas esperadas).

---

## Cuándo convocar la convergencia

- **Gate mínimo sugerido:** build estable, criterios de “producto listo” acordados (ver checklist abajo) y **ventana de lanzamiento** definida a nivel comercial (aunque sea interna).
- **No sustituye sprints:** la convergencia es un **hito**; el trabajo diario sigue en cada comité según su skill.

### Checklist previa (entrada a la sala)

- [ ] **Expertos:** lista de funcionalidades incluidas en el release y exclusiones explícitas; riesgos residuales documentados.
- [ ] **UX:** estado del design system aplicable al release; temas claro/oscuro revisados en pantallas críticas.
- [ ] **Implementación:** CI verde, despliegue probado (staging o equivalente), runbook/ops al día para lo que se lanza.
- [ ] **Marketing:** borrador de mensaje y canales; **revisión legal/compliance** si aplica (disclaimers alineados al producto real).

---

## Agenda tipo “todos en la mesa” (orden sugerido)

Duración orientativa: 60–90 minutos. Objetivo: **requisitos alineados** + **plan de lanzamiento al mercado** sin contradicciones.

1. **Contexto (5 min)** — Qué release es, qué fecha objetivo y qué no entra.
2. **Expertos (10–15 min)** — Qué promete el producto en el mundo real; límites y disclaimers; qué debe quedar claro en copy y en UI.
3. **Implementación (10–15 min)** — Qué está desplegado y cómo se monitorea; degradaciones conocidas; criterios de rollback.
4. **UX (10 min)** — Coherencia visual y de flujo en la experiencia que verá el mercado; accesibilidad mínima acordada.
5. **Marketing (10–15 min)** — Narrativa, audiencias, canales; ajustes para no **sobre-prometer** frente a lo que Expertos + Implementación confirmaron.
6. **Convergencia (15–20 min)** — Decisiones cerradas: requisitos congelados para comunicación; fecha de lanzamiento o “no-go”; dueños y próximos pasos.

**Regla de conversación:** cada comité expone **límites y dependencias** antes de pedir cambios a otros; Marketing no fija promesas que Expertos no respalden; Implementación no asume alcance que no esté en el build.

---

## Salidas obligatorias (documentación mínima)

Tras la sesión, deberían existir (aunque sea en el cuerpo del ticket o del PR de release):

1. **Requisitos congelados para el lanzamiento** — qué está dentro y qué queda fuera (una sola fuente de verdad para copy y demos).
2. **Plan de lanzamiento al mercado** — canales, fechas, mensajes clave, materiales, responsables.
3. **Go / No-Go explícito** — con firma o consenso registrado (quién decide en última instancia debe estar definido en el equipo).

Opcional: enlace a `docs/DEPLOY_RAILWAY.md` u operación equivalente para el **día D**.

---

## Relación con Excelencia y fases

- **Fase E (premium / integraciones comerciales):** solo entra en el plan de mercado si hay **gate comercial** explícito (ver `EXCELENCIA_INDUSTRIAL_FASES.md`).
- **Fase D:** no bloquea el lanzamiento por sí sola salvo riesgo operativo; la convergencia debe explicitar si “deuda técnica aceptada” forma parte del release.

---

*Documento vivo; actualizar cuando cambie el modelo de gobierno o los dueños por comité.*
