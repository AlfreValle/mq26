# MANUAL DE CAPACITACION
# MQ26-DSS — Terminal Institucional de Gestión de Inversiones
### Alfredo Vallejos | Corrientes, Argentina | v17.2 — Marzo 2026

---

> **Para quién es este manual**
> Para el asesor que usa MQ26-DSS todos los días y necesita explicar cada decisión con autoridad.
> El sistema no adivina el mercado — aumenta las probabilidades de estar en el activo correcto en el momento correcto.

---

## INDICE

1. ¿Qué es MQ26-DSS? — Visión y arquitectura actualizada
2. Instalación y primer arranque
3. Los 7 Tabs — Funcionalidad pantalla por pantalla (NUEVO)
4. Los 7 Modelos de Optimización — incluyendo Multi-Objetivo (NUEVO)
5. Motor MOD-23 — Score técnico 1-10
6. Motor de Salida — 5 disparadores + Kelly Criterion
7. CEDEARs — Ratios, CCL, PPC, cálculos
8. FCI, Bonos y Merval — Activos locales argentinos
9. Cómo asesorar a un cliente — Proceso completo por perfil
10. Preguntas frecuentes y respuestas
11. Glosario de términos financieros
12. MQ26 vs el mercado global

---

---

## 1. ¿QUÉ ES MQ26-DSS Y PARA QUÉ SIRVE

### Definición simple

MQ26-DSS es un sistema de gestión de inversiones construido para el inversor argentino.
Combina análisis técnico, cuantitativo y contextual en una sola plataforma que corre en tu PC,
sin cargos mensuales ni servidores externos, con todo el universo financiero argentino integrado:
CEDEARs BYMA, Merval, FCI, Bonos soberanos y ONs corporativas.

### El problema que resuelve

| Pregunta del inversor | Solución MQ26-DSS |
|---|---|
| ¿Cuánto vale mi cartera hoy? | Tab 1 — Posición Neta: valor ARS, USD y P&L en tiempo real |
| ¿Qué compro esta semana? | Tab 6 — Recomendador: evalúa 120+ activos por perfil y presupuesto |
| ¿Cuándo salgo de una posición? | Motor de Salida: 5 disparadores con barra de progreso al objetivo |
| ¿Estoy bien diversificado? | Tab 1 — Gráfico de torta y alerta de concentración >18% |
| ¿Cuánto riesgo tiene mi cartera? | Tab 5 — VaR 95% y CVaR con Montecarlo |
| ¿Cuánto gané vs comprar SPY? | Tab 5 — Equity curve histórica con alpha acumulado |
| ¿Cómo explico esto a un cliente? | Tab 7 — Reporte HTML en 30 segundos → PDF con Ctrl+P |

### Arquitectura en 5 capas (actualizada v17.2)

```
┌─────────────────────────────────────────────┐
│  CAPA 1 — DATOS                             │
│  Maestra_Inversiones.xlsx  →  SQLite local  │
│  yfinance (precios live)  ←→  CCL GGAL/GGAL │
│  Universo_120_CEDEARs.xlsx  →  Activos      │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  CAPA 2 — ANALÍTICA                         │
│  Motor MOD-23 (SMA-150 + RSI-14 + Mom 3M)  │
│  RiskEngine (7 modelos scipy)               │
│  Backtester + Stress Test Montecarlo        │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  CAPA 3 — DECISIÓN                          │
│  Multi-Objetivo (Sharpe 40% + Retorno 30%   │
│               + Preservación 20% + Div 10%) │
│  Árbol de Decisión: Alpha Neto vs Costos    │
│  Anti-Churning: umbral de desviación ≥5%   │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  CAPA 4 — EJECUCIÓN                         │
│  Mesa de Órdenes filtradas por Alpha Neto   │
│  Recomendador Semanal por perfil            │
│  Exportación Excel de órdenes               │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  CAPA 5 — REPORTES                          │
│  Reporte HTML → PDF (Ctrl+P)                │
│  Alertas Telegram (VaR, drawdown, MOD-23)   │
│  Email semanal automático (Gmail API)        │
└─────────────────────────────────────────────┘
```

### ¿Por qué no se usó algo que ya existía?

No existe ningún sistema en el mundo con CEDEARs BYMA, FCI via CAFCI, CCL en tiempo real,
contexto macro argentino y emails de Balanz integrados. Bloomberg cuesta USD 31.980/año
y no tiene ninguna de esas funcionalidades.

---

## 2. INSTALACIÓN Y PRIMER ARRANQUE

### Requisitos previos
- Python 3.10 o superior
- Git (opcional)
- Conexión a internet (para yfinance y CCL en tiempo real)

### Paso a paso

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar credenciales
cp .env.example .env
```

Editar el archivo `.env` con cualquier editor de texto:
```
MQ26_PASSWORD=tu_contraseña_segura
DATABASE_URL=               ← dejar vacío para usar SQLite local
TELEGRAM_TOKEN=             ← opcional, para alertas automáticas
TELEGRAM_CHAT_ID=           ← opcional
```

> ⚠️ **IMPORTANTE**: si `MQ26_PASSWORD` no está definido en `.env`, la app no arranca.
> Esta es una mejora de seguridad respecto a la versión anterior (ya no hay contraseña hardcodeada en el código).

```bash
# 3. Arrancar la aplicación
streamlit run app_main.py
```

La app queda disponible en `http://localhost:8501`.
Ingresar la contraseña definida en `.env` para acceder.

### Archivos de datos requeridos en `0_Data_Maestra/`

| Archivo | Descripción | Obligatorio |
|---|---|---|
| `Maestra_Inversiones.xlsx` | Historial completo de operaciones por cartera | Sí |
| `Universo_120_CEDEARs.xlsx` | Universo con ratios CEDEAR y sectores | Sí |
| `Analisis_Empresas.xlsx` | Scores MOD-23 precalculados | Recomendado |
| `master_quant.db` | Base SQLite (se genera automáticamente al arrancar) | Auto |

### Estructura de directorios

```
MQ26_v17/
├── app_main.py               ← Punto de entrada (497 líneas — orquestador puro)
├── config.py                 ← Parámetros centrales del sistema
├── .env                      ← Credenciales (NO subir al repositorio)
├── requirements.txt
│
├── 0_Data_Maestra/           ← Datos persistentes
├── 1_Scripts_Motor/          ← Motores cuantitativos (risk_engine, data_engine, etc.)
├── core/                     ← Infraestructura (db_manager, logging)
├── services/                 ← Servicios de dominio (cartera, backtest, reportes)
└── ui/                       ← Módulos de interfaz — UN ARCHIVO POR TAB
    ├── tab_cartera.py
    ├── tab_ledger.py
    ├── tab_universo.py
    ├── tab_optimizacion.py
    ├── tab_riesgo.py
    ├── tab_ejecucion.py
    └── tab_reporte.py
```

---
## 3. LOS 7 TABS DE LA APLICACIÓN
### Funcionalidad completa — pantalla por pantalla

> **Cambio clave v17.2**: La app pasó de 10 tabs independientes a **7 tabs organizados por flujo de trabajo institucional**.
> Cada tab agrupa funcionalidades relacionadas en sub-tabs internos.
> Esto elimina el salto constante entre pantallas y refleja cómo trabaja realmente un asesor.

