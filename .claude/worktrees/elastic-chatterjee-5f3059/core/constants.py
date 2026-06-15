"""
core/constants.py — Constantes de dominio centralizadas para MQ26.
"""
from __future__ import annotations

# ── Tipos de instrumento BYMA ─────────────────────────────────────────────────
TIPOS_INSTRUMENTO: list[str] = [
    "CEDEAR", "ACCION", "ETF", "BONO", "BONO_USD", "LETRA", "ON", "ON_USD", "FCI",
]

# ── Horizontes de inversión ───────────────────────────────────────────────────
HORIZONTES_INVERSION: list[str] = [
    "1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años",
]

HORIZONTE_A_DIAS: dict[str, int] = {
    "1 mes":   30,
    "3 meses": 90,
    "6 meses": 180,
    "1 año":   365,
    "3 años":  1095,
    "+5 años": 1825,
}

# ── Tipos de alerta ───────────────────────────────────────────────────────────
TIPOS_ALERTA: list[str] = [
    "VAR_BREACH", "DRAWDOWN", "SELL_SIGNAL", "AUDITORIA", "ACCESO",
    "OBJETIVO_VENCE", "OBJETIVO_COMPLETADO",
]

# ── Paleta de colores institucional ──────────────────────────────────────────
COLORES = {
    # MQ26
    "mq26_primary":    "#1565C0",
    "mq26_bg":         "#0A0A14",
    "mq26_accent":     "#2E86AB",
    # Semáforos
    "verde":   "#2E7D32",
    "amarillo":"#F9A825",
    "rojo":    "#C62828",
    # Neutros
    "texto":   "#212121",
    "caption": "#A0A0B8",
}

# ── Mensajes de error estándar ────────────────────────────────────────────────
MENSAJES = {
    "cliente_requerido":  "Seleccioná un cliente para continuar.",
    "sin_datos":          "No hay datos disponibles para el período seleccionado.",
    "sin_cartera":        "Esta cartera no tiene posiciones cargadas aún.",
    "error_precio":       "No se pudo obtener el precio actualizado de {ticker}.",
    "guardado_ok":        "Cambios guardados correctamente.",
    "eliminado_ok":       "Registro eliminado.",
    "campo_obligatorio":  "El campo '{campo}' es obligatorio.",
}
