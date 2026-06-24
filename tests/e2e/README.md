# E2E (navegador real, Playwright)

Smoke end-to-end del flujo de Estudio en un navegador real. Complementa los tests
de lógica (function-level) que ya cubren las invariantes del wizard.

> Estado: el test está escrito contra las etiquetas reales del código, pero **no
> fue ejecutado** donde se escribió (faltaba el paquete `playwright`). En la
> primera corrida puede que haya que ajustar los selectores de los pasos profundos
> del wizard (los `selectbox`/`expander` de Streamlit no son nativos del DOM).

## Setup (una vez)

```bash
pip install -r tests/e2e/requirements-e2e.txt
python -m playwright install chromium
```

## Correr

1. Levantá la app con el `.env` de demo:
   ```bash
   python -m streamlit run run_mq26.py --server.port 8501
   ```
2. En otra terminal:
   ```bash
   pytest tests/e2e -m e2e -v
   ```

Variables (opcionales): `BASE_URL` (default `http://localhost:8501`),
`MQ26_E2E_USER` (`estudio`), `MQ26_E2E_PASSWORD` (`Demo2026!`),
`MQ26_E2E_HEADFUL=1` para ver el navegador.

## Capas

- **Capa 1 — `test_login_estudio_renderiza_mis_clientes`**: boot + login estudio →
  header "Mis clientes". Verifica el fix de auth 0.4 y el arranque en navegador.
  Debería pasar tal cual.
- **Capa 2 — `test_wizard_capital_deja_menos_5pct_efectivo`** (`xfail` hasta
  validar): cliente → wizard → capital → recomendar → "Queda en efectivo". Cuando
  valides los selectores en vivo, sacá el `xfail` y afinálos.

## Por qué está separado de la suite

Estos tests necesitan un navegador y la app corriendo, así que NO entran en la
suite normal (`-m "not integration and not slow"`). El marker `e2e` los aísla.
