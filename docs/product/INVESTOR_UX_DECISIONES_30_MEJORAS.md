# MQ26 · Base de comprensión del inversor + Estudio + Asesor + UI responsive

Documento para **decidir** qué se mantiene, qué se saca, qué merece **pestaña nueva** o **fusión**, y cómo ordenar el trabajo. La **primera parte (inversor)** es la base conceptual de “qué necesita entender una persona”; **Estudio** y **Asesor** reutilizan los mismos motores con **otra escala** y **otras suites** de presentación. Incluye requisitos transversales de **legibilidad** y **adaptación a notebook / PC / tablet / móvil**. Complementa ideas ya charladas (perfil ideal, carga simple, comparación vs óptimo, rebalanceo, contexto automático, salida/stop).

---

## Cómo usar este documento

Para cada ítem o bloque funcional, elegí una etiqueta:

| Decisión | Significado |
|----------|-------------|
| **QUEDA** | Se mantiene donde está (quizá solo mejoras menores). |
| **SALE** | Se elimina, oculta por rol, o pasa a solo B2B. |
| **NUEVA** | Nueva pestaña o pantalla dedicada (evitar si se puede un flujo guiado). |
| **FUSIÓN** | Se integra dentro de otra vista (menos tabs, más asistente). |
| **AUTO** | El motor hace el cálculo; el usuario solo confirma o ajusta 1–2 parámetros. |

Podés anotar al margen: `QUEDA | SALE | NUEVA | FUSIÓN` + prioridad `P0/P1/P2`.

---

## Contexto actual (recordatorio)

Hoy el **inversor** en `run_mq26.py` ve en gran medida **una sola pestaña** (“Mi cartera”). El resto de potencia (optimización, riesgo, mesa de ejecución, universo) está del lado **asesor/admin**. Tu intuición es correcta: **muchos motores son útiles pero el recorrido inversor no está “ensamblado”** como producto guiado.

---

## Una base, tres experiencias (misma lógica, distinta escala)

| Rol | Escala | Cambia respecto al inversor |
|-----|--------|-----------------------------|
| **Inversor** | 1 persona | Hub simple: una cartera, un perfil, acciones claras. |
| **Estudio** | N clientes (10 / 20 / 100…) | **Todo lo del inversor**, multiplicado: lista/dash de carteras, alertas agregadas, drill-down por cliente, onboarding masivo y comparativos “quién está peor vs su ideal”. Sin duplicar motores; sí **vistas de agregación** (semáforos, ranking de riesgo, tareas pendientes por centro de costos). |
| **Asesor** | N clientes + herramientas pro | Misma base de datos y motores; **pestañas separadas por tipo de análisis** y **suites** configurables (ver sección siguiente). |

**Principio:** el inversor no “ve” el laboratorio; el estudio **prioriza** quién mirar primero; el asesor **profundiza** con la mejor suite posible sin romper el núcleo estable.

---

## Estudio: multi-cliente sin perder la brújula

- **Vista “torre de control”:** tabla o tarjetas con cliente, perfil, % alineación vs ideal, última carga, alertas abiertas (mismo lenguaje que el hub inversor para coherencia).  
- **Mismos pasos mentales** que el inversor (qué tiene / qué debería / qué hacer), pero **en paralelo** y con **filtros** (peor alineado, vence objetivo, sin posiciones).  
- **Bulk operativo:** generación de informes, notas de asesor, recordatorios; no exigir repetir 20 veces el mismo click.  
- **Límite de complejidad:** el estudio no debería ser “20 copias del asesor apiladas”; si algo es ultra-técnico, queda en tier asesor o en expander “profundizar”.

---

## Asesor: suites de análisis que aprovechen el motor (sin reescribir lo sólido)

**Objetivo:** que el asesor sienta que tiene la **mejor suite** de análisis para clientes retail/pro, sin que MQ26 se convierta en 200 toggles. La **estructura** (optimización, riesgo, scoring, cartera, ejecución, reportes) **se mantiene**; cambia la **curaduría** en pestañas y **presets**.

### Pestañas / bloques sugeridos (separados por tipo de análisis)

