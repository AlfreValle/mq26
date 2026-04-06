"""
alert_bot.py — Sistema de Alertas Telegram + Log en BD
MQ26 + DSS Unificado | Reintentos, backoff y logging estructurado.
Conectado a: VaR breach, drawdown excesivo, señales MOD-23
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.logging_config import get_logger

logger = get_logger(__name__)

_MAX_REINTENTOS = 2
_TIMEOUT_SEG    = 10


def _get_config():
    return (
        os.environ.get("TELEGRAM_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
    )


def _enviar_seguro(mensaje: str) -> bool:
    """
    Wrapper resiliente sobre enviar_telegram.
    Nunca propaga excepciones — retorna False si enviar_telegram falla.
    Invariante: todas las funciones alerta_* pueden usarlo sin riesgo de lanzar.
    """
    try:
        return enviar_telegram(mensaje)
    except Exception as exc:
        logger.warning("_enviar_seguro: fallo silencioso: %s", exc)
        return False


def enviar_telegram(mensaje: str) -> bool:
    """
    Envía mensaje a Telegram con hasta _MAX_REINTENTOS intentos.
    Nunca lanza excepción — fallo silencioso con log de warning.
    """
    token, chat_id = _get_config()
    if not token or not chat_id:
        logger.debug("Telegram no configurado (token o chat_id vacíos).")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"}

    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT_SEG)
            if resp.status_code == 200:
                logger.debug("Telegram: mensaje enviado OK.")
                return True
            logger.warning(
                "Telegram: HTTP %d en intento %d/%d — %s",
                resp.status_code, intento, _MAX_REINTENTOS, resp.text[:120],
            )
        except requests.exceptions.Timeout:
            logger.warning("Telegram: timeout en intento %d/%d.", intento, _MAX_REINTENTOS)
        except Exception as exc:
            logger.warning("Telegram: error en intento %d/%d: %s", intento, _MAX_REINTENTOS, exc)

        if intento < _MAX_REINTENTOS:
            time.sleep(1.5 * intento)

    logger.error("Telegram: todos los reintentos agotados. Mensaje no enviado.")
    return False


def alerta_var_breach(ticker: str, var_95: float, umbral: float = -0.20,
                      cliente: str = "") -> bool:
    """Alerta cuando el VaR supera un umbral de pérdida."""
    if var_95 > umbral:
        return False
    msg = (
        f"🚨 <b>ALERTA VaR</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"👤 Cliente: {cliente or 'N/D'}\n"
        f"📉 VaR 95%: <b>{var_95*100:.1f}%</b> (umbral: {umbral*100:.0f}%)\n"
        f"Revisar posición: {ticker}"
    )
    return _enviar_seguro(msg)


def alerta_drawdown(drawdown: float, umbral: float = -0.15, cliente: str = "") -> bool:
    """Alerta cuando el drawdown supera el umbral."""
    if drawdown > umbral:
        return False
    msg = (
        f"📉 <b>ALERTA DRAWDOWN</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"👤 Cliente: {cliente or 'N/D'}\n"
        f"⚠️ Max Drawdown: <b>{drawdown*100:.1f}%</b> (umbral: {umbral*100:.0f}%)"
    )
    return _enviar_seguro(msg)


def alerta_senal_venta(ticker: str, score: float, estado: str, cliente: str = "") -> bool:
    """Alerta cuando MOD-23 emite señal de venta (score < 4)."""
    if score >= 4.0:
        return False
    msg = (
        f"🔴 <b>SEÑAL DE VENTA MOD-23</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"👤 Cliente: {cliente or 'N/D'}\n"
        f"📊 Ticker: <b>{ticker}</b>\n"
        f"⚡ Score: {score:.1f}/10 — Estado: {estado}"
    )
    return _enviar_seguro(msg)


def alerta_rebalanceo(tickers_compra: list, tickers_venta: list, cliente: str = "") -> bool:
    """Alerta de rebalanceo sugerido."""
    compras = ", ".join(tickers_compra) if tickers_compra else "ninguno"
    ventas = ", ".join(tickers_venta) if tickers_venta else "ninguno"
    msg = (
        f"🔄 <b>REBALANCEO SUGERIDO</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"👤 Cliente: {cliente or 'N/D'}\n"
        f"🟢 Comprar: {compras}\n"
        f"🔴 Vender: {ventas}"
    )
    return _enviar_seguro(msg)


def alerta_objetivo_proximo_vencimiento(objetivo: dict, cliente: str = "") -> bool:
    """
    Alerta cuando un objetivo de inversión está próximo a vencer (H9).
    objetivo: dict con claves 'Ticker', 'Motivo', 'Monto ARS', 'Días restantes'.
    Se lanza automáticamente al arrancar la app si dias_restantes <= 30.
    Invariante: nunca lanza — retorna False si el plazo > 30 días o Telegram no configurado.
    """
    dias_restantes = int(objetivo.get("Días restantes", 999) or 999)
    if dias_restantes > 30:
        return False
    ticker    = str(objetivo.get("Ticker", ""))
    motivo    = str(objetivo.get("Motivo", "Sin descripción"))
    monto_ars = float(objetivo.get("Monto ARS", 0) or 0)
    emoji    = "⏰" if dias_restantes > 7 else "🔴"
    urgencia = "URGENTE" if dias_restantes <= 7 else "PRÓXIMO A VENCER"
    msg = (
        f"{emoji} <b>OBJETIVO {urgencia}</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"👤 Cliente: {cliente}\n"
        f"📊 Activo: <b>{ticker or 'N/D'}</b>\n"
        f"💰 Monto: ${monto_ars:,.0f} ARS\n"
        f"📝 Motivo: {motivo or 'Sin descripción'}\n"
        f"⏳ Días restantes: <b>{dias_restantes}</b>"
    )
    return _enviar_seguro(msg)


def verificar_objetivos_por_vencer(df_objetivos, prop_nombre: str) -> int:
    """
    Verifica todos los objetivos de un cliente y envía alertas para los próximos a vencer.
    Retorna el número de alertas enviadas.
    """
    enviadas = 0
    if df_objetivos is None or df_objetivos.empty:
        return 0
    for _, row in df_objetivos.iterrows():
        dias = int(row.get("Días restantes", 999) or 999)
        if dias <= 30 and row.get("Estado") == "ACTIVO":
            ok = alerta_objetivo_proximo_vencimiento(
                objetivo={
                    "Ticker":          str(row.get("Ticker", "")),
                    "Motivo":          str(row.get("Motivo", "")),
                    "Días restantes":  dias,
                    "Monto ARS":       float(row.get("Monto ARS", 0) or 0),
                },
                cliente=prop_nombre,
            )
            if ok:
                enviadas += 1
    return enviadas


def filtrar_token_logs(mensaje: str) -> str:
    """
    Sanitiza mensajes de log eliminando tokens de Telegram (E2).
    Evita que tokens aparezcan en archivos de log.
    """
    import re
    # URLs de API usan /bot<token>; mensajes sueltos usan \\bdigitos:
    s = re.sub(r"/bot\d{9,10}:[A-Za-z0-9_-]{25,}\b", "/bot***", mensaje)
    return re.sub(r"\b\d{9,10}:[A-Za-z0-9_-]{25,}\b", "***", s)


def test_conexion() -> bool:
    """Verifica que el bot esté configurado y responda."""
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False
    return enviar_telegram("✅ MQ26-DSS: Conexión Telegram OK")
