#!/bin/sh
set -e
# Railway (y otros PaaS) inyectan PORT; Streamlit debe escuchar ahí, no en 8501 por defecto.
# Marcador de imagen: si no ves esta línea en los logs del deploy, no corre este entrypoint.
echo "[MQ26] deploy_marker=entry_run_mq26_20260324"

# Railway a veces define STREAMLIT_SERVER_PORT como el TEXTO literal "$PORT" (sin expandir).
# Streamlit falla: "not a valid integer". Siempre borrar y volver a fijar solo dígitos.
unset STREAMLIT_SERVER_PORT

_listen=8080
if [ -n "$PORT" ]; then
  case "$PORT" in
    *[!0-9]*) ;;
    *) _listen="$PORT" ;;
  esac
fi

export STREAMLIT_SERVER_PORT="${_listen}"
echo "[MQ26] listen port ${_listen} (PORT raw was: ${PORT:-<unset>})"

# env fuerza el valor visto por el proceso hijo (evita heredar basura)
exec env STREAMLIT_SERVER_PORT="${_listen}" streamlit run run_mq26.py \
  --server.port="${_listen}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false
