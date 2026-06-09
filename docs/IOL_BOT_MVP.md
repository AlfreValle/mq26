# IOL Bot MVP (demo y real)

Implementacion inicial del bot de trading IOL en `services/iol_api/`.

## Variables de entorno

- `IOL_TRADING_MODE=demo|real`
- `IOL_USERNAME` y `IOL_PASSWORD`
- `IOL_DRY_RUN=true|false`
- `IOL_MAX_NOTIONAL_ARS`
- `IOL_MAX_DAILY_LOSS_ARS`
- `IOL_MAX_ORDERS_PER_DAY`
- `IOL_KILL_SWITCH_FILE`
- `IOL_SANDBOX_BASE_URL` y `IOL_REAL_BASE_URL`

## Scripts

Los scripts `scripts/iol_sandbox_probe.py` y `scripts/iol_bot_runner.py` cargan automaticamente `MQ26_V11/.env` si existe (via `python-dotenv`).

1) Validacion de API/sandbox:

`python scripts/iol_sandbox_probe.py --market argentina --symbol GGAL`

Opcional para orden de prueba:

`python scripts/iol_sandbox_probe.py --market argentina --symbol GGAL --send-order --side BUY --quantity 1 --price 1000`

2) Runner del bot:

`python scripts/iol_bot_runner.py --prices-csv data/precios.csv --market argentina --symbol GGAL --quantity 1 --price 1000`

Modo loop (scheduler interno):

`python scripts/iol_bot_runner.py --prices-csv data/precios.csv --loop-seconds 60`

## Seguridad y control de riesgo

- `dry_run` habilitado por defecto.
- Idempotencia de ordenes por ventana temporal configurable.
- Kill switch por archivo: si existe el archivo configurado, no se envian ordenes.
- Limites de notional, perdida diaria y cantidad diaria de ordenes.

## Integracion con MQ26

La capa de ejecucion expone:

- `get_positions()` para leer posiciones broker.
- `get_orders()` para reconciliar estado de ordenes.

Esto permite conectar una vista futura de monitoreo en UI MQ26 sin habilitar ejecucion automatica desde la app principal.

## Backtest de metodos de entrada/salida y seleccion de estrategia

Modulo `services/iol_api/backtest_lab.py`:

- **Comparacion**: varias reglas predefinidas (cruces MA, RSI mean-reversion, breakout) con la misma convencion de retardo de 1 barra y costo por cambio de posicion.
- **Router (aprendizaje supervisado simple)**: en la porcion *train* del historial, para cada **regimen de volatilidad** (terciles relativos), se elige la estrategia con mayor Sharpe condicional; en *test* (OOS) se aplica ese mapa usando el regimen observado al inicio de cada dia.

CLI:

`python scripts/iol_strategy_backtest.py --csv ruta/precios.csv --train-ratio 0.65 --commission 0.001`

Sensibilidad OOS del router ante distintos cortes train/test (varios `train_ratio` en una sola corrida; el JSON incluye `walk_forward_oos_por_train_ratio`):

`python scripts/iol_strategy_backtest.py --csv ruta/precios.csv --train-ratio 0.65 --commission 0.001 --walk-forward-ratios 0.55,0.65,0.75`

Desde codigo tambien podes usar `walk_forward_oos_grid` importado del paquete publico `services.iol_api` (misma firma que en `backtest_lab`).

**Nota honesta**: esto no garantiza ganancias futuras; sirve para **comparar** reglas y evitar look-ahead obvio. Para produccion conviene walk-forward multi-ventana y validacion con costos y slippage del broker.

## Runner en vivo con mapa `regime_to_strategy`

1. Generar JSON con backtest + router:

`python scripts/iol_strategy_backtest.py --csv ruta/precios.csv > router_out.json`

2. Copiar en un archivo solo `router_regimen_vol`, `default_strategy` (y opcional `vol_window` / `rank_window`).

3. Ejecutar el bot con el router (fuerza `IOL_DRY_RUN=true` en el proceso aunque el `.env` diga otra cosa):

`python scripts/iol_bot_runner.py --prices-csv ruta/precios.csv --router-json router_config.json`

Con `TradingBotRunner(..., regime_router=RegimeRouterConfig(...))`, si `IOL_DRY_RUN=false`, **no se llama al broker**: se devuelve `router_safety_blocked` hasta que desactives explicitamente esa capa de seguridad en codigo.

## Escáner de anomalías (perlas, corto plazo)

Script: `MQ26_V11/scripts/iol_pearl_scanner.py`. Lógica reusable: `services/iol_api/pearl_scanner_runner.py`, scoring: `services/iol_api/anomaly_scan.py`, estado JSON: `services/iol_api/pearl_state.py`.

**Directorio de trabajo:** los ejemplos asumen `cd MQ26_V11`. Si estás en la raíz del repo (`MQ26_final_v4`), podés usar el mismo comando con `python scripts/iol_pearl_scanner.py` (hay un wrapper en `MQ26_final_v4/scripts/` que delega a `MQ26_V11` con el `cwd` correcto).

**Datos híbridos:** el histórico diario viene de **yfinance** (cache local bajo `data/pearl_hist_cache` por defecto). El precio “live” viene de **IOL** (`get_quote`). Puede haber desalineación (cierres distintos, feriados, CEDEARs vs ticker Yahoo). El modo `--offline` usa el **último cierre del histórico** como proxy de cotización (útil para pruebas sin credenciales).

**Archivo de símbolos** (texto, una línea por activo):

- `GGAL` → Yahoo por defecto `GGAL.BA` si `--market argentina`.
- `AAPL,AAPL` → Yahoo explícito (mercado USA u otro).

Ejemplo `data/pearl_symbols_ejemplo.txt`:

```
# lineas con # se ignoran
GGAL
YPFD
```

**Telegram:** mismas variables que el resto de MQ26 (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` en `.env` o entorno). Flag `--notify-telegram` para enviar mensajes al disparar candidato o al cumplir salida (TP / stop / tiempo).

**Estado y ciclo trade:** por defecto se persiste JSON (`--state-file`, por defecto `%TEMP%/iol_pearl_state.json`). Fases `idle` → `in_position` (tras alerta con mejor score) → `cooldown` tras take profit, stop o tiempo máximo. Parámetros: `--target-pct`, `--stop-pct`, `--max-hold-days`, `--cooldown-seconds`. `--no-position-state` desactiva bloqueo y seguimiento (solo candidatos y deduplicación de alertas).

**Anti-spam:** `--dedupe-min-seconds` y `--dedupe-score-delta` evitan renotificar el mismo ticker salvo que suba mucho el score.

**Ejecución (una pasada, demo IOL + Telegram):**

`python scripts/iol_pearl_scanner.py --symbols-file data/pearl_symbols_ejemplo.txt --market argentina --notify-telegram --min-score 0.5`

**Prueba sin IOL:**

`python scripts/iol_pearl_scanner.py --symbols-file data/pearl_symbols_ejemplo.txt --offline --min-score 0.3`

**Loop:**

`python scripts/iol_pearl_scanner.py --symbols-file data/pearl_symbols_ejemplo.txt --loop-seconds 120 --notify-telegram`

**Órdenes reales:** este escáner **no** envía órdenes al broker; solo alerta y opcionalmente mantiene estado. Para ejecución automática seguir `IOLExecutionService` / `iol_bot_runner.py` y el checklist de riesgo en `docs/product/PLAN_BOT_IOL_ROBUSTEZ.md`. No es asesoramiento financiero ni garantía de rentabilidad.
