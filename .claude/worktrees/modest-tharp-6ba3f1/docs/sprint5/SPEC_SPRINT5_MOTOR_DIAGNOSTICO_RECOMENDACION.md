# MQ26 · Sprint 5 — Motor de Diagnóstico + Motor de Recomendación de Capital

**Fecha:** 02/04/2026 | **Base:** MQ26_V7 (1.461 tests, 0 failures)

**NO CODIFICAR** en este archivo: es **documento de diseño + especificación técnica** solamente.

---

## VISIÓN DEL SPRINT

Este sprint construye el corazón del producto para el inversor individual.
Dos motores nuevos que consumen lo que ya existe y producen decisiones concretas en lenguaje humano.

```
FLUJO COMPLETO:
df_ag (posiciones) + perfil + horizonte + capital_nuevo + ccl
        ↓
  diagnostico_cartera.py  →  DiagnosticoResult
        ↓
  recomendacion_capital.py →  RecomendacionResult
        ↓
  reporte_inversor.py      →  HTML/PDF profesional
        ↓
  ui/tab_inversor.py       →  Pantalla del inversor (3 cards)
```

---

## PARTE 1 — ESTRUCTURA DE DATOS COMPARTIDA

### Los tipos base que ambos motores usan

Todo el sistema habla con estos tipos. Son los contratos entre módulos.

