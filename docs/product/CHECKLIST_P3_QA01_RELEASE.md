# Checklist P3-QA-01 — QA antes de release mayor

Objetivo: **misma barra que CI** + cobertura opcional alineada al repo + revisión visual **tema claro / oscuro** sin regresiones obvias.

**CI de referencia:** [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (job `test`).

---

## 1. Tests automatizados (obligatorio antes de tag)

Paridad exacta con GitHub Actions (`pytest tests/ -q --tb=short --no-cov`):

**PowerShell (Windows)**

```powershell
$env:MQ26_PASSWORD = "test_password_123"
python -m pytest tests/ -q --tb=short --no-cov
```

**bash**

```bash
export MQ26_PASSWORD=test_password_123
python -m pytest tests/ -q --tb=short --no-cov
```

Criterio: **salida 0 fallos**. Si hay fallos, no se etiqueta release hasta corregirlos o documentar la excepción aprobada por el comité.

---

## 2. Cobertura local (recomendado)

Alineado a [`pyproject.toml`](../../pyproject.toml) (`--cov=services --cov=core`, umbral **75%**):

```bash
export MQ26_PASSWORD=test_password_123
python -m pytest tests/ -q --tb=short --cov=services --cov=core --cov-report=term-missing --cov-fail-under=75
```

Útil en máquina de desarrollo antes de merge a `main`; la CI actual **no** ejecuta este comando (evita tiempos largos y diferencias de entorno). Opcional: añadir job de cobertura en Actions en una fase posterior.

---

## 3. Revisión visual — modo claro y oscuro

Checklist manual (no automatizable de forma fiable en Streamlit sin E2E dedicado):

- [ ] **Login** (`pantalla_ingreso` / flujo previo a auth): textos y campos legibles (tema claro retail por defecto en flujos sin sesión).
- [ ] Tras autenticación: **toggle de tema claro** en sidebar si está disponible para el rol; alternar **claro ↔ oscuro**.
- [ ] Pestaña **Inversor** (o rol equivalente): hero / semáforo / métricas sin texto invisible ni contrastes rotos.
- [ ] Al menos una pestaña “caliente”: **Cartera** o **Riesgo** — tablas, gráficos Plotly y `st.dataframe` legibles en ambos temas.
- [ ] Banners de degradación / avisos (`st.info`, `st.warning`): fondo y texto distinguibles.

---

## 4. Post-deploy (solo si aplica Railway)

Tras push a `main`, el workflow puede ejecutar `scripts/smoke_produccion.py`. Ver variables en CI y [`docs/DEPLOY_RAILWAY.md`](../DEPLOY_RAILWAY.md).

---

*Ítem de inventario comité: [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) — P3-QA-01.*
