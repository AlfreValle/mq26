"""
services/salud_datos.py — Pilar 4: monitor de salud de datos para el admin.

Responde de un vistazo "¿puedo confiar en los números que la app está
mostrando AHORA?": estado del CCL, edad de los datos de referencia mantenidos
a mano (serie CCL mensual, catálogo RF), cobertura y frescura de los precios
del contexto, caché de fundamentals y actividad del audit trail.

Se apoya en la fundación del Pilar 1 (PriceSource, stale flag) — acá solo se
agrega y se traduce a semáforos. Sin Streamlit. Sin red por defecto:
``ping_proveedores()`` es la única función que sale a internet y se llama
aparte, bajo demanda.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from core.logging_config import get_logger

_log = get_logger(__name__)

OK = "OK"
AVISO = "AVISO"
CRITICO = "CRITICO"

_ORDEN_ESTADO = {OK: 0, AVISO: 1, CRITICO: 2}


@dataclass
class ChequeoSalud:
    nombre: str
    estado: str            # OK | AVISO | CRITICO
    detalle: str           # una oración para el admin
    valor: dict[str, Any] = field(default_factory=dict)


@dataclass
class SaludDatos:
    generado_utc: str
    chequeos: list[ChequeoSalud] = field(default_factory=list)

    @property
    def semaforo_global(self) -> str:
        if not self.chequeos:
            return AVISO
        return max((c.estado for c in self.chequeos), key=lambda e: _ORDEN_ESTADO.get(e, 1))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Chequeos individuales (cada uno degrada solo) ───────────────────────────

def _chequeo_ccl_spot(ccl: float | None) -> ChequeoSalud:
    from config import CCL_FALLBACK

    v = float(ccl or 0)
    if v <= 0:
        return ChequeoSalud("CCL spot", CRITICO, "No hay CCL: las valuaciones ARS↔USD no son confiables.", {"ccl": v})
    if abs(v - float(CCL_FALLBACK)) < 0.01:
        return ChequeoSalud(
            "CCL spot", AVISO,
            f"El CCL en uso es el fallback hardcodeado ({v:,.0f}) — el cálculo live (GGAL.BA/GGAL) falló.",
            {"ccl": v, "es_fallback": True},
        )
    return ChequeoSalud("CCL spot", OK, f"CCL live en uso: {v:,.0f}.", {"ccl": v, "es_fallback": False})


def _chequeo_serie_ccl(hoy: date | None = None) -> ChequeoSalud:
    from core.pricing_utils import CCL_HISTORICO

    if not CCL_HISTORICO:
        return ChequeoSalud("Serie CCL histórica", CRITICO, "La serie mensual está vacía.", {})
    ultimo = max(CCL_HISTORICO)
    h = hoy or date.today()
    anio, mes = int(ultimo[:4]), int(ultimo[5:7])
    meses_atraso = (h.year - anio) * 12 + (h.month - mes)
    val = {"ultimo_mes": ultimo, "meses_atraso": meses_atraso}
    if meses_atraso >= 2:
        return ChequeoSalud(
            "Serie CCL histórica", AVISO if meses_atraso < 4 else CRITICO,
            f"Última entrada {ultimo} ({meses_atraso} meses de atraso): los costos históricos "
            "recientes usan un CCL viejo. Actualizar core/pricing_utils.CCL_HISTORICO.",
            val,
        )
    return ChequeoSalud("Serie CCL histórica", OK, f"Serie al día (último mes: {ultimo}).", val)


def _chequeo_catalogo_rf(hoy: date | None = None) -> ChequeoSalud:
    from core.renta_fija_ar import INSTRUMENTOS_RF

    h = hoy or date.today()
    edades: list[int] = []
    sin_fecha = 0
    for meta in INSTRUMENTOS_RF.values():
        if not meta.get("activo", True):
            continue
        f_ref = str(meta.get("fecha_ref", "") or "")
        try:
            d = date.fromisoformat(f_ref[:10])
            edades.append((h - d).days)
        except ValueError:
            sin_fecha += 1
    if not edades:
        return ChequeoSalud("Catálogo RF", AVISO, "Ningún instrumento activo con fecha_ref parseable.", {})
    max_edad = max(edades)
    val = {"instrumentos_activos": len(edades), "max_edad_dias": max_edad, "sin_fecha": sin_fecha}
    if max_edad > 90:
        return ChequeoSalud(
            "Catálogo RF", CRITICO,
            f"Hay paridades de referencia con {max_edad} días: los precios de catálogo de ONs "
            "pueden estar lejos del mercado. Actualizar paridad_ref/tir_ref/fecha_ref.",
            val,
        )
    if max_edad > 45:
        return ChequeoSalud(
            "Catálogo RF", AVISO,
            f"La paridad más vieja tiene {max_edad} días — conviene refrescar el catálogo.",
            val,
        )
    return ChequeoSalud("Catálogo RF", OK, f"{len(edades)} instrumentos activos, paridades de ≤{max_edad} días.", val)


def _chequeo_precios(precio_records: dict | None) -> list[ChequeoSalud]:
    if not precio_records:
        return [
            ChequeoSalud(
                "Precios de cartera", AVISO,
                "Sin records de precios en el contexto (cartera vacía o motor no corrió).",
                {},
            )
        ]
    total = len(precio_records)
    por_fuente: dict[str, int] = {}
    live = stale = missing = 0
    for rec in precio_records.values():
        src = getattr(getattr(rec, "source", None), "value", "desconocida")
        por_fuente[src] = por_fuente.get(src, 0) + 1
        if getattr(getattr(rec, "source", None), "is_live", False):
            live += 1
        if getattr(rec, "stale", False):
            stale += 1
        if src == "missing":
            missing += 1
    pct_live = 100.0 * live / total
    pct_stale = 100.0 * stale / total
    out: list[ChequeoSalud] = []
    val_cob = {"total": total, "por_fuente": por_fuente, "pct_live": round(pct_live, 1), "missing": missing}
    if missing:
        out.append(ChequeoSalud(
            "Cobertura de precios", CRITICO,
            f"{missing} de {total} tickers SIN precio por ninguna fuente.", val_cob,
        ))
    elif pct_live < 50.0:
        out.append(ChequeoSalud(
            "Cobertura de precios", AVISO,
            f"Solo {pct_live:.0f}% de los precios son live — la app está viviendo de fallbacks.",
            val_cob,
        ))
    else:
        out.append(ChequeoSalud(
            "Cobertura de precios", OK,
            f"{total} tickers con precio; {pct_live:.0f}% live.", val_cob,
        ))
    val_fr = {"stale": stale, "pct_stale": round(pct_stale, 1)}
    if pct_stale > 30.0:
        out.append(ChequeoSalud(
            "Frescura de precios", CRITICO,
            f"{pct_stale:.0f}% de los precios vencieron el umbral de su tipo — no operar sin verificar.",
            val_fr,
        ))
    elif stale:
        out.append(ChequeoSalud(
            "Frescura de precios", AVISO,
            f"{stale} precio(s) viejos para su tipo (marcados ⚠STALE en las tablas).", val_fr,
        ))
    else:
        out.append(ChequeoSalud("Frescura de precios", OK, "Todos los precios dentro de umbral.", val_fr))
    return out


def _chequeo_fundamentals_cache() -> ChequeoSalud:
    try:
        from services.fundamental_cache import listar_tickers_cacheados

        n = len(listar_tickers_cacheados())
        if n == 0:
            return ChequeoSalud(
                "Caché de fundamentals", AVISO,
                "Caché vacío: las fichas saldrán degradadas hasta la primera consulta con red.",
                {"tickers": 0},
            )
        return ChequeoSalud("Caché de fundamentals", OK, f"{n} tickers con snapshot (TTL 24 h).", {"tickers": n})
    except Exception as exc:
        return ChequeoSalud("Caché de fundamentals", AVISO, f"No se pudo leer el caché: {exc}", {})


def _chequeo_auditoria() -> ChequeoSalud:
    try:
        from services.audit_trail import listar_recomendaciones

        df = listar_recomendaciones(limit=200)
        n = len(df)
        if n == 0:
            return ChequeoSalud(
                "Audit trail", AVISO,
                "Sin recomendaciones registradas todavía (¿app recién instalada?).", {"eventos": 0},
            )
        ultimo = str(df.iloc[0]["timestamp"]) if "timestamp" in df.columns else "—"
        return ChequeoSalud(
            "Audit trail", OK,
            f"{n} evento(s) registrados; último: {ultimo}.", {"eventos": n, "ultimo": ultimo},
        )
    except Exception as exc:
        return ChequeoSalud("Audit trail", CRITICO, f"No se pudo leer la BD de auditoría: {exc}", {})


# ─── Snapshot (sin red) ───────────────────────────────────────────────────────

def snapshot_salud_datos(
    *,
    ccl: float | None = None,
    precio_records: dict | None = None,
) -> SaludDatos:
    """Snapshot completo de salud, sin tocar la red. Nunca lanza."""
    chequeos: list[ChequeoSalud] = []
    for builder in (
        lambda: _chequeo_ccl_spot(ccl),
        _chequeo_serie_ccl,
        _chequeo_catalogo_rf,
        _chequeo_fundamentals_cache,
        _chequeo_auditoria,
    ):
        try:
            chequeos.append(builder())
        except Exception as exc:  # un chequeo roto no tumba el monitor
            _log.warning("salud_datos: chequeo falló: %s", exc)
    try:
        chequeos.extend(_chequeo_precios(precio_records))
    except Exception as exc:
        _log.warning("salud_datos: chequeo precios falló: %s", exc)
    return SaludDatos(
        generado_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        chequeos=chequeos,
    )


# ─── Ping de proveedores (CON red — solo bajo demanda) ───────────────────────

def ping_proveedores() -> list[ChequeoSalud]:
    """Verifica proveedores externos en vivo. Llamar solo si el admin lo pide."""
    out: list[ChequeoSalud] = []
    try:
        import yfinance as yf

        h = yf.Ticker("SPY").history(period="5d")
        if h is not None and len(h) > 0:
            out.append(ChequeoSalud("yfinance", OK, f"Respondió ({len(h)} velas SPY 5d).", {"velas": len(h)}))
        else:
            out.append(ChequeoSalud("yfinance", CRITICO, "Respondió vacío — proveedor degradado.", {}))
    except Exception as exc:
        out.append(ChequeoSalud("yfinance", CRITICO, f"Sin respuesta: {exc}", {}))
    try:
        from services.byma_provider import fetch_precios_ars_batch

        px = fetch_precios_ars_batch(["GGAL"])
        if px and any(float(v or 0) > 0 for v in px.values()):
            out.append(ChequeoSalud("BYMA", OK, "Respondió con precios.", {"tickers": len(px)}))
        else:
            out.append(ChequeoSalud("BYMA", AVISO, "Respondió sin precios útiles.", {}))
    except Exception as exc:
        out.append(ChequeoSalud("BYMA", AVISO, f"Sin respuesta: {exc}", {}))
    return out
