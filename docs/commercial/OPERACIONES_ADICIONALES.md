# Operaciones aún no detalladas en el plan base

Lista de **aspectos complementarios** al kit comercial mínimo. Priorizá según tamaño de equipo y exposición B2B.

## 1. Consentimiento y cookies (landing y futuro login web)

- Si usás **Google Analytics**, **Meta Pixel** o similares en la landing: banner de cookies + registro de bases legales (consentimiento / interés legítimo según asesor).
- Versión mínima sin tracking de terceros: menos fricción legal; medís solo conversiones con **UTM + CRM**.

## 2. Facturación y cobro (Argentina)

- Definir si facturás en **ARS** (moneda de curso legal), **USD** con conversión a liquidación, o mix **B2B export** vs **B2C local**.
- Integraciones típicas: **Mercado Pago** (checkout Pro), **Stripe** (clientes con tarjeta internacional), transferencia + factura manual en etapa temprana.
- Contrato o condiciones generales de suscripción deben alinearse con **defensa del consumidor** si vendés B2C masivo.

## 3. Acuerdo de tratamiento de datos (DPA)

- Clientes **B2B** (estudios) pueden pedir un **DPA** o anexo RGPD-style aunque operen solo en AR.
- Plantilla corta: objeto, categorías de datos, subencargados (hosting, email), ubicación servidores, plazo de borrado, notificación de brechas.

## 4. Seguridad e incidentes

- Procedimiento interno: **quién avisa**, a quién (cliente / ARPCE si aplica), plazo.
- Backups cifrados o al menos segregados por tenant si crecés SaaS multi-cliente.

## 5. Marca y contenido

- Búsqueda de **libre de terceros** en nombre comercial antes de gastar en ads.
- **Manual de marca** (logo, colores, tono) para partners; evitá que reinterpreten el mensaje como “rentabilidad asegurada”.

## 6. Métricas de producto (no solo CRM)

- Eventos mínimos: registro, primera importación completada, primer informe descargado.
- Herramientas livianas: **Plausible**, **PostHog** self-host, o logs propios con **PII** minimizada.

## 7. Onboarding B2B “playbook”

- Checklist PDF de 2 páginas: crear tenant, cargar universo, primera cartera piloto, reunión de validación.
- Reduce churn y justifica precio de **onboarding pago** en [PRICING_B2B.md](PRICING_B2B.md).

## 8. Canales de soporte

- Correo **soporte@** vs **comercial@**; SLAs solo en Enterprise.
- Estado de sistema (**status page**) si pasás de 50+ usuarios concurrentes.

## 9. Internacionalización futura

- Si un día ofrecés hosting con datos fuera de AR: cláusulas de **transferencia** y elección de ley revisada con abogado.

---

Mantené este documento como “backlog operativo comercial”; no sustituye asesoramiento profesional.
