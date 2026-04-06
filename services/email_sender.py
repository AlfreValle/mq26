"""
services/email_sender.py — Envío real de emails vía Gmail SMTP
MQ26 | Reporte semanal de compras

Requiere en .env:
    GMAIL_USER=tu_email@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   ← contraseña de aplicación Gmail
    (Activar en: Google → Seguridad → Contraseñas de aplicaciones)

Alternativa: configurar ambos desde la UI de MQ26 (se guardan en la BD).
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def enviar_email_gmail(
    destinatario: str,
    asunto:       str,
    cuerpo_html:  str,
    remitente:    str | None = None,
    app_password: str | None = None,
    adjuntos:     list[str] = None,
) -> tuple[bool, str]:
    """
    Envía un email HTML vía Gmail SMTP con SSL.

    Args:
        destinatario: Email del destinatario.
        asunto:       Asunto del correo.
        cuerpo_html:  Contenido HTML del cuerpo.
        remitente:    Email remitente (default: GMAIL_USER del .env).
        app_password: Contraseña de aplicación Gmail (default: GMAIL_APP_PASSWORD del .env).
        adjuntos:     Lista de rutas de archivos a adjuntar (opcional).

    Returns:
        (True, "OK") si se envió correctamente, (False, "mensaje de error") si falló.
    """
    # Leer credenciales desde parámetros o variables de entorno
    gmail_user = remitente    or os.environ.get("GMAIL_USER", "").strip()
    gmail_pwd  = app_password or os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_user:
        return False, "GMAIL_USER no configurado. Definilo en .env o en la configuración de la app."
    if not gmail_pwd:
        return False, (
            "GMAIL_APP_PASSWORD no configurado.\n"
            "Para generarla: Google → Seguridad → Contraseñas de aplicaciones → "
            "Seleccionar app 'Correo' → Copiar las 16 letras generadas."
        )
    if not destinatario:
        return False, "Email de destinatario no especificado."

    # Construir el mensaje
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = gmail_user
    msg["To"]      = destinatario

    # Adjuntar cuerpo HTML
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    # Adjuntar archivos si los hay
    for ruta in (adjuntos or []):
        try:
            p = Path(ruta)
            if p.exists():
                part = MIMEBase("application", "octet-stream")
                part.set_payload(p.read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{p.name}"',
                )
                msg.attach(part)
        except Exception as e:
            return False, f"Error adjuntando {ruta}: {e}"

    # Enviar vía SMTP con SSL (puerto 465)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_user, gmail_pwd)
            server.sendmail(gmail_user, destinatario, msg.as_string())
        return True, f"Email enviado correctamente a {destinatario}"
    except smtplib.SMTPAuthenticationError:
        return False, (
            "Error de autenticación Gmail (SMTPAuthenticationError).\n"
            "Soluciones:\n"
            "1. Verificar que la Contraseña de Aplicación sea correcta\n"
            "2. Activar verificación en 2 pasos en tu cuenta Google\n"
            "3. Generar nueva contraseña en: Google → Seguridad → Contraseñas de aplicaciones"
        )
    except smtplib.SMTPRecipientsRefused:
        return False, f"Destinatario rechazado por el servidor: {destinatario}"
    except smtplib.SMTPException as e:
        return False, f"Error SMTP: {e}"
    except Exception as e:
        return False, f"Error inesperado al enviar email: {e}"


def verificar_config_email(dbm=None) -> tuple[bool, str, str]:
    """
    Verifica si las credenciales de Gmail están configuradas.
    Busca primero en la BD (via dbm), luego en variables de entorno.

    Returns:
        (configurado, gmail_user, mensaje_estado)
    """
    gmail_user = ""
    gmail_pwd  = ""

    # Intentar leer desde BD primero
    if dbm:
        try:
            gmail_user = dbm.obtener_config("gmail_user") or ""
            gmail_pwd  = dbm.obtener_config("gmail_app_password") or ""
        except Exception:
            pass

    # Fallback a variables de entorno
    if not gmail_user:
        gmail_user = os.environ.get("GMAIL_USER", "").strip()
    if not gmail_pwd:
        gmail_pwd  = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if gmail_user and gmail_pwd:
        return True, gmail_user, f"✅ Gmail configurado: {gmail_user}"
    elif gmail_user and not gmail_pwd:
        return False, gmail_user, "⚠️ Gmail User ok pero falta la Contraseña de Aplicación"
    else:
        return False, "", "❌ Gmail no configurado (falta GMAIL_USER y GMAIL_APP_PASSWORD)"
