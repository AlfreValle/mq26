# ── STAGE 1: dependencias (capa cacheable) ───────────────────────────────────
FROM python:3.12-slim AS deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── STAGE 2: aplicación (imagen final mínima) ─────────────────────────────────
FROM python:3.12-slim AS app

# Copiar site-packages y binarios del stage de deps
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# curl para el HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Entrypoint fija PORT en runtime (evita que Streamlit quede en 8501 con CMD sin shell)
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copiar el código (capa que cambia más frecuentemente — va al final)
COPY . .

# Falla el build si run_mq26.py no cumple pantalla ingreso (archivo canónico de la app).
RUN grep -q "def cached_clientes_df" run_mq26.py \
 && grep -Fq "df_cli = cached_clientes_df(TENANT_ID)" run_mq26.py \
 && grep -Fq "_cached_clientes_ingreso = cached_clientes_df" run_mq26.py \
 && ! grep -Fq "df_cli = _cached_clientes_ingreso()" run_mq26.py \
 || (echo "ERROR: run_mq26.py pantalla ingreso"; exit 1)

RUN python3 -c "import pathlib; t=pathlib.Path('run_mq26.py').read_text(encoding='utf-8'); \
    assert 'df_cli = cached_clientes_df(TENANT_ID)' in t; \
    assert 'df_cli = _cached_clientes_ingreso()' not in t; \
    print('run_mq26.py pantalla ingreso: OK')"

# Railway inyecta PORT=8080 automáticamente
EXPOSE 8080

# Healthcheck (Docker local). En Railway manda railway.json → healthcheckTimeout.
# --start-period=600s: gracia alineada a arranque lento (Streamlit + imports/red).
HEALTHCHECK --interval=45s --timeout=25s --start-period=600s --retries=8 \
    CMD sh -c 'curl -f "http://127.0.0.1:$${PORT:-8080}/_stcore/health" || exit 1'

# Variables de entorno de producción (no sobreescriben las del sistema)
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MQ26_DEPLOY_MARKER=entry_run_mq26_20260324

ENTRYPOINT ["/docker-entrypoint.sh"]
