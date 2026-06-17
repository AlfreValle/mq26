---
name: sprint-pilar
description: Ejecuta el siguiente sprint del roadmap "mejor optimizador AR" (docs/PLAN_MEJOR_OPTIMIZADOR_AR.md) siguiendo la metodología probada del proyecto. Usar cuando el usuario diga "continuemos", "siguiente sprint", "arranquemos el pilar X" o similar.
---

# Sprint del roadmap MQ26

## Metodología (probada en Pilares 1-3)

1. **Leer el roadmap**: `docs/PLAN_MEJOR_OPTIMIZADOR_AR.md` — identificar el sprint "pendiente" y sus ítems.
2. **Mapear antes de tocar**: despachar un agente Explore con preguntas concretas (API exacta, shape de retorno, consumidores file:line, dependencias de red). No diseñar sobre supuestos.
3. **Diseñar el contrato primero**: dataclasses con degradación elegante (cada sección/ítem falla independiente), explicación humana por componente, `to_dict()` JSON-serializable.
4. **Implementar service-first**: la lógica va en `services/` o `core/` SIN Streamlit (regla de arquitectura). La UI es un componente en `ui/components/` que solo renderiza.
5. **Tests con dobles**: monkeypatch sobre los nombres importados en el módulo bajo test (`monkeypatch.setattr(modulo, "funcion", fake)`). Sin red. Cubrir: camino feliz, degradación por sección, casos especiales (RF, ticker desconocido, vacío).
6. **Verificar**: skill `verificar-mq26` (ruff + suite -n 4 + smoke imports).
7. **Commit atómico** en español, formato `feat(scope): Pilar N sprint M — qué`, cuerpo explicando el porqué y los números de verificación.
8. **Actualizar roadmap**: marcar sprint ✅ con commit hash, definir el siguiente sprint, commit `docs:` separado.

## Convenciones del proyecto

- Patrones ya construidos que SIEMPRE se reusan (no reinventar):
  - `core.instrument_master.get_master()` — maestro de instrumentos (tipo/ratio/validación)
  - `core.stale_policy` — frescura por tipo de activo
  - `core.fx.ccl_para_fecha()` — FX por fecha de operación
  - `services.ficha_ticker.generar_ficha_ticker()` — ficha unificada (Pilar 2)
  - `services.recomendador_explicable.construir_plan_accion()` — plan auditable (Pilar 3)
- UI lazy: nada que gaste red se ejecuta sin que el usuario lo pida (botón → session_state → render).
- Streamlit: los botones solo son True en el run del click — persistir estado en session_state.
- Auditoría: `auditar_plan()` / `registrar_recomendacion_evento()` nunca deben romper el flujo (try/except + log).
