# Landing estática Master Quant

Archivos en esta carpeta: `index.html`, `apply-config.js`, `site.config.example.js`. La primera vez, copiá el example a `site.config.js` o editá el `site.config.js` local (no se sube a Git).

## Puesta en marcha (5 minutos)

1. Copiá el archivo de configuración:
   - `site.config.example.js` → `site.config.js` (mismo directorio).
2. Editá `site.config.js` con:
   - URL real de **Cal.com** o **Calendly** (evento “Demo 30 min”, zona Buenos Aires).
   - Correos **comercial** y **legal**.
   - Razón social o nombre comercial.
   - Opcional: `termsUrl` y `privacyUrl` cuando los publiques en tu dominio.
3. Abrí `index.html` en un navegador. Los scripts deben cargar desde el **mismo directorio** (doble clic puede bloquear `file://` en algunos navegadores; en ese caso usá un servidor estático).

### Servidor local rápido (Python)

Desde esta carpeta `commercial/landing/`:

```bash
python -m http.server 8080
```

Luego: http://127.0.0.1:8080/

## Archivos

| Archivo | En repo | Uso |
|---------|---------|-----|
| `index.html` | sí | Página |
| `apply-config.js` | sí | Aplica datos a la página |
| `site.config.example.js` | sí | Plantilla |
| `site.config.js` | **no** (gitignore) | Tus URLs y correos reales |

## Despliegue

Subí a **Netlify**, **Cloudflare Pages**, **Vercel** (static) o al bucket de tu hosting el contenido de `commercial/landing/` **incluyendo** tu `site.config.js` (configuralo en el panel del host como variable de entorno solo si generás HTML en build; con este enfoque basta subir el JS editado).

## CRM y seguimiento

Convención UTM sugerida para campañas:

- `?utm_source=linkedin&utm_medium=social&utm_campaign=demo_b2b_q2`
- En el CRM registrá la misma cadena en el campo “fuente” o en notas.

Detalle operativo: [docs/commercial/SALES_STACK.md](../../docs/commercial/SALES_STACK.md).
