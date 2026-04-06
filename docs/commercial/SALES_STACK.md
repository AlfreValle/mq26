# Stack comercial: CRM, demos y calendario

Implementación **ligeramente ambiciosa pero posible** sin código propio de CRM en el repo.

## CRM (elegir uno)

| Herramienta | Cuándo usarla |
|-------------|----------------|
| **HubSpot Free** | Embudo B2B + formularios + secuencias email simples |
| **Pipedrive** | Equipos pequeños, pipeline por etapa (demo → propuesta → cierre) |
| **Notion + base** | Etapa 0 sin presupuesto: tabla prospects, etapa, próximo paso |

**Campos mínimos por prospect:** nombre, firma, rol, email, segmento (estudio/broker), fuente (LinkedIn, referral, webinar), próxima acción, monto estimado.

## Calendario de demos (self-serve)

1. Crear cuenta **Cal.com** (open) o **Calendly** (pago avanzado).
2. Tipo de evento: **Demo Master Quant 30’** — buffer 10’, zona **America/Argentina/Buenos_Aires**.
3. Preguntas previas: tamaño de cartera de clientes, uso actual (Excel, otro software), broker principal.
4. Enlazar desde la landing estática [`commercial/landing/index.html`](../../commercial/landing/index.html) — sustituir el enlace "Agendar demo" por la URL real de Cal.com/Calendly.

Alternativa LATAM: **Google Appointment Schedules** si ya usan Workspace.

## Secuencia post-demo (plantilla)

- **H 0:** email gracias + resumen 3 bullets + enlace a `CASE_STUDIES_B2B_ANONIMOS.md` (PDF exportado).
- **D+2:** email con pricing y FAQ legal (herramienta vs asesoría).
- **D+7:** check-in corto o llamada 10 min si hubo interés caliente.

## KPIs mínimos del stack

- Tasa de asistencia a demo agendada vs no-show (objetivo \>70% con recordatorio automático).
- Tasa demo → propuesta enviada (objetivo 40–50% ICP).
- Ciclo medio de cierre B2B (medir desde primer contacto).

## Enlace en código y configuración local

La landing usa `site.config.js` (copia de `site.config.example.js`) — ver [DEPLOY_LANDING.md](DEPLOY_LANDING.md) y [commercial/landing/README.md](../../commercial/landing/README.md).

## Conectar HubSpot (ejemplo concreto)

1. Creá cuenta **HubSpot Free** y un “Company” de prueba.
2. **Marketing** → **Forms** → Create form: campos Nombre, Email, Empresa, Mensaje, campo oculto `utm_campaign` (query param).
3. Publicá el form y copiá el **embed code** (JavaScript). Podés pegarlo en una segunda página `contacto.html` junto a la landing o enlazar “Escribinos” a la URL del formulario hospedado por HubSpot.
4. **Settings** → **Tracking code**: solo activarlo si el abogado aprueba cookies + aviso en la web.
5. Automatización: **Workflow** “Demo solicitada” → si el contacto tiene etapa “Demo agendada”, enviar secuencia de 3 emails (plantillas en [WEBINAR_Y_CONTENIDO.md](WEBINAR_Y_CONTENIDO.md)).

## Conectar Pipedrive (alternativa)

1. Pipeline: `Lead` → `Demo agendada` → `Propuesta enviada` → `Cerrada ganada/perdida`.
2. Integración **Cal.com** → “Connect Pipedrive” para crear deal al reservar (plan según proveedor).
3. Campos personalizados: `utm_source`, `tamaño_firma`, `broker_principal`.

## Cal.com / Calendly (detalle)

- Crear evento **30 min**, ubicación videollamada fija, buffer **10 min** después.
- Preguntas obligatorias: “¿Cuántos clientes finales gestionás?” (número), “¿Usás Excel u otro software hoy?” (texto corto).
- En **Cal.com**: la URL pública del tipo de evento va en `demoUrl` dentro de `site.config.js`.
- Opcional: añadir `?utm_source=cal` en enlaces internos para distinguir en analytics.

## CRM + calendario sin código (etapa 0)

- **Google Sheet** compartido: columnas Fecha, Nombre, Email, Fuente, Próximo paso, Link reunión.
- Enlace de Calendly/Cal en la celda “Link demo” para el equipo.

## Enlace en código (legacy)

Si aún no migraste a `site.config.js`, reemplazá manualmente cualquier placeholder `CALENDLY_O_DEMO_URL` antes de campañas pagas.
