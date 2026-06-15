#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# MQ26 — Deploy a Railway en 5 pasos
# Ejecutar desde la raíz del repo: bash scripts/deploy_railway.sh
# Requiere: git, railway CLI (npm install -g @railway/cli) o usar la web
# ═══════════════════════════════════════════════════════════════════════════
set -e

echo ""
echo "═══════════════════════════════════════════════"
echo "  MQ26 — Deploy Railway"
echo "═══════════════════════════════════════════════"
echo ""

# ── PASO 1: Verificar que los tests pasan ───────────────────────────────────
echo "→ Paso 1/5: Verificando tests..."
MQ26_PASSWORD=test_password_123 python -m pytest tests/ -q --tb=no --no-cov
echo "  ✓ Tests OK"

# ── PASO 2: Verificar que no hay regresiones de paleta ─────────────────────
echo ""
echo "→ Paso 2/5: Verificando reglas de no-regresión..."
if grep -q "use_light=True" app_main.py; then
  echo "  ✗ ERROR: app_main.py tiene use_light=True hardcodeado."
  echo "    Corregir antes de deployar (ver SKILL comite-implementacion)."
  exit 1
fi
ACENTO=$(grep "c-accent:" assets/style_retail_light.css | head -1)
if echo "$ACENTO" | grep -q "2563eb"; then
  echo "  ✗ ERROR: style_retail_light.css tiene acento azul #2563eb."
  echo "    Debe ser #8B1A2E (borgoña). Corregir antes de deployar."
  exit 1
fi
if [ -z "$ACENTO" ]; then
  echo "  ✗ ERROR: no se encontró --c-accent en assets/style_retail_light.css."
  exit 1
fi
echo "  ✓ Paleta OK (borgoña en tema claro, use_light condicional)"

# ── PASO 3: Push a GitHub ───────────────────────────────────────────────────
echo ""
echo "→ Paso 3/5: Push a GitHub..."
BRANCH=$(git branch --show-current)
git add -A
if git diff --cached --quiet; then
  echo "  (nada nuevo para commitear)"
else
  git commit -m "chore: deploy $(date +%Y-%m-%d) — V12 + tab Mercado"
fi
git push origin "$BRANCH"
echo "  ✓ Push OK (rama: $BRANCH)"

# ── PASO 4: Variables de entorno Railway ────────────────────────────────────
echo ""
echo "→ Paso 4/5: Variables de entorno necesarias en Railway"
echo ""
echo "  Copiar y pegar en Railway → Variables:"
echo "  ─────────────────────────────────────────"
cat << 'VARS'
  DEMO_MODE=true
  MQ26_PASSWORD=demo.2026
  MQ26_VIEWER_PASSWORD=visor/2026
  MQ26_INVESTOR_PASSWORD=inversor+2026
  MQ26_USER_ADMIN=admin1452
  CCL_FALLBACK=1400.0
  MQ26_RETAIL_LIGHT=1
  MQ26_TRY_DB_USERS=false
VARS
echo "  ─────────────────────────────────────────"
echo ""
echo "  IMPORTANTE: cambiar MQ26_PASSWORD antes de usar datos reales."

# ── PASO 5: URL y acceso ───────────────────────────────────────────────────
echo ""
echo "→ Paso 5/5: Acceso"
echo ""
echo "  Después del deploy Railway muestra una URL tipo:"
echo "  https://mq26-production.up.railway.app"
echo ""
echo "  Mandar a los 10 usuarios beta:"
echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  URL: [tu-url].up.railway.app                   │"
echo "  │  Admin:    admin1452 / demo.2026                 │"
echo "  │  Estudio:  estudio   / visor/2026                │"
echo "  │  Inversor: inversor  / inversor+2026             │"
echo "  └──────────────────────────────────────────────────┘"
echo ""
echo "═══════════════════════════════════════════════"
echo "  Deploy listo. Verificar health:"
echo "  curl https://[url]/_stcore/health"
echo "═══════════════════════════════════════════════"
