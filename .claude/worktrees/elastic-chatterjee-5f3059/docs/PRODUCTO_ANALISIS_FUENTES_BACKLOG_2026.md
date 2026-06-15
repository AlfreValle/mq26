# MQ26-DSS: análisis de fuentes de datos y backlog competitivo (referencia 2026)

**Fecha de referencia:** 24 de marzo de 2026  
**Autor original del análisis:** ecosistema de datos financieros argentinos + benchmark de producto  
**Uso en el repo:** documento de **referencia** (benchmark y narrativa). La **fuente de verdad para priorización e issues** sigue siendo [BACKLOG_MOSCOW.md](BACKLOG_MOSCOW.md) (IDs **A01–A50 / D01–D50 / U01–U50**).

---

## Verificación legal y técnica (obligatoria antes de citar en contratos)

- **URLs, productos BYMA/BYMADATA/CNV e IOL** cambian con frecuencia. Los enlaces y condiciones comerciales (“miembro”, “no miembro”, Market Data API) deben **confirmarse en el sitio oficial y en contrato** vigente al momento de licenciar.
- **CAFCI:** el código (`services/cafci_connector.py`) consume la API pública y mantiene **catálogo cacheado**; la **cobertura del universo de fondos** en API es amplia, pero la **calidad en producto** depende de mapear nombres/CUIT a posiciones del usuario y del uso en UI (no asumir “100% resuelto” sin validación de negocio).
- Este documento **no** constituye asesoramiento legal ni comercial.

---

## Crosswalk: mejoras de este documento (A1–P150) → BACKLOG MoSCoW (A/D/U)

Los IDs **A1, B16, F51…** del texto largo son **del análisis original**. Los del repo son **A01…A50, D01…D50, U01…U50**. La tabla agrupa por bloque temático.

### Arquitectura / datos / escala / seguridad / QA / DevOps

| Bloque análisis 2026 | Encaje principal MoSCoW |
| --- | --- |
| A1 Multi-proveedor + fallback | A03, A16, A02, A50 |
| A2 Caché TTL / Redis (distribuido) | A17, A09, A24 |
| A3 Lineage completo metadatos | A02, A44, D27, D47 |
| A4 Webhook push cambio precio | A41 (parcial); **gap:** eventos tiempo real dedicados |
| A5 Históricos columnar Parquet | **gap** (añadir a roadmap o A12 si unifica almacén) |
| A6 Multi-moneda nativa en esquema | A01, A13, A26 |
| A7 FX histórico (ej. BCRA) | A13, A14 |
| A8 Corporate actions | A31 |
| A9 Metadata enriquecido activos | A01, A32 |
| A10 Data quality monitoring | A15, A23, A45 |
| A11 Batch nocturno pre-cálculo | A11, A12 |
| A12 Microservicio pricing | A11, A40 |
| A13 Rate limiting por fuente | A09, A48 |
| A14 Reconciliación automática | A45, A44 |
| A15 Pipeline import universal | A34, A33, U01, U02 |
| B16–B25 Particionamiento, réplicas, CDN, lazy, colas, pool, cache queries, compresión HTTP, índices | A20, A30, A05, A42, A19, A17; **gap:** GraphQL (B20), CDN/Brotli como detalle de despliegue |
| C26–C35 2FA, encryption at rest, rate limit usuario, audit, GDPR, sesiones, PII masking, Dependabot, rotación keys, DDoS | A21, A37, A48, A06, U29; **gap:** 2FA explícito, proveedor WAF, Dependabot como política de repo |
| C36–C43 E2E, chaos, perf CI, integridad datos, load test, pentest, regresión, sintético | A27–A29, A50, A22; W/N para pentest externo formal |
| E44–E50 Blue-green, flags, migraciones, observabilidad, backups+IaC, CI/CD | A39, A08, A19, A22, A38, A24 (ya hay CI en `.github/workflows/ci.yml`) |

### Diseño (F51–J100) → D01–D50