```python
# ═══════════════════════════════════════════════════════════════════════
# Archivo: core/diagnostico_types.py
# Tipos compartidos entre diagnostico_cartera.py y recomendacion_capital.py
# SIN imports de streamlit. SIN imports de yfinance.
# ═══════════════════════════════════════════════════════════════════════
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


# ── Enums de dominio ──────────────────────────────────────────────────────────

class Semaforo(str, Enum):
    VERDE   = "verde"    # Score 80-100: cartera bien posicionada
    AMARILLO = "amarillo" # Score 60-79: hay ajustes recomendados
    ROJO    = "rojo"     # Score  0-59: cartera necesita atención

class PrioridadAccion(str, Enum):
    CRITICA  = "critica"   # Hacer esta semana
    ALTA     = "alta"      # Hacer este mes
    MEDIA    = "media"     # Próxima inyección de capital
    BAJA     = "baja"      # Cuando haya oportunidad
    NINGUNA  = "ninguna"   # No requiere acción

class CategoriaActivo(str, Enum):
    ANCLA_DURA       = "ancla_dura"       # GLD, SHY, BIL, INCOME — preservación pura
    CUASI_DEFENSIVO  = "cuasi_defensivo"  # BRKB, KO, PG, JNJ, XOM — bajo riesgo
    RENTA_FIJA_AR    = "renta_fija_ar"    # ON AAA/AA+, GD29/GD30/GD35 — yield USD local
    GROWTH_QUALITY   = "growth_quality"   # MSFT, GOOGL, AMZN, AAPL — tech blue chip
    GROWTH_AGRESIVO  = "growth_agresivo"  # NVDA, META, MELI, PLTR — alto crecimiento
    LATAM            = "latam"            # MELI, VIST, XP, VALE — exposición regional
    ETF_MERCADO      = "etf_mercado"      # SPY, IVW, VEA — diversificación pasiva
    OTRO             = "otro"             # No clasificado


# ── Observación individual del diagnóstico ───────────────────────────────────

@dataclass
class ObservacionDiagnostico:
    """
    Una sola observación concreta con datos y texto en lenguaje humano.
    Invariante: texto_corto tiene máximo 120 caracteres.
                cifra_clave es siempre un número con unidad (ej: "28%", "USD 1.200", "34%").
    """
    dimension: str           # "cobertura_defensiva" | "concentracion" | "rendimiento" | "senales"
    icono: str               # "✅" | "⚠️" | "🔴"
    titulo: str              # "Cobertura defensiva insuficiente"
    texto_corto: str         # Narrativa ≤ 120 chars: "Tenés 28% defensivo, necesitás 40% para tu perfil Moderado"
    cifra_clave: str         # "28% actual vs 40% requerido"
    accion_sugerida: str     # "Agregar USD 1.200 en GLD o INCOME en la próxima compra"
    prioridad: PrioridadAccion
    score_dimension: float   # 0.0 a 100.0


# ── Resultado del diagnóstico completo ───────────────────────────────────────

@dataclass
class DiagnosticoResult:
    """
    Output completo del motor de diagnóstico.
    Invariante: score_total = promedio ponderado de los 4 scores de dimensión.
                semaforo se deriva automáticamente de score_total.
                len(observaciones) es siempre entre 1 y 6.
    """
    # ── Identificación ──────────────────────────────────────────────────
    cliente_nombre:   str
    perfil:           str    # "Conservador" | "Moderado" | "Arriesgado" | "Muy arriesgado"
    horizonte_label:  str    # "1 año" | "3 años" | "+5 años" etc.
    fecha_diagnostico: str   # ISO date "2026-04-02"

    # ── Score global ────────────────────────────────────────────────────
    score_total:      float  # 0.0 a 100.0
    semaforo:         Semaforo

    # ── Scores por dimensión (0.0 a 100.0) ──────────────────────────────
    score_cobertura_defensiva: float   # peso 35%
    score_concentracion:       float   # peso 25%
    score_rendimiento:         float   # peso 20%
    score_senales_salida:      float   # peso 20%

    # ── Observaciones en lenguaje humano ────────────────────────────────
    observaciones: list[ObservacionDiagnostico] = field(default_factory=list)

    # ── Datos cuantitativos para el reporte ─────────────────────────────
    pct_defensivo_actual:    float = 0.0   # % real de la cartera en activos defensivos
    pct_defensivo_requerido: float = 0.0   # % que exige el perfil
    deficit_defensivo_usd:   float = 0.0   # USD que faltan para cubrir el piso
    activo_mas_concentrado:  str   = ""    # ticker con mayor PESO_PCT
    pct_concentracion_max:   float = 0.0   # PESO_PCT de ese activo
    rendimiento_ytd_usd_pct: float = 0.0   # PNL_PCT_USD de metricas_resumen
    benchmark_ytd_pct:       float = 0.0   # rendimiento del benchmark del perfil
    n_senales_salida_altas:  int   = 0     # posiciones con prioridad ALTA en motor_salida
    n_senales_salida_medias: int   = 0

    # ── Texto narrativo para el reporte ─────────────────────────────────
    titulo_semaforo: str = ""   # "Tu cartera está BIEN con 2 ajustes recomendados"
    resumen_ejecutivo: str = "" # Párrafo de 2-3 oraciones para el reporte PDF

    # ── Metadatos del cálculo ────────────────────────────────────────────
    valor_cartera_usd: float = 0.0
    n_posiciones:      int   = 0
    modo_fallback:     bool  = False   # True si algún cálculo usó datos estimados


# ── Ítem individual de recomendación ────────────────────────────────────────

@dataclass
class ItemRecomendacion:
    """
    Una acción de compra concreta con cantidad exacta calculada.
    Invariante: monto_ars = unidades × precio_ars_estimado (± spread).
                justificacion tiene máximo 150 caracteres.
    """
    orden:               int     # 1, 2, 3... (prioridad de ejecución)
    ticker:              str     # "GLD", "KO", "MSFT" — ticker BYMA
    nombre_legible:      str     # "SPDR Gold Trust", "Coca-Cola", "Microsoft"
    categoria:           CategoriaActivo
    unidades:            int     # cantidad entera a comprar
    precio_ars_estimado: float   # precio de referencia en ARS
    monto_ars:           float   # unidades × precio_ars_estimado
    monto_usd:           float   # monto_ars / ccl
    justificacion:       str     # "Cubre déficit defensivo: pasa de 28% a 36%"
    impacto_en_balance:  str     # "Defensivo: 28% → 36% | Concentración: sin cambio"
    prioridad:           PrioridadAccion
    es_activo_nuevo:     bool    # True si el inversor no lo tiene aún


# ── Resultado de la recomendación completa ───────────────────────────────────

@dataclass
class RecomendacionResult:
    """
    Output completo del motor de recomendación de capital.
    Invariante: sum(i.monto_ars for i in compras_recomendadas) ≤ capital_disponible_ars.
                capital_remanente_ars = capital_disponible_ars - capital_usado_ars.
                Si capital es insuficiente para 1 unidad, compras_recomendadas está vacío.
    """
    # ── Contexto de la recomendación ────────────────────────────────────
    cliente_nombre:       str
    perfil:               str
    capital_disponible_ars: float
    capital_disponible_usd: float
    ccl:                  float
    fecha_recomendacion:  str   # ISO date

    # ── Las compras concretas (ordenadas por prioridad) ──────────────────
    compras_recomendadas: list[ItemRecomendacion] = field(default_factory=list)

    # ── Lo que no alcanza (para mostrar al inversor) ────────────────────
    pendientes_proxima_inyeccion: list[dict] = field(default_factory=list)
    # Formato: [{"ticker": "INCOME", "precio_ars": 185000, "falta_ars": 35000,
    #            "motivo": "Precio unitario mayor al capital disponible"}]

    # ── Resumen de ejecución ─────────────────────────────────────────────
    capital_usado_ars:    float = 0.0
    capital_remanente_ars: float = 0.0
    n_compras:            int   = 0

    # ── Impacto proyectado post-compra ───────────────────────────────────
    pct_defensivo_post:   float = 0.0   # % defensivo DESPUÉS de las compras
    pct_defensivo_pre:    float = 0.0   # % defensivo ANTES de las compras
    delta_balance:        str   = ""    # "Defensivo: 28% → 36% | Concentración: sin cambio"

    # ── Alerta de mercado (modo no-hacer-nada) ───────────────────────────
    alerta_mercado:       bool  = False   # True si VIX > 30 o caída > 15% en 30d
    mensaje_alerta:       str   = ""      # "Mercado en tensión — considera esperar"

    # ── Texto narrativo ──────────────────────────────────────────────────
    resumen_recomendacion: str  = ""   # "Con $150.000 ARS podés hacer 2 compras prioritarias"
```

