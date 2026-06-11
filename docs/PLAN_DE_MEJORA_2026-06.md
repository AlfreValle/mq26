# Plan de Mejora MQ26 — Junio 2026

Diagnóstico realizado el 2026-06-10 sobre la rama `session/nivel-a-multifactor-completo`.
Basado en evidencia concreta: `ruff check` (≈1.700 hallazgos), revisión de `ci.yml`,
`pyproject.toml`, tamaños de módulos y estado del working tree.

> **Estado al 2026-06-10 (cierre de sesión):**
> Fases 0.1–0.3, 1.1–1.5, 2.2–2.3, **3.1–3.4 completadas**.
> Ruff verde (0 errores); 2111 tests pasan; CI con 5 puertas:
> ruff bloqueante + cobertura ≥75% + mypy-strict H06 + mypy informativo + smoke streamlit headless.
> Fase 3.1: smoke streamlit en cada PR (levanta app, GET `/_stcore/health`).
> Fase 3.2: `.github/dependabot.yml` para pip + github-actions semanal.
> Fase 3.3: working tree limpio (debug-*.log, htmlcov/ ya en .gitignore).
> Fase 3.4: `SECTORES` (381 tickers, 128 líneas) extraídos a `data/sectores.csv` con loader+fallback.
> Elimina la clase de bug F601 por diseño; permite editar sin deploy.
> Fase 4.1 (limpieza mypy): de 225 a **149 errores** (-35%). Resueltos: 30× `[valid-type]`
> alias dinámico SQLAlchemy (`_B: Any = ...Base`), 18× `[assignment]` implicit Optional
> (`param: T = None` → `param: T | None = None`).
> **Pendiente:** Fase 2.1 (partir módulos gigantes — sprint dedicado), 8 archivos restantes en
> services/ con `import streamlit` (refactor profundo), 149 errores mypy informativos
> (mayoría: `[arg-type]`/`[operator]`/`[return-value]` por interacción con ndarray/pandas).

---

## Resumen del diagnóstico

| Área | Estado | Evidencia |
|---|---|---|
| Bugs latentes (NameError) | 🔴 Crítico | 18 errores `F821` (nombre no definido) en código de producción |
| Lint en CI | 🟡 No bloqueante | `continue-on-error: true` en el job lint; ~1.700 issues acumulados |
| Cobertura en CI | 🟡 No aplicada | CI corre con `--no-cov`, pero `pyproject` exige `cov-fail-under=75` |
| mypy | 🟡 No ejecutable | Configurado en `pyproject` pero no instalado en el entorno local ni en CI |
| Mantenibilidad | 🟡 Riesgo creciente | `ui/tab_inversor.py` 3.381 líneas; 4 módulos más superan 1.200 líneas |
| Datos de configuración | 🟡 Inconsistencia | Claves duplicadas en dicts de `config.py` (`SONY`, `DESP`, `BBAS3`, `PRIO3`) |
| Tests | 🟢 Sólido | 157 archivos de test, ~1.562 tests, markers bien definidos |
| Higiene de repo | 🟢 Buena | `.gitignore` completo, sin artefactos trackeados |

---

## Fase 0 — Bugs latentes (P0, ~1 día)

Errores `F821`: nombres que no existen en el scope donde se usan. Cada uno es un
`NameError` esperando que un usuario pase por esa rama de código.

### 0.1 Corregir los 18 `F821` en producción

| Archivo | Línea(s) | Nombre indefinido | Riesgo |
|---|---|---|---|
| `services/perlas_service.py` | 434, 627, 655, 711 | `pd` | Alto — archivo en desarrollo activo ahora mismo |
| `ui/tab_optimizacion.py` | 1182, 1238, 1241, 1312, 1345 | `RiskEngine`, `RISK_FREE_RATE`, `_is_viewer`, `sub_multi` | Alto — tab principal del Lab Quant |
| `run_mq26.py` | 1428 | `info_bd` | Alto — entry point |
| `ui/tab_estudio.py` | 950, 966 | `tid` | Medio |
| `core/pipeline_optimizador.py` | 800, 854 | `OptimizationProblem` | Medio |
| `core/db_auth.py`, `core/db_clientes.py`, `core/db_config.py` | 157 / 101, 182 / 140 | `pd` | Medio — capa de datos |

Verificación: `ruff check . --select F821 --exclude .claude` → 0 errores.

### 0.2 Resolver claves duplicadas en `config.py` (`F601`)

Tickers como `SONY`, `DESP`, `BBAS3` y `PRIO3` aparecen dos veces en los dicts de
sectores: la segunda aparición pisa silenciosamente a la primera. Decidir cuál
categoría es la correcta para cada uno y eliminar la duplicada.

Verificación: `ruff check . --select F601 --exclude .claude` → 0 errores.

### 0.3 Revisar los 9 `F823` (variable usada antes de asignarse)

Mismo patrón de bug latente que F821 pero dentro de funciones. Auditar uno por uno.

---

## Fase 1 — Endurecer la red de seguridad (P1, ~2-3 días)

El propio `ci.yml` dice: *"endurecer a blocking cuando el repo esté limpio"*. Esta fase
limpia el repo y cumple esa promesa.