| Bloque análisis 2026 | MoSCoW repo |
| --- | --- |
| F51–F62 Tokens, dark, WCAG, iconografía, tipografía, paleta, grid, microinteracciones, breakpoints, empty states ilustrados, brand, motion | D01, D44, D32, D05, D02, D06, D03, D21, D43, D04, D41, D40 |
| G63–G72 Navegación, breadcrumbs, búsqueda global, onboarding progresivo, shortcuts, tabs portfolio, filtros persistentes, DnD, sidebar, footer | D26, U03, U04, D50, U01; **gap:** breadcrumbs profundidad URL Streamlit limitada |
| H73–H87 Visualización (D3/Recharts, sparklines, comparativas, donut drill-down, heatmap correlación, treemap, velas, timeline, attribution, risk gauge, dividend calendar, export chart, responsive charts, live badge) | D08, D15–D18, D09, D28, D20, D31, D35, U26 (export PNG), D27 |
| I88–I95 Storybook, toasts, modales, loading, error boundary React, forms, empty, paginación | D39 (W), D21, D22; **gap:** React/Storybook si stack sigue siendo solo Streamlit |
| J96–J100 Mobile-first, touch, swipe, PWA, nav móvil | D43, D25 |

### UX (K101–P150) → U01–U50

| Bloque análisis 2026 | MoSCoW repo |
| --- | --- |
| K101–K110 Tour, checklist setup, demo portfolio, import wizard, video, quick add, plantillas, email next steps, progress import, help bubbles | U01, U02, U47, U41, U17, U36, U16 |
| L111–L120 Widgets dashboard, net worth, period selector, quick actions, alertas banner, summary cards, winners/losers, activity feed, market overview, objetivo progress | U08, U35, U07, D07; **gap:** widgets drag-drop modulares como producto |
| M121–M130 Agrupación holdings, bulk actions, inline edit, cost basis, colores performance, tags, notas, export vistas, multi-portfolio, comparar portfolios | U20–U22, U30, U14, U48, U12 |
| N131–N138 Date picker, duplicar tx, bulk import preview, currency auto, recurrence, tipos tx claros, confirm delete, export histórico | U02, U05, U44, U45 |
| O139–O145 AI insights, benchmarking auto, fee analyzer, dividend yield dashboard, tax loss harvesting, correlación, escenarios | U11, U10; **gap:** AI insights, fee analyzer, tax loss como features nuevas |
| P146–P150 Moneda display, tema color, notificaciones granulares, export programado, API power users | U49, U08, U09; A40, A49 (API documentada) |

### Ítems destacados sin fila 1:1 en MoSCoW (candidatos a ampliar backlog v2)

- Webhooks de **precio** en tiempo real (distinto de alertas Telegram).
- **GraphQL** para frontend si se separa API.
- **Parquet** / almacén analítico de series largas.
- **2FA** obligatorio por umbral de patrimonio.
- **Widgets dashboard** drag-and-drop modulares.
- **AI / tax loss harvesting / fee analyzer** (producto avanzado).

---

## PARTE 1: análisis de fuentes — mercado argentino

### 1.1 Fuentes oficiales y cobertura actual

#### BYMA (Bolsas y Mercados Argentinos)

**Estado de conexión en MQ26:** parcial — depende de Yahoo Finance + maestros manuales (ver [ADR-001](adr/001-fuentes-de-datos-mq26.md), [ADR-002](adr/002-proveedores-datos-byma.md)).

**Referencias de mercado (verificar antes de licitar):**

- Productos de datos / APIs comerciales según BYMA y operadores autorizados.
- BYMADATA u otros vendors de reference data y herramientas (suscripción).

**Gap:** sin licencia acordada, la app no garantiza universo BYMA ni convenciones de cotización idénticas al libro oficial.

#### CAFCI

**Estado en repo:** conector activo — API `https://api.cafci.org.ar`, catálogo cacheado en disco, resolución fondo por nombre y opcionalmente CUIT (`services/cafci_connector.py`).

**Matiz:** “cobertura completa FCI” en **datos CAFCI** ≠ cada **posición de usuario** ya mapeada sin configuración.

#### CNV / AIF

Datos de emisores y hechos relevantes; acceso masivo programático suele ser **restringido**. Scraping o curación manual implica revisión **legal y de TOS**.

