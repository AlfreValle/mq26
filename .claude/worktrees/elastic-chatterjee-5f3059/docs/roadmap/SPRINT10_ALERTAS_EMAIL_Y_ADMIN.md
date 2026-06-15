# Sprint 10 (borrador técnico) — Alertas, email y admin

Alineado al plan estratégico Q2 2026 (jul–sep). No implementado aún; sirve como especificación para el siguiente ciclo de desarrollo.

## Alcance propuesto

1. **Email automático**: informe mensual o resumen al cliente final (template HTML, cola o envío síncrono con rate limit).
2. **Alertas Telegram**: MOD-23 (señales de venta) y vencimientos próximos (reutilizar `monitor_service` / `FlowManager` donde aplique).
3. **Resumen semanal**: plantilla única (email o WhatsApp vía proveedor externo — definir).
4. **Panel admin**: métricas de uso por tenant (logins, informes generados, último acceso) — lectura desde `alertas_log` o tablas dedicadas.
5. **Onboarding tier IN**: wizard corto post-login (checklist: importar broker, ver semáforo).

## Postgres (julio / deploy autónomo)

- Cuando `DATABASE_URL` esté definida, la app usa PostgreSQL ([DEPLOY_RAILWAY.md](../DEPLOY_RAILWAY.md)).
- Checklist migración: backup SQLite → restore en Supabase → variable en Railway → smoke login + cartera.

## Dependencias nuevas probables

- SMTP o API (SendGrid, Resend, etc.) — secretos en Railway.
- Bot de Telegram (token ya contemplado en UI admin parcial; consolidar).

## Tests

- No regresión: suite completa `pytest` tras cada módulo nuevo.
- Contratos inmutables del repo: no tocar `tab_optimizacion.py`, `optimization_service.py`, `risk_engine.py` salvo brief explícito.