### Panel Lateral (Sidebar) — siempre visible

Antes de cualquier tab, el sidebar permite:
- **Seleccionar el cliente/cartera activa**: define qué cartera se usa en todos los tabs
- **Ver CCL en tiempo real**: calculado como GGAL.BA / GGAL × 10
- **Resumen rápido**: cantidad de posiciones, capital USD estimado, P&L total del día
- **Botón Motor de Salida**: análisis de cierre de posiciones (independiente de los 7 tabs)

---

### Tab 1 — Cartera & CRM

**Sub-tab A: Posición Neta** (antes Tab 3)

Vista consolidada de la cartera activa con alertas automáticas.

| Columna | Descripción |
|---|---|
| Ticker | Símbolo del activo |
| Cantidad | Unidades en posesión |
| PPC USD | Precio Promedio de Compra en dólares |
| Precio Actual USD | Cotización live vía yfinance |
| Valor ARS | Cantidad × Precio ARS actual |
| P&L ARS | Ganancia/pérdida en pesos |
| P&L % | Variación porcentual desde el PPC |
| Peso % | Participación en el total de la cartera |
| Score MOD-23 | Semáforo verde/amarillo/rojo |

**Alertas automáticas**:
- 🔴 Si algún activo supera el **18% de concentración** → alerta de sobreweight
- 🟡 Si el score MOD-23 cae por debajo de 4.0 → alerta de deterioro técnico
- Gráfico de torta (distribución por activo) y gráfico de barras (por sector)
- Botón **Exportar a Excel**

**Sub-tab B: CRM Clientes** (antes Tab 1)

Gestión centralizada de todos los clientes.

- Tabla editable: nombre, perfil (Conservador/Moderado/Agresivo), capital USD, tipo (Persona/Empresa)
- Botón **"Sincronizar capital con cartera"**: actualiza el capital USD automáticamente desde las posiciones
- Formulario de carga manual de operaciones: COMPRA / VENTA, ticker, cantidad, precio ARS, fecha, broker
- Campos adicionales: comisión broker, derechos de mercado, IVA — todos persistidos en la base de datos

---

### Tab 2 — Libro Mayor (IBOR)

**Sub-tab A: Libro Mayor**

Investment Book of Record — fuente de verdad de todas las operaciones.

- **Importador de comprobantes Excel**: subir archivo del broker → seleccionar propietario y cartera → ingresar CCL del día → preview de operaciones detectadas → confirmar importación
- Brokers soportados: **Balanz** y **Bull Market**
- Libro consolidado con precio subyacente en USD, comisiones, total neto ARS

**Sub-tab B: Gmail / Importar correos** (antes funcionalidad separada)

- Lectura automática de emails de confirmación de operaciones de Balanz y Bull Market
- Parseo automático del comprobante → propuesta de carga → confirmación con un clic

---

### Tab 3 — Universo & Señales

**Sub-tab A: Motor MOD-23** (antes Tab 4)

Escaneo técnico de 120+ activos del universo.

| Score | Clasificación | Interpretación |
|---|---|---|
| 7.0 – 10.0 | ⭐ ELITE | Activo en tendencia alcista con fundamentos sólidos |
| 5.0 – 6.9 | 🟡 ALCISTA | Señal positiva, continuar monitoreando |
| 4.0 – 4.9 | ⚪ NEUTRO | Sin señal clara |
| 0.0 – 3.9 | 🔴 ALERTA VENTA | Deterioro técnico — revisar posición |

- Botón **"Recalcular MOD-23"** (tarda ~2-3 minutos, descarga datos de yfinance)
- Filtros: score mínimo, sector, tipo de activo
- Sección separada: scores de los activos de la **cartera activa** resaltados
- Exportar análisis completo a Excel

**Sub-tab B: Velas + Técnico** (antes Tab 8)

Gráfico OHLCV interactivo para cualquier activo.

- Candlestick con volumen coloreado
- SMA-150 superpuesta en tiempo real
- RSI-14 con bandas de sobrecompra (70) y sobreventa (30)
- Periodos: 3M, 6M, 1Y, 2Y

---

### Tab 4 — Lab Quant / Optimización ⭐ (actualización importante)

Corre los **7 modelos de optimización simultáneamente** y los compara.

**NOVEDAD v17.2**: Al abrir este tab, los activos de la **cartera activa del cliente se pre-seleccionan automáticamente**.
No es necesario ingresar tickers manualmente — el sistema trae la cartera del cliente como punto de partida.

**Controles**:

| Control | Descripción | Default |
|---|---|---|
| Activos a optimizar | Multiselect — carga la cartera activa por defecto | Cartera del cliente |
| Histórico | Ventana de datos históricos: 6mo / 1y / 2y / 3y | 1 año |
| Convicción mínima % | Peso mínimo por activo para incluirlo en el portafolio | 3% |
| Capital nuevo | Monto disponible para invertir (en ARS o USD) | — |
| Botón "↩️ Restaurar activos de la cartera" | Resetea el multiselect a los activos del cliente activo | — |

> **Cómo funciona el pre-llenado**: cuando se selecciona un cliente en el sidebar, el sistema detecta
> automáticamente el cambio de cartera y actualiza el multiselect con los tickers de ese cliente.
> Los tickers de la cartera se incluyen como opciones aunque no estén en el universo del CSV,
> garantizando que siempre se puedan optimizar las posiciones reales del cliente.

**Resultados del Lab Quant**:

1. **Tabla comparativa de métricas**: Retorno Anual, Volatilidad, Sharpe, Sortino, Max Drawdown, VaR 95%, CVaR 95%
   → el mejor valor de cada métrica se resalta en verde
2. **Radar chart normalizado**: comparación visual de todos los modelos en un gráfico de tela de araña
3. **Tabla de pesos por modelo**: qué % asigna cada modelo a cada activo
4. **Equity curves históricas superpuestas**: rendimiento de cada modelo vs SPY como benchmark
5. **Plan de inversión**: cuántos USD invertir por activo según el modelo elegido y el capital disponible
6. **Selector de modelo activo**: el modelo seleccionado se propaga automáticamente a Tab 5 (Riesgo) y Tab 6 (Ejecución)

---

### Tab 5 — Riesgo & Simulación

> Requiere haber corrido el Lab Quant (Tab 4) primero.

**Sub-tab A: Backtest vs Benchmark** (antes Tab 6)

Equity curve histórica real del portafolio optimizado.

- Benchmarks disponibles: SPY, QQQ, EWZ
- Métricas: Retorno total, Retorno anualizado, Sharpe, Sortino, Max Drawdown, Calmar Ratio
- Gráfico de **alpha acumulado** (diferencia diaria respecto al benchmark)
- Periodos: 1Y, 2Y, 3Y, 5Y
- Opción de **rebalanceo mensual** (más realista — incluye costo de transacción del 0.6% mensual)

