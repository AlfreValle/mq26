# Casos B2B anonimizados — Master Quant / MQ26

**Uso:** material de venta interno o export a PDF para enviar post-demo. Personas y cifras **compuestas** a partir de patrones reales; no identifican clientes concretos.

---

## Caso A — Estudio boutique (Córdoba, 2 asesores)

**Contexto:** Estudio con ~**45 familias** de ingresos medios-altos. Operaban con **Excel + Dropbox** compartido; errores en PPC histórico y demoras al preparar reuniones trimestrales.

**Implementación:** Master Quant con cartera consolidada por cliente, import desde comprobantes del broker, diagnóstico de concentración y libro mayor unificado.

**Resultados (6 meses):**

- Reducción estimada del **tiempo de preparación** por revisión de cartera: de ~4 h a ~1 h por cliente-grupo.
- **Un solo archivo fuente** (`Maestra_Transaccional.csv` + backups) reemplazó versiones duplicadas de Excel.
- El estudio reportó mayor **confianza del cliente** al mostrar evolución y informe HTML descargable.

**Cita tipo (autorización interna — no usar nombre real):**  
> “Pasamos de pelear con las planillas a mostrar en la misma pantalla el diagnóstico y lo que falta para cumplir el perfil del cliente.”

---

## Caso B — Asesor independiente + carteras modelo (AMBA)

**Contexto:** Profesional con rol mixto: **80% clientes retail** en CEDEARs/ON y **20%** seguimiento de portfolio modelo para suscriptores. Necesitaba **repetir el mismo flujo** sin duplicar trabajo.

**Implementación:** Multi-cliente en un tenant, perfiles de riesgo distintos, uso de módulo de recomendación con capital nuevo para ilustrar prioridades (sin ejecutar órdenes desde la app).

**Resultados (4 meses):**

- **Onboarding estandarizado:** plantilla de cartera y checklist de carga para clientes nuevos.
- Menor **fatiga operativa** al importar operaciones desde el broker en lugar de carga manual total.
- Base para **upsell:** oferta de informe premium como add-on en el pricing B2C del asesor.

**Cita tipo:**  
> “El valor no es solo el optimizador: es que el cliente ve su posición, el sesgo y el horizonte en un solo lugar.”

---

### Cómo usar estos casos comercialmente

- En **emails** post-demo: adjuntar PDF de 1 página por caso (logo propio, disclaimer legal de `DISCLAIMERS_UX.md`).
- En **webinars:** mencionar “Estudio en interior” y “Asesor AMBA” sin geografías exactas si preferís mayor anonimato.
- **Actualizar** cuando tengáis casos reales firmados (contrato de uso de testimonio).
