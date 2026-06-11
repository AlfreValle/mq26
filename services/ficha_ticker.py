"""
services/ficha_ticker.py — Pilar 2: ficha unificada de ticker (nivel pro).

Compone en una sola estructura los motores de análisis que hasta ahora vivían
sueltos (varios sin ningún consumidor en la UI):

- Identidad:        core.instrument_master (tipo, sector, ratio, RF/RV)
- Fundamentals:     services.fundamental_cache (snapshot 24h con calidad)
- Score multifactor: services.scoring_multifactor (35 valor / 30 calidad /
                     20 momentum / 15 sectorial, con flags)
- Valuación DCF:    services.dcf_simple (2 etapas + margen de seguridad)
- Comparables:      services.industry_benchmarks (empresa vs mediana industria)

Principios:
- **Degradación elegante**: cada sección se construye en su propio try —
  si una falla, la ficha sale igual con esa sección marcada y explicada.
- **Explicación humana**: cada sección trae un texto que un asesor puede
  leerle a su cliente sin traducir; el score nunca es un número mudo.
- Sin Streamlit. La red entra solo vía los servicios compuestos (cacheados).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.instrument_master import get_master
from core.logging_config import get_logger
from services.dcf_simple import calcular_dcf
from services.fundamental_cache import obtener_fundamentales
from services.industry_benchmarks import comparar_vs_industria
from services.scoring_multifactor import calcular_action_score

_log = get_logger(__name__)


@dataclass
class SeccionFicha:
    """Una sección de la ficha: datos + explicación humana + estado."""

    nombre: str
    ok: bool
    datos: dict[str, Any] = field(default_factory=dict)
    explicacion: str = ""
    error: str = ""


@dataclass
class FichaTicker:
    """Ficha unificada de un ticker. Las secciones degradan independientes."""

    ticker: str
    generada_utc: str
    identidad: SeccionFicha
    fundamentals: SeccionFicha
    multifactor: SeccionFicha
    valuacion_dcf: SeccionFicha
    comparables: SeccionFicha
    score_global: float | None = None
    recomendacion: str = "SIN DATOS"
    resumen: str = ""

    @property
    def secciones(self) -> list[SeccionFicha]:
        return [
            self.identidad,
            self.fundamentals,
            self.multifactor,
            self.valuacion_dcf,
            self.comparables,
        ]

    @property
    def cobertura(self) -> str:
        ok = sum(1 for s in self.secciones if s.ok)
        return f"{ok}/{len(self.secciones)}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Secciones ────────────────────────────────────────────────────────────────

def _seccion_identidad(ticker: str) -> SeccionFicha:
    inst = get_master().get(ticker)
    if inst is None:
        return SeccionFicha(
            nombre="identidad",
            ok=False,
            error="Ticker fuera del maestro de instrumentos.",
            explicacion=(
                f"{ticker} no está en el universo MQ26 ni en el catálogo de "
                "renta fija. Verificá el símbolo."
            ),
        )
    datos = {
        "ticker": inst.ticker,
        "tipo": inst.tipo,
        "nombre": inst.nombre,
        "sector": inst.sector,
        "moneda": inst.moneda,
        "ratio_cedear": inst.ratio_cedear,
        "es_renta_fija": inst.es_renta_fija,
        "emisor": inst.emisor,
        "vencimiento": inst.vencimiento,
    }
    if inst.es_renta_fija:
        expl = (
            f"{inst.ticker} es renta fija ({inst.tipo}, emisor {inst.emisor or '—'}, "
            f"vence {inst.vencimiento or '—'}). Esta ficha analiza renta variable: "
            "para RF mirá TIR, paridad y calendario de pagos en la ficha RF."
        )
    else:
        ratio_txt = (
            f" · ratio {inst.ratio_cedear:.0f}:1" if inst.ratio_cedear and inst.ratio_cedear > 1 else ""
        )
        expl = f"{inst.ticker} — {inst.nombre or 'sin nombre'} · {inst.tipo}{ratio_txt} · sector {inst.sector or '—'}."
    return SeccionFicha(nombre="identidad", ok=True, datos=datos, explicacion=expl)


def _seccion_fundamentals(snap: Any) -> SeccionFicha:
    if snap is None or str(getattr(snap, "calidad", "missing")) == "missing":
        return SeccionFicha(
            nombre="fundamentals",
            ok=False,
            error="Sin snapshot de fundamentales.",
            explicacion="No hay datos fundamentales disponibles (proveedor caído o ticker sin cobertura).",
        )
    datos = {
        "calidad": snap.calidad,
        "precio_actual_usd": snap.precio_actual_usd,
        "pe_forward": snap.pe_forward,
        "pb_ratio": snap.pb_ratio,
        "roe": snap.roe,
        "profit_margin": snap.profit_margin,
        "debt_to_equity": snap.debt_to_equity,
        "revenue_growth": snap.revenue_growth,
        "dividend_yield": snap.dividend_yield,
        "market_cap": snap.market_cap,
        "sector": snap.sector,
        "industry": snap.industry,
    }
    calidad_txt = {
        "live": "datos frescos del proveedor",
        "cache": "datos de las últimas 24 h",
        "stale": "datos viejos — tomalos como referencia, no como foto actual",
    }.get(str(snap.calidad), str(snap.calidad))
    return SeccionFicha(
        nombre="fundamentals",
        ok=True,
        datos=datos,
        explicacion=f"Fundamentals de {snap.industry or snap.sector or 'la empresa'} ({calidad_txt}).",
    )


def _nivel(score: float) -> str:
    if score >= 70:
        return "fuerte"
    if score >= 40:
        return "neutral"
    return "débil"


def _seccion_multifactor(action: Any) -> SeccionFicha:
    if action is None:
        return SeccionFicha(
            nombre="multifactor",
            ok=False,
            error="Score multifactor no disponible.",
            explicacion="No se pudo calcular el score multifactor (faltan fundamentales).",
        )
    datos = action.to_dict()
    partes = [
        f"Score {action.score_total:.0f}/100 → {action.recomendacion}.",
        f"Valor {action.score_valor:.0f} ({_nivel(action.score_valor)}; pesa 35%):"
        " qué tan barata está vs. sus propios múltiplos.",
        f"Calidad {action.score_calidad:.0f} ({_nivel(action.score_calidad)}; 30%):"
        " rentabilidad y solidez de balance.",
        f"Momentum {action.score_momentum:.0f} ({_nivel(action.score_momentum)}; 20%):"
        " tendencia técnica reciente.",
        f"Sectorial {action.score_sectorial:.0f} ({_nivel(action.score_sectorial)}; 15%):"
        " posición relativa contra su industria.",
    ]
    if action.flags_alerta:
        partes.append("Alertas: " + " · ".join(str(f) for f in action.flags_alerta[:4]))
    return SeccionFicha(
        nombre="multifactor",
        ok=True,
        datos=datos,
        explicacion=" ".join(partes),
    )


def _seccion_dcf(dcf: Any) -> SeccionFicha:
    if dcf is None:
        return SeccionFicha(
            nombre="valuacion_dcf",
            ok=False,
            error="DCF no calculable.",
            explicacion=(
                "No se pudo valuar por DCF: hace falta flujo de caja libre positivo "
                "y datos de acciones en circulación."
            ),
        )
    datos = dcf.to_dict()
    margen = float(dcf.margen_seguridad_pct)
    if margen > 0:
        margen_txt = f"cotiza {margen:.0f}% por debajo de su valor intrínseco estimado"
    else:
        margen_txt = f"cotiza {abs(margen):.0f}% por encima de su valor intrínseco estimado"
    expl = (
        f"DCF 2 etapas: valor intrínseco ≈ USD {dcf.valor_intrinseco_usd:,.2f} vs precio "
        f"USD {dcf.precio_actual_usd:,.2f} → {dcf.recomendacion_dcf} ({margen_txt}). "
        f"Supuestos: crecimiento {dcf.growth_explicito_pct:.1f}%, WACC {dcf.wacc_pct:.1f}%. "
        "Es una estimación sensible a los supuestos, no un precio objetivo."
    )
    if dcf.warnings:
        expl += " Notas: " + " · ".join(str(w) for w in dcf.warnings[:2])
    return SeccionFicha(nombre="valuacion_dcf", ok=True, datos=datos, explicacion=expl)


def _seccion_comparables(comp: dict | None) -> SeccionFicha:
    if not comp or comp.get("fuente") in (None, "—") or not comp.get("metricas"):
        return SeccionFicha(
            nombre="comparables",
            ok=False,
            error="Sin benchmark de industria.",
            explicacion="No hay benchmark de la industria para comparar (sector sin cobertura).",
        )
    summary = comp.get("summary") or {}
    n_mejor = int(summary.get("n_mejor", 0))
    total = int(summary.get("total", summary.get("total_evaluado", 0)) or 0)
    expl = (
        f"Contra la mediana de su {comp.get('fuente')} ({comp.get('industria', '—')}): "
        f"mejor en {n_mejor} de {total} métricas evaluadas."
    )
    return SeccionFicha(nombre="comparables", ok=True, datos=comp, explicacion=expl)


# ─── Resumen ejecutivo ────────────────────────────────────────────────────────

def _resumen_ejecutivo(
    ticker: str,
    multifactor: SeccionFicha,
    dcf: SeccionFicha,
    comparables: SeccionFicha,
) -> tuple[float | None, str, str]:
    """(score_global, recomendacion, resumen) combinando las secciones vivas."""
    if not multifactor.ok:
        return None, "SIN DATOS", (
            f"No hay datos suficientes para puntuar {ticker}. "
            "Revisá el símbolo o reintentá más tarde."
        )
    score = float(multifactor.datos.get("score_total", 0))
    reco = str(multifactor.datos.get("recomendacion", "MANTENER"))
    partes = [f"{ticker}: score multifactor {score:.0f}/100 → {reco}."]
    if dcf.ok:
        reco_dcf = str(dcf.datos.get("recomendacion_dcf", ""))
        if reco_dcf == "SOBREVALUADA" and reco == "COMPRAR":
            partes.append(
                "Ojo: el DCF la ve sobrevaluada — el score compra por calidad/momentum, "
                "no por precio. Si entrás, que sea escalonado."
            )
        elif reco_dcf == "INFRAVALORADA" and reco != "VENDER":
            partes.append("El DCF refuerza: cotiza con descuento sobre su valor intrínseco.")
        elif reco_dcf:
            partes.append(f"El DCF la considera {reco_dcf}.")
    if comparables.ok:
        partes.append(comparables.explicacion)
    flags = multifactor.datos.get("flags_alerta") or []
    rojos = [f for f in flags if "🔴" in str(f)]
    if rojos:
        partes.append(f"Hay {len(rojos)} alerta(s) roja(s) — leelas antes de decidir.")
    return score, reco, " ".join(partes)


# ─── Entrada principal ────────────────────────────────────────────────────────

def generar_ficha_ticker(ticker: str, *, force_refresh: bool = False) -> FichaTicker:
    """
    Ficha unificada de un ticker de renta variable (CEDEAR/acción/ETF).

    Nunca lanza: cada sección degrada por separado y el estado queda en
    ``SeccionFicha.ok`` / ``error``. Para tickers de renta fija devuelve la
    identidad con la indicación de usar la ficha RF.
    """
    tu = str(ticker or "").strip().upper()
    generada = datetime.now(UTC).isoformat(timespec="seconds")

    identidad = _seccion_identidad(tu)

    if identidad.ok and identidad.datos.get("es_renta_fija"):
        # RF: la ficha RV no aplica; devolvemos identidad + secciones vacías explicadas
        no_aplica = "No aplica a renta fija — usá la ficha RF (TIR, paridad, vencimientos)."
        sec_na = lambda n: SeccionFicha(nombre=n, ok=False, error="No aplica a RF.", explicacion=no_aplica)  # noqa: E731
        return FichaTicker(
            ticker=tu,
            generada_utc=generada,
            identidad=identidad,
            fundamentals=sec_na("fundamentals"),
            multifactor=sec_na("multifactor"),
            valuacion_dcf=sec_na("valuacion_dcf"),
            comparables=sec_na("comparables"),
            recomendacion="VER FICHA RF",
            resumen=identidad.explicacion,
        )

    snap = None
    try:
        snap = obtener_fundamentales(tu, force_refresh=force_refresh)
    except Exception as exc:
        _log.warning("ficha_ticker %s: fundamentales fallaron: %s", tu, exc)
    fundamentals = _seccion_fundamentals(snap)

    action = None
    if fundamentals.ok:
        try:
            action = calcular_action_score(tu, force_refresh=force_refresh)
        except Exception as exc:
            _log.warning("ficha_ticker %s: multifactor falló: %s", tu, exc)
    multifactor = _seccion_multifactor(action)

    dcf_res = None
    if fundamentals.ok:
        try:
            dcf_res = calcular_dcf(tu, snap=snap)
        except Exception as exc:
            _log.warning("ficha_ticker %s: DCF falló: %s", tu, exc)
    valuacion_dcf = _seccion_dcf(dcf_res)

    comp = None
    if fundamentals.ok and snap is not None:
        try:
            comp = comparar_vs_industria(snap, getattr(snap, "industry", None), getattr(snap, "sector", None))
        except Exception as exc:
            _log.warning("ficha_ticker %s: comparables fallaron: %s", tu, exc)
    comparables = _seccion_comparables(comp)

    score, reco, resumen = _resumen_ejecutivo(tu, multifactor, valuacion_dcf, comparables)
    if not identidad.ok:
        resumen = identidad.explicacion + " " + resumen
    return FichaTicker(
        ticker=tu,
        generada_utc=generada,
        identidad=identidad,
        fundamentals=fundamentals,
        multifactor=multifactor,
        valuacion_dcf=valuacion_dcf,
        comparables=comparables,
        score_global=score,
        recomendacion=reco,
        resumen=resumen,
    )
