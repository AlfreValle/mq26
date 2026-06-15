# Prueba de flujo Inversor (staging) — Alfredo / stakeholders

**Objetivo:** validar el camino **cartera vacía → Empezar de cero → capital en ARS → cartera sugerida** (motor de recomendación según perfil), en la **URL de staging** que provea Implementación.

**Qué no es:** la sugerencia **no** es promesa de resultado ni sustituto del asesor; es **simulación** con reglas del producto (perfil, universo, precios disponibles).

---

## 1. Lo que debe preparar el equipo (antes de tu prueba)

| Entregable | Quién | Notas |
|------------|--------|--------|
| **URL** `https://…` | Implementación | Misma build que consideran candidata a demo. |
| **Usuario + contraseña** rol **Inversor** | Implementación | No publicar en repos abiertos. |
| **Cliente con cartera sin activos** (o instructivo para crear uno) | Implementación / Admin | Sin posiciones debe aparecer la **bienvenida** con *Empezar de cero* y *Ya tengo activos* (`ui/tab_inversor.py`). Si el demo trae cartera cargada, crear cliente nuevo vacío o vaciar según runbook interno. |
| **Versión** (tag, commit o fecha de deploy) | Implementación | Para cruzar tu feedback. |

Referencia de demo local: [`GUIA_DEMO_10_USUARIOS.md`](../GUIA_DEMO_10_USUARIOS.md) (perfil 10 — primera vez; contraseñas ejemplo en `.env.demo` solo para entornos demo).

---

## 2. Planilla de devolución

1. Descargá o abrí el archivo **`CHECKLIST_PRUEBA_INVERSOR_ALFREDO.csv`** (en esta misma carpeta `docs/product/`).
2. **Excel:** Datos → Obtener datos → Desde archivo / Texto, delimitador **coma**, UTF-8.  
3. **Google Sheets:** Archivo → Importar → Subir → separador **coma**.
4. Completá la columna **`ok_si_no_na`** con SI, NO o NA, y **`notas_alfredo`** con observaciones.

---

## 3. Secuencia mínima recomendada (clic a clic)

1. Abrís la **URL** en el navegador.  
2. Iniciás sesión con el **usuario Inversor** que te pasaron.  
3. Si aparece elección de cliente/perfil, elegís el que el equipo dijo **sin cartera**.  
4. En **Mi cartera**, si ves la bienvenida: elegís el camino **Empezar de cero** → **Armar mi primera cartera**.  
5. Ingresás un **monto en ARS** (el que quieras dentro del rango permitido).  
6. Clic en **Calcular cartera óptima para perfil …**.  
7. Leés el resultado (lista sugerida o mensaje de *no hay compras posibles* / alerta de mercado).  
8. Completás la **planilla** fila por fila.

---

## 4. Después de la prueba

Enviá el CSV completado (o export de la planilla) a **Producto / Implementación** con el asunto sugerido: `Feedback Inversor staging — [fecha] — [versión]`.
