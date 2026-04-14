# Guía de demo — 10 usuarios beta

## Antes de la demo (30 minutos antes)

```bash
# 1. Activar modo demo
cp .env.demo .env
# Windows (cmd): copy .env.demo .env

# 2. Generar BD demo (si no existe o querés regenerarla)
python scripts/generate_demo_data.py

# 3. Verificar
MQ26_PASSWORD=test_password_123 pytest tests/ -q --no-cov --tb=no

# 4. Levantar la app
streamlit run run_mq26.py
# URL: http://localhost:8501
```

## Usuarios y contraseñas para la demo

Los valores exactos están en **`.env.demo`** del repo (copiarlos a `.env` antes de la sesión). Ejemplo típico:

| Rol | Usuario | Contraseña demo | Lo que ve |
|-----|---------|-----------------|-----------|
| Admin completo | `admin1452` | `demo.2026` | Todo el sistema + Mercado + Admin |
| Estudio | `estudio` | `visor/2026` | Torre de clientes + Mercado + Cartera |
| Inversor | `inversor` | `inversor+2026` | Solo su cartera (suite Mi Cartera) |

## Flujo según perfil de usuario beta

### Perfil 1–2: Jóvenes (Santi, Reto, Pablo)

1. Login como `inversor` → rol inversor
2. Si el demo tiene un solo cliente asignado al inversor, entra directo; si no, elegir el perfil y **Ingresar →**
3. Mostrar el tab Resumen → sus posiciones
4. Tab Plan → proyección de ahorro mensual
5. "¿Qué compro con $100.000?" → resultado del motor

### Perfil 3 (Andrea — inversora con cartera existente)

1. Login como `admin` → seleccionar "María Fernández | Ahorro Familiar"
2. Tab Salud → semáforo + observaciones
3. Tab Plan → torta ideal vs actual
4. Generar informe → descargar PDF/HTML

### Perfil 4 (Admin / colega profesional)

1. Login como `admin1452` → ver el listado de los 10 clientes demo
2. Tab **Mercado** → Renta Variable: ver señales MOD-23 de CEDEARs y Acciones
3. Tab Mercado → Renta Fija: ver TIR de ONs y tasa mensual de Letras
4. Tab Mercado → Cartera Óptima: ver sugerencia según perfil Moderado
5. Seleccionar un cliente → Tab Cartera → posición actual
6. Tab Informe → generar + descargar HTML

### Perfil 6 (Jubilado — conservador)

1. Login como `admin` → seleccionar "Jorge Herrera | Conservador Total"
2. Semáforo (esperado: favorable si mix defensivo)
3. Tab Salud → % defensivo
4. Tab Rebalanceo → targets y stops

### Perfil 9 (Contador / Estudio)

1. Login como `estudio`
2. Ver el dashboard con **10 clientes** demo, semáforos y scores
3. Clic en "📊 Plan" de un cliente
4. Mostrar el plan de ese cliente sin salir del dashboard
5. Generar informe del cliente → enviar por email

### Perfil 10 (Sin experiencia — primera vez)

1. Login como `inversor`
2. Crear cliente nuevo: nombre propio, perfil Moderado, horizonte 3 años
3. Pantalla de bienvenida → "Empezar de cero" → ingresar $500.000
4. El motor muestra qué comprar → explicar cada activo
5. Indicar que la operación concreta puede hacerse en el broker (p. ej. Balanz / IOL)

## Las 5 frases que cierran cada demo

1. "El motor analizó cientos de activos y corrió el scoring completo para darte recomendaciones concretas."
2. "Lo que ves acá es el mismo tipo de análisis que un profesional hace en horas, condensado en minutos."
3. "No es una opinión suelta: es un marco con fundamentos, técnico y contexto macro argentino."
4. "Para el inversor individual el coste es bajo; para el estudio, menos que un recurso part-time."
5. "La herramienta trabaja en español y en tiempo real sobre CEDEARs y renta fija local."

## Después de la demo

- Compartir el link de despliegue (p. ej. Railway) cuando esté publicado
- Pedir feedback en un formulario acordado con el equipo comercial
- Ofrecer período de prueba para quienes quieran datos reales