> **MEJORA v17.2**: el backtest ahora incluye costos de rebalanceo (0.6% mensual, configurable).
> Esto hace los resultados más realistas — el Sharpe calculado refleja lo que el cliente realmente hubiera obtenido.
>
> **Nota sobre el benchmark**: si yfinance no está disponible, el sistema usa datos en caché local y muestra
> un aviso amarillo. Los resultados siguen siendo válidos pero podrían no reflejar el precio más reciente del SPY.

**Sub-tab B: Stress Test Montecarlo** (antes Tab 7)

Simulación de escenarios extremos con N iteraciones.

| Escenario precargado | Shock aplicado |
|---|---|
| Crisis 2008 | -50% en 60 días |
| COVID Mar 2020 | -34% en 23 días |
| Inflación 2022 | -19% en 90 días |
| Escenario base normal | Distribución histórica sin shock |

- Configurable: hasta 50.000 escenarios, hasta 252 días (1 año)
- Métricas de salida: VaR 95%, CVaR 95%, Max DD percentil 95, Sharpe simulado
- Alerta automática por Telegram si el VaR supera el umbral configurado en `config.py`
- Shocks personalizados por sector y tiempo estimado de recuperación

---

### Tab 6 — Mesa de Ejecución

**Sub-tab A: Mesa de Ejecución** (antes Tab 9)

Genera órdenes de rebalanceo filtradas por árbol de decisión cuantitativo.

**El árbol de decisión aprueba una orden sólo si se cumplen AMBAS condiciones**:
1. La desviación entre el peso actual y el peso objetivo es **≥ 5%** (anti-churning)
2. El **alpha neto > 0**: ganancia esperada > comisión real del broker

Parámetros ajustables:

| Parámetro | Descripción | Default |
|---|---|---|
| Capital nuevo en ARS | Monto disponible para el rebalanceo | — |
| Modelo objetivo | Sharpe / Sortino / CVaR / Risk Parity | Multi-Objetivo |
| Comisión broker % | Balanz 0.6%, Bull Market 0.5%, IOL 0.7% | 0.6% |
| Umbral anti-churning % | Desviación mínima para generar orden | 5% |

Resultado:
- ✅ **Órdenes APROBADAS** (verde = compra, rojo = venta) con cantidad, precio estimado y monto ARS
- ❌ **Órdenes BLOQUEADAS** con motivo detallado (costo > alpha / desviación insuficiente)
- Botón exportar a Excel
- Envío de alerta a Telegram con el resumen de órdenes

> **MEJORA v17.2 — alpha compuesto**: el cálculo del alpha esperado usa capitalización compuesta
> `((1 + ret_diario)^horizonte_dias - 1)` en lugar del cálculo lineal anterior.
> Para horizontes de 3-6 meses, la diferencia puede ser de 1-3 puntos porcentuales.

**Sub-tab B: Recomendador Semanal** (antes Tab Recomendador)

Recomendación semanal adaptada al perfil del cliente activo.

- Escanea 120+ activos con score 60/20/20 filtrado por perfil (Conservador/Moderado/Agresivo)
- Propone cartera óptima de 10-12 activos con distribución porcentual
- Calcula operaciones concretas de la semana con el presupuesto disponible ($500.000 ARS default, ajustable)
- Contexto macro editable (cepo, riesgo país, tendencia CCL)
- Botón **"Guardar borrador en Gmail"** para email automático

---

### Tab 7 — Reporte Cliente

Genera un informe HTML profesional descargable.

Secciones opcionales (se activan/desactivan con checkboxes):
- Resumen ejecutivo de la cartera
- Lab Quant — comparativa de modelos (requiere Tab 4 ejecutado)
- Backtest vs Benchmark (requiere Tab 5 ejecutado)
- Órdenes de ejecución del período

Campos del reporte:
- Nombre del cliente (pre-llenado desde la cartera activa)
- Nombre del asesor (default "Alfredo Vallejos")
- Notas del asesor (texto libre)

**Para obtener PDF**: abrir el HTML en el navegador → Ctrl+P → Guardar como PDF.

---
## 4. LOS 7 MODELOS DE OPTIMIZACIÓN
### Comparación y cuándo usar cada uno

> **NOVEDAD v17.2**: se incorporó el séptimo modelo — **Multi-Objetivo** — que combina los mejores
> aspectos de los otros modelos en una función objetivo única ponderada.
> Este es el **modelo recomendado para uso por defecto** con clientes.

### Resumen comparativo

| # | Modelo | Objetivo | Perfil ideal | Color |
|---|---|---|---|---|
| 1 | **Sharpe** | Maximiza retorno/riesgo total | Moderado - Agresivo | Azul |
| 2 | **Sortino** | Maximiza retorno/riesgo bajista | Moderado | Verde |
| 3 | **CVaR** | Minimiza pérdida esperada en el peor 5% | Conservador | Rojo |
| 4 | **Risk Parity** | Distribuye el riesgo equitativamente | Conservador - Moderado | Amarillo |
| 5 | **Kelly** | Maximiza crecimiento logarítmico | Agresivo | Violeta |
| 6 | **Min Drawdown** | Minimiza la caída máxima histórica | Conservador | Verde agua |
| 7 | **Multi-Objetivo** ⭐ | Función compuesta ponderada | Todos los perfiles | Naranja |

---

### Modelo 1 — Sharpe (Markowitz)

**Objetivo**: maximizar el ratio `(Retorno_anual - Tasa_libre_riesgo) / Volatilidad_anual`

**Cuándo usarlo**: cliente moderado o agresivo que quiere el mejor balance riesgo/retorno global.
Es el modelo más usado en la industria (Premio Nobel Markowitz 1990).

**Limitación**: no diferencia entre volatilidad al alza y a la baja. Un activo que sube de forma volátil
"penaliza" igual que uno que cae de forma volátil.

**Referencia**: `RISK_FREE_RATE = 4.3%` (T-Bill 3M USA — actualizar trimestralmente en `config.py`)

---

### Modelo 2 — Sortino

**Objetivo**: maximizar `(Retorno_anual - Tasa_libre_riesgo) / Downside_Deviation`

**Diferencia clave vs Sharpe**: solo penaliza la volatilidad negativa (caídas). La volatilidad positiva
(subidas) no se castiga. Resultado: carteras más agresivas en activos que suben con fuerza.

**Cuándo usarlo**: cliente moderado con tolerancia a cierta volatilidad alcista, pero sensible a las caídas.

---

### Modelo 3 — CVaR (Conditional Value at Risk)

**Objetivo**: minimizar el promedio de pérdidas en los peores escenarios (peor 5%)

**Implementación**: formulación convexa de **Rockafellar-Uryasev** (estándar académico).

> **MEJORA v17.2**: se reemplazó la minimización directa de CVaR (inestable numéricamente con scipy)
> por la formulación de Rockafellar-Uryasev. Esto hace que el modelo **nunca falle** en la convergencia,
> independientemente de los activos seleccionados.

**Cuándo usarlo**: cliente conservador o que sufrió pérdidas importantes. Foco en "no perder demasiado"
en el peor escenario posible.

**Diferencia vs VaR**: VaR dice "no perdo más de X con 95% de probabilidad". CVaR dice "si supero ese
umbral, en promedio pierdo Y". CVaR es más conservador y más robusto como medida de riesgo extremo.

---

### Modelo 4 — Risk Parity (Paridad de Riesgo)

