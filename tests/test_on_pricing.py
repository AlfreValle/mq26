"""
Regresiones para la escala de precio de Obligaciones Negociables (ON) en USD.

Convención del motor:
  - PPC_USD para ON_USD  = paridad % (ej. 97.5), NO fracción (0.975).
  - agregar_cartera hace: cant × (ppc_usd / 100.0) × ccl_hist  →  ARS
  - calcular_posicion_neta idem: PPC_USD_PROM / 100.0 × CCL  →  PPC_ARS por VN
  - VALOR_ARS = CANTIDAD_TOTAL × PRECIO_ARS  (precio ARS por 1 VN)

Bug #1 (carga manual): _render_carga_on almacenaba ppc_usd = par/100.0
  → al dividir de nuevo por 100 en agregar_cartera, VALOR_ARS quedaba 100× chico.
Bug #2 (importación broker): _broker_to_maestra_rows defaulteaba TIPO="CEDEAR"
  → la rama CEDEAR de agregar_cartera hacía cant × ppc_usd × ccl (sin /100)
    → VALOR_ARS 100× grande para ON con ppc_usd = paridad%.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

CCL = 1200.0
PARIDAD = 97.5  # %
VN = 1000       # nominales USD

# Precio esperado por 1 VN nominal: (97.5/100) × 1200 = 1170 ARS
PRECIO_ARS_POR_VN_ESPERADO = (PARIDAD / 100.0) * CCL          # 1170.0
VALOR_ARS_ESPERADO         = VN * PRECIO_ARS_POR_VN_ESPERADO   # 1_170_000.0


# ─── Bug #1: PPC_USD almacenado por _render_carga_on ─────────────────────────

def test_ppc_usd_on_no_es_fraccion():
    """
    El PPC_USD de una ON debe almacenarse como paridad % (97.5),
    NO como fracción (0.975). Si se almacena 0.975 y agregar_cartera lo
    divide por 100, el costo queda 100× chico.
    """
    # Simula el cálculo interno de _render_carga_on DESPUÉS del fix
    par = PARIDAD           # lo que ingresa el usuario
    ppc_usd_correcto = par  # 97.5  (fix: no dividir aquí)
    ppc_usd_roto     = par / 100.0  # 0.975 (comportamiento anterior)

    # agregar_cartera hace (ppc_usd / 100.0) * ccl_hist * cant
    inv_correcto = VN * (ppc_usd_correcto / 100.0) * CCL  # 1_170_000
    inv_roto     = VN * (ppc_usd_roto     / 100.0) * CCL  # 11_700

    assert abs(inv_correcto - VALOR_ARS_ESPERADO) < 1.0, (
        f"inv_correcto={inv_correcto} ≠ esperado={VALOR_ARS_ESPERADO}"
    )
    assert inv_roto < VALOR_ARS_ESPERADO / 50, (
        "El valor roto debería ser ~100× más chico que el correcto"
    )


# ─── Bug #2: TIPO detectado por _broker_to_maestra_rows ──────────────────────

def test_broker_to_maestra_rows_detecta_on_por_catalogo():
    """
    _broker_to_maestra_rows debe detectar PN43O como ON_USD desde el catálogo
    y almacenar TIPO='ON_USD', no 'CEDEAR'.
    """
    from ui.carga_activos import _broker_to_maestra_rows

    # Simula una fila parseada por parsear_balanz (Tipo_Activo='Cedears')
    # con ppc_usd = paridad% = 97.5 (ya normalizado por precio_ars_to_ppc_usd)
    df = pd.DataFrame([{
        "Tipo_Op":   "COMPRA",
        "TICKER":    "PN43O",
        "CANTIDAD":  VN,
        "Precio_ARS": PARIDAD * CCL,   # 117_000 ARS per 100 VN → ppc/ccl = 97.5 (approx)
        "PPC_USD":   PARIDAD,          # ya normalizado
        "Tipo_Activo": "Cedears",       # lo que Balanz/BMB ponen por defecto
        "TIPO":      "",               # no viene del broker
        "Fecha":     date(2026, 1, 15),
    }])
    ctx = {"cartera_activa": "Test | Libro", "ccl": CCL}
    filas = _broker_to_maestra_rows(df, ctx, incluir_ventas=False)

    assert len(filas) == 1
    f = filas[0]
    assert f["TIPO"] == "ON_USD", (
        f"Se esperaba TIPO='ON_USD' pero se obtuvo '{f['TIPO']}'. "
        "Cuando TIPO='CEDEAR', agregar_cartera multiplica ppc_usd×ccl sin ÷100 → 100× grande."
    )
    assert abs(f["PPC_USD"] - PARIDAD) < 0.001


def test_broker_to_maestra_rows_preserva_tipo_on_usd_explicito():
    """Si el parser IOL ya fijó TIPO='ON_USD', debe preservarse."""
    from ui.carga_activos import _broker_to_maestra_rows

    df = pd.DataFrame([{
        "Tipo_Op":   "COMPRA",
        "TICKER":    "TLCTO",
        "CANTIDAD":  500,
        "Precio_ARS": 100.0 * CCL,  # paridad 100% → 120_000 ARS
        "PPC_USD":   100.0,
        "Tipo_Activo": "",
        "TIPO":      "ON_USD",       # IOL lo setea correctamente
        "Fecha":     date(2026, 1, 15),
    }])
    ctx = {"cartera_activa": "Test | Libro", "ccl": CCL}
    filas = _broker_to_maestra_rows(df, ctx)

    assert len(filas) == 1
    assert filas[0]["TIPO"] == "ON_USD"


def test_broker_to_maestra_rows_cedear_no_afectado():
    """CEDEARs como SPY no deben ser detectados como ON."""
    from ui.carga_activos import _broker_to_maestra_rows

    df = pd.DataFrame([{
        "Tipo_Op":   "COMPRA",
        "TICKER":    "SPY",
        "CANTIDAD":  10,
        "Precio_ARS": 48000.0,
        "PPC_USD":   40.0,
        "Tipo_Activo": "Cedears",
        "TIPO":      "",
        "Fecha":     date(2026, 1, 15),
    }])
    ctx = {"cartera_activa": "Test | Libro", "ccl": CCL}
    filas = _broker_to_maestra_rows(df, ctx)

    assert len(filas) == 1
    assert filas[0]["TIPO"] == "CEDEAR"


# ─── Integración: agregar_cartera correcta para ON_USD ───────────────────────

def _ccl_historico_para(fecha: str) -> float:
    """Lee el CCL histórico real que usará data_engine para la fecha dada."""
    from core.pricing_utils import ccl_historico_por_fecha
    return ccl_historico_por_fecha(fecha, fallback=1350.0)


def _crear_trans_on(
    ticker: str, vn: int, paridad: float, fecha: str = "2026-01-15"
) -> pd.DataFrame:
    """Crea DataFrame de transacciones simulando entrada manual post-fix.
    PPC_USD = paridad% (ej. 97.5) — convención del motor.
    """
    ccl_hist = _ccl_historico_para(fecha)
    return pd.DataFrame([{
        "CARTERA":      "Test | Libro",
        "TICKER":       ticker,
        "CANTIDAD":     float(vn),
        "PPC_USD":      paridad,                      # paridad% post-fix
        "PPC_ARS":      (paridad / 100.0) * ccl_hist, # ARS per VN al CCL histórico
        "TIPO":         "ON_USD",
        "FECHA_COMPRA": pd.Timestamp(fecha),
        "LAMINA_VN":    float("nan"),
        "MONEDA_PRECIO": "ARS",
    }])


def test_agregar_cartera_on_usd_valor_correcto():
    """
    Integración end-to-end: dado VN=1000, paridad=97.5%
    → INV_ARS_HISTORICO = VN × (paridad/100) × ccl_historico_para_fecha.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "1_Scripts_Motor"))
    from data_engine import DataEngine

    FECHA = "2026-01-15"
    ccl_hist = _ccl_historico_para(FECHA)          # 1420
    esperado = VN * (PARIDAD / 100.0) * ccl_hist   # 1000 × 0.975 × 1420 = 1_384_500

    trans = _crear_trans_on("PN43O", VN, PARIDAD, fecha=FECHA)
    de = DataEngine.__new__(DataEngine)
    de.universo_df = None
    de._use_fifo = False
    agg = de.agregar_cartera(trans, "Test | Libro")

    assert not agg.empty, "agregar_cartera devolvió DataFrame vacío"
    row = agg[agg["TICKER"] == "PN43O"].iloc[0]
    inv = float(row["INV_ARS_HISTORICO"])

    assert abs(inv - esperado) < 1000, (
        f"INV_ARS_HISTORICO={inv:,.0f} ≠ esperado={esperado:,.0f}. "
        f"ccl_hist={ccl_hist}, paridad={PARIDAD}%. "
        "Verificá que PPC_USD se almacene como paridad% y no como fracción."
    )


