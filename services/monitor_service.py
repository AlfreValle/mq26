"""
services/monitor_service.py — Orquestador de alertas proactivas (Sprint 9)
MQ26-DSS | Revisa toda la cartera en una pasada y dispara las alertas
que correspondan via Telegram y/o registro en AlertaLog.

Invariante: nunca lanza excepcion — cada alerta falla silenciosamente.
Puede llamarse desde la UI (boton "Revisar cartera") o programaticamente.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def revisar_cartera_completa(
    df_pos:          pd.DataFrame,
    df_analisis:     pd.DataFrame,
    metricas:        dict,
    cliente_id:      int | None,
    prop_nombre:     str,
    ccl:             float = 1500.0,
    enviar_telegram: bool = True,
) -> dict[str, int]:
    """
    Revisa toda la cartera y dispara alertas correspondientes.

    Checks realizados:
    1. Alertas MOD-23: tickers con score < 4
    2. Concentracion por activo: peso > 30%
    3. Drawdown de cartera: PNL_PCT < -15%
    4. Objetivos proximos a vencer: dias_restantes <= 7

    Retorna dict con conteo de alertas disparadas por categoria:
    {'mod23': n, 'concentracion': n, 'drawdown': n,
     'vencimientos': n, 'total': n}
    """
    resultado = {
        "mod23": 0, "concentracion": 0, "drawdown": 0,
        "vencimientos": 0, "total": 0,
    }
    if df_pos is None or df_pos.empty:
        return resultado

    try:
        import services.alert_bot as ab
        import services.mod23_service as m23svc

        # 1. Alertas MOD-23 (score < 4)
        tickers = df_pos["TICKER"].tolist() if "TICKER" in df_pos.columns else []
        alertas_venta = m23svc.detectar_alertas_venta(df_analisis, tickers)
        for alerta in alertas_venta:
            try:
                if enviar_telegram:
                    ab.alerta_senal_venta(
                        alerta["ticker"], alerta["score"],
                        alerta["estado"], prop_nombre,
                    )
                resultado["mod23"] += 1
            except Exception as e:
                logger.warning("alerta_senal_venta fallo: %s", e)

        # 2. Concentracion por activo (> 30%)
        if "PESO_PCT" in df_pos.columns:
            sobreconc = df_pos[df_pos["PESO_PCT"] > 30.0]
            for _, row in sobreconc.iterrows():
                try:
                    if enviar_telegram:
                        ab.enviar_telegram(
                            f"\u26a0\ufe0f MQ26 | Concentracion alta: "
                            f"{row['TICKER']} \u2192 {row['PESO_PCT']:.1f}% | {prop_nombre}"
                        )
                    resultado["concentracion"] += 1
                except Exception as e:
                    logger.warning("alerta_concentracion fallo: %s", e)

        # 3. Drawdown de cartera (< -15%)
        pnl_pct = float(metricas.get("pnl_pct", 0.0))
        if pnl_pct < -0.15:
            try:
                if enviar_telegram:
                    ab.alerta_drawdown(pnl_pct, cliente=prop_nombre)
                resultado["drawdown"] += 1
            except Exception as e:
                logger.warning("alerta_drawdown fallo: %s", e)

        # 4. Objetivos proximos a vencer (<= 7 dias)
        if cliente_id:
            try:
                from core.db_manager import obtener_objetivos_cliente
                df_obj = obtener_objetivos_cliente(cliente_id)
                if not df_obj.empty and "Dias restantes" in df_obj.columns:
                    proximos = df_obj[
                        (df_obj["Dias restantes"] <= 7) &
                        (df_obj["Estado"] == "ACTIVO")
                    ]
                elif not df_obj.empty and "Días restantes" in df_obj.columns:
                    proximos = df_obj[
                        (df_obj["Días restantes"] <= 7) &
                        (df_obj["Estado"] == "ACTIVO")
                    ]
                else:
                    proximos = pd.DataFrame()

                for _, obj in proximos.iterrows():
                    try:
                        if enviar_telegram:
                            ab.alerta_objetivo_proximo_vencimiento(
                                obj.to_dict(), prop_nombre
                            )
                        resultado["vencimientos"] += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("revisar_objetivos fallo: %s", e)

    except Exception as e:
        logger.error("revisar_cartera_completa fallo: %s", e)

    resultado["total"] = sum(v for k, v in resultado.items() if k != "total")
    return resultado


def contar_vencimientos_proximos(cliente_id: int | None, dias: int = 7) -> int:
    """
    Cuenta objetivos activos que vencen en los proximos `dias` dias.
    Retorna 0 si cliente_id es None o no hay objetivos.
    Invariante: nunca lanza excepcion.
    """
    if not cliente_id:
        return 0
    try:
        from core.db_manager import obtener_objetivos_cliente
        df = obtener_objetivos_cliente(cliente_id)
        if df.empty:
            return 0
        # Soportar ambas versiones de nombre de columna (con/sin tilde)
        col = "Días restantes" if "Días restantes" in df.columns else \
              "Dias restantes" if "Dias restantes" in df.columns else None
        if col is None:
            return 0
        return int(
            df[(df[col] <= dias) & (df["Estado"] == "ACTIVO")].shape[0]
        )
    except Exception:
        return 0


def enviar_reporte_mensual_email(
    nombre_cliente: str,
    df_pos:         pd.DataFrame,
    metricas:       dict,
    ccl:            float,
    df_analisis:    pd.DataFrame,
    destinatario:   str,
    cartera:        str = "",
    perfil:         str = "Moderado",
) -> bool:
    """
    Genera el reporte mensual HTML y lo envia por Gmail.
    Retorna True si el envio tuvo exito.
    Invariante: nunca lanza excepcion — retorna False si algo falla.
    """
    try:
        from datetime import date as _date

        from services.email_sender import enviar_email_gmail
        from services.reporte_mensual import generar_reporte_mensual_html

        hoy = _date.today()
        meses_es = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        mes_ano = f"{meses_es[hoy.month - 1]} {hoy.year}"

        html = generar_reporte_mensual_html(
            cliente=nombre_cliente,
            cartera=cartera,
            perfil=perfil,
            df_posiciones=df_pos,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas,
            recomendaciones=[],
            ccl=ccl,
            mes_ano=mes_ano,
        )
        asunto = (
            f"Reporte Mensual MQ26 \u2014 {nombre_cliente} \u2014 {mes_ano}"
        )
        return enviar_email_gmail(
            destinatario=destinatario,
            asunto=asunto,
            cuerpo_html=html,
        )
    except Exception as e:
        logger.error("enviar_reporte_mensual_email fallo: %s", e)
        return False
