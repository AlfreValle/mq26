"""
services/recomendador_explicable.py — Pilar 3: el "qué hago con mi plata" auditable.

Los motores de MQ26 ya deciden bien, pero cada uno explica en su propio
dialecto: recomendacion_capital da una frase, motor_salida emite disparadores
con emoji, perlas arma HTML y decision_engine devuelve un número. Esta capa
los unifica en un contrato único — PlanAccion → RecomendacionExplicada → motivos
atómicos — donde cada sugerencia lleva:

- la **acción** y el monto,
- **por qué** (motivos atómicos, cada uno con su origen),
- **con qué datos** (precio usado, fuente y frescura → confianza),
- y queda **registrada** en el audit trail con el payload completo.

La ficha del Pilar 2 es el "por qué profundo": toda recomendación de RV
lleva el flag de ficha disponible para que la UI la enlace.

Sin Streamlit. No re-decide nada: envuelve y explica lo que los motores ya
decidieron (si un motor cambia, sus razones cambian acá solas).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.logging_config import get_logger

_log = get_logger(__name__)

CONFIANZA_ALTA = "ALTA"
CONFIANZA_MEDIA = "MEDIA"
CONFIANZA_BAJA = "BAJA"


@dataclass
class Motivo:
    """Razón atómica y auditable de una recomendación."""

    texto: str
    origen: str  # "motor_capital" | "motor_salida" | "datos" | "mercado"


@dataclass
class RecomendacionExplicada:
    """Una sugerencia con su porqué completo."""

    accion: str                      # COMPRAR | VENDER | REVISAR
    ticker: str
    nombre: str = ""
    unidades: float | None = None
    monto_ars: float | None = None
    prioridad: str = "MEDIA"         # CRITICA | ALTA | MEDIA | BAJA
    tesis: str = ""                  # narrativa ejecutiva (1-2 oraciones)
    motivos: list[Motivo] = field(default_factory=list)
    confianza: str = CONFIANZA_MEDIA  # calidad de los datos que la sostienen
    advertencias: list[str] = field(default_factory=list)
    datos: dict[str, Any] = field(default_factory=dict)   # trazabilidad
    motor: str = ""                  # qué motor la originó
    tiene_ficha: bool = False        # la UI puede enlazar la ficha Pilar 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlanAccion:
    """El plan completo: comprar / vender-revisar, con contexto y resumen."""

    generado_utc: str
    perfil: str
    capital_ars: float | None
    comprar: list[RecomendacionExplicada] = field(default_factory=list)
    vender_revisar: list[RecomendacionExplicada] = field(default_factory=list)
    alerta_mercado: str = ""
    resumen: str = ""

    @property
    def n_acciones(self) -> int:
        return len(self.comprar) + len(self.vender_revisar)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Confianza desde frescura del precio (Pilar 1) ────────────────────────────

def _confianza_precio(ticker: str, precio_records: dict | None) -> tuple[str, dict, list[str]]:
    """(confianza, trazabilidad, advertencias) según fuente y frescura del precio."""
    rec = (precio_records or {}).get(str(ticker).upper())
    if rec is None:
        return CONFIANZA_MEDIA, {"fuente_precio": "desconocida"}, []
    traz = {
        "fuente_precio": getattr(getattr(rec, "source", None), "value", str(getattr(rec, "source", ""))),
        "timestamp_precio": getattr(rec, "timestamp", None).isoformat() if getattr(rec, "timestamp", None) else None,
        "stale": bool(getattr(rec, "stale", False)),
    }
    if getattr(rec, "stale", False):
        return (
            CONFIANZA_BAJA,
            traz,
            ["El precio usado superó el umbral de frescura de su tipo — verificá la cotización antes de operar."],
        )
    src = getattr(rec, "source", None)
    if getattr(src, "is_live", False):
        return CONFIANZA_ALTA, traz, []
    return CONFIANZA_MEDIA, traz, []


def _tiene_ficha(ticker: str) -> bool:
    try:
        from core.instrument_master import get_master

        inst = get_master().get(ticker)
        return inst is not None and not inst.es_renta_fija
    except Exception:
        return False


# Debajo de este monto, la fricción del broker (comisión + derechos + spread,
# ~1.5% ida y vuelta) pesa proporcionalmente más que el beneficio de rebalanceo
# que aporta una compra tan chica.
UMBRAL_MONTO_CHICO_ARS = 20_000.0


def _costos_operacion(
    ticker: str,
    unidades: float,
    precio_ars: float,
    monto_ars: float,
) -> tuple[dict[str, Any], list[str]]:
    """
    (trazabilidad de costos, advertencias) usando el modelo de decision_engine.

    El nocional se calcula sobre ``monto_ars`` directamente (nominales=1,
    precio=monto): evita el truncado de unidades fraccionarias y garantiza
    que el % de costo refiera al mismo monto que ve el usuario.
    """
    if not monto_ars or monto_ars <= 0:
        return {}, []
    traz: dict[str, Any] = {}
    try:
        from services.decision_engine import calcular_costos_operacion

        c = calcular_costos_operacion(ticker, "COMPRA", 1, float(monto_ars))
        costo = float(c.get("costo_total", 0) or 0)
        if costo > 0:
            traz = {
                "costo_operacion_ars": round(costo, 2),
                "costo_operacion_pct": round(100.0 * costo / monto_ars, 2),
            }
    except Exception:
        costo = 0.0
    advert: list[str] = []
    # La advertencia de monto chico no depende del modelo de costos: aun si
    # falla, los mínimos fijos por boleto del broker castigan montos chicos.
    if monto_ars < UMBRAL_MONTO_CHICO_ARS:
        detalle_costo = f" (fricción ida y vuelta ~ARS {2.0 * costo:,.0f} +" if costo > 0 else " ("
        advert.append(
            f"Operación chica (ARS {monto_ars:,.0f}):{detalle_costo} comisión mínima "
            "fija por boleto del broker, que en montos chicos pesa más) — evaluá "
            "agruparla con la próxima inyección."
        )
    return traz, advert


# ─── Compras: envuelve RecomendacionResult (recomendacion_capital) ────────────

def explicar_compras(
    rr: Any,
    *,
    precio_records: dict | None = None,
) -> list[RecomendacionExplicada]:
    """
    Convierte las compras de un ``RecomendacionResult`` en recomendaciones
    explicadas. No re-decide: traduce y traza.
    """
    out: list[RecomendacionExplicada] = []
    for it in list(getattr(rr, "compras_recomendadas", None) or []):
        tk = str(getattr(it, "ticker", "") or "").upper()
        if not tk:
            continue
        motivos = [Motivo(texto=str(getattr(it, "justificacion", "") or ""), origen="motor_capital")]
        impacto = str(getattr(it, "impacto_en_balance", "") or "")
        if impacto:
            motivos.append(Motivo(texto=impacto, origen="motor_capital"))
        prioridad = getattr(getattr(it, "prioridad", None), "name", None) or str(
            getattr(it, "prioridad", "") or "MEDIA"
        )
        confianza, traz, advert = _confianza_precio(tk, precio_records)
        if getattr(it, "es_activo_nuevo", False):
            motivos.append(Motivo(texto="Activo nuevo en tu cartera (diversifica).", origen="motor_capital"))
        traz.update(
            {
                "precio_ars_usado": float(getattr(it, "precio_ars_estimado", 0) or 0),
                "categoria": getattr(getattr(it, "categoria", None), "value", str(getattr(it, "categoria", ""))),
            }
        )
        # decision_engine: costos de operación como trazabilidad + advertencia
        traz_costos, advert_costos = _costos_operacion(
            tk,
            float(getattr(it, "unidades", 0) or 0),
            float(getattr(it, "precio_ars_estimado", 0) or 0),
            float(getattr(it, "monto_ars", 0) or 0),
        )
        traz.update(traz_costos)
        advert = advert + advert_costos
        out.append(
            RecomendacionExplicada(
                accion="COMPRAR",
                ticker=tk,
                nombre=str(getattr(it, "nombre_legible", "") or ""),
                unidades=float(getattr(it, "unidades", 0) or 0),
                monto_ars=float(getattr(it, "monto_ars", 0) or 0),
                prioridad=prioridad.upper(),
                tesis=str(getattr(it, "justificacion", "") or ""),
                motivos=motivos,
                confianza=confianza,
                advertencias=advert,
                datos=traz,
                motor="recomendacion_capital",
                tiene_ficha=_tiene_ficha(tk),
            )
        )
    return out


# ─── Ventas/Revisiones: envuelve señales de motor_salida ─────────────────────

_SENAL_ACCION = {
    "🔴 SALIR": ("VENDER", "CRITICA"),
    "🟠 REVISAR": ("REVISAR", "ALTA"),
    "🟡 ATENCIÓN": ("REVISAR", "MEDIA"),
}


def explicar_senales_salida(
    senales: list[dict] | None,
    *,
    precio_records: dict | None = None,
) -> list[RecomendacionExplicada]:
    """
    Convierte señales de ``motor_salida.evaluar_salida`` en recomendaciones
    explicadas. Las señales «⚪ EN CAMINO» no generan acción.
    """
    out: list[RecomendacionExplicada] = []
    for s in senales or []:
        senal = str(s.get("senal", "") or "")
        mapeo = _SENAL_ACCION.get(senal)
        if mapeo is None:
            continue
        accion, prioridad = mapeo
        tk = str(s.get("ticker", "") or "").upper()
        if not tk:
            continue
        disparadores = list(s.get("disparadores") or [])
        motivos = [
            Motivo(
                texto=f"{str(d.get('tipo', '')).strip()}: {str(d.get('detalle', '')).strip()}",
                origen="motor_salida",
            )
            for d in disparadores
        ]
        pnl = float(s.get("pnl_pct", 0) or 0)
        confianza, traz, advert = _confianza_precio(tk, precio_records)
        traz.update({"pnl_pct": pnl, "senal_motor": senal})
        n_disp = len(disparadores)
        tesis = (
            f"La posición acumula {pnl:+.1f}% y activó {n_disp} disparador(es) de salida."
            if n_disp
            else f"La posición acumula {pnl:+.1f}% y el motor sugiere {accion.lower()}."
        )
        out.append(
            RecomendacionExplicada(
                accion=accion,
                ticker=tk,
                prioridad=prioridad,
                tesis=tesis,
                motivos=motivos,
                confianza=confianza,
                advertencias=advert,
                datos=traz,
                motor="motor_salida",
                tiene_ficha=_tiene_ficha(tk),
            )
        )
    return out


# ─── Plan completo ────────────────────────────────────────────────────────────

def construir_plan_accion(
    *,
    perfil: str,
    rr: Any = None,
    senales: list[dict] | None = None,
    capital_ars: float | None = None,
    precio_records: dict | None = None,
) -> PlanAccion:
    """
    El "qué hago con mi plata" unificado: compras del motor de capital +
    ventas/revisiones del motor de salida, todo explicado y trazado.
    """
    comprar = explicar_compras(rr, precio_records=precio_records) if rr is not None else []
    vender = explicar_senales_salida(senales, precio_records=precio_records)
    alerta = ""
    if rr is not None and getattr(rr, "alerta_mercado", False):
        alerta = str(getattr(rr, "mensaje_alerta", "") or "Mercado en estrés: moderá el ritmo de entrada.")

    partes: list[str] = []
    if comprar:
        total = sum(float(r.monto_ars or 0) for r in comprar)
        partes.append(f"{len(comprar)} compra(s) sugerida(s) por ARS {total:,.0f}.")
    if vender:
        criticas = sum(1 for r in vender if r.prioridad == "CRITICA")
        partes.append(
            f"{len(vender)} posición(es) a revisar"
            + (f" ({criticas} con salida sugerida)" if criticas else "")
            + "."
        )
    if not partes:
        partes.append("Sin acciones sugeridas: tu cartera está alineada al plan.")
    bajas = sum(1 for r in comprar + vender if r.confianza == CONFIANZA_BAJA)
    if bajas:
        partes.append(f"{bajas} sugerencia(s) usan precios viejos — verificá antes de operar.")
    if alerta:
        partes.append(alerta)

    return PlanAccion(
        generado_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        perfil=str(perfil or "Moderado"),
        capital_ars=float(capital_ars) if capital_ars is not None else None,
        comprar=comprar,
        vender_revisar=vender,
        alerta_mercado=alerta,
        resumen=" ".join(partes),
    )


# ─── Audit trail (cierra el circuito que estaba sin cablear) ─────────────────

def auditar_plan(plan: PlanAccion, *, ctx: dict | None = None) -> int | None:
    """
    Persiste el plan completo (payload con motivos y trazabilidad) en
    recomendaciones_auditoria. Devuelve el id o None si falla — auditar
    nunca rompe el flujo del usuario.
    """
    try:
        from services.audit_trail import registrar_recomendacion_evento

        c = ctx or {}
        return registrar_recomendacion_evento(
            evento="PLAN_ACCION_EXPLICADO",
            origen="recomendador_explicable",
            cliente_id=c.get("cliente_id"),
            cliente_nombre=str(c.get("cliente_nombre", "")),
            tenant_id=str(c.get("tenant_id", "default") or "default"),
            actor=str(c.get("login_user", "") or ""),
            correlation_id=str(c.get("correlation_id", "") or ""),
            cartera=str(c.get("cartera_activa", "") or ""),
            perfil=plan.perfil,
            capital_ars=float(plan.capital_ars or 0),
            filas=plan.n_acciones,
            payload=plan.to_dict(),
        )
    except Exception as exc:
        _log.warning("auditar_plan falló (no bloquea): %s", exc)
        return None