#### IOL (InvertirOnline)

API para clientes habilitados: puede servir **importación por usuario**, no como fuente universal para todos los titulares sin cuenta.

#### Otras

TradingView / Investing: útiles para gráficos; no sustituyen pipeline de pricing propio sin acuerdo. Bloomberg/Reuters: típico enterprise.

### 1.2 Cobertura real vs. promesa de producto

| Tipo de activo | Cobertura orientativa | Fuente principal en MQ26 | Gap crítico |
| --- | --- | --- | --- |
| Acciones líderes | Alta | Yahoo `.BA` | Colaterales / baja liquidez |
| CEDEARs top | Alta | Yahoo | Nuevos / illiquid; convención ARS vs subyacente |
| Bonos soberanos | Media | Maestro + Yahoo | Lámina, limpio/sucio |
| ON corporativas | Baja–media | Maestro | Automatización |
| Letras tesoro | Baja | Manual | Ticker estándar |
| FCI | Alta (datos) | CAFCI | Mapeo a cartera usuario |
| Cauciones / opciones / futuros | No objetivo core típico | — | Scope explícito |

**Conclusión:** no hay conexión oficial con **todo** BYMA. Para retail masivo con promesa de “todos los activos”, hace falta **proveedor licenciado** o integración broker. Para nicho asesor con disclaimers, el stack actual puede ser defendible.

### 1.3 Recomendaciones de arquitectura de datos (prioridad)

1. **Contrato de precio por tipo** — ver [ADR-003](adr/003-convencion-precios-y-lineage.md).
2. **Lineage explícito** — fuente, timestamp, stale/error, retraso estimado.
3. **Degradación** — último precio conocido + aviso; sin pantallas rotas.
4. Post-piloto: evaluación económica licencia BYMA / data vendor; import broker (IOL, etc.).

---

## PARTE 2: 150 mejoras competitivas (texto de benchmark)

*Benchmarks citados en el análisis original: Empower / Personal Capital, Kubera, Snowball, Morningstar, Delta/CoinStats, Sharesight, IOL, BYMADATA, TradingView, etc.*

### 2.1 Arquitectura

**A. Datos y proveedores (A1–A15)**  
A1. Multi-proveedor con fallback (BYMA → Yahoo → maestro → cache).  
A2. Caché TTL adaptativo; Redis multi-instancia.  
A3. Data lineage en cada precio (valor, fuente, timestamp, delay, confianza).  
A4. Webhook/eventos ante movimiento de precio &gt; umbral.  
A5. Históricos largos en formato columnar (Parquet).  
A6. Esquema multi-moneda nativo por holding.  
A7. FX histórica automática (ej. BCRA).  
A8. Corporate actions en tabla y ajustes cantidades/PPC.  
A9. Metadata enriquecido (sector, cap, ratios).  
A10. Monitoreo calidad de datos (stale, anomalías).  
A11. Batch nocturno de recálculos.  
A12. Microservicio de pricing desacoplado.  
A13. Rate limiting y backoff por proveedor.  
A14. Reconciliación automática entre fuentes.  
A15. Pipeline universal de import CSV/broker.

**B. Performance y escalabilidad (B16–B25)**  
B16. Particionamiento por usuario. B17. Read replicas. B18. CDN estáticos.  
B19. Lazy loading de tabs pesados. B20. GraphQL. B21. Cola async Celery/RQ.  
B22. Connection pooling. B23. Caché de queries de cartera. B24. Compresión HTTP.  
B25. Índices estratégicos.

**C. Seguridad y compliance (C26–C35)**  
C26. 2FA. C27. Encryption at rest. C28. Rate limit por usuario API.  
C29. Audit log. C30. GDPR / residencia datos. C31. Sesiones y JWT.  
C32. PII masking en logs. C33. Escaneo vulnerabilidades dependencias.  
C34. Rotación API keys. C35. Protección DDoS.

