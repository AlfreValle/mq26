# Paquete de entrega al abogado — TyC y privacidad

Objetivo: acelerar la **primera reunión** con abogado de mercado de capitales + datos personales (Argentina).

## Documentos del repo para compartir (PDF o carpeta ZIP)

1. [TYC_PLANTILLA_MQ26.md](TYC_PLANTILLA_MQ26.md) — completar corchetes `[·]` antes de enviar.
2. [POLITICA_PRIVACIDAD_PLANTILLA.md](POLITICA_PRIVACIDAD_PLANTILLA.md) — idem.
3. [DISCLAIMERS_UX.md](DISCLAIMERS_UX.md) — textos que aparecerán en app y marketing.
4. [LEGAL_NOTA_ABOGADO.md](LEGAL_NOTA_ABOGADO.md) — checklist de temas a tratar.
5. Descripción funcional breve del producto (si el estudio no usa la app): flujo inversor, import broker, diagnósticos orientativos, informes exportables.

## Preguntas explícitas para la primera consulta

- El producto califica como **herramienta** exclusivamente, o algún flujo activa obligaciones de **sistema de recomendación / asesoramiento** a la luz de la normativa aplicable?
- Qué cláusulas exige el contrato **B2B** con estudios (responsabilidad, límites, datos del cliente final)?
- Textos obligatorios en la **landing** y en **correos** post-demo.
- Tratamiento de **datos financieros** (categorización, plazo de conservación, subencargados si el hosting es extranjero).
- Si ofrecen **prueba gratuita**: condiciones y consentimiento.

## Entregables esperados del abogado (para publicar)

- TyC y política de privacidad **versión 1.0** en HTML o Markdown listo para publicar en `www`.
- Contrato marco **licencia SaaS** (plantilla reutilizable con anexos).
- Opinión escrita breve sobre uso del término “optimizador” en comunicaciones (si recomienda matices).

## Tras la aprobación legal

1. Publicá los documentos en URLs estables (`/terminos`, `/privacidad`).
2. Copiá esas URLs en `site.config.js` (`termsUrl`, `privacyUrl`) — ver [DEPLOY_LANDING.md](DEPLOY_LANDING.md).
3. Actualizá la app Streamlit con enlaces a esas páginas (footer o menú “Avisos legales”) cuando implementes UI.