1. **Cartera y posición** (libro + valoración + cobertura de precios).  
2. **Universo y señales** (scanner acotado por preset del asesor).  
3. **Optimización** (modelos existentes; entrada única de restricciones RF/RV).  
4. **Riesgo y simulación** (métricas hero + laboratorio honesto).  
5. **Mesa de ejecución** (órdenes accionables).  
6. **Reporte e informe cliente** (export, email).

### Parametrización “sí, pero con techo”

- **% Renta fija / variable (objetivo o techo):** el asesor define **rangos o anclas** que alimentan al optimizador y al diagnóstico (una sola fuente de verdad, como ya planteaste para inversor).  
- **Qué incluir en cada bucket:** selección de **subconjuntos** (ej. solo bonos ARS + CEDEARs tech + panel local energía), guardado como **preset** reutilizable (“Conservador RF pesado”, “RV internacional light”).  
- **No demasiado:** máximo **N presets** nombrados + **un “Custom”** con sliders acotados; evitar matriz infinita de checkboxes. Los casos raros pueden seguir en admin o script.

### “Suites” = combinación preset + pestañas visibles

- Suite **Estándar:** pocas métricas, foco informe y ejecución.  
- Suite **Quant:** más riesgo, correlaciones, optimización comparada.  
- Suite **Institucional** (si aplica): export, auditoría, multi-cuenta.  
Misma base de código; **distinta plantilla de UI** (`layout` + qué expanders vienen abiertos por defecto).

---

## UI/UX transversal: legibilidad, tablas y responsive (P0 producto)

**Problema percibido:** pantalla muy oscura, texto difícil de leer; tablas que no se adaptan; en notebook vs móvil se pierde lo importante.

### Lineamientos (aplicar a inversor, estudio y asesor)

1. **Contraste:** texto principal **mínimo ~4.5:1** respecto al fondo (objetivo WCAG AA en copy largo); evitar gris sobre gris en tema oscuro. **Tema claro por defecto** en retail si el oscuro no está auditado.  
2. **Jerarquía visual:** una sola “pieza hero” por scroll en móvil (métrica o tabla principal); el resto debajo o en acordeón.  
3. **Tablas:** `st.dataframe` / componentes con **altura máxima + scroll interno**; columnas clave fijadas si la lib lo permite; en pantallas chicas **ocultar columnas secundarias** o **vista tarjeta** por fila.  
4. **Breakpoints mentales:**  
   - **Móvil (<768px):** 1 columna, CTAs ancho completo, gráficos altura fija razonable.  
   - **Tablet:** 2 columnas donde aporte; tablas con scroll horizontal **con indicador** (“deslizá →”).  
   - **Notebook / PC:** rejilla 2–3 columnas; más densidad solo donde el rol lo justifique (asesor).  
5. **Tipografía:** tamaño mínimo 14–16px cuerpo; títulos +2–4 escalones; no depender de color solo para estado (usar icono o texto).  
6. **Prueba física:** revisar cada pantalla crítica en **1366×768** (notebook), **390px** ancho (móvil) y **tablet** intermedia.

### Relación con Streamlit

Hoy el layout depende mucho de CSS/markdown y de `use_container_width`. Trabajo típico: **tokens de color** (fondo, superficie, texto, acento), **bloques** reutilizables en `mq26_ux` o CSS central, y **menos** estilos inline duplicados.

---

## Opinión: qué debería ser para el inversor que recién arranca

**Objetivo:** que en **5 minutos** entienda: *qué tengo / qué debería tener / qué hacer hoy* — sin pedirle que entienda optimización convexa ni correlaciones.

**Navegación óptima (conceptual), alineada a buenas prácticas de apps de inversión y a vuestros motores:**

1. **Hogar inversor (una sola entrada)**  
   Un único “hub” (puede ser la pestaña actual renombrada y reordenada) con **pasos verticales** o acordeón:  
   `(1) Mi cartera real` → `(2) Mi objetivo (perfil + plazo)` → `(3) Comparación vs ideal` → `(4) Qué hacer` (comprar, esperar, rebalancear) → `(5) Salidas y reglas` (stop, objetivo cumplido).

2. **Sin cartera cargada**  
   Primero **carga mínima** (CSV broker, 3 campos manuales, o “empezar con cartera sugerida de ejemplo” en demo). Sin activos, el diagnóstico siempre será incompleto; la app debe **decirlo explícitamente** y ofrecer **solo** caminos: carga / perfil-only con rangos genéricos educativos.