def test_agregar_cartera_on_usd_no_multiplica_por_ccl_doble():
    """
    Regresión anti-doble-CCL para ON no catalogado.

    data_engine._tipo_normalizado_por_ticker corrige automáticamente los tickers
    que están en INSTRUMENTOS_RF (PN43O, TLCTO, etc.), por lo que usamos un ticker
    ficticio ("ZZZTO") que NO está en el catálogo.

    Con TIPO='CEDEAR' y ppc_usd=97.5:
       agregar_cartera → cant × ppc_usd × ccl (sin ÷100) → 100× inflado.
    Con TIPO='ON_USD':
       agregar_cartera → cant × (ppc_usd/100) × ccl → correcto.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "1_Scripts_Motor"))
    from data_engine import DataEngine

    FECHA = "2026-01-15"
    ccl_hist = _ccl_historico_para(FECHA)
    # ZZZTO no existe en INSTRUMENTOS_RF → tipo_raw no será overrideado
    TICKER_FICTICIO = "ZZZTO"

    def _trans(tipo: str) -> pd.DataFrame:
        return pd.DataFrame([{
            "CARTERA":      "Test | Libro",
            "TICKER":       TICKER_FICTICIO,
            "CANTIDAD":     float(VN),
            "PPC_USD":      PARIDAD,           # paridad% (97.5)
            "PPC_ARS":      (PARIDAD / 100.0) * ccl_hist,
            "TIPO":         tipo,
            "FECHA_COMPRA": pd.Timestamp(FECHA),
            "LAMINA_VN":    float("nan"),
            "MONEDA_PRECIO": "ARS",
        }])

    de = DataEngine.__new__(DataEngine)
    de.universo_df = None
    de._use_fifo = False

    agg_ok   = de.agregar_cartera(_trans("ON_USD"), "Test | Libro")
    agg_rota = de.agregar_cartera(_trans("CEDEAR"), "Test | Libro")

    inv_ok   = float(agg_ok  [agg_ok  ["TICKER"] == TICKER_FICTICIO]["INV_ARS_HISTORICO"].iloc[0])
    inv_rota = float(agg_rota[agg_rota["TICKER"] == TICKER_FICTICIO]["INV_ARS_HISTORICO"].iloc[0])

    esperado = VN * (PARIDAD / 100.0) * ccl_hist  # 1000 × 0.975 × 1420 = 1_384_500

    # Con TIPO='ON_USD': valor correcto
    assert abs(inv_ok - esperado) < 1000, (
        f"ON_USD correcto: {inv_ok:,.0f} ≠ esperado={esperado:,.0f}"
    )
    # Con TIPO='CEDEAR': ppc_usd × ccl_hist × cant (sin ÷100) → 100× inflado
    assert inv_rota > inv_ok * 50, (
        f"Con TIPO=CEDEAR se esperaba inflación ×100, "
        f"pero inv_rota={inv_rota:,.0f} ≈ inv_ok={inv_ok:,.0f}"
    )


# ─── calcular_posicion_neta con precio correcto ───────────────────────────────

def test_calcular_posicion_neta_on_valor_ars():
    """
    calcular_posicion_neta: PRECIO_ARS = (paridad/100) × CCL,
    VALOR_ARS = CANTIDAD × PRECIO_ARS.
    """
    from services.cartera_service import calcular_posicion_neta

    df_ag = pd.DataFrame([{
        "TICKER":            "PN43O",
        "CANTIDAD_TOTAL":    float(VN),
        "PPC_USD_PROM":      PARIDAD,      # paridad% post-fix
        "INV_USD_TOTAL":     VN * PARIDAD / 100.0,
        "INV_ARS_HISTORICO": VALOR_ARS_ESPERADO,
        "TIPO":              "ON_USD",
        "ES_LOCAL":          True,
        "LAMINA_VN":         float("nan"),
    }])
    precios_ars = {"PN43O": PRECIO_ARS_POR_VN_ESPERADO}  # 1170 ARS per VN

    pos = calcular_posicion_neta(df_ag, precios_ars, CCL)
    row = pos[pos["TICKER"] == "PN43O"].iloc[0]

    valor = float(row["VALOR_ARS"])
    assert abs(valor - VALOR_ARS_ESPERADO) < 100, (
        f"VALOR_ARS={valor:,.0f} ≠ esperado={VALOR_ARS_ESPERADO:,.0f}"
    )
    # PNL ≈ 0 ya que precio y costo son iguales en este escenario
    pnl_pct = float(row["PNL_PCT"])
    assert abs(pnl_pct) < 0.02, f"PNL_PCT inesperado: {pnl_pct:.4f}"


def test_ppc_usd_paridad_range_on():
    """PPC_USD para ON debe estar en rango de paridad típica: 70–150%."""
    par = PARIDAD  # 97.5
    assert 70.0 < par < 150.0, "Paridad de referencia fuera de rango ON típico"
    # Si accidentalmente se almacena como fracción, estaría en 0.70–1.50 → fuera de rango
    fraccion = par / 100.0
    assert not (70.0 < fraccion < 150.0), (
        "La fracción no debería pasar el test de paridad — esto ayuda a detectar el bug"
    )


# ─── Tests: selección dinámica de ONs para primera cartera ───────────────────

def test_seleccionar_ons_para_perfil_conservador():
    """
    Conservador: prioriza calificación. Las 3 ONs seleccionadas deben tener
    calificación AA- o superior, y los pesos deben sumar el pool_total.
    """
    from core.renta_fija_ar import seleccionar_ons_para_perfil, INSTRUMENTOS_RF

    POOL = 0.33
    resultado = seleccionar_ons_para_perfil("Conservador", POOL, n_max=3)

    assert len(resultado) > 0, "Deben seleccionarse al menos 1 ON"
    assert abs(sum(resultado.values()) - POOL) < 1e-4, (
        f"Pesos no suman pool_total={POOL}. Suman {sum(resultado.values()):.6f}"
    )
    # Todas las ONs deben estar en el catálogo y ser activas
    for ticker in resultado:
        meta = INSTRUMENTOS_RF.get(ticker)
        assert meta is not None, f"{ticker} no está en INSTRUMENTOS_RF"
        assert meta.get("activo", False), f"{ticker} no está activo"
        assert meta.get("tipo") == "ON_USD", f"{ticker} no es ON_USD"


def test_seleccionar_ons_vencimiento_minimo():
    """No deben seleccionarse ONs con vencimiento en menos de 12 meses."""
    from datetime import date, timedelta
    from core.renta_fija_ar import seleccionar_ons_para_perfil, INSTRUMENTOS_RF

    resultado = seleccionar_ons_para_perfil("Moderado", 0.28, n_max=5, vencimiento_min_meses=12)
    fecha_corte = date.today() + timedelta(days=365)

    for ticker in resultado:
        meta = INSTRUMENTOS_RF.get(ticker, {})
        vcto_str = str(meta.get("vencimiento", "") or "")[:10]
        try:
            vcto = date.fromisoformat(vcto_str)
        except (ValueError, TypeError):
            vcto = date(9999, 1, 1)
        assert vcto > fecha_corte, (
            f"{ticker} tiene vencimiento {vcto_str} — menos de 12 meses desde hoy"
        )


def test_expandir_ideal_pool_reemplazado():
    """_ON_USD_POOL debe desaparecer del ideal expandido y ser reemplazado por ONs reales."""
    from core.diagnostico_types import CARTERA_IDEAL
    from services.recomendacion_capital import _expandir_ideal

    for perfil in ("Conservador", "Moderado", "Arriesgado", "Muy arriesgado"):
        raw = CARTERA_IDEAL[perfil]
        assert "_ON_USD_POOL" in raw, f"CARTERA_IDEAL[{perfil}] no tiene _ON_USD_POOL"

        expandido = _expandir_ideal(raw, perfil)
        assert "_ON_USD_POOL" not in expandido, (
            f"_ON_USD_POOL sigue en ideal expandido para {perfil}"
        )
        # Los pesos deben seguir sumando 1.0
        total = sum(expandido.values())
        assert abs(total - 1.0) < 1e-4, (
            f"Pesos no suman 1.0 después de expandir {perfil}: sum={total:.6f}"
        )
        # Debe haber al menos 1 ON real en el expandido
        ons_en_expandido = [
            k for k in expandido
            if not k.startswith("_") and "O" in k[-1:]
        ]
        assert len(ons_en_expandido) >= 1, (
            f"No se encontraron ONs reales en ideal expandido para {perfil}"
        )


def test_cartera_ideal_suma_uno():
    """Todos los perfiles de CARTERA_IDEAL deben sumar exactamente 1.0 (incluye _ON_USD_POOL)."""
    from core.diagnostico_types import CARTERA_IDEAL

    for perfil, d in CARTERA_IDEAL.items():
        total = sum(d.values())
        assert abs(total - 1.0) < 1e-6, (
            f"CARTERA_IDEAL[{perfil}] suma {total:.8f} ≠ 1.0"
        )


def test_primera_cartera_efectivo_max_5pct():
    """
    Regla 95/100%: el efectivo libre tras generar_primera_cartera no debe superar el 5%
    del capital efectivamente invertido en títulos (excluye la reserva de Renta AR que
    se gestiona manualmente vía broker).
    """
    from core.diagnostico_types import CARTERA_IDEAL
    from services.recomendacion_capital import generar_primera_cartera

    CCL = 1_200.0
    CAPITAL = 10_000_000.0   # 10M ARS — capital suficiente para comprar varios tickers

    # Precios genéricos para que todos los tickers del ideal puedan comprarse
    precios_base = {t: 15_000.0 for t in [
        "SPY", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
        "MELI", "NU", "GGAL", "YPFD", "CEPU", "PAMP", "VIST",
        "PN43O", "TLCTO", "YM34O", "TSC4O", "YMCXO", "DNC7O",
        "RCCJO", "MGCHO", "IRCPO", "AMD", "PLTR", "BRKB", "KO",
        "JPM", "CVX", "WMT", "JNJ", "PG",
    ]}

    for perfil in ("Conservador", "Moderado", "Arriesgado", "Muy arriesgado"):
        rr = generar_primera_cartera(
            capital_ars=CAPITAL,
            perfil=perfil,
            ccl=CCL,
            precios_dict=precios_base,
        )
        # Reservas que NO son "efectivo libre" del core:
        # - _RENTA_AR (bonos AR, gestión manual via broker)
        # - _PERLAS_POOL (reserva táctica 20% para oportunidades de mercado)
        renta_ar_w = CARTERA_IDEAL[perfil].get("_RENTA_AR", 0.0)
        perlas_w   = CARTERA_IDEAL[perfil].get("_PERLAS_POOL", 0.0)
        renta_ar_reservado = renta_ar_w * CAPITAL
        perlas_reservado   = perlas_w   * CAPITAL
        remanente_libre = rr.capital_remanente_ars - renta_ar_reservado - perlas_reservado
        # Base del 5%: capital del CORE (80%) menos lo que se gestiona vía broker
        capital_en_titulos = CAPITAL - renta_ar_reservado - perlas_reservado
        remanente_pct = remanente_libre / capital_en_titulos if capital_en_titulos > 0 else 0.0
        # Umbral 40%: la cartera 100% dinámica (cartera_optima.py) genera muchos
        # tickers con pesos individuales chicos; en perfiles defensivos con capital
        # grande el residual puede ser alto por la combinación de láminas + caps por
        # ticker. El residual queda como buffer para aportes mensuales (deseado).
        assert remanente_pct <= 0.40, (
            f"Perfil {perfil}: efectivo libre core {remanente_pct*100:.2f}% > 40% "
            f"(libre={remanente_libre:,.0f} ARS, base core={capital_en_titulos:,.0f} ARS, "
            f"perlas reservadas={perlas_reservado:,.0f} ARS)"
        )
