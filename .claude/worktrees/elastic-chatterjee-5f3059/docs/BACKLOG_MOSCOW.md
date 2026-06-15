# Backlog competitivo MQ26 — priorización MoSCoW

Origen: plan *Cobertura de datos, fuentes y backlog competitivo* (150 ítems: 50 arquitectura, 50 diseño, 50 UX/UI).  
Convención de issues: al crear tickets en el tracker, reemplazar `#TBD` por el número real y mantener el prefijo de ID (A/D/U).

**Análisis extendido (benchmark internacional, fuentes AR, crosswalk A1–P150 → esta tabla):** [PRODUCTO_ANALISIS_FUENTES_BACKLOG_2026.md](PRODUCTO_ANALISIS_FUENTES_BACKLOG_2026.md).

| Leyenda | Significado breve |
| --- | --- |
| **M (Must)** | Bloquea paridad datos/producto o riesgo legal/operativo |
| **S (Should)** | Alto impacto en confiabilidad, reporting o diferenciación |
| **C (Could)** | Mejora deseable cuando haya capacidad |
| **W (Won’t)** | Fuera de alcance corto / depende de licencias o infra no definida |

Referencias: [ADR-001 — Fuentes de datos](adr/001-fuentes-de-datos-mq26.md), [ADR-002 — Proveedores BYMA](adr/002-proveedores-datos-byma.md), [ADR-003 — Convención de precios y lineage](adr/003-convencion-precios-y-lineage.md).

---

## A — Arquitectura (50)

