/**
 * Aplica window.MQ26_LANDING definido en site.config.js.
 */
(function () {
  var c = window.MQ26_LANDING;
  if (!c || typeof c !== "object") {
    console.warn(
      "[MQ26 landing] Copiá site.config.example.js a site.config.js y completalo."
    );
    return;
  }
  function qs(sel) {
    return document.querySelector(sel);
  }
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
    mCom.setAttribute(
      "href",
      "mailto:" + mailCom + "?subject=" + encodeURIComponent("Consulta Master Quant")
    );
  }
  var mLeg = qs("[data-mq26-legal-link]");
  if (mLeg) {
    var tu = (c.termsUrl || "").trim();
    var pu = (c.privacyUrl || "").trim();
    if (tu || pu) {
      mLeg.setAttribute("href", tu || pu);
      mLeg.setAttribute("target", "_blank");
      mLeg.setAttribute("rel", "noopener noreferrer");
      mLeg.textContent =
        tu && pu && tu !== pu ? "Términos y privacidad" : "Términos y condiciones";
    } else if (mailLeg) {
      mLeg.setAttribute(
        "href",
        "mailto:" +
          mailLeg +
          "?subject=" +
          encodeURIComponent("TVC y privacidad — Master Quant")
      );
      mLeg.removeAttribute("target");
      mLeg.textContent = "Privacidad y términos (contacto legal)";
    }
  }
  var yn = document.getElementById("mq26-company-year");
  if (yn) yn.textContent = new Date().getFullYear() + " · " + company;
})();