**D. Testing y QA (C36–C43)**  
*(Nota: en el documento original la numeración comparte prefijo “C” con seguridad.)*  
C36. E2E flujos críticos. C37. Chaos en staging. C38. Benchmarks perf en CI.  
C39. Tests integridad contable. C40. Load tests. C41. Pentest externo.  
C42. Regresión por bugfix. C43. Monitoreo sintético 24/7.

**E. DevOps (E44–E50)**  
E44. Blue-green. E45. Feature flags. E46. Migraciones con rollback.  
E47. Observabilidad completa. E48. Backup + restore probado.  
E49. IaC. E50. CI/CD end-to-end.

### 2.2 Diseño

**F. Visual design (F51–F62)** — tokens, dark mode, WCAG, iconografía, tipografía, paleta finanzas, grid 8px, microinteracciones, breakpoints, empty states, brand, motion.

**G. Information architecture (G63–G72)** — navegación clara, breadcrumbs, búsqueda global `Cmd+K`, onboarding, shortcuts, tabs portfolio, filtros persistentes, drag-drop, sidebar colapsable, footer legal.

**H. Data visualization (H73–H87)** — charts interactivos, semántica de color + daltonismo, sparklines, comparación vs benchmarks, donut drill-down, heatmap correlación, treemap, velas + indicadores, timeline transacciones, attribution, risk gauge, calendario dividendos, export PNG/SVG, responsive charts, badge live update.

**I. Componentes (I88–I95)** — Storybook, toasts, modales, loading/skeleton, error boundaries (React), validación forms, empty states, paginación/infinite scroll.

**J. Mobile (J96–J100)** — mobile-first, touch targets, swipe gestures, PWA, navegación adaptativa.

### 2.3 UX/UI

**K. Onboarding (K101–K110)** — tour, checklist, portfolio demo, import wizard, video, quick add, plantillas, email post-registro, progress bar import, help contextual.

**L. Dashboard (L111–L120)** — widgets modulares, net worth hero, selector periodo, quick actions, alertas, cards resumen, top winners/losers, actividad reciente, overview mercado, progreso objetivos.

**M. Portfolio (M121–M130)** — agrupación, bulk actions, inline edit, cost basis visible, colores performance, tags, notas, export vistas, multi-portfolio, modo comparación.

**N. Transacciones (N131–N138)** — date picker inteligente, duplicar tx, preview import con errores, detección moneda, recurrence, tipos claros, confirmación borrado, export filtrado.

**O. Análisis (O139–O145)** — insights ML (opcional), benchmarking, fee analyzer, dividend dashboard, tax loss suggestions (disclaimer), matriz correlación, escenarios.

**P. Personalización (P146–P150)** — moneda display, tema, preferencias notificaciones, export programado, API keys usuarios power.

---

## Resumen ejecutivo de fases (del análisis original)

| Fase | Horizonte | Enfoque |
| --- | --- | --- |
| Fase 1 MVP defendible | 4–6 semanas | Lineage, caché/fallback, diseño base, onboarding, dashboard core, portfolio básico, seguridad mínima viable |
| Fase 2 PMF | 3–6 meses | Multi-moneda/actions, visualizaciones avanzadas, insights, IA |
| Fase 3 Escala | 6–12 meses | Infra multi-instancia, observabilidad, personalización profunda, design system dev |

---

## Next steps accionables (alineados al repo)

1. **Modelo de precios:** [ADR-003](adr/003-convencion-precios-y-lineage.md) + implementación incremental en `price_engine` / `cartera_service` cuando se apruebe.
2. **Licencia BYMA / vendor:** decisión comercial; actualizar [ADR-002](adr/002-proveedores-datos-byma.md) al decidir.
3. **Priorización:** sesión MoSCoW sobre [BACKLOG_MOSCOW.md](BACKLOG_MOSCOW.md); usar este documento solo para **contexto y gaps** nuevos listados arriba.

---

## Anexo: stack técnico MQ26 (repo)

- Python 3.12+, Streamlit, PostgreSQL/SQLite, pandas, yfinance, plotly, pytest (umbral cobertura en `pyproject.toml`), Alembic, GitHub Actions, Railway (workflow existente).

---

**Versión documento en repo:** 1.1 (integración con MoSCoW + ADR-003)
