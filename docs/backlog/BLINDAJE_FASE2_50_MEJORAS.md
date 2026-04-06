# Backlog 50 mejoras — Blindaje Fase 1–2 (catálogo priorizable)

Catálogo derivado de auditorías de credibilidad, trazabilidad y FinOps. **No** son 50 PRs simultáneos; cada ítem debe convertirse en issue con criterio de aceptación al priorizarlo.

---

## 1. Seguridad / tenant (5)

1. Revisar y eliminar `return trans.copy()` u otros patrones legacy que expongan filas fuera de tenant.
2. Política **fail-closed** en filtros de lectura que aún permitan omitir `tenant_id`.
3. Auditoría de `obtener_*` sin filtro de tenant en rutas de API internas.
4. Rate limit global en endpoints internos sensibles (ingesta, export).
5. Headers CSP / hardening en proxy reverso frente a la app Streamlit.

## 2. Compliance / auditoría (5)

1. Ampliar ledger tipo `OPTIMIZATION_AUDIT` con hash de inputs cuant cuando exista lineage estable.
2. Correlacionar logs de importación broker con `cliente_id` y nombre de archivo (sin PII innecesaria).
3. Política de retención y purga de `alertas_log` / logs de aplicación.
4. Exportación “paquete abogado”: auditoría + TyC + versión de modelo en un ZIP firmable.
5. Incluir versión de términos y de modelo en pie de informes PDF/HTML.

## 3. Ingesta / datos (5)

1. Contadores explícitos de filas omitidas por regla (además de excepciones) en todos los parsers broker.
2. Validación opcional por fila (Pydantic) en plantillas CSV/Excel de carga.
3. Checksum SHA-256 del archivo subido almacenado en metadatos de sesión o auditoría.
4. Detección y reporte de duplicados explícitos (misma fecha/ticker/cantidad).
5. Plantilla Excel validada con hoja de instrucciones y columnas congeladas.

## 4. Matemática / quant (5)

1. Tests de borde NaN/Inf en Sharpe, Sortino y métricas derivadas.
2. Límites configurables en fracción Kelly y fallback cuando óptimo explota.
3. Validación explícita PSD de matriz de covarianza con mensaje de usuario accionable.
4. Coherencia CEDEAR ratio en todos los caminos de precio y P&L.
5. Stress uniforme `CCL=0` o ausente en flujos de valoración e informes.

## 5. FinOps / Yahoo y datos externos (5)

1. TTL unificado documentado entre `cache_historico`, correlaciones y VaR.
2. Tabla local de cotizaciones recientes para reducir round-trips a YF en caliente.
3. Límite de tickers por sesión/usuario para evitar abuso accidental.
4. Circuit breaker compartido entre módulos que llaman al mismo proveedor.
5. Roadmap worker/async para descargas masivas (fuera del request Streamlit).

## 6. UX / errores (5)

1. Sustituir `st.error(f"{e}")` por mensaje genérico al usuario + log estructurado.
2. Paginación o virtualización en Libro Mayor y tablas grandes.
3. `height` consistente en `st.dataframe` para evitar scroll infinito.
4. Estados vacíos guiados (CTA siguiente paso) en cada tab crítico.
5. Toasts o `st.status` para operaciones largas (ingesta, optimización).

## 7. ORM / dinero (5)

1. Roadmap migración a `Decimal` para nominales y montos en moneda.
2. Migración gradual por módulo con capa de compatibilidad float→Decimal.
3. Redondeo explícito y política HALF_EVEN en informes regulatorios.
4. Tests de invariante de centavo en sumas de cartera y cash.
5. Documentar invariantes de cartera (suma pesos, coherencia ARS/USD).

## 8. Multi-tenant producto (5)

1. Pasar `tenant_id` explícito a export y reconciliación desde sesión.
2. Aislar seeds demo por tenant en entornos compartidos.
3. Admin solo ve clientes/recursos de su tenant (revisión residual).
4. Nombres de archivo export incluyen tenant slug para trazabilidad.
5. Tests de integración cruzados “tenant A no lee B” en cada nueva API.

## 9. Objetivos / negocio (5)

1. Documentar en producto que “capital” y ciertos montos son contexto de sesión.
2. Roadmap buckets por objetivo (liquidez, retiro, largo plazo).
3. Etiquetas de cartera por plazo enlazadas a objetivos en BD.
4. Flujo de dividendos explícito si el producto lo declara soportado.
5. KPIs de uso por objetivo (activación, completados, vencidos).

## 10. Observabilidad (5)

1. Métricas Prometheus/OpenTelemetry en contenedor (latencia, errores por tab).
2. Healthcheck enriquecido: BD, proveedor precios, disco, versión desplegada.
3. Alertas Sentry (o similar) en ingestión broker y escrituras maestras.
4. Dashboard de errores por versión de app y tenant.
5. Trazas correlacionadas `run_id` entre optimización, ejecución e informe.

---

*Última actualización: alineado al plan Blindaje Fase 2 (MQ26).*