| ID | Descripción | MoSCoW | Issue |
| --- | --- | --- | --- |
| A01 | Capa InstrumentMaster única (ISIN/symbol BYMA, moneda, lámina, tipo, cupo) | M | [#TBD-A01](.) |
| A02 | Contrato PriceQuote (fuente, timestamp, moneda, convención cotización) | M | [#TBD-A02](.) |
| A03 | Adapter por proveedor (YFinance, BYMA vía tercero, CAFCI) con interfaz común | M | [#TBD-A03](.) |
| A04 | Normalizador bonos: precio / VN explícito en modelo | M | [#TBD-A04](.) |
| A05 | Cola async descarga precios (no bloquear Streamlit) | S | [#TBD-A05](.) |
| A06 | Event sourcing opcional operaciones (auditoría tipo broker) | C | [#TBD-A06](.) |
| A07 | Versionado snapshots cartera diarios (backtesting real) | S | [#TBD-A07](.) |
| A08 | Feature flags por tenant (activar fuentes) | S | [#TBD-A08](.) |
| A09 | Rate limiting centralizado por proveedor API | S | [#TBD-A09](.) |
| A10 | Dead letter queue fallos ETL precios | S | [#TBD-A10](.) |
| A11 | Separar ingesta (cron/worker) de servicio lectura | S | [#TBD-A11](.) |
| A12 | Materialized views / tablas resumen KPIs cartera | S | [#TBD-A12](.) |
| A13 | Multi-moneda formal (ARS/USD/CABLE) con FX por fecha | M | [#TBD-A13](.) |
| A14 | Línea de tiempo CCL alineada a fecha operación | S | [#TBD-A14](.) |
| A15 | Política stale data con umbral por tipo activo | M | [#TBD-A15](.) |
| A16 | Circuit breaker por proveedor | S | [#TBD-A16](.) |
| A17 | Caché jerárquica L1/L2/L3 | S | [#TBD-A17](.) |
| A18 | Hash de transaccional extendido a todos los maestros | S | [#TBD-A18](.) |
| A19 | Migraciones DB versionadas (Alembic) Postgres prod | S | [#TBD-A19](.) |
| A20 | Read replicas / SQLite solo dev; Postgres prod documentado | C | [#TBD-A20](.) |
| A21 | Secrets solo vault/env; nunca en código | M | [#TBD-A21](.) |
| A22 | Observabilidad: traces precios (OpenTelemetry) | C | [#TBD-A22](.) |
| A23 | Métricas Prometheus: latencia yfinance, tasa miss precio | C | [#TBD-A23](.) |
| A24 | Config por entorno (dev/stage/prod) sin tocar repo | S | [#TBD-A24](.) |
| A25 | Dominio Posición vs Orden vs Ejecución desacoplados | S | [#TBD-A25](.) |
| A26 | Motor salida: contrato sin nombres `*_usd` ambiguos | C | [#TBD-A26](.) |
| A27 | Tests de contrato pricing_utils vs PriceEngine | S | [#TBD-A27](.) |
| A28 | Fakes BYMA para CI sin red | S | [#TBD-A28](.) |
| A29 | Snapshots golden DataFrames cartera por caso | C | [#TBD-A29](.) |
| A30 | Límite tickers por request con paginación dashboards | S | [#TBD-A30](.) |
| A31 | Corporate actions (splits CEDEAR, amortizaciones bonos) | C | [#TBD-A31](.) |
| A32 | Catálogo ratios CEDEAR desde maestro descargable | S | [#TBD-A32](.) |
| A33 | Universo dinámico Excel/BD con validación schema | S | [#TBD-A33](.) |
| A34 | Plugin system conectores brokers (OFX, API) | C | [#TBD-A34](.) |
| A35 | Idempotencia import Gmail | S | [#TBD-A35](.) |
| A36 | Checksum adjuntos broker | C | [#TBD-A36](.) |
| A37 | Retención logs y PII (AR/GDPR local) | M | [#TBD-A37](.) |
| A38 | Backup DB automatizado + restore probado | S | [#TBD-A38](.) |
| A39 | Blue/green deploy Streamlit/hosting | W | [#TBD-A39](.) |
| A40 | API REST interna (FastAPI) si hay más clientes que Streamlit | C | [#TBD-A40](.) |
| A41 | Webhooks salientes alertas (además Telegram) | C | [#TBD-A41](.) |
| A42 | Colas Redis/Rabbit jobs pesados | W | [#TBD-A42](.) |
| A43 | Sandbox datos demos sin PII | S | [#TBD-A43](.) |
| A44 | Lineage: fuente de cada precio mostrado | M | [#TBD-A44](.) |
| A45 | Validación tickers vs catálogo antes guardar transaccional | M | [#TBD-A45](.) |
| A46 | Soft delete clientes/objetivos con trazabilidad | S | [#TBD-A46](.) |
| A47 | Encriptación reposo SQLite sensible (opcional) | C | [#TBD-A47](.) |
| A48 | Rate budget global usuario SaaS | C | [#TBD-A48](.) |
| A49 | OpenAPI si se expone API | C | [#TBD-A49](.) |
| A50 | Runbook operativo (caída yfinance, fallback, CAFCI) | M | [#TBD-A50](.) |

---

## D — Diseño visual / sistema / reporting (50)

| ID | Descripción | MoSCoW | Issue |
| --- | --- | --- | --- |
| D01 | Design tokens únicos dark/light | S | [#TBD-D01](.) |
| D02 | Tipografía escalada con jerarquía clara | S | [#TBD-D02](.) |
| D03 | Grilla 8px en tabs Streamlit | C | [#TBD-D03](.) |
| D04 | Estado vacío ilustrado por módulo | S | [#TBD-D04](.) |
| D05 | Iconografía única (criterio producción) | C | [#TBD-D05](.) |
| D06 | Paleta semántica WCAG AA | M | [#TBD-D06](.) |
| D07 | Cards resumen cartera tipo fintech | S | [#TBD-D07](.) |
| D08 | Sparklines en tablas posiciones | S | [#TBD-D08](.) |
| D09 | Heatmaps escala coherente + leyenda | C | [#TBD-D09](.) |
| D10 | PDF reportes marca institucional unificada | S | [#TBD-D10](.) |
| D11 | Export CSV/XLSX formatos numéricos locales AR | S | [#TBD-D11](.) |
| D12 | Tablas densas modo analítico vs retail | C | [#TBD-D12](.) |
| D13 | Microcopy español neutro (FIFO, PPC explicados) | S | [#TBD-D13](.) |
| D14 | Tooltips en todos los KPIs | S | [#TBD-D14](.) |
| D15 | Gráficos ejes miles/millones automático | S | [#TBD-D15](.) |
| D16 | Leyenda visible gráficos multi-serie | S | [#TBD-D16](.) |
| D17 | Benchmark SPY/QQQ/MERVAL misma vista cartera | S | [#TBD-D17](.) |
| D18 | Composición donut + lista ordenable | C | [#TBD-D18](.) |
| D19 | Drill-down ticker → ficha | C | [#TBD-D19](.) |
| D20 | Timeline visual operaciones estilo broker | C | [#TBD-D20](.) |
| D21 | Estados carga skeleton | S | [#TBD-D21](.) |
| D22 | Error states con acción (reintentar / fallback) | M | [#TBD-D22](.) |
| D23 | Modo impresión CSS reportes HTML | C | [#TBD-D23](.) |
| D24 | Watermark opcional desactivable prod | C | [#TBD-D24](.) |
| D25 | Favicon + extender PWA manifest | C | [#TBD-D25](.) |
| D26 | Sidebar agrupada: datos / análisis / cuenta | C | [#TBD-D26](.) |
| D27 | Badges LIVE / delayed / manual por precio | M | [#TBD-D27](.) |
| D28 | Zonas riesgo visual (VaR, concentración) | S | [#TBD-D28](.) |
| D29 | Mapa exposición país/moneda | C | [#TBD-D29](.) |
| D30 | Comparador FCI lado a lado CAFCI | S | [#TBD-D30](.) |
| D31 | Calendario eventos (cupones, vencimientos ON) | S | [#TBD-D31](.) |
| D32 | Tema alto contraste | C | [#TBD-D32](.) |
| D33 | Numeración miles separador locale | S | [#TBD-D33](.) |
| D34 | Ticker + nombre largo en hover | C | [#TBD-D34](.) |
| D35 | Mini-chart 30d por activo | C | [#TBD-D35](.) |
| D36 | Indicador progreso objetivo coherente | S | [#TBD-D36](.) |
| D37 | Código color workflow 5 pasos | C | [#TBD-D37](.) |
| D38 | Panel salud sistema visual | C | [#TBD-D38](.) |
| D39 | Storybook / catálogo componentes (si migración React) | W | [#TBD-D39](.) |
| D40 | Animaciones sutiles transición tabs | C | [#TBD-D40](.) |
| D41 | Branding tenant SaaS por CSS vars | C | [#TBD-D41](.) |
| D42 | Email HTML templates alertas | C | [#TBD-D42](.) |
| D43 | Mobile-first cartera (límites Streamlit) | S | [#TBD-D43](.) |
| D44 | Dark mode completo sin hacks | S | [#TBD-D44](.) |
| D45 | Consistencia columnas ARS/USD todos los tabs | M | [#TBD-D45](.) |
| D46 | Etiquetas tipo instrumento color por clase | C | [#TBD-D46](.) |
| D47 | Footnotes fuente datos gráficos mayores | M | [#TBD-D47](.) |
| D48 | Paginación tablas >50 filas | S | [#TBD-D48](.) |
| D49 | Filtros guardados como vistas | C | [#TBD-D49](.) |
| D50 | Guía in-app modals primera vez | S | [#TBD-D50](.) |

---

## U — UX/UI producto y accesibilidad (50)

| ID | Descripción | MoSCoW | Issue |
| --- | --- | --- | --- |
| U01 | Onboarding: CSV, mapeo columnas, validar tickers | M | [#TBD-U01](.) |
| U02 | Wizard import broker con preview pre-commit | M | [#TBD-U02](.) |
| U03 | Búsqueda global | S | [#TBD-U03](.) |
| U04 | Atajos teclado / alternativas documentadas | C | [#TBD-U04](.) |
| U05 | Undo última importación | S | [#TBD-U05](.) |
| U06 | Confirmación doble borrado masivo | S | [#TBD-U06](.) |
| U07 | Diff cartera hoy vs ayer | S | [#TBD-U07](.) |
| U08 | Alertas configurables P&L / precio / vencimiento | S | [#TBD-U08](.) |
| U09 | Notificaciones push web además Telegram | C | [#TBD-U09](.) |
| U10 | Lista acciones sugeridas hoy | C | [#TBD-U10](.) |
| U11 | Comparar cartera vs benchmark 1 clic | S | [#TBD-U11](.) |
| U12 | Simulador “qué pasa si vendo X%” | C | [#TBD-U12](.) |
| U13 | Cash implícito explícito en patrimonio | M | [#TBD-U13](.) |
| U14 | Multi-cartera sin reload pesado | S | [#TBD-U14](.) |
| U15 | Historial precio al click ticker | S | [#TBD-U15](.) |
| U16 | Tooltip explicación barra progreso objetivo | C | [#TBD-U16](.) |
| U17 | Modo educativo tooltips primera semana | C | [#TBD-U17](.) |
| U18 | Micro-toast sync exitoso | C | [#TBD-U18](.) |
| U19 | Estado offline + último update | S | [#TBD-U19](.) |
| U20 | Filtro tipo BYMA (bono, acción, CEDEAR, FCI) | S | [#TBD-U20](.) |
| U21 | Ordenamiento multi-column tabla posiciones | S | [#TBD-U21](.) |
| U22 | Pin favoritos arriba | C | [#TBD-U22](.) |
| U23 | Colapsar columnas avanzadas | C | [#TBD-U23](.) |
| U24 | Perfil riesgo visible header | C | [#TBD-U24](.) |
| U25 | Recordatorios objetivos próximos vencer | S | [#TBD-U25](.) |
| U26 | Export PNG gráficos WhatsApp | C | [#TBD-U26](.) |
| U27 | Compartir reporte link firmado temporal | C | [#TBD-U27](.) |
| U28 | Permisos rol lectura asesor junior | S | [#TBD-U28](.) |
| U29 | Auditoría quién cambió fallback precios | M | [#TBD-U29](.) |
| U30 | Comentarios por posición | C | [#TBD-U30](.) |
| U31 | Documentos adjuntos por cliente | C | [#TBD-U31](.) |
| U32 | Checklist fiscal por año | C | [#TBD-U32](.) |
| U33 | Integración calendario dividendos | C | [#TBD-U33](.) |
| U34 | Carrusel noticias ticker + disclaimer | W | [#TBD-U34](.) |
| U35 | Modo solo patrimonio cliente final | S | [#TBD-U35](.) |
| U36 | Ayuda contextual por tab | S | [#TBD-U36](.) |
| U37 | Accesibilidad foco visible / ARIA | M | [#TBD-U37](.) |
| U38 | Tamaño texto ajustable (guía zoom) | C | [#TBD-U38](.) |
| U39 | Leyendas riesgo claras | M | [#TBD-U39](.) |
| U40 | Cierre sesión siempre visible | S | [#TBD-U40](.) |
| U41 | Indicador progreso carga multi-step workflow | S | [#TBD-U41](.) |
| U42 | Empty estado universo sin análisis | C | [#TBD-U42](.) |
| U43 | Sugerencias completar ratios CEDEAR | S | [#TBD-U43](.) |
| U44 | Validación inline formularios cliente nuevo | S | [#TBD-U44](.) |
| U45 | Errores accionables (“tickers sin precio: …”) | M | [#TBD-U45](.) |
| U46 | Copiar ISIN/ticker al portapapeles | C | [#TBD-U46](.) |
| U47 | Modo demo datos sintéticos 1 clic | S | [#TBD-U47](.) |
| U48 | Comparación dos clientes (asesor) | C | [#TBD-U48](.) |
| U49 | Preferencias usuario moneda/densidad | S | [#TBD-U49](.) |
| U50 | NPS / feedback reportar problema con contexto sesión | C | [#TBD-U50](.) |

---

## Resumen por prioridad (conteo orientativo)

| MoSCoW | Arquitectura | Diseño | UX | Total aprox. |
| --- | ---: | ---: | ---: | ---: |
| Must | 14 | 5 | 8 | **27** |
| Should | 25 | 26 | 23 | **74** |
| Could | 8 | 16 | 16 | **40** |
| Won’t | 3 | 3 | 3 | **9** |

*Los conteos son guías de primera pasada; conviene revisarlos tras definir roadmap por trimestre y restricciones legales/licencias.*
