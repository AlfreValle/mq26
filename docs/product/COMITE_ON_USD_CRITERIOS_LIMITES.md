# Comité de expertos — ON USD (Hard Dollar): criterios, límites y convenciones MQ26

**Objetivo:** alinear lenguaje de producto, motor y UI con la realidad de negociación en Argentina: **referencia técnica en USD (nominal / paridad / TIR)** y **comercialización mayormente en pesos** (cotización operativa en BCBA).

---

## 1. Definiciones obligatorias (sin ambigüedad)

### 1.1 Valor nominal (VN)

- Es la **base contractual** del instrumento (USD), sobre la que se calculan cupones y, según prospecto, amortización.
- En MQ26, la **paridad %** se interpreta como **porcentaje del nominal** (100 % = al par).

### 1.2 Valor de mercado (precio)

- Es lo que **se paga hoy** por el instrumento, expresado típicamente como:
  - **Paridad %** (sobre nominal), y/o
  - **ARS por cada 100 nominales USD** en pantalla de mercado local (BYMA / plataforma).
- **No** debe confundirse con “precio de acción” ni con un monto suelto en pesos sin aclarar unidad (por 100 VN, clean/dirty, plazo).

### 1.3 Lámina mínima

- Cantidad mínima negociable en **nominales USD** (múltiplos). Varía por serie y prospecto.
- En catálogo MQ26: `lamina_min` (VN USD). No sustituye folleto oficial.

### 1.4 Amortización y nominal residual

- Si el bono amortiza principal antes del vencimiento, el **nominal vivo** baja; el precio de pantalla debe entenderse sobre ese **saldo**, no sobre el nominal original.
- **Límite MQ26 (hoy):** el catálogo no modela cronograma de amortización por serie; los valores son **referencia** salvo que se cargue explícitamente en el futuro.

### 1.5 Intereses corridos (clean vs dirty)

- **Clean:** precio del bono “puro”.
- **Dirty:** incluye **intereses corridos** hasta la fecha de operación.
- **Límite MQ26 (hoy):** no se separa clean/dirty en todos los flujos; cuando el proveedor entrega un solo precio, se documenta como **referencia de mercado**, no como liquidación final.

### 1.6 Liquidación (CI vs T+2)

- Puede haber **diferencias de precio** por plazo de compensación.
- **Límite MQ26 (hoy):** no se discrimina CI vs T+2 salvo que la fuente lo exporte.

### 1.7 Tipo de cambio (CCL / MEP)

- La ON es **dólar cable / nominal USD**; la **cotización en pesos** oscila con el tipo que use el mercado al momento.
- En MQ26, **ARS / 100 VN USD** se aproxima como **paridad_% × CCL** (referencia pedagógica), salvo override por **BYMA en vivo** cuando exista.

---

## 2. Criterios de presentación en producto (UX)

| Concepto | Debe mostrarse como | Evitar |
|----------|---------------------|--------|
| Referencia técnica | Paridad %, **USD ref. / 100 VN**, TIR ref. (catálogo) | Un solo número “en pesos” sin unidad |
| Comercialización típica | **ARS / 100 VN** (y **Precio ARS** si BYMA lo entrega) | Mezclar TIR con “precio” en la misma celda sin etiqueta |
| Cantidad en cartera | Nominales USD (múltiplo de lámina) | Nominales como si fueran “acciones” |

**Regla de oro:** si el usuario opera en **pesos el ~90 % del tiempo**, la UI debe **destacar ARS comercial** y mantener **USD técnico** visible como segunda línea o columna explícita.

### 2.1 ON corporativas en pesos (cuando existan en catálogo)

- El **nominal contractual** y la **paridad** suelen estar en **ARS**; no aplica una columna “USD ref.” salvo que el instrumento sea dual o cable.
- La **cotización en pantalla** coincide con la unidad del nominal (ARS por 100 VN ARS, etc.).
- **Límite MQ26 (hoy):** el monitor dedicado cubre **ON_USD (Hard Dollar)**; las ON en pesos siguen en tablas de cartera / universo con la misma **disciplina de etiquetas** (nominal, paridad %, no mezclar con TIR sin aclarar).

---

## 3. Límites del motor (honestidad operativa)

1. **No es asesoramiento personalizado** ni sustituye prospecto, aviso de suscripción ni custodio.
2. **TIR ref.** del catálogo es **referencia interna**; la TIR de mercado puede diferir (precio, curva, spread).
3. **Datos BYMA en vivo** pueden faltar o estar desfasados; se muestra **Fuente** (BYMA vs catálogo).
4. **Coherencia de unidades:** si un feed mezcla TIR, paridad y precio, MQ26 debe **validar y etiquetar** antes de mostrar (roadmap).

---

## 4. Criterios de aceptación (release)

- [ ] Panel ON USD muestra **USD ref. / 100 VN** y **ARS / 100 VN USD** de forma simultánea.
- [ ] Copy y disclaimer explican nominal vs mercado y el rol del CCL.
- [ ] Catálogo ON con `lamina_min` y fechas coherentes con prospecto cuando se actualice un instrumento.

---

## 5. Referencias internas de código

- Convención y fórmulas: `core/renta_fija_ar.py` (`ON_USD_PARIDAD_BASE_VN`, `precio_usd_ref_on_usd_por_base_vn`, `precio_ars_on_usd_por_base_vn`, `MONITOR_ON_USD_DISCLAIMER`).
- UI: `ui/monitor_on_usd.py`.
- Datos BYMA: `services/byma_market_data.py`.
