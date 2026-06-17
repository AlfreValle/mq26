# Plan de Contingencia y Mejoras — MQ26

Fecha: 2026-06-16. Basado en la prueba funcional de los 3 perfiles (estudio +
asesor), el monitor de salud de datos (Pilar 4) y la auditoría del repo.

> **Cómo usar este documento.** La sección 1 es para **operar bajo fallo**
> (qué hacer cuando algo se rompe en producción). La sección 2 es el **backlog
> de mejoras priorizado** (qué construir para que falle menos). El monitor
> `🩺 Salud datos` (Admin) es el primer lugar a mirar siempre.

---

## 1. Plan de contingencia (operación bajo fallo)

La app **degrada por diseño** (nunca explota): ante un fallo muestra el último
dato bueno con su marca de calidad. La contingencia consiste en *detectar* la
degradación y *acotar* su impacto. Diagnóstico guiado en la skill
`diagnostico-degradaciones` y el runbook `RUNBOOK_INCIDENTES_DEGRADACIONES.md`.

### C1 — Proveedor de precios caído (yfinance / BYMA)

| | |
|---|---|
| **Síntoma** | Columna "Fuente px" muestra FALLBACK-* en masa; Salud datos → "Cobertura de precios" en AVISO/CRÍTICO; ⚠STALE en tablas. |
| **Impacto** | Valuaciones y P&L usan último precio conocido; las recomendaciones marcan confianza BAJA. |
| **Acción inmediata** | 1) Admin → 🩺 Salud datos → "Ping a proveedores" para confirmar cuál cayó. 2) Si es yfinance, activar `byma_first` (flag, sin deploy) para que BYMA tome la delantera. 3) Comunicar a asesores: "precios de referencia, verificar antes de operar". |
| **Mitigación de fondo** | Los precios fallback (`PRECIOS_FALLBACK_ARS`) y el catálogo RF mantienen la app usable. Mantenerlos frescos (ver C3). |
| **Verificación** | Salud datos vuelve a "Cobertura ≥50% live". |

### C2 — CCL no disponible / sospechoso

| | |
|---|---|
| **Síntoma** | Salud datos → "CCL spot" en AVISO ("es el fallback hardcodeado"). |
| **Impacto** | Conversiones ARS↔USD usan `CCL_FALLBACK` (1500); P&L en USD puede estar corrido. |
| **Acción inmediata** | Verificar `obtener_ccl()` (GGAL.BA/GGAL × 10). Si yfinance está caído, el CCL live falla → es consecuencia de C1. Ajustar `CCL_FALLBACK` en `config.py` al valor de mercado del día si la caída se prolonga. |
| **Verificación** | Salud datos → "CCL spot" en OK (live). |

### C3 — Datos de referencia vencidos (serie CCL / catálogo RF)

| | |
|---|---|
| **Síntoma** | Salud datos → "Serie CCL histórica" o "Catálogo RF" en AVISO/CRÍTICO (X meses / días de atraso). |
| **Impacto** | Costos históricos en ARS y precios de ONs derivan del mercado real. |
| **Acción** | Skill `actualizar-datos-referencia`: agregar el mes a `core/pricing_utils.CCL_HISTORICO`; refrescar `paridad_ref`/`tir_ref`/`fecha_ref` en `core/renta_fija_catalogo.py`. Verificar con `pytest tests/test_fx.py tests/test_renta_fija_ar.py`. |
| **Prevención** | Tarea mensual fija (ver M1). El monitor ya lo detecta automáticamente. |

### C4 — Base de datos no responde

| | |
|---|---|
| **Síntoma** | Salud datos → "Audit trail" en CRÍTICO; errores al listar clientes. |
| **Impacto** | Alta/edición de clientes y auditoría caídas; el motor (diagnóstico/recomendación) sigue funcionando sobre la cartera en memoria. |
| **Acción** | Verificar SQLite local (`0_Data_Maestra/master_quant.db`) o la conexión Postgres en prod. Restaurar desde backup (`scripts/backup_sqlite_mvp.py`). La auditoría nunca bloquea el flujo del usuario (degrada sola). |

### C5 — Deploy roto (Railway) / CI rojo

