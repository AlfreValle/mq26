# Despliegue de la landing: URLs, correos y scripts

Para aplicar **automáticamente** los archivos `.js` y cambios en `index.html`, usá **Agent mode** en Cursor. Si preferís hacerlo a mano, seguí esta guía.

## 1. Ignorar `site.config.js` en Git

Agregá al [`.gitignore`](../../.gitignore) del repo (raíz):

```
# Landing comercial — datos de contacto locales
commercial/landing/site.config.js
```

## 2. Crear `commercial/landing/site.config.example.js`

Copiá el contenido siguiente como archivo nuevo `commercial/landing/site.config.example.js`:

```javascript
/**
 * Copiá a site.config.js y completá. site.config.js no se commitea.
 */
window.MQ26_LANDING = {
  demoUrl: "https://cal.com/TU_USUARIO_O_EQUIPO/demo-master-quant-30min",
  emailComercial: "comercial@tudominio.com",
  emailLegal: "legal@tudominio.com",
  companyLegalName: "Tu Razón Social S.A.",
  termsUrl: "",
  privacyUrl: "",
  demoButtonLabel: "Agendar demo 30 min",
};
```

Luego ejecutá en la carpeta `commercial/landing/`:

```bash
copy site.config.example.js site.config.js   # Windows
# o
cp site.config.example.js site.config.js     # macOS/Linux
```

Y editá `site.config.js` con tus datos reales.

## 3. Crear `commercial/landing/apply-config.js`

```javascript
(function () {
  var c = window.MQ26_LANDING;
  if (!c || typeof c !== "object") {
    console.warn("[MQ26 landing] Copiá site.config.example.js a site.config.js y completalo.");
    return;
  }
  function qs(sel) { return document.querySelector(sel); }
  var demo = c.demoUrl && String(c.demoUrl).trim();
  if (demo && !/^https?:\/\//i.test(demo)) {
    demo = "https://" + demo.replace(/^\/+/, "");
  }
  var mailCom = (c.emailComercial || "").trim();
  var mailLeg = (c.emailLegal || "").trim();
  var company = (c.companyLegalName || "").trim() || "Master Quant";
  var demoLabel = (c.demoButtonLabel || "").trim() || "Agendar demo 30 min";
  [qs("[data-mq26-demo]"), qs("[data-mq26-demo-2]")].forEach(function (el) {
    if (el && demo) {
      el.setAttribute("href", demo);
      el.setAttribute("target", "_blank");
      el.setAttribute("rel", "noopener noreferrer");
    }
  });
  var d1 = qs("[data-mq26-demo]");
  var d2 = qs("[data-mq26-demo-2]");
  if (d1) d1.textContent = demoLabel;
  if (d2) d2.textContent = "Quiero una demo";
  var mCom = qs("[data-mq26-mail-comercial]");
  if (mCom && mailCom) {
    mCom.setAttribute("href", "mailto:" + encodeURIComponent(mailCom) +
      "?subject=" + encodeURIComponent("Consulta Master Quant"));
  }
  var mLeg = qs("[data-mq26-legal-link]");
  if (mLeg) {
    var tu = (c.termsUrl || "").trim();
    var pu = (c.privacyUrl || "").trim();
    if (tu || pu) {
      mLeg.setAttribute("href", tu || pu);
      mLeg.textContent = tu && pu && tu !== pu ? "Términos y privacidad" : "Términos y condiciones";
    } else if (mailLeg) {
      mLeg.setAttribute("href", "mailto:" + encodeURIComponent(mailLeg) +
        "?subject=" + encodeURIComponent("TVC y privacidad — Master Quant"));
      mLeg.textContent = "Privacidad y términos (contacto legal)";
    }
  }
  var yn = document.getElementById("mq26-company-year");
  if (yn) yn.textContent = new Date().getFullYear() + " · " + company;
})();
```

## 4. Ajustar `commercial/landing/index.html`

Antes de `</head>`, agregar:

```html
<script src="site.config.js"></script>
<script defer src="apply-config.js"></script>
```

En el body, reemplazar los enlaces fijos por:

- Primer CTA demo: `<a class="btn btn-primary" data-mq26-demo href="#">Agendar demo 30 min</a>`
- Mail: `<a class="btn btn-secondary" data-mq26-mail-comercial href="#">Escribinos</a>`
- Segundo CTA: `<a class="btn btn-primary" data-mq26-demo-2 href="#">Quiero una demo</a>`
- Pie: `<p>© <span id="mq26-company-year"></span> · Argentina</p>`
- Legal: `<p><a data-mq26-legal-link href="#">Privacidad y términos</a></p>`

Eliminá el script que solo ponía el año si ya lo hace `apply-config.js`.

## 5. Probar en local

Desde `commercial/landing/`:

```bash
python -m http.server 8080
```

Abrí http://127.0.0.1:8080/ y verificá CTAs y mailto.

---

Ver también: [SALES_STACK.md](SALES_STACK.md) (CRM + calendario) y [README de la carpeta landing](../../commercial/landing/README.md).