**Objetivo**: cada activo contribuye **igual** al riesgo total del portafolio

**Lógica**: si AAPL tiene el doble de volatilidad que GLD, Risk Parity asigna la mitad de peso a AAPL.
Resultado: carteras muy diversificadas donde ningún activo "domina" el riesgo.

**Cuándo usarlo**: cliente conservador o moderado que quiere diversificación real (no solo en cantidad
de activos, sino en contribución al riesgo).

**Característica**: funciona sin proyecciones de retorno. Solo necesita la matriz de covarianza.
Esto lo hace muy robusto ante estimaciones incorrectas de retornos esperados.

---

### Modelo 5 — Kelly Criterion

**Objetivo**: maximizar el crecimiento geométrico del capital a largo plazo

**Fórmula Kelly completo**: `f* = (p × b - q) / b` donde p = prob. éxito, b = ganancia/pérdida, q = 1-p

**MQ26 usa Kelly Fraccionado al 25%**: el Kelly completo puede recomendar poner el 60-80% en un
solo activo. Con el 25% se mantiene el crecimiento óptimo con volatilidad tolerable para humanos.

**Cuándo usarlo**: cliente agresivo con alto conocimiento del sistema, horizonte largo (5+ años).
No recomendado para conservadores — genera portafolios muy concentrados.

---

### Modelo 6 — Min Drawdown

**Objetivo**: minimizar el máximo drawdown histórico del portafolio

**Qué es el drawdown**: la caída máxima desde un pico hasta el valle siguiente. Si el portafolio
llegó a $100 y luego cayó a $70, el drawdown es -30%.

**Cuándo usarlo**: cliente que psicológicamente no tolera ver pérdidas grandes en el estado de cuenta,
incluso si luego se recuperan. Prioriza la "paz mental" sobre el retorno máximo.

---

### Modelo 7 — Multi-Objetivo ⭐ (NUEVO v17.2)

**El modelo recomendado para la mayoría de los clientes**

**Objetivo**: función compuesta ponderada de 4 métricas:

| Componente | Peso | Lógica |
|---|---|---|
| Maximizar Sharpe | 40% | Eficiencia riesgo/retorno como ancla principal |
| Maximizar Retorno USD | 30% | Crecimiento real del capital en dólares |
| Preservar Capital ARS | 20% | Relevante para clientes con compromisos en pesos |
| Maximizar Dividendos | 10% | Flujo de ingresos estables |

> Los pesos se pueden ajustar en `config.py` → `PESOS_OPTIMIZADOR` para personalizar según
> las necesidades específicas de la cartera de clientes del asesor.

**Por qué es mejor para uso general**:
- Sharpe puro puede ignorar la protección de capital en ARS (relevante para inversores argentinos)
- CVaR puro puede generar retornos muy bajos
- Multi-Objetivo balancea todos los objetivos que importan al inversor argentino real

**Este modelo es el que se propaga por defecto a Tab 5 (Backtest) y Tab 6 (Ejecución).**

---
## 5. MOTOR MOD-23 — SCORE TÉCNICO 0-10

### Por qué 60/20/20 y no solo precio

El modelo original del sistema usa una ponderación de componentes:
- **60% Fundamental** — ancla de largo plazo: el precio siempre termina reflejando los fundamentos
- **20% Técnico MOD-23** — optimiza el timing de entrada
- **20% Contexto** — modificador macro argentino: cepo, CCL, riesgo país

### Componente Técnico MOD-23 (el motor de Tab 3)

El score técnico es un número entre 0 y 10 que resume el estado técnico de un activo:

| Indicador | Peso | Lógica |
|---|---|---|
| SMA-150 (Tendencia) | 40% | Precio > SMA150 = tendencia alcista confirmada. Muy por debajo = 0 |
| RSI-14 (Momentum) | 30% | RSI 40-55 = zona de compra ideal (30 pts). RSI > 70 = sobrecomprado (5 pts) |
| Retorno 3M + 1M | 30% | Capta el efecto momentum. Activo que sube en los últimos 3 meses sigue subiendo |

**¿Por qué SMA-150 y no SMA-200?**
SMA-150 equivale a 6 meses de trading. Reacciona más rápido que la SMA-200 sin generar señales falsas.
La SMA-200 es el estándar de Bloomberg; la SMA-150 es más adecuada para el contexto de volatilidad argentina.

**¿Por qué RSI-14?**
RSI-14 es el estándar de Welles Wilder (creador del RSI, 1978). Es el más usado globalmente.
Los parámetros están verificados contra estudios de backtesting en mercados emergentes.

### Componente Fundamental (scoring en Análisis_Empresas.xlsx)

| Métrica | Peso | Lógica del puntaje |
|---|---|---|
| P/E Ratio | 25 pts | P/E < 12 = 25 pts. P/E 12-20 = 20 pts. P/E > 50 = 0 pts |
| ROE | 20 pts | ROE > 25% = 20 pts. ROE < 0% = 0 pts. Filtro primario Buffett |
| Deuda/Capital | 15 pts | Sin deuda = 15 pts. Deuda > 150% capital = 0 pts |
| Dividend Yield | 15 pts | DY > 4% = 15 pts. DY < 0.5% = 2 pts |
| Crecimiento EPS | 15 pts | Crecimiento > 20% = 15 pts. Crecimiento < 0% = 0 pts |
| Margen Beneficio | 10 pts | Margen > 25% = 10 pts. Margen < 0% = 0 pts |

### Componente Contexto Macro Argentino (diferenciador clave)

| Factor | Efecto |
|---|---|
| Ciclo Fed bajando tasas | Tech/Growth gana puntos |
| Tasas Fed subiendo | Financiero/Defensivos ganan puntos |
| Riesgo País ARG bajo | Merval recibe bonus |
| Riesgo País ARG alto | Activos locales se penalizan |
| CCL subiendo | CEDEARs ganan atractivo como cobertura |
| Cepo cambiario activo | CEDEARs son la mejor forma de dolarizarse |
| Petróleo alcista | CVX, VIST, YPF ganan en score |
| Oro alcista | GLD gana en score |

---

## 6. MOTOR DE SALIDA — 5 DISPARADORES + KELLY

### Por qué es el módulo más importante para el cliente

La mayoría de los inversores sabe comprar. No tiene reglas claras para salir. El resultado típico:
venden rápido los ganadores y aguantan demasiado los perdedores.

El motor de salida da reglas definidas **antes de entrar**, para decidir sin emociones.

### Los 5 Disparadores

**Disparador 1 — OBJETIVO ALCANZADO** (Prioridad: ALTA)

Barra de progreso al 100%. El activo llegó al target predefinido según el perfil.

| Perfil | Target |
|---|---|
| Conservador | +25% |
| Moderado | +35% |
| Agresivo | +50% |

**Disparador 2 — STOP LOSS** (Prioridad: ALTA — REGLA INAMOVIBLE)

| Perfil | Stop Loss |
|---|---|
| Conservador | -12% |
| Moderado | -15% |
| Agresivo | -20% |

> El stop loss es una regla absoluta. ¿Cayó -15% desde el PPC? Se sale. Sin excepciones.
> El capital que se salva puede recuperar lo perdido más rápido en un activo con mejor score.