3. **Cartera “sugerida por la app”**  
   No reemplaza la cartera real hasta que el usuario **acepte** (“usar como referencia” vs “ Registrar como mi cartera modelo”). Evita confusiones legales y de expectativas.

4. **Un motor visible, muchos por debajo**  
   Optimización, riesgo, scoring y diagnóstico deberían **alimentar tarjetas** (“desvío vs objetivo”, “prioridad 1”) en lugar de exponerse como laboratorio.

5. **Parametrización por cliente**  
   Perfil, plazo, tope de volatilidad, % máximo en un activo, si acepta internacional, moneda de referencia — eso **condiciona umbrales** (rebalanceo, alerta MOD-23, pesos óptimos). Lo demás **AUTO**.

6. **Pestaña “Comparar / Camino al óptimo”** (nombre comercial suave: “¿Voy bien?”)  
   Tiene sentido **como segunda vista** solo si el hogar se mantiene breve; si no, **FUSIÓN** dentro del hub como sección expandida. Evitá tres lugares que digan lo mismo.

---

## 30 mejoras (lista accionable)

1. **Asistente de primera vez** al login inversor: detectar `cartera vacía` → flujo obligado (carga o “omitir con advertencia”).  
2. **Tres vías de carga**: import CSV/OCA, “cargá 5 líneas a mano”, enlazar con asesor que carga por vos.  
3. **Perfil + horizonte** en el propio flujo inversor (no solo wizard estudio), con **texto en criollo** (Conservador = más X, menos Y).  
4. **Tabla “ideal por perfil”** visible y trazable (fuente: reglas internas documentadas, no caja negra).  
5. **Gauge principal**: % alineación con ideal (una métrica principal antes del resto).  
6. **“Qué hacer hoy”** priorizado: máx. 3 acciones (comprar X, reducir Y, no operar).  
7. **Botón único “Quiero comprar más”** que abre flujo de capital nuevo enlazado a límites de perfil.  
8. **Rebalanceo en lenguaje simple**: “Te desviaste X% del objetivo; sugerimos mover Z” + umbral parametrizable por perfil.  
9. **Modo educativo** toggle: más explicación vs vista compacta.  
10. **Comparación multi-portfolio** (real vs modelo vs “si hubiera seguido el plan”) en una sola gráfica cuando haya datos.  
11. **Salida y stop**: integrar **Motor de salida** como **sección** del hub inversor (no solo sidebar genérico).  
12. **Alertas inteligentes**: solo las que el perfil marcó como relevantes (menos ruido).  
13. **Contexto de mercado** en 3 bullets + “última actualización” y fuente (aunque sea “interno + Yahoo”).  
14. **Internacional sí/no** como pregunta explícita que **reescribe** el universo sugerido y los límites.  
15. **Sincronización explícita** entre “objetivo declarado” y “parámetros del optimizador” (una sola verdad).  
16. **Historial de decisiones** del usuario (“acepté sugerencia el …”) para auditoría y confianza.  
17. **PDF/HTML ligero** “estado de mi cartera” para el inversor (sin depender del estudio).  
18. **Demo tour** 60 s si `DEMO_MODE` o primera visita.  
19. **Accesibilidad**: contraste, tamaños, teclado; mejora percepción de “app profesional”.  
20. **Mobile-first** en el hub (el inversor argentino usa mucho celular).  
21. **Menos métricas simultáneas** en la primera pantalla; el resto en “detalle para curiosos”.  
22. **Glosario inline** (tooltips) para RF/RV, CEDEAR, drawdown — ya tenés patrones en riesgo; reutilizar.  
23. **Límites regulatorios/disclaimers** en el momento de la acción sugerida (no solo al pie).  
24. **Integración asesor**: botón “Pedir revisión” que envía snapshot (email/Telegram interno).  
25. **Offline degradado**: si no hay precios LIVE, mensaje claro + usar último cierre sin fingir precisión.  
26. **Parametrización por tenant** (B2B): mismos motores, distintos umbrales por marca/asesor.  
27. **Pruebas A/B de copy** en CTAs (“Rebalancear” vs “Alinear con mi plan”).  
28. **Telemetría de producto** (opt-in): dónde abandonan en el flujo inversor.  
29. **Cache y tiempos**: spinners con “qué está calculando” para motores lentos.  
30. **Roadmap visible** (qué viene en inversor próximas semanas) para gestionar expectativas.