---

## PARTE 2 — CLASIFICACIÓN DE ACTIVOS

### Mapa completo (fuente de verdad)

El mapa `CLASIFICACION_ACTIVOS`, el universo `UNIVERSO_RENTA_FIJA_AR`, `CATEGORIAS_DEFENSIVAS`, `PISO_DEFENSIVO`, `LIMITE_CONCENTRACION`, `BENCHMARK_RENDIMIENTO`, `AJUSTE_HORIZONTE_CORTO` y `CARTERA_IDEAL` están especificados en el **documento de producto** con comentarios ticker a ticker (incl. reglas de uso de `_RENTA_AR` y ladder de ONs).

**Orden correcto en código (Python válido):**

1. Cerrar **`CLASIFICACION_ACTIVOS`** solo después de incluir el bloque **LATAM / Argentina** (MELI, VIST, etc.).
2. Declarar **`UNIVERSO_RENTA_FIJA_AR`** como **otro `dict`** debajo (ONs y soberanos; sin yfinance).
3. Luego constantes `CATEGORIAS_DEFENSIVAS` … `CARTERA_IDEAL`.

En el borrador en chat, `UNIVERSO_RENTA_FIJA_AR` apareció **entre medio** de `CLASIFICACION_ACTIVOS`; eso **no** es sintaxis válida: corregir al implementar o al copiar.

**Implementación canónica en el repo:** `core/diagnostico_types.py` (mantener alineada con esta spec: tickers, TIR de referencia, textos de descripción).

Comentarios de producto que deben conservarse en docs/código:

- ONs argentinas **no** van en `CLASIFICACION_ACTIVOS` por ticker fijo; muchas se detectan por **tipo** en BD/universo.
- `_RENTA_AR` en `CARTERA_IDEAL` es **placeholder** de ladder; en recomendación va a **pendientes** con mensaje tipo: *ON/Bonos AR — configurar manualmente con tu broker*.
- Reglas de ladder por calificación (AA+ primero, etc.) según texto de producto.

---

## PARTE 3 — MOTOR DE DIAGNÓSTICO

### Archivo: `services/diagnostico_cartera.py`

