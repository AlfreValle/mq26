---
name: nueva-seccion-ficha
description: Agrega una sección nueva a la ficha unificada de ticker (services/ficha_ticker.py) siguiendo el patrón de degradación elegante del Pilar 2. Usar cuando se pida sumar análisis nuevo a la ficha (ej. insiders, short interest, dividendos, técnico extendido).
---

# Nueva sección en FichaTicker

El patrón del Pilar 2 garantiza que una sección nueva nunca rompe la ficha.
Pasos exactos (replicar lo hecho con "consenso" en commit b0369fd):

## 1. Fuente de datos

- Si necesita red: crear un helper **liviano y autónomo** en el servicio dueño
  del dato (ej. `consenso_analistas()` en analizador_ticker) que devuelva
  `dict | None` y **nunca lance** (try/except → None).
- Si ya hay un servicio: importarlo a nivel módulo en ficha_ticker.py
  (los tests lo monkeypatchean por ese nombre).

## 2. Builder de sección

En `services/ficha_ticker.py`, función `_seccion_<nombre>(dato) -> SeccionFicha`:
- `ok=False` con `error` + `explicacion` humana si el dato es None/vacío.
- `ok=True` con `datos` (dict serializable) + `explicacion` en lenguaje que un
  asesor pueda leerle al cliente (números con contexto, disclaimer si aplica).

## 3. Cableado en FichaTicker

- Campo nuevo en el dataclass (con `default_factory` de sección "No evaluado").
- Agregarlo a la property `secciones` (la cobertura X/N se actualiza sola).
- En `generar_ficha_ticker()`: construir **solo si `fundamentals.ok`** (heurística
  de red disponible) y dentro de su propio try/except con `_log.warning`.
- Rama RF: agregar el `sec_na("<nombre>")`.
- Si aporta al veredicto: sumarlo al `_resumen_ejecutivo` o concatenar al resumen.

## 4. Export HTML

Agregar `_html_seccion(ficha.<nombre>, "Título")` en `ficha_ticker_html()`.

## 5. Tests (tests/test_ficha_ticker.py)

- Mock en fixture `todo_ok` (monkeypatch sobre el nombre importado en ft).
- Actualizar los asserts de cobertura: "N/N" → "N+1/N+1", degradados análogos.
- Tests nuevos: dato presente (explicación correcta), dato None (degrada solo
  esa sección), aparece en HTML.

## 6. Verificar y commitear

Skill `verificar-mq26`. Commit `feat(analisis): ficha — sección <nombre>`.
