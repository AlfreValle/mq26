---
name: verificar-mq26
description: Corre la puerta de verificación completa de MQ26 (ruff + suite paralela + smoke de imports) con los quirks conocidos del repo. Usar antes de cada commit, después de cualquier refactor, o cuando el usuario pida "verificá", "corré los tests" o "está todo verde?".
---

# Verificación completa MQ26

Ejecutar en este orden. Si un paso falla, frenar, diagnosticar y arreglar antes de seguir.

## 1. Lint (bloqueante en CI)

```bash
python -m ruff check . --exclude .claude
```

Si hay errores autofixeables: `python -m ruff check --fix . --exclude .claude`.
**NO usar black** — el repo no está black-formateado (191 archivos divergen); la puerta de estilo es ruff.

## 2. Suite de tests (paralela — la suite es xdist-safe)

```bash
python -m pytest tests/ -q --tb=short --no-cov -m "not integration and not slow" -n 4 -p no:cacheprovider
```

- Esperado: **~2200+ passed** en ~1:35. Secuencial tarda 3:20+ — siempre usar `-n 4`.
- El `PermissionError: [WinError 5] ... pytest-of-...` en atexit es **ruido conocido de Windows**, no un fallo.
- Si falla la creación de temp dirs: agregar `--basetemp="$TEMP/pyt_$RANDOM"`.

## 3. Cobertura (solo si se va a tocar la puerta)

La cobertura real es ~62%; la puerta `cov-fail-under` está en **60** (pyproject.toml).
No subirla sin medir antes: `python -m pytest tests/ -q -m "not integration and not slow" -n 4 | grep TOTAL`.

## 4. Smoke de imports (tras tocar ui/ o entry points)

```bash
python -c "from ui.tab_inversor import render_tab_inversor; import ui.tab_universo; print('OK')"
```

## Quirks del repo

- **CRLF**: los warnings "LF will be replaced by CRLF" de git son normales, ignorarlos.
- **pre-commit** está instalado: ruff --fix + check-yaml/toml/merge-conflict/large-files corren al commitear. Si ruff del hook difiere de local, el rev de `.pre-commit-config.yaml` debe coincidir con la versión local (hoy v0.15.x).
- Tests nuevos: siempre con dobles/monkeypatch — **nunca red real** en la suite rápida.