```python
"""
services/diagnostico_cartera.py — Motor de Diagnóstico de Cartera

Evalúa 4 dimensiones y produce un DiagnosticoResult con semáforo,
observaciones en lenguaje humano y cifras concretas.

SIN imports de streamlit. SIN llamadas a yfinance.
Toda la información viene del ctx ya calculado en run_mq26.py.

Firma principal:
    diagnosticar(df_ag, perfil, horizonte_label, metricas, ccl,
                 precios_dict, universo_df) → DiagnosticoResult
"""

# ── DIMENSIÓN 1: Cobertura defensiva (peso 35%) ──────────────────────────────
#
# Calcula el % real de la cartera en activos defensivos.
# Un activo es defensivo si:
#   a) Su ticker está en CLASIFICACION_ACTIVOS con categoría ANCLA_DURA o CUASI_DEFENSIVO
#   b) Su tipo en universo_df es "ON" (Obligación Negociable) → siempre es RENTA_FIJA_AR
#   c) El ticker empieza con prefijos típicos de bonos AR: AL, GD, TX, PR (para soberanos)
#
# Score:
#   ratio = pct_defensivo_actual / piso_requerido_ajustado_por_horizonte
#   score = min(ratio, 1.0) × 100
#
# Ajuste por horizonte corto: si horizonte ∈ {"1 mes", "3 meses", "6 meses"}
#   piso_requerido += 0.10 (porque el inversor puede necesitar el dinero pronto)

# ── DIMENSIÓN 2: Concentración (peso 25%) ────────────────────────────────────
#
# Verifica que ningún activo supere el LIMITE_CONCENTRACION del perfil.
# Usa la columna PESO_PCT de df_ag (ya calculada en cartera_service.py).
#
# Score base: 100
# Penalización: -25 por cada activo que supere el límite (máximo -75)
#
# Observación generada: "NVDA representa el 34% de tu cartera.
#   Si NVDA cae 20%, tu cartera pierde 6.8%."
# La cifra "6.8%" = PESO_PCT × 0.20 — impacto real calculado.

# ── DIMENSIÓN 3: Rendimiento en contexto (peso 20%) ──────────────────────────
#
# Compara pnl_pct_total_usd (de metricas_resumen) contra el benchmark del perfil.
# El benchmark es ANUAL: se proratea a los días transcurridos desde la primera compra.
#
# Fecha de inicio: min(FECHA_COMPRA) de df_ag — si no disponible, usar 365 días.
# dias_invertido = (hoy - fecha_inicio).days
# benchmark_ytd = BENCHMARK_RENDIMIENTO[perfil] × (dias_invertido / 365)
#
# Score:
#   diff = pnl_pct_total_usd - benchmark_ytd
#   Si diff >= +0.05:  score = 100  (supera benchmark en 5%+)
#   Si diff >= 0:      score = 75   (en línea con benchmark)
#   Si diff >= -0.10:  score = 50   (hasta 10% por debajo)
#   Si diff >= -0.20:  score = 25   (hasta 20% por debajo)
#   Si diff <  -0.20:  score = 0    (más de 20% por debajo)

# ── DIMENSIÓN 4: Señales de acción pendientes (peso 20%) ──────────────────────
#
# Cuenta posiciones marcadas por motor_salida.evaluar_salida() con señal activa.
# IMPORTANTE: NO llamar a evaluar_salida() desde acá — recibir los resultados
# precalculados como parámetro opcional (evitar re-cálculo).
# Si no se pasan → score = 100 (sin penalización por falta de datos).
#
# Score:
#   score = max(0, 100 - (n_alta × 30) - (n_media × 10))

# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────
#
# def diagnosticar(
#     df_ag:          pd.DataFrame,          # posiciones enriquecidas de cartera_service
#     perfil:         str,                   # "Conservador" | "Moderado" | "Arriesgado" | "Muy arriesgado"
#     horizonte_label: str,                  # "1 año" | "3 años" | "+5 años"
#     metricas:       dict,                  # output de metricas_resumen()
#     ccl:            float,                 # tipo de cambio ARS/USD
#     universo_df:    pd.DataFrame | None,   # para detectar ON por tipo
#     senales_salida: list[dict] | None,     # output de evaluar_salida() si ya se calculó
# ) -> DiagnosticoResult:
#
# Pasos internos:
# 1. Detectar activos defensivos → calcular pct_defensivo_actual
# 2. Calcular piso requerido ajustado por horizonte
# 3. Score dimensión 1 (cobertura)
# 4. Score dimensión 2 (concentración) — usar PESO_PCT de df_ag
# 5. Score dimensión 3 (rendimiento) — usar pnl_pct_total_usd de metricas
# 6. Score dimensión 4 (señales) — usar senales_salida si se pasa
# 7. score_total = 0.35×d1 + 0.25×d2 + 0.20×d3 + 0.20×d4
# 8. Derivar semaforo desde score_total
# 9. Construir observaciones en lenguaje humano (máximo 4, ordenadas por prioridad)
# 10. Construir texto narrativo (titulo_semaforo + resumen_ejecutivo)
# 11. Retornar DiagnosticoResult
```

---

## PARTE 4 — MOTOR DE RECOMENDACIÓN DE CAPITAL

