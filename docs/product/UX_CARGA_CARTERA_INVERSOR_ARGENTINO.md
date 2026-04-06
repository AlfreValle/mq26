# Carga de cartera — cómo piensa el inversor argentino (producto)

Documento de **producto y UX**, no de implementación. Complementa Sprint 5 (motores) y orienta Sprint 6 (Experiencia de carga + feedback inmediato al diagnóstico).

---

## Desde la persona, no la tecnología

En Balanz o IOL el usuario no piensa en “activos financieros” sino en frases concretas: acciones de Coca-Cola, bono de YPF, GLD hace dos años, ON de Telecom. La carga debe hablar en **ese idioma**.

---

## Cuatro tipos de carga

1. **Importar desde el broker** — export Excel/CSV; menor fricción; `broker_importer.py` como base; selectores visuales Balanz / IOL / BMB + upload.
2. **CEDEARs / acciones manual** — buscador por nombre o ticker; cantidad; precio (USD para CEDEARs como en el broker); fecha; CCL del día de compra para llevar a ARS internamente.
3. **ONs / bonos soberanos** — VN, paridad %, fecha; preview monto pagado, TIR al precio; mismos patrones que el comprobante; validación suave (90–115% típico).
4. **Letras** — VN a cobrar, precio % del nominal, fecha; preview ganancia implícita; precio puede prellenarse desde tabla de referencia.

---

## Onboarding en tres caminos

- Importar desde broker  
- Cargar uno por uno  
- Empezar de cero con sugerencia (motor de recomendación + capital disponible → cartera ideal accionable)

No excluyentes.

---

## Principios de UX

1. Una pregunta a la vez.  
2. El sistema adivina (fecha hoy, CCL, nombres, precios de letras).  
3. Lenguaje del comprobante (VN + % paridad).  
4. Confirmación visual: impacto en semáforo / % defensivo tras cada carga.  
5. Errores: advertir, no bloquear punitivamente.  
6. Cargas sucesivas = mismo flujo que la primera.

---

## Vista cartera (propuesta)

Resumen humano: patrimonio **ARS y USD**, rendimiento, estado tipo semáforo, barra defensivo/variable, filas por activo con nombre legible y %, acciones (agregar / importar / precios).

---

## Casos especiales (producto)

- Misma ON, varias compras: PPC consolidado + historial de lotes.  
- Efectivo en cuenta: ARS y USD por separado → alimenta recomendación.  
- Ventas: cantidad negativa o flujo “Registrar venta” desde posición.  
- Cupón ON: cobro registrado (ticker, monto, fecha).

---

## Secuencia de sprints

- **Sprint 5:** motores de diagnóstico y recomendación estables y alimentados por `df_ag` + métricas coherentes.  
- **Sprint 6:** pantallas de carga al estilo de este documento + **feedback inmediato** (semáforo, defensivo) después de cada operación.

---

## ARS, USD y CCL (reglas acordadas para diseño)

**Mostrar siempre** montos relevantes en **ARS y en USD** cuando tenga sentido (patrimonio, P&L, recomendaciones).

- **Al registrar una compra/venta:** guardar (o reconstruir) el **tipo de cambio CCL del día de la operación** para fijar el vínculo ARS ↔ USD de **esa** transacción (`PPC_USD`, `PPC_ARS`, etc.).  
- **Al mostrar valor marcado al mercado hoy:** usar **precios actuales** y el **CCL actual** para la conversión ARS de activos cotizados en USD.  
- **Comparaciones de rendimiento y costos (“cómo me fue vs cuánto puse”):** en **USD de adquisición** — es decir, usando la base en USD derivada del comprobante (PPC en USD por línea), para no mezclar dos efectos (activo vs devaluación) en el mensaje de performance que el inversor usa para decidir.

*Detalle a afilar con negocio:* si en algún informe regulatorio o comercial se requiere además “P&L nominal en ARS histórico”, puede mostrarse como **línea secundaria**, explícitamente etiquetada, sin reemplazar la comparación en USD de adquisición.

---

## Momento “producto indispensable”

Cuando después de cargar la última compra el semáforo pasa de **rojo a amarillo** (o mejora el % defensivo) de forma visible — ese es el hook emocional del valor entregado.