---

## Qué suele estar “de más” para el inversor retail (candidatos a SALE o solo asesor)

Estas funciones suelen **confundir o abrumar** si están al mismo nivel que “Mi cartera”. No implica borrarlas del producto completo.

- Laboratorio completo de **optimización multi-modelo** sin narrativa.  
- **Universo y scanner** completo (mejor: “activos recomendados para tu perfil” filtrado).  
- **Riesgo avanzado** (VaR, correlaciones) antes de tener cartera mínima cargada.  
- **Mesa de ejecución** cruda sin órdenes ya traducidas a texto humano.  
- Cualquier pantalla que requiera **entender PPC, nominal, ratio** sin asistente.

*Decisión sugerida:* **SALE** del tier inversor como pantalla principal → **FUSIÓN** en resúmenes o **QUEDA** solo en tier profesional.

---

## Esqueleto de pestañas inversor (propuesta de decisión)

Anotá tu veredicto en la segunda columna cuando lo tengas claro.

| Bloque | Sugerencia inicial | Tu decisión |
|--------|-------------------|-------------|
| Mi cartera / Hub | **QUEDA** pero reestructurado como hogar con pasos | |
| Carga de activos | **FUSIÓN** dentro del hub (siempre a 1 clic) | |
| Diagnóstico vs perfil ideal | **FUSIÓN** en hub + snapshot en PDF | |
| Comparar vs óptimo | **NUEVA** *o* **FUSIÓN** en sección “¿Voy bien?” | |
| Comprar / más capital | **FUSIÓN** como CTA desde “Qué hacer hoy” | |
| Rebalanceo | **FUSIÓN** + **AUTO** con confirmación | |
| Salida / stop / objetivos | **FUSIÓN** (motor salida embebido) | |
| Contexto mercado | **FUSIÓN** (bloque corto en hub) | |
| Optimización “tal cual hoy” | **SALE** del inversor retail (solo asesor) | |
| Riesgo avanzado | **SALE** del inversor retail o link “Profundizar” | |
| Universo completo | **SALE** inversor; recorte a lista contextual | |

---

## Motores que ya tenés y cómo parametrizarlos “por lo que el cliente busca”

- **Diagnóstico / perfil / scoring:** umbrales de semáforo y mensajes según perfil y plazo.  
- **Optimizador:** usar **el mismo vector de restricciones** que el usuario declaró (límites RF/RV, país, ticket máximo).  
- **Riesgo:** mostrar **una** métrica hero + detalle opcional.  
- **Motor de salida:** reglas de stop y objetivo ligadas al **perfil** (más estricto conservador).  
- **Monitor MOD-23 / alertas:** silenciar categorías según preferencias explícitas.

Línea roja: **no prometer** rentabilidad; sí prometer **coherencia con el plan declarado** y **transparencia de fuentes**.

---

## Próximo paso práctico (cuando quieras implementar)

1. Congelar **una** definición de “perfil ideal” (tabla RF/RV + internacional).  
2. Elegir **QUEDA/SALE/NUEVA/FUSIÓN** para cada bloque de la tabla de arriba.  
3. Definir **tokens de tema** (claro/oscuro) y checklist de **contraste + tablas + breakpoints** (bloque UI de arriba).  
4. Wireframe **hub inversor** + wireframe **torre de control estudio** + matriz **suites asesor** (presets × pestañas).  
5. Solo entonces tocar código: primero flujo vacío → carga → comparación → acciones; en paralelo **deuda UI** en pantallas más usadas.

---

## Resumen ejecutivo

- **Inversor** = una brújula clara (este doc como base).  
- **Estudio** = misma brújula × N clientes, con priorización y operaciones masivas.  
- **Asesor** = motores actuales + **suites** y **presets RF/RV/instrumentos**, en pestañas de análisis separadas, sin inflar la parametrización.  
- **Todos** = misma exigencia de **lectura cómoda** y **layout que funcione en notebook, PC, tablet y móvil**.

---

*Documento elaborado para decisión de producto; actualizar según feedback legal/comercial.*