### Archivo: `services/recomendacion_capital.py`

```python
"""
services/recomendacion_capital.py — Motor de Recomendación de Capital Nuevo

Dado un capital disponible, calcula exactamente qué comprar (ticker + unidades)
para acercar la cartera actual a la cartera ideal del perfil.

Orden de prioridad INAMOVIBLE:
  1. Cubrir piso defensivo (si hay déficit)
  2. Reducir concentración (si hay activo > límite)
  3. Completar pesos de la cartera ideal (delta entre actual e ideal)
  4. Agregar activos nuevos de alto score MOD-23

SIN imports de streamlit. SIN llamadas a yfinance (usa precios_dict).

Firma principal:
    recomendar(df_ag, perfil, horizonte_label, capital_ars, ccl,
               precios_dict, diagnostico, universo_df) → RecomendacionResult
"""

# ── PASO 1: Detectar estado del mercado (alerta no-hacer-nada) ─────────────
#
# Si market_stress_map puede calcular el estado del VIX:
#   - VIX > 30 → alerta_mercado = True
#   - Si no hay datos de VIX → alerta_mercado = False (no bloquear por falta de datos)
# Si alerta_mercado = True: retornar RecomendacionResult con compras_recomendadas=[]
# y mensaje_alerta con texto explicativo. El inversor sigue pudiendo invertir si quiere,
# pero la app lo advierte.

# ── PASO 2: Calcular pesos actuales de la cartera ────────────────────────────
#
# Para cada ticker en df_ag: peso_actual = VALOR_ARS / valor_total_cartera
# Para los activos en CARTERA_IDEAL que NO están en df_ag: peso_actual = 0.0
# Para _RENTA_AR: peso_actual = suma de PESO_PCT de activos tipo "ON" en df_ag

# ── PASO 3: Calcular delta (cuánto falta de cada activo) ────────────────────
#
# delta[ticker] = peso_ideal[ticker] - peso_actual[ticker]
# Solo interesa delta > 0 (lo que falta, no lo que sobra)
# Para _RENTA_AR con delta > 0: generar ítem "pendiente" no ejecutable automáticamente

# ── PASO 4: Ordenar candidatos por prioridad ─────────────────────────────────
#
# Prioridad 1 (CRITICA): activos defensivos con delta > 0 Y hay déficit de piso
#   Ordenar por: mayor delta primero, desempate por menor precio (más accesible)
#
# Prioridad 2 (ALTA): activos con delta > 0 que reducen concentración
#   (el inversor tiene >límite en algo, comprar otros diluye la concentración)
#
# Prioridad 3 (MEDIA): activos con delta > 0 de la cartera ideal
#   Ordenar por: mayor delta primero, desempate por score MOD-23 (scoring_engine)
#
# Prioridad 4 (BAJA): activos del universo con score MOD-23 > 75 que no están
#   en la cartera ni en la cartera ideal (oportunidades de diversificación)
#   Solo si todo lo anterior ya está cubierto.

# ── PASO 5: Asignar capital en orden de prioridad ───────────────────────────
#
# capital_restante = capital_ars (inicializar)
# Para cada candidato en orden de prioridad:
#
#   precio_ticker = precios_dict.get(ticker, None)
#   Si precio_ticker is None o == 0 → saltar al siguiente
#
#   # Cuánto capital asignar a este activo:
#   proporcion = delta[ticker] / sum(deltas positivos restantes)
#   capital_para_ticker = capital_restante × proporcion
#   # Pero no asignar más de lo que necesita para llegar al peso ideal:
#   capital_para_ticker = min(capital_para_ticker, delta[ticker] × valor_total_cartera)
#
#   unidades = floor(capital_para_ticker / precio_ticker)
#   Si unidades < 1:
#     pendientes_proxima_inyeccion.append({"ticker": ticker, "precio_ars": precio_ticker,
#                                          "falta_ars": precio_ticker - capital_para_ticker})
#     continuar con el siguiente
#
#   monto_real = unidades × precio_ticker
#   Si monto_real > capital_restante → ajustar unidades hacia abajo
#
#   capital_restante -= monto_real
#   agregar ItemRecomendacion a compras_recomendadas

# ── PASO 6: Calcular impacto post-compra ─────────────────────────────────────
#
# valor_post = valor_actual + capital_usado
# pct_defensivo_post = (valor_defensivo_actual + monto_compras_defensivas) / valor_post
# Construir delta_balance como string descriptivo

# ── PASO 7: Generar texto narrativo ──────────────────────────────────────────
#
# resumen_recomendacion: "Con $150.000 ARS podés hacer 2 compras prioritarias.
#   Tu defensa pasa de 28% a 36% luego de estas operaciones."
# Para cada ItemRecomendacion: justificacion en lenguaje simple, máximo 150 chars.
```