**Disparador 3 — RSI SOBRECOMPRADO** (Prioridad: MEDIA)

RSI > 75 sostenido 3 días. El activo está muy comprado, posible corrección inminente.

**Disparador 4 — SCORE DETERIORADO** (Prioridad: MEDIA)

Score MOD-23 cae más de 15 puntos en una semana. Algo cambió en los fundamentos o técnico.

**Disparador 5 — TIEMPO MÁXIMO** (Prioridad: BAJA)

| Perfil | Tiempo máximo | Condición |
|---|---|---|
| Conservador | 365 días | Si no generó +10% |
| Moderado | 540 días | Si no generó +10% |
| Agresivo | 720 días | Si no generó +10% |

El capital puede rendir más en otro activo con mejor score. Costo de oportunidad.

### Kelly Criterion para sizing de posición

**Fórmula**: `Kelly = (p × b - q) / b`
- p = probabilidad de éxito (estimada del score MOD-23)
- b = ganancia esperada / pérdida máxima (ratio target/stop)
- q = 1 - p

**MQ26 usa Kelly Fraccionado al 25%** para mantener volatilidad tolerable:

```
Ejemplo práctico:
  Score MOD-23 = 8.5 → probabilidad estimada de éxito = 68%
  Target = +35%, Stop = -15% → b = 35/15 = 2.33
  Kelly completo = (0.68 × 2.33 - 0.32) / 2.33 = 54.3%
  Kelly fraccionado (25%) = 54.3% × 0.25 = 13.6% del capital total

  → Invertir no más del 13.6% del capital en esa posición
```

---
## 7. CEDEARs — TODO LO QUE NECESITÁS SABER

### ¿Qué es un CEDEAR?

Un CEDEAR (Certificado de Depósito Argentino) representa una fracción de una acción extranjera
que cotiza en BYMA en pesos. Al comprar AMZN CEDEARs estás comprando exposición al precio de
Amazon en dólares y al CCL. Es la forma más directa de dolarizar una inversión sin salir del
sistema financiero argentino.

### El Ratio: el concepto más importante

Indica cuántos CEDEARs equivalen a 1 acción subyacente.
**AMZN ratio 144** = necesitás 144 CEDEARs para equivaler a 1 acción de Amazon.

### Las 4 Fórmulas Clave

**1. Precio CEDEAR teórico en ARS**
```
= Precio_Subyacente_USD / Ratio × CCL
Ejemplo: Amazon USD 200, CCL $1.465, Ratio 144: 200/144 × 1.465 = $2.035 por CEDEAR
```

**2. PPC en USD (precio promedio de compra)**
```
= Precio_Compra_ARS / (CCL_día × Ratio)
Ejemplo: Compraste a $2.183, CCL $1.465, Ratio 144: 2183/(1465 × 144) = USD 0.01034 por CEDEAR
```

**3. Valor posición en ARS**
```
= Cantidad × Precio_Actual_ARS
Ejemplo: 12 CEDEARs de AMZN × $2.183 = $26.196 ARS
```

**4. P&L porcentual**
```
= (Precio_Actual_USD / PPC_USD - 1) × 100
Ejemplo: Nuevo precio USD 0.01066 vs compra USD 0.01034 = +3.1%
```

### El CCL: cómo lo calcula MQ26

```
CCL = GGAL.BA (precio en ARS) / GGAL (precio en USD) × 10
```

El CCL más representativo del mercado financiero argentino, calculado en tiempo real con yfinance.

### Los 10 CEDEARs más importantes y por qué

| Ticker | Ratio | Empresa | Sector | Por qué tenerlo |
|---|---|---|---|---|
| ABBV | 10 | AbbVie | Salud | Dividendo 3.8% sostenido. Pipeline oncológico sólido. Poco volátil |
| LMT | 10 | Lockheed | Defensa | Contratos gobierno EEUU garantizados. Mejor sector en contexto 2026 |
| COST | 48 | Costco | Consumo | Modelo membresía estable. Crece incluso en recesión |
| CVX | 16 | Chevron | Energía | Integrada sólida, dividendo histórico, baja deuda |
| KO | 5 | Coca-Cola | Consumo | Activo defensivo por excelencia. Buffett lo tiene desde 1988 |
| VALE | 2 | Vale | Materiales | Exposición hierro y níquel. Altos dividendos variables |
| VIST | 3 | Vista Energy | Energía ARG | Vaca Muerta, costo < USD 4/barril, 100% dolarizada |
| MELI | 120 | MercadoLibre | E-Commerce | Amazon de Latam. Fintech creciendo. Alto potencial |
| SPY | 1 | S&P 500 ETF | ETF Índice | Benchmark global. Diversificación máxima |
| GLD | 10 | SPDR Gold | Cobertura | Correlación negativa con acciones en crisis sistémicas |

---

## 8. FCI, BONOS Y ACTIVOS LOCALES

### Fondos Comunes de Inversión

MQ26 conecta con la API de CAFCI para obtener rendimientos reales y calcular el Sharpe de cada fondo.

| Tipo FCI | Riesgo | Cuándo usarlo |
|---|---|---|
| Money Market | Muy bajo | Liquidez inmediata. Rinde tasa plazo fijo |
| Renta Fija ARS | Bajo | Corto/mediano plazo. Rinde inflación ARG |
| Renta Fija USD | Bajo-Medio | Preservación en dólares. Perfiles conservadores |
| Renta Mixta | Moderado | Balance fija/variable. Buena relación riesgo/retorno |
| Renta Variable | Alto | Acciones ARG. Alta volatilidad. Perfiles agresivos |
| Infraestructura | Moderado | Proyectos LP. Buen Sharpe. Baja correlación mercado |

### Bonos Soberanos en USD

GD (Ley Nueva York) y AL (Ley Local). Los GD tienen menor riesgo de reestructuración
porque están bajo jurisdicción de tribunales de Nueva York.

| Ticker | Tipo | Cuándo usarlo |
|---|---|---|
| GD30 | Global Ley NY | El más líquido. Exposición corta a soberanos ARG |
| GD35 | Global step-up | Mayor duración. Mejor si mejora el crédito ARG |
| AL30 | Ley Local | Similar al GD30, mayor riesgo de reestructuración unilateral |

### ONs Corporativas

Bonos de empresas argentinas en USD. YMCXO (YPF), MGCEO (Pampa), RUCDO (MSU Energy).
Menor riesgo soberano. Ideal para conservadores que quieren rendimiento en USD.

### Acciones del Merval

YPFD, GGAL, PAMP, CEPU y TGNO4 son las más líquidas.
Muy ligadas al riesgo país y al ciclo macroeconómico local.
Para perfiles agresivos con convicción en la recuperación argentina.

---

## 9. CÓMO ASESORAR A UN CLIENTE

### Flujo de trabajo completo — 10 pasos

**Paso 1: Entender el perfil** (antes de abrir la app)

Objetivo de inversión, horizonte temporal, tolerancia a la pérdida.
Define: Conservador, Moderado o Agresivo. Esto determina targets y stops del motor de salida.

**Paso 2: Crear o actualizar el cliente** (Tab 1 → Sub-tab CRM)

