"""
core/formato_montos.py — Formato único de montos (Excelencia Industrial #25).

Sin Streamlit. Miles con punto; decimales con coma.
"""
from __future__ import annotations


def _split_number(x: float, decimales: int) -> tuple[bool, int, str]:
    neg = x < 0
    ax = abs(x)
    if decimales <= 0:
        return neg, int(round(ax)), ""
    scaled = round(ax * (10**decimales))
    ip = int(scaled // (10**decimales))
    fp = int(scaled % (10**decimales))
    frac = str(fp).zfill(decimales)
    return neg, ip, frac


def formato_monto_ar(value: float | int | None, *, simbolo: str = "$", decimales: int = 2) -> str:
    """Ej.: ``$ 1.250.300,00``."""
    if value is None:
        return "—"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "—"
    if x != x:
        return "—"
    neg, ip, frac = _split_number(x, decimales)
    ent = f"{ip:,}".replace(",", ".")
    body = ent if not frac else f"{ent},{frac}"
    pref = f"-{simbolo} " if neg else f"{simbolo} "
    return f"{pref}{body}"


def formato_monto_usd(value: float | int | None, decimales: int = 0) -> str:
    """USD para KPI; por defecto sin decimales."""
    if value is None:
        return "—"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "—"
    if x != x:
        return "—"
    neg, ip, frac = _split_number(x, decimales)
    ent = f"{ip:,}".replace(",", ".")
    body = ent if not frac else f"{ent},{frac}"
    return f"-USD {body}" if neg else f"USD {body}"