---

## PARTE 5 — REPORTE PROFESIONAL

### Archivo: `services/reporte_inversor.py`

Tres funciones, tres niveles de detalle:

```python
"""
services/reporte_inversor.py — Generador de reportes profesionales

Tres niveles según el tier del usuario:
  - generar_reporte_inversor()    → 1 página, lenguaje humano, para tier IN
  - generar_reporte_estudio()     → 2 páginas, con metodología, para tier ES
  - generar_reporte_institucional() → documento completo, para tier SA

SIN imports de streamlit. Retorna siempre HTML string.
El HTML está optimizado para Ctrl+P → Guardar como PDF.
"""

# ── REPORTE INVERSOR (tier IN) — estructura ──────────────────────────────────
#
# SECCIÓN 1: CABECERA
#   Logo MQ26 + nombre cliente + fecha + perfil + horizonte
#
# SECCIÓN 2: TU CARTERA EN NÚMEROS (3 métricas grandes)
#   Valor actual en USD | Rendimiento YTD en USD | Semáforo con label
#
# SECCIÓN 3: DIAGNÓSTICO (máximo 3 observaciones)
#   Para cada ObservacionDiagnostico: icono + título + texto + cifra_clave
#   Solo incluir observaciones con prioridad CRITICA, ALTA o MEDIA
#
# SECCIÓN 4: ACCIÓN RECOMENDADA (si hay capital disponible)
#   "Con $X podés hacer estas compras:"
#   Para cada ItemRecomendacion: ticker + unidades + precio + justificación
#   Si hay pendientes: "Para la próxima inyección: X requiere $Y más"
#
# SECCIÓN 5: TU PROYECCIÓN (3 escenarios simples)
#   Usar retirement_goal.simulate_retirement() con parámetros del perfil
#   Mostrar como barra: Pesimista / Base / Optimista en 3 años
#
# SECCIÓN 6: DISCLAIMER
#   "Este informe es informativo y no constituye asesoramiento financiero."

# ── REPORTE ESTUDIO (tier ES) — agrega sobre el de inversor ─────────────────
#
# Igual que el de inversor MÁS:
#   - Tabla comparativa de todos los clientes del estudio (semáforo por cliente)
#   - Metodología de cálculo del score (para justificar al cliente)
#   - "Acciones recomendadas para el asesor esta semana" (clientes en rojo/amarillo)
#
# ── REPORTE INSTITUCIONAL (tier SA) — documento completo ────────────────────
#
# Todo lo anterior MÁS:
#   - Metodología completa con fórmulas
#   - Parámetros del modelo (PISO_DEFENSIVO, LIMITE_CONCENTRACION, etc.)
#   - Fuentes de datos (yfinance, datos.gob.ar, BCRA)
#   - Disclaimer regulatorio extenso
#   - Firma del asesor con número de matrícula
```

---

## PARTE 6 — INTEGRACIÓN EN UI

### `ui/tab_inversor.py` — reescribir con las 3 cards

```python
"""
ui/tab_inversor.py — Vista simplificada para el inversor individual (tier IN)

Estructura de 3 cards en una sola pantalla sin scroll:

CARD 1: "¿Cómo estoy?" — Diagnóstico con semáforo
  - Semáforo grande (verde/amarillo/rojo) con título
  - 3 métricas: patrimonio USD | rendimiento YTD | n° posiciones
  - Máximo 3 observaciones concretas

CARD 2: "¿Qué hago ahora?" — Recomendación con cantidades exactas
  - Campo: "Tengo $ ___ ARS para invertir" (editable)
  - Botón: "Calcular"
  - Lista de compras con ticker + unidades + monto + justificación

CARD 3: "¿Hacia dónde voy?" — Proyección simple
  - Slider: "¿Cuánto podés aportar por mes?" (ARS)
  - Gráfico de barras: Pesimista / Base / Optimista en 3/5/10 años
"""

# Notas de implementación:
# - diagnosticar() y recomendar() se llaman SOLO cuando el usuario hace click
#   o cuando entra a la app (no en cada rerun)
# - Cachear DiagnosticoResult en st.session_state["diagnostico_cache"]
#   con TTL de 5 minutos (no recalcular si el usuario solo mueve un slider)
# - El campo de capital nuevo inicializa con ctx["capital_nuevo"] si existe
# - Si df_ag está vacío → mostrar wizard de onboarding (import desde tab_estudio.py)
# - use_container_width=True en todos los gráficos y dataframes
```