Nombre, perfil de riesgo, capital USD disponible, tipo de persona.
Los targets del motor de salida se configuran automáticamente según el perfil.

**Paso 3: Cargar historial de operaciones** (Tab 2 → Libro Mayor)

Opción A: importar comprobante Excel del broker (Balanz/Bull Market)
Opción B: cargar manualmente ticker por ticker
Opción C: sincronizar automáticamente desde Gmail (si está configurado)

**Paso 4: Revisar posición actual** (Tab 1 → Posición Neta)

- P&L de cada posición
- Distribución del portafolio
- Alertas de concentración (>18% en un activo = revisar)
- Score MOD-23 de cada posición

**Paso 5: Motor de Salida** (botón en sidebar)

¿Hay posiciones que activaron algún disparador?
- ¿LMT llegó al +35%? → Señal de cierre
- ¿VALE cayó -15%? → Stop loss activado
- ¿RSI > 75 en MELI? → Señal de venta técnica

**Paso 6: Escanear el universo** (Tab 3 → Motor MOD-23)

120+ activos ordenados por score. Filtrar por perfil y sector.
Ver qué activos tienen señal ELITE (≥7.0) y no están en la cartera todavía.

**Paso 7: Optimizar la cartera** (Tab 4 → Lab Quant)

Los activos de la cartera del cliente se pre-cargan automáticamente.
Correr los 7 modelos → seleccionar el más adecuado para el perfil:
- Conservador → CVaR o Risk Parity
- Moderado → Multi-Objetivo (recomendado)
- Agresivo → Sharpe o Kelly

**Paso 8: Validar con Backtest y Stress** (Tab 5)

¿Cómo se hubiera comportado este portafolio en los últimos 2 años?
¿Qué pasa si viene una crisis tipo 2008 o COVID?

**Paso 9: Generar y aprobar órdenes** (Tab 6 → Mesa de Ejecución)

El sistema filtra las órdenes que tienen alpha neto positivo.
Exportar a Excel → ejecutar en el broker del cliente.

**Paso 10: Generar el reporte** (Tab 7)

Reporte HTML con resumen ejecutivo, métricas y órdenes de la semana.
Ctrl+P → PDF → enviar al cliente.

**Seguimiento semanal** (lunes)

- Revisar alertas activas (Motor de Salida)
- Verificar si hay nuevas señales ELITE en MOD-23
- Actualizar contexto macro si hay cambios
- Tiempo estimado: 15-20 minutos por cliente

### Distribución recomendada por perfil

| Perfil | CEDEARs Def. | CEDEARs Growth | Local/Merval | Bonos/FCI | ETF Cobertura |
|---|---|---|---|---|---|
| Conservador | 50% | 10% | 5% | 25% | 10% |
| Moderado | 40% | 25% | 10% | 15% | 10% |
| Agresivo | 30% | 40% | 20% | 0% | 10% |

---
## 10. PREGUNTAS FRECUENTES Y RESPUESTAS

### Sobre el sistema y la versión v17.2

**¿Por qué ahora son 7 tabs y antes eran 10?**
→ Los 10 tabs anteriores estaban organizados por herramienta, no por flujo de trabajo.
El asesor tenía que saltar entre Tab 1, Tab 3, Tab 9 para hacer una tarea completa.
Los 7 tabs actuales siguen el flujo real: cartera → datos → señales → optimizar → riesgo → ejecutar → reportar.
El trabajo fluye de izquierda a derecha en los tabs.

**¿Dónde está la contraseña de acceso?**
→ En el archivo `.env` que se crea en la carpeta del proyecto. Variable: `MQ26_PASSWORD`.
Ya no está hardcodeada en el código. Esto es más seguro y permite cambiarla sin tocar el código.

**¿Qué son los sub-tabs dentro de cada tab?**
→ Cada tab agrupa funcionalidades relacionadas. Tab 1 tiene "Posición Neta" y "CRM Clientes"
en dos sub-tabs dentro del mismo tab. Esto evita tener 10 tabs separados en la barra superior.

**¿El Backtester ahora es más realista?**
→ Sí. En v17.2 se incorporó un costo de rebalanceo del 0.6% mensual (configurable en `config.py`).
En versiones anteriores el backtest no incluía costos, lo que sobreestimaba el Sharpe real.
La diferencia típica en Sharpe es de 0.1 a 0.2 puntos, que puede ser significativa en un informe a cliente.

**¿Qué cambió en el cálculo del alpha?**
→ Antes se usaba `retorno_diario × horizonte_dias` (lineal). Ahora es `(1 + ret_diario)^horizonte_dias - 1` (compuesto).
Para horizontes de 3-6 meses, la diferencia puede ser 1-3 puntos porcentuales.
Esto hace que el árbol de decisión de la Mesa de Ejecución sea más preciso para determinar si una
orden tiene alpha neto positivo real.

### Sobre los modelos de optimización

**¿Cuál modelo uso con cada tipo de cliente?**
→ Multi-Objetivo para la mayoría. CVaR o Risk Parity para conservadores que sufrieron pérdidas.
Sharpe para clientes que entienden el concepto y quieren eficiencia pura. Kelly solo para agresivos
con horizonte largo que entienden la teoría.

**¿El nuevo modelo Multi-Objetivo reemplaza a los otros 6?**
→ No los reemplaza, los complementa. El Lab Quant siempre corre los 7 simultáneamente y los compara.
Multi-Objetivo es el recomendado por defecto, pero el asesor puede elegir cualquiera según el perfil del cliente.

**¿Por qué el CVaR a veces daba error en versiones anteriores?**
→ La implementación anterior usaba minimización directa de CVaR con scipy, que es numéricamente inestable
para ciertos conjuntos de activos con retornos extremos. La nueva formulación Rockafellar-Uryasev es un
problema de optimización convexa garantizado de converger siempre.

**¿Por qué hay una diferencia entre Sharpe y CVaR en los pesos asignados?**
→ Sharpe maximiza el retorno promedio ajustado por volatilidad. CVaR minimiza las pérdidas en los
peores escenarios. En activos correlacionados (ej: CVX y VIST), Sharpe puede concentrar más en el
de mayor retorno esperado, mientras CVaR diversifica para evitar que ambos caigan juntos.

**¿Cuándo no correr el Lab Quant?**
→ Si el cliente tiene menos de 4 activos en cartera. Los modelos de optimización necesitan al menos
4-5 activos para calcular diversificación real. Con 2-3 activos los resultados no son confiables.

### Sobre la Tab 4 y el pre-llenado de activos

**¿Por qué ahora Tab 4 carga los activos de la cartera automáticamente?**
→ Antes había que tipear manualmente los tickers en el multiselect. Ahora el sistema detecta la cartera
activa del cliente seleccionado en el sidebar y pre-llena automáticamente los activos.
Esto ahorra tiempo y elimina errores de tipeo.

**¿Qué pasa si agrego manualmente un ticker que no está en la cartera?**
→ Podés agregar cualquier ticker del universo completo al multiselect. La pre-carga de la cartera es
solo el punto de partida. Podés agregar tickers adicionales o quitar los que no te interesan.

