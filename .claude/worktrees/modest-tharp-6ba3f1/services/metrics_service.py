"""
services/metrics_service.py — Métricas de uso en memoria (Sprint 16)
MQ26-DSS | Registra eventos clave en memoria para diagnóstico.
Los contadores se reinician al reiniciar la app (no se persisten en BD).
Accesibles desde la UI en el expander "Salud del sistema".

Invariante: todas las funciones son no-bloqueantes y nunca lanzan.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

# Contadores globales (módulo-level — persistentes en la sesión Streamlit)
_contadores: dict[str, int]         = defaultdict(int)
_tiempos:    dict[str, list[float]] = defaultdict(list)
_errores:    list[dict[str, Any]]   = []
_MAX_ERRORES = 100  # ring buffer


def incrementar(evento: str, n: int = 1) -> None:
    """
    Incrementa el contador de un evento.
    Ej: incrementar('cache_hit') o incrementar('cache_miss', 3)
    Invariante: no lanza, silencia errores internos.
    """
    try:
        _contadores[evento] += n
    except Exception:
        pass


def registrar_tiempo(operacion: str, segundos: float) -> None:
    """
    Registra el tiempo de ejecución de una operación (últimos 50 valores).
    Ej: registrar_tiempo('calcular_posicion_neta', 0.12)
    Invariante: mantiene máximo 50 muestras por operación, nunca lanza.
    """
    try:
        tiempos = _tiempos[operacion]
        tiempos.append(round(float(segundos), 4))
        if len(tiempos) > 50:
            _tiempos[operacion] = tiempos[-50:]
    except Exception:
        pass


def registrar_error(modulo: str, mensaje: str, extra: dict | None = None) -> None:
    """
    Registra un error en el ring buffer (máx 100 entradas).
    Ej: registrar_error('price_engine', 'yfinance timeout', {'ticker': 'AAPL'})
    Invariante: mantiene máximo _MAX_ERRORES entradas, nunca lanza.
    """
    try:
        entry = {
            "ts":      time.strftime("%Y-%m-%d %H:%M:%S"),
            "modulo":  str(modulo or ""),
            "mensaje": str(mensaje or "")[:200],
            "extra":   extra or {},
        }
        _errores.append(entry)
        if len(_errores) > _MAX_ERRORES:
            _errores.pop(0)
    except Exception:
        pass


def obtener_resumen() -> dict[str, Any]:
    """
    Retorna un resumen de las métricas actuales de la sesión.
    Usado por el expander 'Salud del sistema' en mq26_main.py.

    Retorna dict con:
        contadores:       dict de eventos → conteo
        tiempos_promedio: dict de operación → promedio en segundos
        ultimos_errores:  últimos 5 errores registrados
        n_errores_total:  total de errores en el ring buffer
    Invariante: siempre retorna un dict (vacío ante error interno).
    """
    try:
        tiempos_promedio = {
            op: round(sum(vals) / len(vals), 4) if vals else 0.0
            for op, vals in _tiempos.items()
        }
        return {
            "contadores":       dict(_contadores),
            "tiempos_promedio": tiempos_promedio,
            "ultimos_errores":  _errores[-5:],
            "n_errores_total":  len(_errores),
        }
    except Exception:
        return {}


def resetear() -> None:
    """
    Resetea todos los contadores, tiempos y errores.
    Útil para tests y para el botón 'Resetear métricas' en la UI.
    Invariante: nunca lanza.
    """
    try:
        _contadores.clear()
        _tiempos.clear()
        _errores.clear()
    except Exception:
        pass