---

## PARTE 7 — TESTS

### `tests/test_diagnostico_cartera.py`

```python
# Tests mínimos requeridos (todos con datos sintéticos, sin yfinance):

# test_diagnostico_cartera_conservadora_deficiente():
#   df_ag con 0% defensivo, perfil Conservador → semáforo ROJO, score < 60

# test_diagnostico_cartera_bien_balanceada():
#   df_ag con 55% defensivo y sin concentración excesiva, perfil Conservador → semáforo VERDE

# test_ajuste_horizonte_corto():
#   perfil Moderado + horizonte "3 meses" → piso requerido = 50% (40% + 10% ajuste)

# test_concentracion_detecta_activo_sobre_limite():
#   df_ag con NVDA al 40%, perfil Moderado (límite 25%) → score_concentracion < 75

# test_observaciones_tienen_cifras_concretas():
#   Todas las ObservacionDiagnostico tienen cifra_clave no vacía

# test_score_total_es_promedio_ponderado():
#   Verificar 0.35×d1 + 0.25×d2 + 0.20×d3 + 0.20×d4

# test_activo_on_cuenta_como_defensivo():
#   df_ag con activo tipo="ON" → contado en pct_defensivo_actual

# test_diagnostico_sin_posiciones():
#   df_ag vacío → no lanza excepción, retorna DiagnosticoResult con score bajo
```

### `tests/test_recomendacion_capital.py`

```python
# test_recomendacion_prioriza_defensa_primero():
#   df_ag sin defensivos, capital suficiente para GLD y MSFT
#   → primera compra siempre es GLD (defensivo), no MSFT

# test_recomendacion_unidades_enteras():
#   Todas las unidades en compras_recomendadas son int >= 1

# test_recomendacion_capital_no_supera_disponible():
#   sum(i.monto_ars for i in result.compras_recomendadas) <= capital_disponible_ars

# test_pendientes_si_precio_supera_capital():
#   GLD cuesta $215.000 ARS, capital = $100.000 → GLD en pendientes, no en compras

# test_recomendacion_cartera_perfecta_no_compra_nada_innecesario():
#   df_ag con cartera ideal exacta → compras_recomendadas vacío o solo oportunidades

# test_recomendacion_capital_cero():
#   capital_ars = 0 → compras_recomendadas vacío, sin excepción

# test_renta_ar_placeholder_va_a_pendientes():
#   _RENTA_AR con delta > 0 → aparece en pendientes_proxima_inyeccion con mensaje
```

---

## PARTE 8 — CHECKLIST DE VERIFICACIÓN

```bash
# 1. Suite completa
pytest tests/ -q --tb=short
# Esperado: ≥ 1461 passed, 0 failed

# 2. Tests nuevos específicamente
pytest tests/test_diagnostico_cartera.py tests/test_recomendacion_capital.py -v

# 3. Smoke: diagnostico con df_ag vacío no rompe nada
python -c "
import pandas as pd
from core.diagnostico_types import DiagnosticoResult
from services.diagnostico_cartera import diagnosticar
result = diagnosticar(
    df_ag=pd.DataFrame(),
    perfil='Moderado',
    horizonte_label='3 años',
    metricas={},
    ccl=1150.0,
    universo_df=None,
    senales_salida=None,
)
print(f'Score: {result.score_total:.1f} | Semáforo: {result.semaforo}')
print('Smoke OK')
"

# 4. Smoke: recomendación con capital pequeño
python -c "
import pandas as pd
from services.recomendacion_capital import recomendar
result = recomendar(
    df_ag=pd.DataFrame(),
    perfil='Moderado',
    horizonte_label='3 años',
    capital_ars=50_000.0,
    ccl=1150.0,
    precios_dict={'KO': 8200.0, 'SPY': 580_000.0, 'GLD': 215_000.0},
    diagnostico=None,
    universo_df=None,
)
print(f'Compras: {result.n_compras} | Remanente: \${result.capital_remanente_ars:,.0f} ARS')
print('Smoke OK')
"

# 5. Verificar que no importa streamlit en los módulos nuevos
python -c "
import ast, sys
for m in ['core/diagnostico_types.py',
          'services/diagnostico_cartera.py',
          'services/recomendacion_capital.py',
          'services/reporte_inversor.py']:
    src = open(m).read()
    assert 'import streamlit' not in src, f'{m} importa streamlit!'
print('Sin streamlit en módulos de negocio OK')
"
```

