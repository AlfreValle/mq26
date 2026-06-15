"""
core/validators.py — Validaciones de dominio reutilizables (MQ-D9 / DS-S6)
Centraliza las validaciones hoy dispersas en formularios de tab_dss.py y cartera_service.py.
"""
from __future__ import annotations

import datetime as dt

# ── Finanzas generales ────────────────────────────────────────────────────────

def validar_monto(v: float | None, nombre: str = "monto", permitir_cero: bool = False) -> tuple[bool, str]:
    """
    Valida que un monto sea un número positivo.
    Retorna (valido, mensaje_error).
    """
    if v is None:
        return False, f"El campo '{nombre}' es obligatorio."
    try:
        v = float(v)
    except (TypeError, ValueError):
        return False, f"El campo '{nombre}' debe ser un número."
    if not permitir_cero and v <= 0:
        return False, f"El campo '{nombre}' debe ser mayor a cero."
    if permitir_cero and v < 0:
        return False, f"El campo '{nombre}' no puede ser negativo."
    return True, ""


def validar_monto_egreso(v: float | None) -> tuple[bool, str]:
    """Un egreso debe ser positivo (si el usuario cargó negativo, se corrige automáticamente)."""
    if v is None:
        return False, "El monto es obligatorio."
    v = float(v)
    if v == 0:
        return False, "El monto no puede ser cero."
    return True, ""


def normalizar_monto(v: float, tipo: str) -> float:
    """
    Asegura que el monto sea positivo independientemente del signo cargado.
    Si tipo=='EGRESO' y v<0, invierte el signo y lo devuelve positivo.
    """
    v = float(v)
    if tipo == "EGRESO" and v < 0:
        return abs(v)
    if tipo == "INGRESO" and v < 0:
        return abs(v)
    return v


# ── Fechas ────────────────────────────────────────────────────────────────────

def validar_fecha(d, nombre: str = "fecha") -> tuple[bool, str]:
    """Valida que sea una fecha válida (date o string ISO)."""
    if d is None:
        return False, f"El campo '{nombre}' es obligatorio."
    if isinstance(d, dt.date):
        return True, ""
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                dt.datetime.strptime(d, fmt)
                return True, ""
            except ValueError:
                continue
        return False, f"Formato de fecha inválido en '{nombre}'. Usar DD/MM/YYYY."
    return False, f"Tipo de dato inválido para '{nombre}'."


def fecha_no_futura(d: dt.date, nombre: str = "fecha") -> tuple[bool, str]:
    """Una transacción histórica no puede tener fecha futura."""
    if d > dt.date.today():
        return False, f"La {nombre} no puede ser en el futuro."
    return True, ""


# ── Categorías ────────────────────────────────────────────────────────────────

def validar_categoria(categoria: str | None, tipo: str = "EGRESO") -> tuple[bool, str]:
    """Valida que la categoría no sea vacía."""
    if not categoria or not categoria.strip():
        return False, "La categoría es obligatoria."
    return True, ""


# ── Instrumentos financieros ──────────────────────────────────────────────────

def validar_ticker(ticker: str | None) -> tuple[bool, str]:
    """Un ticker debe ser una cadena no vacía de hasta 10 caracteres alfanuméricos."""
    if not ticker or not ticker.strip():
        return False, "El ticker es obligatorio."
    ticker = ticker.strip().upper()
    if len(ticker) > 15:
        return False, f"Ticker demasiado largo: '{ticker}'."
    if not all(c.isalnum() or c in "._-" for c in ticker):
        return False, f"Ticker con caracteres inválidos: '{ticker}'."
    return True, ""


def validar_cantidad(cantidad: float | None) -> tuple[bool, str]:
    """La cantidad de nominales debe ser positiva."""
    if cantidad is None:
        return False, "La cantidad es obligatoria."
    try:
        cantidad = float(cantidad)
    except (TypeError, ValueError):
        return False, "La cantidad debe ser un número."
    if cantidad <= 0:
        return False, "La cantidad debe ser mayor a cero."
    return True, ""


def validar_precio_compra(precio: float | None) -> tuple[bool, str]:
    """El precio de compra no puede ser negativo ni cero."""
    if precio is None:
        return False, "El precio de compra es obligatorio."
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return False, "El precio debe ser un número."
    if precio <= 0:
        return False, "El precio de compra debe ser mayor a cero."
    if precio > 100_000_000:
        return False, "El precio parece demasiado alto. Verificá las unidades (¿ARS o USD?)."
    return True, ""


# ── Tarjetas de crédito ───────────────────────────────────────────────────────

def validar_cuotas(cuotas_total: int | None, cuotas_pagadas: int | None = None) -> tuple[bool, str]:
    """Valida coherencia de cuotas."""
    if cuotas_total is None or int(cuotas_total) < 1:
        return False, "Las cuotas deben ser al menos 1."
    if cuotas_pagadas is not None and int(cuotas_pagadas) > int(cuotas_total):
        return False, "Las cuotas pagadas no pueden superar el total."
    return True, ""


# ── DataFrame ─────────────────────────────────────────────────────────────────

def validar_df_columnas(df, columnas_requeridas: list[str], nombre_df: str = "DataFrame") -> tuple[bool, list[str]]:
    """
    Verifica que el DataFrame tenga todas las columnas requeridas.
    Retorna (valido, lista_faltantes).
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return False, columnas_requeridas
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    return len(faltantes) == 0, faltantes
