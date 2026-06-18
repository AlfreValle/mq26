# Plan de usabilidad para llevar MQ26 a la venta

Fecha del audit: 2026-06-18. Compradores objetivo: **inversor retail (B2C)** y
**estudio/asesor (B2B)**. Audit hecho leyendo los flujos reales (3 revisores:
flujo inversor, flujo estudio, pulido visual).

Veredicto: el producto funciona de punta a punta; lo que falta es **fricción de
"se nota prototipo"** concentrada en el primer minuto de cada comprador — justo
donde se decide la venta.

Severidad: **P0** = bloquea/confunde y frena la venta · **P1** = fricción alta ·
**P2** = pulido. Esfuerzo: S (<½ día) · M (½–1 día) · L (>1 día).

---

## Quick Wins de venta — PR `feat/usabilidad-quickwins-venta`

Alto impacto / bajo esfuerzo, visibles de inmediato para ambos compradores.

- [x] **E · Selector de perfil con paleta propia** (`ui/tab_inversor.py`). Las 4
  tarjetas de perfil (lo primero que toca el retail) usaban hex Material y un
  gris fijo `#424242` que desaparecía en modo claro. → tokens `--c-green/accent/
  yellow/red` + `-muted`, borde `--c-border`. **[S, hecho]**
- [x] **P1 · "Cambiar cliente" ambiguo para el admin** (`ui/sidebar.py`). El
  admin sin cliente (post #11) veía "🔄 Cambiar cliente". → se muestra solo con
  cliente activo; admin sin cliente ve "👤 Elegir un cliente". **[S, hecho]**
- [x] **P0 retail · Onboarding sin retorno** (`ui/tab_inversor.py`). La guía de 3
  pasos se ocultaba para siempre. → queda colapsable y recuperable. **[S, hecho]**
- [x] **Pulido · Ladder RF rompe modo claro** (`ui/inversor/paneles_kpi.py`).
  Fondo forzado a mano + azul Material. → `plotly_chart_layout_base` + azul de
  marca. **[S, hecho]**

---

## P0 — Bloquean la venta (sprints de fondo)

- [~] **A · Login** (`run_mq26.py`). REVISADO: NO era dual confuso — es un
  `if/else` limpio (SaaS **o** legacy, nunca ambos). El form legacy guía bien.
  No se toca el componente de auth (compartido, funciona). Mensaje de "sin
  clientes" para viewer ya orienta. **[descartado tras revisión]**
- [x] **B · Jerga (retail)** (`ui/tab_inversor.py`, `ui/carga_activos.py`).
  REVISADO: ya tenía tooltips `help=` en las métricas y `GLOSARIO_INVERSOR`.
  Cerrado lo real: caption de la tabla de universo + typo "situación";
  selector de perfil con tokens; help de paridad con ejemplo. **[hecho]**
- [x] **C · Carga de activos (retail)** (`ui/carga_activos.py`). REVISADO: el
  CEDEAR ya tenía radio con help, warnings informativos y preview. Cerrado lo
  real: help de "paridad %" con ejemplo (ON/bono) + aviso de preview truncado
  ("primeras 30 de N"). **[hecho]**
- [~] **D · Estado al cambiar de cliente (asesor)** (`ui/sidebar.py`,
  `run_mq26.py`). Parcial: el spinner de tab ya existe. El snapshot de estado
  por `cliente_id` cross-tab es M–L y riesgoso a ciegas → **follow-up con la app
  corriendo para verificar**.
- [ ] **Entregables · Email/PDF** (`ui/tab_estudio.py`). SMTP configurable + PDF
  directo son infra; **follow-up con verificación en browser** (no a ciegas).

---

## P1 — Fricción alta

- [ ] Estados vacíos sin CTA: botón "📥 Importar ahora" dentro del aviso de
  cartera vacía (`ui/tab_inversor.py`). **[S]**
- [ ] Rol viewer (estudio) en "sin clientes": dead-end → mensaje "pedí a tu
  asesor/admin que cree el cliente" (`run_mq26.py`). **[S]**
- [ ] Tabla "estado del universo" sin contexto para retail → caption explicativa
  (`ui/tab_inversor.py`). **[S]**
- [ ] "Plata nueva": aclarar que **suma** capital, no reemplaza
  (`ui/inversor/plata_nueva.py`). **[S]**
- [ ] Importador de broker: "mostrando 1–30 de N" + aviso si hay más filas
  (`ui/carga_activos.py`). **[S]**
- [ ] Escaneo de universo (perlas): progreso real, no solo spinner; refrescar al
  terminar (`ui/tab_perlas.py`). **[S]**
- [x] Plotly en tabs profesionales con `template="plotly_dark"` → rompía modo
  claro. → nuevo helper `plotly_template_actual()` (17 gráficos en riesgo,
  optimización, resultados, universo, cartera). **[hecho]**
- [ ] Ficha rápida del cliente recalcula diagnóstico al abrir (lento con red
  lenta): caché por fingerprint persistente (`ui/tab_estudio.py`). **[M]**
- [x] Render de tab que falla muestra error genérico sin ID para reportar
  (`ui/navigation.py`). → ahora da un código corto reportable. **[hecho]**

---

## P2 — Pulido y confianza

- [x] `style.css` se autoviolaba: clases `mq-estudio-*` con hex. → tokens
  `--c-green/yellow/red(-muted)` + `--c-text-3`/`--c-surface-2`. **[hecho]**
- [ ] Checkbox "Confirmo que ejecuté…" ambiguo → aclarar que MQ26 es seguimiento,
  no ejecución (`ui/inversor/primera_cartera.py`). **[S]**
- [ ] Cambiar perfil no recalcula KPIs automáticamente → hint/rerun
  (`ui/tab_inversor.py`). **[S]**
- [ ] Informe HTML crudo → "Guardar como PDF" / claridad de envío
  (`ui/tab_estudio.py`, `ui/tab_reporte.py`). **[M]**
- [ ] Marcas de tiempo en score/diagnóstico ("calculado hace 2h" / "LIVE")
  (`ui/tab_cartera.py`, `ui/tab_estudio.py`). **[S]**
- [ ] Badge "precios offline" sin explicación de qué se está viendo
  (`ui/sidebar.py`). **[S]**
- [ ] Historial de snapshots: orden descendente + filtro por fecha
  (`ui/tab_reporte.py`). **[S]**
- [ ] Plantilla CSV sin descripción de campos (`ui/carga_activos.py`). **[S]**
- [ ] Refactor: form de alta de cliente duplicado (ingreso vs estudio)
  (`run_mq26.py`, `ui/tab_estudio.py`). **[S]**

---

## Ya resuelto / consistente (no tocar)

- `ui/mq26_ux.py` y `ui/inversor/proyeccion.py`: usan tokens + helpers; modelo a
  seguir.
- Tabla de clientes duplicada en estudio: **eliminada**.
- Densidad retail vs profesional: bien separada (`mq-inv-*` vs `mq-estudio-*`).
- Carga diferida de la Torre de control y wizard de capital del cliente: hechos
  (dictamen #12/#13).

## Orden sugerido

1. **Quick Wins** (este PR) — primera impresión para ambos. ✅
2. **B** (jerga) + **P1 estados vacíos** — comprensión retail.
3. **C** (carga de activos) — donde más se traba el retail nuevo.
4. **A** (login) — puerta de entrada de ambos.
5. **D** (estado por cliente) — eficiencia del asesor B2B.
6. **P2** pulido + `style.css`.