---

## REGLAS GLOBALES (recordatorio)

1. Nunca importar `streamlit` en `core/` ni `services/`.
2. `np.random` siempre con `np.random.default_rng(seed=42)`.
3. Toda función nueva en `core/`: mínimo 2 tests.
4. Toda función nueva en `services/`: mínimo 1 test con datos sintéticos.
5. Un commit por archivo: `feat(S5-diagnostico): ...`, `feat(S5-recomendacion): ...`
6. Tras cada commit: `pytest tests/ -q --tb=short` debe pasar.
7. `use_container_width=True` en todos los widgets de UI.
8. Scripts siempre completos, sin truncar.

---

## NOTAS PARA CURSOR

- `core/diagnostico_types.py` debe crearse PRIMERO — es la dependencia de todo lo demás.
- `diagnostico_cartera.py` NO llama a yfinance ni a scoring_engine para su cálculo principal.
  El scoring_engine solo se usa en `recomendacion_capital.py` para el paso 4 (oportunidades).
- El campo `_RENTA_AR` en CARTERA_IDEAL NO es un ticker real — es un placeholder.
  En `recomendacion_capital.py` se debe detectar y poner siempre en `pendientes_proxima_inyeccion`
  con el mensaje: "ON/Bonos AR — configurar manualmente con tu broker".
- `tab_inversor.py` debe cachear el DiagnosticoResult en `st.session_state` para no
  recalcular en cada rerun de Streamlit.
- Los tests NO deben hacer llamadas a yfinance — usar precios_dict con valores hardcodeados.

---

## VENTAJA DIFERENCIAL vs COMPETENCIA (Inversiones Andinas — abril 2026)

### Lo que ellos tienen

- Reporte mensual en Word/PDF con rendimiento de la cartera modelo
- 3 carteras estáticas (Conservadora 70/30, Moderada 65/35, Agresiva 50/50)
- Sugerencia de aporte mensual genérica (mismo para todos del perfil)
- TIR de referencia por ON (dato relevante que hay que mostrar)

### Lo que MQ26 tiene y ellos no

- Diagnóstico de la cartera REAL del cliente, no de una cartera modelo
- Recomendación de aporte mensual personalizada al estado actual de esa cartera
- Backtesting con equity curves de la cartera específica
- 9 modelos de optimización con comparación simultánea
- Score MOD-23 por activo para fundamentar cada recomendación

### El reporte de MQ26 debe incluir (para superar a IA)

1. Rendimiento YTD de la cartera del cliente vs rendimiento de la cartera modelo del perfil  
   → "Tu cartera moderada subió +6.2% YTD. La cartera moderada de referencia: +8.69%"  
   → "Diferencia: -2.49%. Acciones recomendadas para cerrar el gap."

2. TIR ponderada del segmento de renta fija del cliente  
   → "Tu renta fija rinde un promedio de 7.4% TIR. El mercado ofrece hasta 8.3% (TLCTO)."

3. Tabla de ONs disponibles con TIR actual para el próximo aporte  
   → Mostrar los 3-4 mejores instrumentos de UNIVERSO_RENTA_FIJA_AR por relación TIR/calificación

4. Ladder de vencimientos (gráfico de barras)  
   → Cuándo vencen las ONs del cliente, para planificar reinversión

5. Comparación vs SPY y vs la cartera modelo del perfil en el mismo gráfico  
   → El chart con 3 líneas: cartera del cliente / cartera modelo / SPY

---

## Índice de archivos en `docs/sprint5/`

| Archivo | Contenido |
|---------|-----------|
| `SPEC_SPRINT5_MOTOR_DIAGNOSTICO_RECOMENDACION.md` | **Esta spec completa** (Partes 1 y 3–8 íntegras; Parte 2 por referencia a código + orden de dicts). |
| `SPEC_MOTOR_DIAGNOSTICO_RECOMENDACION.md` | Resumen operativo previo (opcional; puede unificarse con este). |
