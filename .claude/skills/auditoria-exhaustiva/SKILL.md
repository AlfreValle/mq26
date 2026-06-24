---
name: auditoria-exhaustiva
description: Auditoría exhaustiva de MQ26 (o un proyecto financiero/SaaS similar) — correctitud de dinero, datos, motor de recomendación, seguridad, UX, confiabilidad, tests, CI/deploy, dependencias y arquitectura. Usar cuando el usuario pida "auditá el proyecto", "revisión completa", "qué está mal / qué falta para vender", o antes de un release importante.
---

# Auditoría exhaustiva MQ26

App financiera en producción (carteras AR, multi-rol/SaaS, cálculos de dinero
reales). El objetivo del audit NO es opinar: es **encontrar lo que está mal y
demostrarlo con números reproducibles**, con la vara "¿se puede vender y operar
con plata real sin romper la confianza?".

## Los 3 principios (no negociables)

1. **Reproducir, no opinar.** Cada hallazgo se prueba con un script mínimo y un
   **número** ("DICP da P&L −99.93%", "efectivo 21%"). Sin número, es corazonada.
2. **Distinguir bug de decisión de diseño.** (Ej.: el 20% de "perlas" sin invertir
   era diseño; el 100× de las letras era bug.) Confundirlos rompe lo que andaba.
3. **Falsar la propia hipótesis.** Verificá la causa, no la confirmes. Si la
   hipótesis no se reproduce, declarala falsa (pasó: "faltan precios RF" era falso).

## Método (orquestación)

Fan-out por dimensión con revisores especializados EN PARALELO, luego verificación:
- `revisor-quant` → dimensiones 1-3 (lo que más plata mueve)
- `revisor-ux-mq26` → dimensión 5
- `explorador-mq26` / Explore → 4, 6, 7, 8, 9, 10
- **Pase de síntesis**: deduplica y prioriza.
- **Crítico de completitud**: "¿qué dimensión no se cubrió, qué hallazgo no se verificó?".
- Para cada P0: 2-3 verificadores **adversariales** independientes antes de confirmarlo.

Si el usuario habilitó workflows/ultracode, correlo como workflow multi-agente
(find → verify adversarial → synthesize). Si no, lanzá los agentes con el Agent tool.

## Dimensiones (probar cada una con reproducción)

1. **Correctitud cuantitativa / de dinero (máxima prioridad).** Unidades y escala
   (% vs fracción, ×100), moneda (ARS/USD/CCL, conversión por fecha), valor
   nominal/lámina, paridad, TIR, P&L, costo histórico. **Probar cada tipo de
   instrumento por separado** (no asumir que si uno anda, andan todos — pasó con
   "solo ON_USD calculaba bien"). Comprar a precio de referencia → P&L ~0; si no,
   hay bug de escala.
2. **Fundación de datos.** Frescura vs staleness, fuentes en vivo vs fallback, qué
   pasa con una conexión caída/pausada. ¿El fallback enmascara errores? ¿El usuario
   sabe que ve datos viejos?
3. **Motor de decisión/recomendación.** ¿Despliega lo que debe? Casos borde (poco
   capital, mucho, cartera vacía, ya-óptima). ¿Concentración? ¿Efectivo ocioso?
   ¿La selección usa el scoring real o un fallback estático?
4. **Seguridad.** Secrets en repo/historial (incluí `.env*`/backups), aislamiento
   multi-tenant (IDOR: ¿un asesor ve clientes de otro?), matriz rol×acción
   (deny-by-default), fail-closed.
5. **Usabilidad por rol** (onboarding, jerga sin explicar, estados vacíos sin
   salida, callejones, errores crudos) con la vara del comprador objetivo.
6. **Confiabilidad.** Manejo de errores, degradación elegante, performance (reruns,
   recálculos, red innecesaria), reproducibilidad offline.
7. **Tests.** Cobertura **real vs declarada** (¿el gate mide o corre `--no-cov`?),
   invariantes vs valores mágicos, caminos críticos sin test.
8. **CI/CD y deploy.** ¿Los gates corren de verdad? ¿Deploy reproducible (versiones
   pineadas)? Secrets/infra.
9. **Higiene de dependencias.** PRs de update pendientes; saltos mayores que rompen
   — revisar el **USO en el código**, no solo la versión (pasó con
   streamlit-authenticator 0.3→0.4).
10. **Arquitectura/mantenibilidad.** Código muerto/duplicado, módulos gigantes,
    lógica duplicada, deuda que delata "prototipo".

## Formato de salida (por hallazgo)

`[P0|P1|P2] archivo:línea — qué está mal — número que lo demuestra (antes→después
esperado) — impacto (dinero/venta/seguridad) — fix concreto — esfuerzo (S/M/L)`

P0 = bloquea operar/vender o corrompe plata. Priorizar por impacto en la decisión
de compra y en la integridad del dinero.

## Reglas

- No inflar hallazgos (el silencio sobre algo correcto vale).
- No proponer fixes a ciegas en lógica de dinero: marcar lo que necesita
  verificación en vivo.
- No tocar `main`/producción; entregar ramas/PRs.
- Verificación antes de cerrar: ruff + suite (ver skill `verificar-mq26`).

## Entregable final

Backlog priorizado (P0/P1/P2) con la evidencia numérica de cada hallazgo, separando
"bug real" de "decisión de diseño", y un plan por sprints. Persistir en
`docs/` si el audit es grande (ver `docs/PLAN_USABILIDAD_VENTA.md` como ejemplo).
