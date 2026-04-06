# Voz, tono y glosario — MQ26 (inversor)

## Voz

- Español argentino, **vos**, frases cortas.
- Priorizar el **lenguaje del comprobante** y del home banking (ON, paridad, nominal, CEDEAR).
- Evitar en la primera lectura: PPC, FIFO, transaccional, beta, MOD-23, DataFrame.

## Tono

- Sobrio, claro, sin alarmismo; las alertas **sugieren** (“Convendría…”, “Revisá si…”).
- Los números van con contexto (“para tu perfil **Moderado** conviene…”).

## Glosario (UI vs sistema)

| En pantalla (inversor) | Concepto interno |
|------------------------|------------------|
| Participación en tu cartera | PESO_PCT |
| Cuánto pusiste / precio de compra | PPC / costo |
| Parte defensiva | % en anclas + cuasi-defensivo + RF AR |
| Importar desde tu broker | Parser Balanz/BMB (+ CSV genérico) |
| Historial de compras | Maestra transaccional |

## ARS, USD y CCL (resumen)

1. **Al registrar una compra:** se guarda la relación precio/CCL del día (PPC en ARS y en USD coherente con ese día).
2. **Valor “hoy”:** precios de mercado con **CCL actual** para mostrar patrimonio en pesos y en dólares.
3. **Rendimiento comparado** (mensajes de “cómo me fue”: usar marco en **USD de adquisición** según métricas del motor; no mezclar con nominales pesos históricos sin aclarar).

Detalle extendido: [UX_CARGA_CARTERA_INVERSOR_ARGENTINO.md](UX_CARGA_CARTERA_INVERSOR_ARGENTINO.md).