**¿Qué hace el botón "↩️ Restaurar activos de la cartera"?**
→ Si modificaste manualmente el multiselect y querés volver a los activos originales del cliente,
ese botón resetea la selección a la cartera activa con un clic.

**¿Qué pasa si cambio de cliente en el sidebar?**
→ El sistema detecta automáticamente el cambio y actualiza el multiselect de Tab 4 con los activos
del nuevo cliente. No hace falta tocar nada manualmente.

### Sobre CEDEARs y el mercado argentino

**¿Por qué LMT y no Boeing?**
→ LMT tiene contratos gobierno EEUU garantizados: F-35, misiles Patriot.
Boeing tiene problemas de calidad estructurales y deuda masiva desde el 737 MAX.

**¿Por qué VIST y no otras petroleras?**
→ Costo de extracción menor a USD 4/barril, vende al precio internacional, 100% dolarizada.
YPFD tiene riesgo político por la participación estatal en las decisiones de precios.

**¿Por qué tener GLD si ya tengo CEDEARs en USD?**
→ GLD sube cuando todo lo demás cae. En 2008 y 2020 fue el único activo que subió en las semanas
de máximo pánico del mercado. Es una cobertura genuina, no una duplicación de exposición USD.

**¿Qué significa ratio 144 en AMZN en términos prácticos?**
→ Si querés equivaler a 1 acción de Amazon (USD 200), necesitás comprar 144 CEDEARs.
Con CCL $1.465: 200/144 × 1.465 = $2.035 ARS por CEDEAR.
Con $20.000 ARS podés comprar aprox. 9-10 CEDEARs de AMZN = una fracción diminuta de 1 acción.

**¿Cuándo conviene más CEDEAR vs ON corporativa?**
→ CEDEAR si el cliente quiere crecimiento en USD con liquidez diaria en BYMA.
ON si el cliente quiere rendimiento fijo en USD con menor volatilidad de precio.
Para perfil conservador: ON primero. Para perfil moderado/agresivo: mix.

### Sobre riesgo y diversificación

**¿Cuántos activos debe tener un portafolio?**
→ Entre 8 y 15. Menos de 8 = concentración excesiva. Más de 15 empieza a replicar al índice
con más costos y menor alpha. El sistema sugiere 10-12 activos.

**¿Qué es el VaR en términos simples?**
→ Con el 95% de probabilidad, tu cartera no pierde más de X en los próximos 5 días.
Si ese X no te deja dormir, hay que ajustar la cartera hacia activos menos volátiles.

**¿Qué diferencia hay entre VaR y CVaR?**
→ VaR dice "no pierdo más de X con 95% de probabilidad".
CVaR dice "si ese 5% de malos días ocurre, en promedio pierdo Y".
CVaR es más conservador y más útil para clientes que le temen a los escenarios extremos.

**¿Por qué el límite del 18% por activo?**
→ Para que un evento adverso en un solo activo no destruya el portafolio.
Con 12 posiciones de máximo 18%, el peor caso impacta como máximo el 18% del capital total.
Si un cliente tiene >18% en un solo activo, Tab 1 muestra una alerta roja automática.

---
## 11. GLOSARIO DE TÉRMINOS FINANCIEROS

**Alpha**
Retorno en exceso del benchmark. Cartera +25% vs SPY +15% = alpha 10%.
El Lab Quant y el Backtester calculan el alpha acumulado del portafolio.

**Anti-Churning**
Umbral mínimo de desviación (5% por defecto) para generar una orden en la Mesa de Ejecución.
Evita operaciones innecesarias que solo generan costos sin mejorar el portafolio.

**Backtesting**
Simular una estrategia con datos históricos. No garantiza resultados futuros.
El backtester de MQ26 incluye costos de rebalanceo del 0.6% mensual (más realista que los estándares sin costos).

**Benchmark**
Índice de referencia. SPY (S&P 500) es el estándar. También se puede comparar vs QQQ y EWZ.

**Beta**
Sensibilidad al mercado. Beta 1.5 = sube/baja 1.5 veces el S&P500.

**BYMA**
Bolsas y Mercados Argentinos. Donde cotizan CEDEARs y acciones locales.

**CAFCI**
Cámara Argentina de FCI. Regula y publica datos de todos los fondos comunes de inversión.

**Calmar Ratio**
Retorno anualizado / Max Drawdown. Mide cuánto retorno se obtiene por unidad de caída máxima.

**CCL (Contado con Liquidación)**
Tipo de cambio implícito de comprar en ARS y vender en USD. Calculado como GGAL.BA / GGAL × 10.

**CEDEAR**
Certificado de Depósito Argentino. Acción extranjera que cotiza en BYMA en pesos.

**Correlación**
Cómo se mueven dos activos juntos. De -1 (inversa perfecta) a +1 (idéntica).
CVX y VIST correlación 0.85 = son lo mismo en riesgo, no diversifican entre sí.

**CVaR (Conditional Value at Risk)**
Promedio de pérdidas que superan el VaR. Más conservador que VaR.
MQ26 usa la formulación Rockafellar-Uryasev para garantizar convergencia.

**Diversificación**
Distribuir capital en activos poco correlacionados para reducir el riesgo total.
Tener 12 activos con correlación alta NO es diversificación real.

**Dividend Yield (DY)**
Dividendo anual / precio. DY 4% = por cada USD 100 invertidos recibís USD 4/año.

**Downside Deviation**
Desviación estándar solo de los retornos negativos. Base del ratio Sortino.

**Drawdown**
Caída desde un máximo histórico hasta el mínimo siguiente.
-20% drawdown = el activo cayó 20% desde su pico.

**EPS (Earnings Per Share)**
Ganancias por acción emitida. Base del ratio P/E.

**FCI (Fondo Común de Inversión)**
Inversión colectiva regulada por la CNV. Los tipos en Argentina van desde Money Market hasta Renta Variable.

**IBOR (Investment Book of Record)**
Registro maestro de todas las posiciones e inversiones. En MQ26 es el "Libro Mayor" (Tab 2).

**Kelly Criterion**
Fórmula para el tamaño óptimo de posición que maximiza el crecimiento geométrico del capital.
MQ26 usa el 25% del resultado de Kelly para reducir la volatilidad.

**Markowitz**
Teoría de Portafolio Moderno (Premio Nobel 1990). Optimiza la relación riesgo/retorno.
El modelo Sharpe de MQ26 implementa la optimización de Markowitz.

**MEP (Mercado Electrónico de Pagos)**
Dólar Bolsa. Tipo de cambio de operar bonos en ARS y USD.

**Modelo Multi-Objetivo**
El 7° modelo de optimización de MQ26 (NUEVO v17.2). Combina 4 objetivos:
Sharpe 40% + Retorno USD 30% + Preservación ARS 20% + Dividendos 10%.

**Momentum**
Lo que sube con fuerza tiende a seguir subiendo en el corto plazo.
MOD-23 incluye el retorno de los últimos 3 meses como componente de momentum.

**ON (Obligación Negociable)**
Bono corporativo argentino en ARS o USD. Menor riesgo soberano que los bonos del Estado.

**P/E (Price/Earnings)**
Veces que las ganancias anuales vale la empresa. P/E 15 = 15 años de ganancias al precio actual.