| | |
|---|---|
| **Síntoma** | Smoke post-deploy falla; `/_stcore/health` no responde. |
| **Acción** | 1) `git revert` del último merge a main y re-deploy (el deploy dispara solo en push a main). 2) Reproducir local con skill `release-mq26` (las 5 puertas). 3) Si CI pasa local pero falla remoto: comparar versiones de herramienta (caso conocido: rev de ruff en pre-commit). |
| **Red de seguridad** | Cada refactor grande deja una rama `backup/*` (ej. `backup/pre-merge-main-edf79bd`). |

### C6 — Recomendación de baja confianza (datos viejos)

| | |
|---|---|
| **Síntoma** | El plan explicado marca sugerencias con 🔴 "Datos viejos". |
| **Impacto** | La sugerencia se sostiene en un precio vencido. |
| **Acción** | Es el comportamiento correcto: el sistema avisa en vez de mentir. El asesor verifica el precio antes de ejecutar. Resolver la causa raíz vía C1/C3. |

---

## 2. Plan de mejoras (priorizado)

Orden por impacto/riesgo. Los Must cierran brechas de confiabilidad; el resto
es diferenciación.

### Prioridad ALTA — confiabilidad

- **M1 · Automatizar el refresh de datos de referencia.** Hoy es manual y el
  monitor solo *avisa*. Cron mensual (`scripts/cron_update_*` ya existen) que
  actualice CCL_HISTORICO y alerte si el catálogo RF supera 45 días. Cierra C3
  por diseño.
- **M2 · Convención de carga RF a prueba de error.** ✅ *(hecho)* Toda fila RF
  sin `LAMINA_VN` se autocompleta desde el catálogo (`completar_lamina_vn_filas`
  en el embudo `_persist_filas`); las ONs fuera de catálogo avisan al usuario.
  6 tests. Cierra el hallazgo de la prueba funcional.
- **M3 · Tests de integración por rol en CI** ✅ *(hecho)*. `test_flujo_roles_integracion.py`
  cubre estudio + asesor con 3 perfiles e invariantes de negocio. Extender a:
  rol inversor (primera cartera) y rol admin (flags + salud).
- **M4 · A21 / A37 del backlog MoSCoW.** Secrets fuera del código (vault/env) y
  retención de PII (AR/GDPR). Pendientes y son Must legales.

### Prioridad MEDIA — calidad y deuda

- **M5 · mypy informativo a cero.** ~151 errores (`arg-type`/`operator` por
  ndarray/pandas). Bajar gradualmente y promover a bloqueante.
- **M6 · Comisión mínima fija por boleto** ✅ *(hecho)* `decision_engine`
  cobra `max(comisión variable, COMISION_MINIMA_ARS=250)`. La advertencia de
  "operación chica" ahora es cuantitativamente exacta: una compra de ARS 8.000
  paga ~3.3% vs ~0.74% una grande. 4 tests.
- **M7 · Cobertura 60→75%.** La puerta está en 60 (real medido 64%). Ratchet
  hacia 75 sumando tests donde más se tocó: motores de recomendación y RF.
- **M8 · Refactor interno de `render_tab_optimizacion`** (~830 líneas en una
  función). El archivo ya está partido; falta descomponer la función (no es
  movimiento puro).

### Prioridad BAJA — producto

- **M9 · Enganchar la pestaña BYMA (`tab_mercado`)** que entró con el merge de
  main pero quedó sin navegación. Decisión de producto: ¿reemplaza o complementa
  la ficha de ticker en Señales?
- **M10 · Tickers más consultados** como métrica de uso (requiere instrumentar
  la ficha de ticker).
- **M11 · Lockfile reproducible** (`pip-tools`) para builds deterministas en
  Railway; hoy las versiones son mínimos `>=`.

---

## 3. Estado de la red de seguridad (hoy)

| Capa | Estado |
|---|---|
| Tests | 2272+ pasan; integración por rol cubierta; suite `-n 4` en ~1:35 |
| Lint | ruff bloqueante en CI, verde |
| Tipos | mypy H06 strict bloqueante (verde); informativo ~151 (no bloqueante) |
| Smoke | streamlit headless en cada PR (HTTP 200) |
| Monitor | 🩺 Salud datos en vivo (proveedores, frescura, datos de referencia) |
| Auditoría | toda recomendación persistida con motivos y trazabilidad |
| Reversión | ramas `backup/*` antes de cada operación grande |