### 1.1 Limpieza automática de lint (bajo riesgo, alto volumen)

Correcciones auto-aplicables con `ruff check --fix`:
- `I001` imports desordenados (321) · `F401` imports sin usar (119) · `UP037`,
  `UP017`, `UP035`, `F541`, `W292` (~100 más)

Correcciones manuales de bajo riesgo:
- `F841` variables sin usar (90) — auditar: algunas pueden ser resultados de cálculo que se olvidó usar.
- `B905` `zip()` sin `strict=` (58) — **importante en código cuantitativo**: un `zip` que
  trunca silenciosamente series de distinta longitud corrompe cálculos sin error visible.
  Usar `strict=True` donde las longitudes deben coincidir.

### 1.2 Hacer el lint bloqueante en CI

Una vez limpio, quitar `continue-on-error: true` del job lint en `.github/workflows/ci.yml`.
Para `E701`/`E402` (847 casos, estilo histórico) hay dos opciones:
- Agregarlos a `ignore` en `pyproject.toml` (pragmático), o
- Limpiarlos gradualmente por módulo (purista).
Recomendado: ignorarlos hoy y endurecer después — lo urgente es que F-rules (bugs) bloqueen.

### 1.3 Aplicar la puerta de cobertura en CI

Hoy `pyproject` exige `--cov-fail-under=75` pero CI corre `--no-cov`. Cambiar el job test a:

```yaml
run: pytest tests/ -q --tb=short -m "not integration and not slow"
```

(sin `--no-cov`, hereda la config de pyproject). Si la suite completa es lenta en CI,
separar en dos jobs: `smoke` en cada PR y suite completa en push a main.

### 1.4 Activar mypy en CI y local

- Agregar `pip install -e ".[dev]"` o `requirements-dev.txt` al job lint.
- Paso `mypy core services` (no bloqueante al inicio, bloqueante en 2 sprints).
- Los overrides estrictos de H06 (`core.hrp_weights`, etc.) ya existen — aprovecharlos.

### 1.5 Pre-commit hooks

`pre-commit` ya está en las dependencias dev pero no hay `.pre-commit-config.yaml`.
Crear uno con `ruff check --fix`, `ruff format`/black y chequeo de archivos grandes,
para que el lint nunca vuelva a acumularse.

---

## Fase 2 — Mantenibilidad (P2, continuo)

### 2.1 Partir los módulos gigantes

| Módulo | Líneas | Propuesta |
|---|---|---|
| `ui/tab_inversor.py` | 3.381 | Partir en `ui/inversor/` — un archivo por sección (resumen, posiciones, perlas, alta) |
| `core/renta_fija_ar.py` | 2.343 | Separar curvas, cálculo de TIR y catálogo de instrumentos |
| `ui/tab_cartera.py` | 1.673 | Extraer libro mayor y P&L a componentes |
| `ui/tab_optimizacion.py` | 1.510 | Extraer cada modelo de optimización a su panel |

Regla práctica: ningún archivo nuevo > 800 líneas; al tocar uno gigante, extraer lo tocado.

### 2.2 Consolidar la frontera UI / servicios

`README_ARQUITECTURA.md` declara "services/ SIN Streamlit" — verificar que se cumple:

```bash
grep -l "import streamlit" services/*.py core/*.py
```

Todo hit es deuda a migrar (mover la parte de presentación a `ui/`).

### 2.3 Unificar los dos `config.py`

El conflicto raíz vs `1_Scripts_Motor/config.py` ya causó la regla "no usar `import config`".
Plan: renombrar `1_Scripts_Motor/config.py` → `motor_config.py` (o convertir
`1_Scripts_Motor` en paquete con imports relativos) y eliminar el workaround de
`importlib.util` en los entry points.

---

## Fase 3 — Robustez operativa (P3, oportunista)

1. **Smoke en PRs**: hoy el smoke de producción solo corre post-deploy. Agregar un job
   que levante la app con `streamlit run` headless y verifique HTTP 200 en cada PR.
2. **Dependabot / renovate** para `requirements.txt` (hoy las versiones son mínimos `>=`,
   considerar lockfile con `pip-tools` para builds reproducibles en Railway).
3. **Limpiar artefactos del working tree**: `debug-*.log`, `htmlcov/` (ya ignorados,
   solo borrar localmente).
4. **Datos como datos**: los dicts de sectores de ~900 líneas en `config.py` migrarlos a
   CSV/tabla en BD — elimina la clase de bug F601 por diseño y permite editarlos sin deploy.

---

## Orden de ejecución sugerido

```
Semana 1:  Fase 0 completa (bugs) + 1.1 (autofix lint)
Semana 2:  1.2 + 1.3 + 1.4 (CI endurecido) + 1.5 (pre-commit)
Sprint+1:  2.3 (config) + 2.2 (frontera UI/servicios)
Continuo:  2.1 (partir módulos al tocarlos) + Fase 3
```

## Criterio de éxito global

- `ruff check . --exclude .claude` → 0 errores con la config endurecida.
- CI: lint y cobertura **bloqueantes**, suite verde, smoke en PRs.
- Ningún archivo de `ui/` o `core/` supera 2.000 líneas (meta: 800).
- `import config` ambiguo eliminado.