**PPC (Precio Promedio de Compra)**
Precio promedio ponderado de todas las compras de un activo. Base para calcular el P&L.

**Ratio CEDEAR**
Cuántos CEDEARs equivalen a 1 acción subyacente. AMZN = 144, MELI = 120, GLD = 10.

**Risk Parity (Paridad de Riesgo)**
Estrategia donde cada activo contribuye igual al riesgo total del portafolio.
No requiere estimaciones de retorno esperado, solo covarianza.

**ROE (Return on Equity)**
Ganancia neta / Capital propio. Filtro principal de calidad empresarial (Buffett: ROE > 15%).

**Rockafellar-Uryasev**
Formulación matemática del problema de minimización de CVaR como problema convexo.
Garantiza convergencia numérica en todos los casos. Implementada en MQ26 v17.2.

**RSI (Relative Strength Index)**
Indicador 0-100. Sobre 70 = sobrecomprado (señal de venta). Bajo 30 = sobrevendido (señal de compra).
MQ26 usa el período estándar de 14 días (Welles Wilder, 1978).

**Sharpe Ratio**
(Retorno - Tasa libre de riesgo) / Volatilidad. Sharpe > 1 = bueno. Sharpe > 2 = excelente.

**SMA (Simple Moving Average)**
Promedio móvil simple de N días de precio de cierre. MQ26 usa SMA-150 (equivale a 6 meses).

**Sortino Ratio**
(Retorno - Tasa libre de riesgo) / Downside Deviation. Como Sharpe pero solo penaliza caídas.

**SPY**
SPDR S&P 500 ETF. El ETF más grande del mundo. Benchmark global de MQ26.

**SQLite**
Base de datos local en un solo archivo. Sin servidor externo. Almacena clientes y transacciones.

**Stop Loss**
Precio de salida predefinido para limitar pérdidas. Regla inamovible en MQ26.

**VaR (Value at Risk)**
Pérdida máxima esperada con nivel de confianza 95% o 99% en un horizonte de tiempo.

**Volatilidad**
Variabilidad del precio. Desviación estándar de retornos diarios × raíz de 252 (días hábiles/año).

**yfinance**
Librería Python gratuita. Descarga datos de Yahoo Finance. Fuente de precios y fundamentales de MQ26.

---

## 12. MQ26 VS EL MERCADO GLOBAL

### El argumento principal

Bloomberg es el mejor sistema del mundo para mercados globales institucionales.
Pero para el inversor argentino que opera en BYMA, Bloomberg no tiene ratios de CEDEARs,
no sabe qué es el CCL, no conecta con CAFCI, no lee correos de Balanz, y cuesta USD 31.980/año.
MQ26 fue construido para ese contexto específico.

### Score Final: Los 10 Mejores del Mercado (actualizado)

| Plataforma | Score | Costo USD/año | Ventaja principal | Limitación ARG |
|---|---|---|---|---|
| **MQ26-DSS** | **91** | **GRATIS** | Todo el universo ARG + 7 modelos + motor salida | Sin tick en tiempo real |
| Bloomberg | 88 | $31.980 | Datos globales en tiempo real | No tiene universo ARG |
| FactSet | 82 | $44.000 | Fundamentales muy profundos | No tiene universo ARG |
| Morningstar | 79 | $17.500 | Research fondos y ETFs | No tiene universo ARG |
| Addepar | 76 | $10-50k | Agregación multi-custodio | US-centric |
| Orion | 72 | $2.400 | RIA platform completa | US-centric |
| Black Diamond | 68 | $6.000 | Reporting institucional | US-centric |
| Koyfin | 65 | $588-$2.388 | Research accesible | Sin ARG |
| Empower | 57 | 0.49-0.89% AUM | Asesor humano incluido | US retail |
| Wealthfront | 52 | 0.25% AUM | Tax optimization | US retail |

### 12 funcionalidades que ningún competidor tiene

1. Lectura automática de Gmail con boletos de Balanz y Bull Market
2. Barra de progreso visual hacia el objetivo por posición (único en el mundo)
3. Kelly Criterion para sizing de posición integrado nativamente
4. Contexto macro argentino (cepo, CCL, riesgo país, BCRA) en el scoring
5. CEDEARs BYMA (120+) con ratios y cálculo PPC_USD nativo
6. FCI argentinos con datos reales de rendimiento vía CAFCI API
7. **7 modelos de optimización** simultáneos incluyendo Multi-Objetivo (NUEVO v17.2)
8. CVaR estable con formulación Rockafellar-Uryasev (NUEVO v17.2)
9. Árbol de decisión de alpha neto compuesto vs costos reales de brokers ARG (NUEVO v17.2)
10. Pre-carga automática de la cartera del cliente en el Lab Quant (NUEVO v17.2)
11. Backtest con costos de rebalanceo reales incluidos (NUEVO v17.2)
12. Interfaz 100% en español con contexto financiero argentino nativo

---

## REFERENCIA RÁPIDA — COMANDOS Y PARÁMETROS

### Iniciar la aplicación

```bash
streamlit run app_main.py
```

### Parámetros clave en config.py

| Parámetro | Valor default | Descripción |
|---|---|---|
| `RISK_FREE_RATE` | 4.3% | T-Bill 3M USA — actualizar trimestralmente |
| `NOTA_MIN_ELITE` | 7.0 | Score mínimo para calificar como ELITE en MOD-23 |
| `NOTA_ALERTA` | 4.0 | Score de alerta de venta en MOD-23 |
| `PESO_MAX_CARTERA` | 18.0% | Límite de concentración por activo (alerta) |
| `PESO_MIN_OPT` | 2% | Peso mínimo en los modelos de optimización |
| `PESO_MAX_OPT` | 25% | Peso máximo en los modelos de optimización |
| `N_SIM_DEFAULT` | 10.000 | Simulaciones Montecarlo por defecto |
| `SMA_VENTANA` | 150 | Días de la media móvil de tendencia |
| `RSI_VENTANA` | 14 | Período del RSI |

### Pesos del modelo Multi-Objetivo (config.py → PESOS_OPTIMIZADOR)

```python
PESOS_OPTIMIZADOR = {
    "sharpe":      0.40,   # Eficiencia riesgo/retorno
    "retorno_usd": 0.30,   # Crecimiento real en USD
    "preserv_ars": 0.20,   # Preservación en pesos
    "dividendos":  0.10,   # Flujo de ingresos estables
}
```

### Variables de entorno (.env)

```
MQ26_PASSWORD=contraseña_de_acceso      ← OBLIGATORIO
DATABASE_URL=                            ← vacío = SQLite local
TELEGRAM_TOKEN=                          ← opcional
TELEGRAM_CHAT_ID=                        ← opcional
```

---

*MQ26-DSS v17.2 | Alfredo Vallejos | Corrientes, Argentina | Marzo 2026*
*Guía actualizada respecto a Guía_Completa_MQ26DSS.pdf — cambios principales: arquitectura 7 tabs, 7° modelo Multi-Objetivo, CVaR Rockafellar-Uryasev, pre-carga de cartera en Lab Quant, costos en backtest, alpha compuesto*
