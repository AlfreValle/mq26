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

- [ ] **A · Login confuso (ambos)** (`run_mq26.py` pantalla de ingreso). Dos
  formas de login (legacy/SaaS) sin guía; el usuario no sabe qué hacer al entrar.
  → login consciente del rol + copy de ayuda ("¿primera vez? pedí tu usuario a
  tu asesor"). **[M]**
- [ ] **B · Jerga sin traducir (retail)** (`ui/tab_inversor.py`, `ui/carga_activos.py`).
  Sharpe, CVaR, CCL, CEDEAR, TIR, "paridad %" sin tooltip; glosario enterrado.
  → tooltips inline (`get_tooltip` en `ui/mq26_ux.py`) + subir el glosario.
  Parcialmente cubierto por el selector de perfil. **[M]**
- [ ] **C · Carga de activos cruda (retail)** (`ui/carga_activos.py`). "¿ARS o USD
  MEP?" sin explicar, "paridad %" sin ejemplo, warnings en rojo que asustan.
  → help con ejemplos ("pagaste ARS 9.700 por USD 100 → paridad 97%"), campo
  "monto pagado" que calcula paridad, warnings informativos no alarmistas. **[M]**
- [ ] **D · Se pierde el estado al cambiar de cliente (asesor)** (`ui/sidebar.py`,
  `run_mq26.py`). Cambiar cliente = rerun total: se pierde el trabajo en
  Optimización/Riesgo; sin spinner parece colgada. → snapshot de estado por
  `cliente_id` + spinner al cambiar. **[M–L]**
- [ ] **Entregables · Email del informe sin fallback** (`ui/tab_estudio.py`). Si
  no hay Gmail en `.env`, la opción de enviar al cliente desaparece. → SMTP
  configurable desde panel admin. **[M]**

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
- [ ] Plotly en tabs profesionales con `template="plotly_dark"` → romper modo
  claro: pasar a `plotly_chart_layout_base` (`ui/tab_riesgo.py`,
  `ui/tab_optimizacion.py`, `ui/optimizacion/resultados.py`, `ui/tab_universo.py`).
  **[M]**
- [ ] Ficha rápida del cliente recalcula diagnóstico al abrir (lento con red
  lenta): caché por fingerprint persistente (`ui/tab_estudio.py`). **[M]**
- [ ] Render de tab que falla muestra error genérico sin ID para reportar
  (`ui/navigation.py`). **[S]**

---

## P2 — Pulido y confianza

- [ ] `style.css` se autoviola: clases `mq-estudio-*` hardcodean hex en vez de
  `--c-green/yellow/red(-muted)` (raíz de inconsistencia; pantalla principal del
  asesor) (`assets/style.css`). **[S]**
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
