"""
services/recomendacion_capital.py — Motor de Recomendación de Capital Nuevo (S5)

Dado capital disponible, propone compras (ticker + unidades enteras) priorizadas.

SIN streamlit. SIN yfinance (precios vía precios_dict; estrés vía market_stress inyectado).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from config import TICKERS_NO_CEDEAR_BYMA

logger = logging.getLogger(__name__)

from core.diagnostico_types import (
    CARTERA_IDEAL,
    CLASIFICACION_ACTIVOS,
    LIMITE_CONCENTRACION,
    RENTA_AR_PENDIENTE_MSG,
    CategoriaActivo,
    ItemRecomendacion,
    PrioridadAccion,
    RecomendacionResult,
    perfil_diagnostico_valido,
)
from core.perfil_allocation import target_rv_efectivo
from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    es_renta_fija,
    seleccionar_ons_para_perfil,
)
from services.cartera_service import resolver_precios
from services.diagnostico_cartera import _pct_rf_actual, _piso_defensivo_requerido
from services.favoritos_mes import aplicar_prioridad_favoritos, load_favoritos_mes

# ── Scoring estático por sector (proxy sin yfinance) ─────────────────────────
# Refleja SCORE_SECTORIAL_BASE de scoring_engine.py más contexto macro 2026.
_SCORE_SECTOR_ESTATICO: dict[str, float] = {
    "Tecnología":      75.0,
    "Salud":           78.0,
    "Consumo Def.":    72.0,
    "Consumo Ciclico": 69.0,   # MCD, SBUX, COST → defensivos cíclicos de calidad
    "Comunicaciones":  74.0,   # META, MELI, BABA, T, VZ → plataformas digitales
    "Defensa":         80.0,
    "Energía":         65.0,
    "Energía Local":   62.0,
    "Financiero":      70.0,
    "Materiales":      60.0,
    "Industria":       64.0,
    "Real Estate":     63.0,
    "E-Commerce":      73.0,
    "ETF":             74.0,
    "Cobertura":       70.0,
    "Bono USD":        63.0,
    "ON Corporativa":  61.0,
    "Acción Local":    58.0,
    "Internacional":   68.0,
    "Otros":           50.0,
}

# ── Overrides individuales de score (alta convicción, se suman al sector base) ─
# Tickers con calidad diferencial que deben tener prioridad dentro de su sector.
# Escala 0-100 idéntica a Score_Total del motor 60/20/20.
_SCORE_TICKER_OVERRIDE: dict[str, float] = {
    # ── Tech quality ─────────────────────────────────────────────────────────
    "MSFT":  88.0,   # Microsoft — nube + IA, el mejor tech defensivo-agresivo
    "AAPL":  84.0,   # Apple — ecosistema premium, flujo de caja bestial
    "NVDA":  87.0,   # NVIDIA — líder GPUs, IA datacenter
    "GOOGL": 83.0,   # Alphabet — buscador + Cloud + YouTube
    "META":  82.0,   # Meta — 3B+ usuarios, pivot IA, publicidad dominante
    "AMZN":  85.0,   # Amazon — AWS cloud + e-commerce global
    # ── Comunicaciones / E-Commerce ──────────────────────────────────────────
    "MELI":  84.0,   # MercadoLibre — líder LATAM e-commerce + fintech
    "BABA":  76.0,   # Alibaba — e-commerce masivo China, descuento regulatorio ya en precio
    "NU":    78.0,   # Nubank — neobank 100M clientes, crecimiento Brazil/Mx
    # ── Financiero quality ────────────────────────────────────────────────────
    "BRKB":  86.0,   # Berkshire Hathaway — Buffett, 60+ empresas, cash masivo
    "V":     85.0,   # Visa — duopolio pagos digitales, cuasi-monopolio
    "MA":    84.0,   # Mastercard — ídem Visa, sin riesgo crediticio
    "JPM":   82.0,   # JPMorgan — banco líder EEUU, retorno sobre capital top
    # ── Consumo / defensivo ───────────────────────────────────────────────────
    "MCD":   80.0,   # McDonald's — franquicia global, dividendo creciente, defensivo
    "KO":    77.0,   # Coca-Cola — dividendo rey, 60+ años consecutivos
    "PG":    76.0,   # Procter & Gamble — consumo esencial, pricing power
    "COST":  79.0,   # Costco — modelo membresía, moat real, bajo beta
    "WMT":   75.0,   # Walmart — retailer global defensivo
    # ── Salud ─────────────────────────────────────────────────────────────────
    "ABBV":  80.0,   # AbbVie — dividendo alto, pipeline sólido
    "JNJ":   78.0,   # J&J — pharma + devices, defensivo
    "MDT":   76.0,   # Medtronic — medical devices, dividend aristocrat
    # ── Energía ───────────────────────────────────────────────────────────────
    "CVX":   74.0,   # Chevron — oil integrado, dividendo creciente
    # ── Growth agresivo ───────────────────────────────────────────────────────
    "PLTR":  77.0,   # Palantir — IA + gobierno, growth volátil
    "TSLA":  72.0,   # Tesla — EV + autonomía, beta alto
    "AMD":   80.0,   # AMD — GPUs + CPUs, alternativa NVIDIA en IA
    "UBER":  75.0,   # Uber — plataforma movilidad + delivery, primera vez rentable
    # ── LATAM / regional ──────────────────────────────────────────────────────
    "VIST":  74.0,   # Vista Energy — Vaca Muerta, crecimiento upstream
    "GGAL":  70.0,   # Grupo Galicia — banco líder Argentina
    "YPFD":  68.0,   # YPF — energía estatal AR, Vaca Muerta
    # ── Tickers con score explícito por debajo del sector promedio ────────────
    # (Evita que ocupen cupos de tickers de mayor convicción)
    "HAPV3": 60.0,   # Hapvida BR — salud brasileña, calidad media, mercado local
    "HIMS":  57.0,   # Hims & Hers — telehealth startup, alta volatilidad
    "BB":    52.0,   # BlackBerry — legacy, bajo crecimiento
    "HUT":   50.0,   # Hut 8 Mining — crypto miner, especulativo
    "ATAD":  55.0,   # Sociedad Argentina — holdco local, liquidez baja
}

# Multiplicador de score por sector según perfil de riesgo
_SECTOR_BIAS_RV: dict[str, dict[str, float]] = {
    "Conservador": {
        "Consumo Def.":    2.0, "Salud":          1.9,
        "Financiero":      1.7, "Comunicaciones":  1.4,
        "Consumo Ciclico": 1.4, "ETF":             1.5,
        "Cobertura":       1.5, "Defensa":         1.3,
        "Industria":       1.1, "Energía":         1.0,
        "Tecnología":      0.8, "E-Commerce":      0.7,
        "Acción Local":    0.4, "Energía Local":   0.4,
    },
    "Moderado": {
        "Tecnología":      1.6, "E-Commerce":      1.5,
        "Comunicaciones":  1.5, "Salud":           1.3,
        "Consumo Def.":    1.3, "Financiero":      1.3,
        "Consumo Ciclico": 1.2, "ETF":             1.1,
        "Acción Local":    1.0, "Energía Local":   1.0,
        "Energía":         0.9, "Defensa":         0.9,
    },
    "Arriesgado": {
        "Tecnología":      2.0, "Comunicaciones":  1.9,
        "E-Commerce":      1.9, "Acción Local":    1.7,
        "Energía Local":   1.6, "Financiero":      1.3,
        "Energía":         1.2, "Consumo Ciclico": 1.0,
        "ETF":             0.8, "Consumo Def.":    0.7,
        "Salud":           0.7,
    },
    "Muy arriesgado": {
        "Tecnología":      2.5, "Comunicaciones":  2.0,
        "E-Commerce":      2.0, "Acción Local":    2.0,
        "Energía Local":   2.0, "Defensa":         1.5,
        "Financiero":      1.4, "Energía":         1.2,
        "Consumo Ciclico": 0.8, "ETF":             0.5,
        "Consumo Def.":    0.5, "Salud":           0.5,
    },
}

# N° máximo de CEDEARs/acciones por perfil
_N_MAX_RV: dict[str, int] = {
    "Conservador": 14, "Moderado": 16, "Arriesgado": 18, "Muy arriesgado": 20,
}

# N° máximo de tickers por sector (más amplio en perfiles agresivos para diversificación)
_MAX_POR_SECTOR_RV: dict[str, int] = {
    "Conservador": 3, "Moderado": 3, "Arriesgado": 4, "Muy arriesgado": 5,
}

# Sectores de acciones AR (Merval) — incluidos en perfiles agresivos
_SECTORES_MERVAL = frozenset({"Acción Local", "Energía Local"})


def _seleccionar_rv_para_perfil(
    perfil: str,
    peso_rv_total: float,
    df_scores: pd.DataFrame | None = None,
    n_max: int | None = None,
    max_por_sector: int | None = None,
    score_minimo: float = 45.0,
    excluir: set[str] | None = None,
    precios_ars: dict[str, float] | None = None,
    capital_pool_ars: float = 0.0,
) -> dict[str, float]:
    """
    Selecciona los mejores CEDEARs/acciones para el perfil dado.

    Dos rutas:
    1. **Con df_scores** (scanner 60/20/20 ya ejecutado):
       Usa Score_Total real (0-100) + bias de sector por perfil.
    2. **Sin df_scores** (fallback rápido, sin yfinance):
       Usa _SCORE_SECTOR_ESTATICO × _SECTOR_BIAS_RV sobre el universo CEDEAR completo.

    Constraints:
      - Máx. `max_por_sector` tickers por sector (diversificación).
      - Mínimo score efectivo = score_minimo.
      - Acciones AR (Merval) solo para Arriesgado / Muy arriesgado.

    Devuelve {ticker: peso} con pesos sumando ≈ peso_rv_total.
    """
    from config import SECTORES, TICKERS_NO_CEDEAR_BYMA, UNIVERSO_CEDEARS_SCORING
    try:
        from config import UNIVERSO_MERVAL_SCORING
    except ImportError:
        UNIVERSO_MERVAL_SCORING = []  # type: ignore[no-redef]

    n_max = n_max or _N_MAX_RV.get(perfil, 12)
    max_por_sector = max_por_sector if max_por_sector is not None else _MAX_POR_SECTOR_RV.get(perfil, 3)
    bias = _SECTOR_BIAS_RV.get(perfil, {})
    incluir_merval = perfil in ("Arriesgado", "Muy arriesgado")
    _excluir = {str(t).upper() for t in (excluir or set())}

    candidatos: list[tuple[str, float, str]] = []   # (ticker, score_efectivo, sector)

    # ── Ruta A: df_scores disponible ─────────────────────────────────────────
    if df_scores is not None and not df_scores.empty and "Score_Total" in df_scores.columns:
        col_ticker = next(
            (c for c in df_scores.columns if c.upper() in ("TICKER", "ACTIVO")), None
        )
        col_sector = next(
            (c for c in df_scores.columns if c.upper() == "SECTOR"), None
        )
        if col_ticker:
            for _, row in df_scores.iterrows():
                ticker = str(row[col_ticker]).upper().strip()
                if ticker in TICKERS_NO_CEDEAR_BYMA or ticker in _excluir:
                    continue
                tipo = str(row.get("Tipo", row.get("TIPO", "CEDEAR"))).strip()
                es_merval = tipo in ("Acción Local", "Merval") or ticker in UNIVERSO_MERVAL_SCORING
                if es_merval and not incluir_merval:
                    continue
                sector = str(row[col_sector]).strip() if col_sector else SECTORES.get(ticker, "Otros")
                score_base = float(row["Score_Total"] or 0)
                score_ef = score_base * bias.get(sector, 1.0)
                if score_ef >= score_minimo * bias.get(sector, 1.0):
                    candidatos.append((ticker, score_ef, sector))

    # ── Ruta B: fallback estático (sin yfinance) ──────────────────────────────
    if not candidatos:
        universo = list(UNIVERSO_CEDEARS_SCORING)
        if incluir_merval:
            universo += [t for t in UNIVERSO_MERVAL_SCORING if t not in universo]
        for ticker in universo:
            if ticker in TICKERS_NO_CEDEAR_BYMA or ticker in _excluir:
                continue
            es_merval = ticker in UNIVERSO_MERVAL_SCORING
            if es_merval and not incluir_merval:
                continue
            sector = SECTORES.get(ticker, "Otros")
            # Override individual tiene prioridad sobre el promedio sectorial
            score_base = _SCORE_TICKER_OVERRIDE.get(
                ticker, _SCORE_SECTOR_ESTATICO.get(sector, 50.0)
            )
            score_ef = score_base * bias.get(sector, 1.0)
            if score_ef >= score_minimo:
                candidatos.append((ticker, score_ef, sector))

    if not candidatos:
        return {}

    # ── Filtro de ACCESIBILIDAD por precio ────────────────────────────────────
    # Un ticker es "accesible" si su precio unitario cabe al menos 1 vez
    # dentro de su peso target en ARS. Sino, el motor lo descartaría más
    # adelante en `generar_primera_cartera` y dejaría un peso vacío.
    #
    # Criterio: precio_unit <= peso_target_estimado × capital_pool × tolerancia.
    # tolerancia = 1.5x para permitir tickers un poco por encima del target
    # (mejor 1 unidad de un ticker valioso que 0).
    if precios_ars and capital_pool_ars > 0 and len(candidatos) > 0:
        n_estimado = min(n_max, len(candidatos))
        peso_promedio = float(peso_rv_total) / n_estimado if n_estimado > 0 else 0
        target_promedio_ars = capital_pool_ars * peso_promedio
        precio_max_aceptable = target_promedio_ars * 1.5

        _filtrados: list[tuple[str, float, str]] = []
        _descartados_por_precio: list[str] = []
        for ticker, score_ef, sector in candidatos:
            px = float(precios_ars.get(ticker, 0) or 0)
            if px > 0 and px > precio_max_aceptable:
                _descartados_por_precio.append(ticker)
                continue
            _filtrados.append((ticker, score_ef, sector))

        if _descartados_por_precio:
            logger.info(
                "RV: %d ticker(s) descartados por precio inaccesible "
                "(precio > %.0f ARS, target ~%.0f ARS): %s",
                len(_descartados_por_precio), precio_max_aceptable,
                target_promedio_ars, ", ".join(_descartados_por_precio[:5]),
            )

        # Solo aplicar el filtro si quedan suficientes candidatos
        if len(_filtrados) >= max(3, n_max // 2):
            candidatos = _filtrados

    # ── Selección con constraint de sector ────────────────────────────────────
    candidatos.sort(key=lambda x: -x[1])
    por_sector: dict[str, int] = {}
    seleccionados: list[tuple[str, float]] = []

    for ticker, score_ef, sector in candidatos:
        if len(seleccionados) >= n_max:
            break
        cnt = por_sector.get(sector, 0)
        if cnt >= max_por_sector:
            continue
        por_sector[sector] = cnt + 1
        seleccionados.append((ticker, score_ef))

    if not seleccionados:
        return {}

    # ── Distribución de pesos proporcional al score efectivo ─────────────────
    total_score = sum(s for _, s in seleccionados)
    n_sel = len(seleccionados)
    peso_min = float(peso_rv_total) / (n_sel * 3)   # piso: cada ticker recibe al menos 1/3 del avg
    peso_max = float(peso_rv_total) / n_sel * 2.5   # techo: ninguno supera 2.5× el avg

    pesos_raw = {
        tk: min(peso_max, max(peso_min, float(peso_rv_total) * sc / total_score))
        for tk, sc in seleccionados
    }
    # Renormalizar para que sumen exactamente peso_rv_total
    total_raw = sum(pesos_raw.values())
    factor = float(peso_rv_total) / total_raw if total_raw > 0 else 1.0
    pesos = {tk: round(p * factor, 6) for tk, p in pesos_raw.items()}

    # Corrección de redondeo al primero
    diff = round(float(peso_rv_total) - sum(pesos.values()), 6)
    if abs(diff) > 1e-7 and seleccionados:
        pesos[seleccionados[0][0]] = round(pesos[seleccionados[0][0]] + diff, 6)

    return pesos


def _lamina_min_on(ticker: str) -> int:
    """
    Devuelve la lámina mínima en VN USD de una ON del catálogo.
    Si no está en el catálogo o no es ON_USD, devuelve 1.
    """
    meta = INSTRUMENTOS_RF.get(str(ticker).upper())
    if not meta or str(meta.get("tipo", "")).upper() != "ON_USD":
        return 1
    try:
        return int(meta.get("lamina_min") or 1)
    except (TypeError, ValueError):
        return 1


def _expandir_ideal(
    ideal: dict[str, float],
    perfil: str,
    n_max_ons: int = 3,
    df_scores: pd.DataFrame | None = None,
    capital_ars: float = 0.0,
    ccl: float = 1.0,
    precios_ars: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Expande los pools dinámicos del dict ideal:

    - ``_ON_USD_POOL``    → seleccionar_ons_para_perfil()  (core/renta_fija_ar.py)
    - ``_RV_CEDEAR_POOL`` → _seleccionar_rv_para_perfil()  (este módulo)

    Parámetros opcionales ``capital_ars`` y ``ccl`` permiten calcular la lámina
    máxima comprable (``lamina_max_usd``) para evitar recomendar ONs cuyo mínimo
    de negociación supera el capital asignado a renta fija.

    Si ningún pool está presente, devuelve una copia sin cambios.
    """
    resultado = dict(ideal)

    # ── Reserva táctica de Perlas (20%) — queda como efectivo hasta oportunidad ──
    # El pool se retira del ideal para que el motor de compras no lo asigne
    # a tickers regulares. Se devuelve como "_PERLAS_POOL" para que
    # generar_primera_cartera lo trate como capital reservado aparte.
    # No se expande acá: la selección de perlas ocurre en generar_primera_cartera.
    if "_PERLAS_POOL" in resultado:
        pass  # se mantiene en resultado para que generar_primera_cartera lo detecte

    # ── ONs dinámicas ─────────────────────────────────────────────────────────
    if "_ON_USD_POOL" in resultado:
        peso_on = float(resultado.pop("_ON_USD_POOL"))
        # Calcular lámina máxima comprable: cada ON debe poder comprarse
        # al menos 1 lote completo dentro de su peso individual.
        lamina_max: int | None = None
        if capital_ars > 0 and ccl > 0:
            capital_on_usd = capital_ars * peso_on / ccl
            # peso individual = pool / n_max_ons → cada ON tiene ~capital_on_usd/n_max disponible
            capital_por_on_usd = capital_on_usd / max(1, n_max_ons)
            # Tolerancia: hasta 1.5x el target (similar al filtro RV)
            lamina_max = max(1, int(capital_por_on_usd * 1.5))
        ons = seleccionar_ons_para_perfil(
            perfil, peso_on, n_max=n_max_ons, lamina_max_usd=lamina_max
        )
        if ons:
            resultado.update(ons)

    # ── RV dinámica (CEDEARs + acciones) ─────────────────────────────────────
    if "_RV_CEDEAR_POOL" in resultado:
        peso_rv = float(resultado.pop("_RV_CEDEAR_POOL"))
        # Excluir tickers ya asignados (anclas SPY/QQQ + ONs dinámicas + _RENTA_AR)
        ya_asignados = {k for k in resultado if not k.startswith("_")}

        # Limitar número de tickers RV por capital disponible.
        # Regla: 1 ticker nuevo por cada USD 500 en RV, entre 4 y 10.
        # Esto evita micro-posiciones irrelevantes en carteras pequeñas.
        n_max_rv: int | None = None
        if capital_ars > 0 and ccl > 0:
            capital_rv_usd = capital_ars * peso_rv / ccl
            n_max_rv = max(4, min(10, int(capital_rv_usd / 500)))

        capital_rv_ars = capital_ars * peso_rv if capital_ars > 0 else 0
        rv = _seleccionar_rv_para_perfil(
            perfil, peso_rv, df_scores=df_scores,
            excluir=ya_asignados, n_max=n_max_rv,
            precios_ars=precios_ars,
            capital_pool_ars=capital_rv_ars,
        )
        if rv:
            resultado.update(rv)

    return resultado


def _enriquecer_precios_recomendacion(
    precios_dict: dict[str, float],
    perfil: str,
    ccl: float,
    universo_df: pd.DataFrame | None,
    favoritos_mes: dict[str, Any] | None,
    df_scores: pd.DataFrame | None = None,
) -> dict[str, float]:
    """
    El contexto suele traer solo cotizaciones de la cartera; el modelo ideal incluye ON/RV
    que hay que poder cotizar para armar órdenes enteras.
    """
    base = {str(k).upper(): float(v) for k, v in (precios_dict or {}).items()}
    ideal = _expandir_ideal(CARTERA_IDEAL.get(perfil, CARTERA_IDEAL["Moderado"]), perfil, df_scores=df_scores)
    extras: set[str] = {str(k).upper() for k in ideal if k and not str(k).startswith("_")}
    if favoritos_mes:
        extras |= {str(x).upper() for x in (favoritos_mes.get("rf") or []) if x}
        extras |= {str(x).upper() for x in (favoritos_mes.get("rv") or []) if x}
    need = sorted(t for t in extras if base.get(t, 0) <= 0)
    if not need:
        return base
    resolved = resolver_precios(need, base, ccl, universo_df)
    out = dict(base)
    for k, v in resolved.items():
        ku = str(k).upper()
        fv = float(v or 0)
        if fv > 0:
            out[ku] = fv
    return out


def _pct_defensivo_from_df(df_ag: pd.DataFrame, universo_df: pd.DataFrame | None) -> float:
    """Fracción renta fija (campo histórico pct_defensivo_*)."""
    return _pct_rf_actual(df_ag, universo_df)


def _renta_ar_peso_actual(df_ag: pd.DataFrame, universo_df: pd.DataFrame | None) -> float:
    if df_ag is None or df_ag.empty:
        return 0.0
    if "VALOR_ARS" not in df_ag.columns:
        return 0.0
    vt = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum())
    if vt <= 0:
        return 0.0
    acc = 0.0
    for _, row in df_ag.iterrows():
        tipo = str(row.get("TIPO", "") or "").upper()
        tu = tipo
        if universo_df is not None and not universo_df.empty and "TICKER" in universo_df.columns:
            m = universo_df[universo_df["TICKER"].astype(str).str.upper() == _ticker_u(row)]
            if not m.empty:
                tu = str(m.iloc[0].get("TIPO", "") or "").upper()
        if tu in ("ON", "ON_USD") or tipo in ("ON", "ON_USD"):
            va = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
            acc += va
    return acc / vt


def _ticker_u(row: pd.Series) -> str:
    return str(row.get("TICKER", "") or "").strip().upper()


def _nombre_legible(ticker: str, universo_df: pd.DataFrame | None) -> str:
    if universo_df is None or universo_df.empty or "TICKER" not in universo_df.columns:
        return ticker
    tu = ticker.upper()
    m = universo_df[universo_df["TICKER"].astype(str).str.upper() == tu]
    if m.empty:
        return ticker
    for col in ("NOMBRE", "DENOMINACION", "Nombre", "nombre"):
        if col in m.columns:
            v = m.iloc[0].get(col)
            if v and str(v).strip():
                return str(v).strip()[:80]
    return ticker


def _mod23_score_100(ticker: str, df_analisis: pd.DataFrame | None) -> float:
    if df_analisis is None or df_analisis.empty or "TICKER" not in df_analisis.columns:
        return 0.0
    m = df_analisis[df_analisis["TICKER"].astype(str).str.upper() == ticker.upper()]
    if m.empty or "PUNTAJE_TECNICO" not in m.columns:
        return 0.0
    try:
        p = float(m.iloc[0]["PUNTAJE_TECNICO"])
    except (TypeError, ValueError):
        return 0.0
    return p * 10.0


def _es_compra_defensiva(ticker: str) -> bool:
    """Prioridad “core” para cubrir déficit RF: instrumentos de renta fija cotizables."""
    return es_renta_fija(ticker)


def _alerta_mercado(market_stress: dict[str, Any] | None) -> tuple[bool, str]:
    if not market_stress:
        return False, ""
    vix = market_stress.get("vix")
    dd = market_stress.get("spy_drawdown_30d")
    if vix is not None and float(vix) > 30:
        return True, "Mercado en tensión (VIX elevado) — considerá esperar o invertir con cautela."
    if dd is not None and float(dd) <= -0.15:
        return True, "Mercado en tensión (fuerte caída reciente) — considerá esperar."
    return False, ""


def recomendar(
    df_ag: pd.DataFrame,
    perfil: str,
    horizonte_label: str,
    capital_ars: float,
    ccl: float,
    precios_dict: dict[str, float],
    diagnostico: Any | None,
    universo_df: pd.DataFrame | None = None,
    *,
    df_analisis: pd.DataFrame | None = None,
    market_stress: dict[str, Any] | None = None,
    cliente_nombre: str = "",
    favoritos_mes: dict[str, Any] | None = None,
) -> RecomendacionResult:
    fecha = date.today().isoformat()
    perfil_n = perfil_diagnostico_valido(perfil)
    ccl_f = float(ccl or 0.0)
    cap = max(0.0, float(capital_ars or 0.0))
    if ccl_f <= 0:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=cap,
            capital_disponible_usd=0.0,
            ccl=0.0,
            fecha_recomendacion=fecha,
            alerta_mercado=True,
            mensaje_alerta="CCL inválido. No se puede calcular recomendación confiable.",
            resumen_recomendacion=_trunc("CCL inválido. Revisá el dato de mercado antes de recomendar.", 200),
            pct_defensivo_pre=_pct_defensivo_from_df(df_ag, universo_df),
        )
    capital_usd = cap / ccl_f

    alerta, msg_alerta = _alerta_mercado(market_stress)
    if alerta:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=cap,
            capital_disponible_usd=capital_usd,
            ccl=ccl_f,
            fecha_recomendacion=fecha,
            alerta_mercado=True,
            mensaje_alerta=msg_alerta,
            resumen_recomendacion=_trunc(msg_alerta, 200),
            pct_defensivo_pre=_pct_defensivo_from_df(df_ag, universo_df),
        )

    if cap <= 0:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=0.0,
            capital_disponible_usd=0.0,
            ccl=ccl_f,
            fecha_recomendacion=fecha,
            pct_defensivo_pre=_pct_defensivo_from_df(df_ag, universo_df),
            resumen_recomendacion="Ingresá un capital mayor a cero para obtener sugerencias.",
        )

    if df_ag is None:
        df_ag = pd.DataFrame()

    fav_doc = load_favoritos_mes() if favoritos_mes is None else favoritos_mes
    fav_rf = list(fav_doc.get("rf") or [])
    fav_rv = list(fav_doc.get("rv") or [])

    precios_dict = _enriquecer_precios_recomendacion(
        precios_dict or {}, perfil_n, ccl_f, universo_df, fav_doc
    )

    # recomendar() no recibe df_scores: usa fallback estático por sector para _RV_CEDEAR_POOL
    ideal = _expandir_ideal(CARTERA_IDEAL.get(perfil_n, CARTERA_IDEAL["Moderado"]), perfil_n)
    total_valor = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()) if not df_ag.empty else 0.0

    peso_actual: dict[str, float] = {}
    tickers_hold: set[str] = set()
    if not df_ag.empty and total_valor > 0:
        for _, row in df_ag.iterrows():
            t = _ticker_u(row)
            tickers_hold.add(t)
            va = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
            peso_actual[t] = peso_actual.get(t, 0.0) + va / total_valor

    renta_ar_act = _renta_ar_peso_actual(df_ag, universo_df)
    peso_actual["_RENTA_AR"] = renta_ar_act

    piso = _piso_defensivo_requerido(perfil_n, horizonte_label)
    if diagnostico is not None:
        pct_def_pre = float(
            getattr(diagnostico, "pct_defensivo_actual", _pct_defensivo_from_df(df_ag, universo_df))
        )
    else:
        pct_def_pre = _pct_defensivo_from_df(df_ag, universo_df)
    deficit_def = pct_def_pre + 1e-9 < piso
    target_rv_goal = target_rv_efectivo(perfil_n, horizonte_label)

    limite = LIMITE_CONCENTRACION.get(perfil_n, 0.25)
    concentrado = ""
    max_p = 0.0
    for t, w in peso_actual.items():
        if t.startswith("_"):
            continue
        if w > max_p:
            max_p = w
            concentrado = t
    hay_concentracion = max_p > limite + 1e-6 and concentrado

    pendientes: list[dict[str, Any]] = []
    delta_ideal: dict[str, float] = {}
    renta_ar_gap = 0.0
    for tk, ideal_w in ideal.items():
        if tk == "_RENTA_AR":
            renta_ar_gap = float(ideal_w) - renta_ar_act
            continue
        act = peso_actual.get(tk.upper(), 0.0)
        d = float(ideal_w) - act
        if d > 1e-6:
            delta_ideal[tk.upper()] = d

    # ── Garantizar inclusión de favoritos RV aunque no quedaran en el pool ideal ──
    # (El pool dinámico selecciona max N tickers por sector; un favorito puede quedar afuera)
    from config import TICKERS_NO_CEDEAR_BYMA as _NO_BYMA
    _ref_delta = (sum(delta_ideal.values()) / len(delta_ideal)) if delta_ideal else 0.05
    for _t in fav_rv:
        _tu = str(_t).upper()
        if _tu in delta_ideal or _tu in tickers_hold or _tu in _NO_BYMA:
            continue
        _px = float(precios_dict.get(_tu, precios_dict.get(_tu.upper(), 0.0)) or 0.0)
        if _px > 0:
            delta_ideal[_tu] = min(_ref_delta, 0.10)  # delta simbólico para activar compra

    if renta_ar_gap > 1e-6:
        def _px(t: str) -> float:
            return float(precios_dict.get(t, precios_dict.get(t.upper(), 0.0)) or 0.0)
        tiene_rf_cotizable = any(
            _es_compra_defensiva(kt)
            and float(delta_ideal.get(kt, 0.0)) > 1e-6
            and _px(kt) > 0
            for kt in delta_ideal
        )
        if not tiene_rf_cotizable:
            pendientes.append({
                "ticker": "_RENTA_AR",
                "precio_ars": 0.0,
                "falta_ars": 0.0,
                "motivo": RENTA_AR_PENDIENTE_MSG,
            })

    candidatos: list[tuple[str, PrioridadAccion, float]] = []

    def _add_tier(prio: PrioridadAccion, tickers: list[str], deltas: dict[str, float]) -> None:
        for t in tickers:
            if t in delta_ideal and deltas.get(t, delta_ideal[t]) > 1e-9:
                candidatos.append((t, prio, deltas.get(t, delta_ideal[t])))

    if deficit_def:
        defs = sorted(
            [t for t in delta_ideal if _es_compra_defensiva(t)],
            key=lambda x: (-delta_ideal[x], precios_dict.get(x, 1e18) or 1e18),
        )
        defs = aplicar_prioridad_favoritos(defs, fav_rf)
        _add_tier(PrioridadAccion.CRITICA, defs, delta_ideal)

    if hay_concentracion:
        seen_t = {t for t, _, _ in candidatos}
        diluir = sorted(
            [t for t in delta_ideal if t != concentrado],
            key=lambda x: (-delta_ideal[x], precios_dict.get(x, 1e18) or 1e18),
        )
        diluir = aplicar_prioridad_favoritos(diluir, fav_rv)  # favoritos primero también aquí
        for t in diluir:
            if t not in seen_t:
                candidatos.append((t, PrioridadAccion.ALTA, delta_ideal[t]))
                seen_t.add(t)

    rest_keys = [t for t in delta_ideal if t not in {c[0] for c in candidatos}]
    if target_rv_goal >= 0.55:
        rest_ideal = sorted(
            rest_keys,
            key=lambda x: (-_mod23_score_100(x, df_analisis), -delta_ideal[x]),
        )
    else:
        rest_ideal = sorted(
            rest_keys,
            key=lambda x: (-delta_ideal[x], -_mod23_score_100(x, df_analisis)),
        )
    rest_ideal = aplicar_prioridad_favoritos(rest_ideal, fav_rv)
    for t in rest_ideal:
        candidatos.append((t, PrioridadAccion.MEDIA, delta_ideal[t]))

    ideal_keys = {k.upper() for k in ideal if k != "_RENTA_AR"}
    if df_analisis is not None and not df_analisis.empty:
        for _, row in df_analisis.iterrows():
            t = str(row.get("TICKER", "")).upper()
            if not t or t in tickers_hold or t in ideal_keys or t in TICKERS_NO_CEDEAR_BYMA:
                continue
            sc = _mod23_score_100(t, df_analisis)
            if sc > 60.0 and t not in {c[0] for c in candidatos}:
                if float(precios_dict.get(t, 0.0) or precios_dict.get(t.upper(), 0.0) or 0.0) > 0:
                    candidatos.append((t, PrioridadAccion.BAJA, 0.05))

    compras: list[ItemRecomendacion] = []
    capital_restante = cap
    orden = 0
    valor_post = total_valor + cap
    escala_valor = total_valor if total_valor > 1e-6 else max(cap, 1.0)

    for t, prio, delt in candidatos:
        if capital_restante <= 0:
            break
        if t == "_RENTA_AR":
            continue
        precio = float(precios_dict.get(t, precios_dict.get(t.upper(), 0.0)) or 0.0)
        if precio <= 0:
            pendientes.append({
                "ticker": t,
                "precio_ars": 0.0,
                "falta_ars": 0.0,
                "motivo": "Sin precio ARS en MQ26 (cotización / paridad); no se puede calcular unidades.",
            })
            continue
        need_ars = delt * escala_valor
        capital_para = min(capital_restante, need_ars)
        unidades = int(capital_para // precio)
        if unidades < 1:
            falta = precio - capital_para
            pendientes.append({
                "ticker": t,
                "precio_ars": precio,
                "falta_ars": max(0.0, falta),
                "motivo": "Precio unitario mayor al capital asignado o disponible",
            })
            continue
        monto_real = unidades * precio
        if monto_real > capital_restante:
            unidades = int(capital_restante // precio)
            if unidades < 1:
                pendientes.append({
                    "ticker": t,
                    "precio_ars": precio,
                    "falta_ars": precio - capital_restante,
                    "motivo": "Capital remanente insuficiente para 1 unidad",
                })
                continue
            monto_real = unidades * precio
        capital_restante -= monto_real
        orden += 1
        cat = CLASIFICACION_ACTIVOS.get(t, CategoriaActivo.OTRO)
        jus = _trunc(
            f"Acerca a cartera ideal: peso objetivo +{delt*100:.1f} pp en {t}.", 150,
        )
        compras.append(
            ItemRecomendacion(
                orden=orden,
                ticker=t,
                nombre_legible=_nombre_legible(t, universo_df),
                categoria=cat,
                unidades=unidades,
                precio_ars_estimado=precio,
                monto_ars=monto_real,
                monto_usd=monto_real / ccl_f,
                justificacion=jus,
                impacto_en_balance=_impacto_str(t, _es_compra_defensiva(t)),
                prioridad=prio,
                es_activo_nuevo=t not in tickers_hold,
            )
        )

    monto_rf_compras = sum(i.monto_ars for i in compras if es_renta_fija(i.ticker))
    valor_rf_pre = pct_def_pre * total_valor
    pct_post = (valor_rf_pre + monto_rf_compras) / valor_post if valor_post > 0 else pct_def_pre

    delta_bal = f"Renta fija: {pct_def_pre*100:.0f}% → {pct_post*100:.0f}% | concentración vía líneas nuevas"[:200]

    resumen = _trunc(
        f"Con ${cap:,.0f} ARS podés ejecutar {len(compras)} compra(s). RF proyectada ~{pct_post*100:.0f}%.",
        200,
    )

    return RecomendacionResult(
        cliente_nombre=cliente_nombre,
        perfil=perfil_n,
        capital_disponible_ars=cap,
        capital_disponible_usd=capital_usd,
        ccl=ccl_f,
        fecha_recomendacion=fecha,
        compras_recomendadas=compras,
        pendientes_proxima_inyeccion=pendientes,
        capital_usado_ars=cap - capital_restante,
        capital_remanente_ars=capital_restante,
        n_compras=len(compras),
        pct_defensivo_post=pct_post,
        pct_defensivo_pre=pct_def_pre,
        delta_balance=delta_bal,
        resumen_recomendacion=resumen,
    )


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _impacto_str(ticker: str, core_rf: bool) -> str:
    if core_rf:
        return f"Renta fija ↑ por compra en {ticker}"
    return f"Renta variable / diversificación ↑ en {ticker}"


# ─── JUSTIFICACIONES PRIMERA CARTERA ──────────────────────────────────────────
# Una descripción corta y legible por ticker para el flujo "primera cartera".
# No usa el lenguaje de déficit ("peso objetivo +X pp"); explica el ROL del activo.
_JUSTIFICACION_PRIMERA_CARTERA: dict[str, str] = {
    # ── ONs del catálogo INSTRUMENTOS_RF (selección dinámica) ─────────────────
    "PN43O": "Renta fija USD — Pan American Energy ON 2037 (AA+, TIR ref. ~7.3%, ancla dólar)",
    "TLCTO": "Renta fija USD — Telecom Argentina ON 2036 (AA, TIR ref. ~8.0%, cupón semestral)",
    "YM34O": "Renta fija USD — YPF ON 2034 (AA, TIR ref. ~7.1%, ley Nueva York)",
    "TSC4O": "Renta fija USD — TGS ON 2035 (AA+, TIR ref. ~7.1%, lámina 10.000 USD)",
    "IRCPO": "Renta fija USD — Irsa ON 2035 (AA-, TIR ref. ~7.1%, lámina 1 USD)",
    "DNC7O": "Renta fija USD — Edenor ON 2030 (A+, TIR ref. ~8.3%, cupón semestral)",
    "YMCXO": "Renta fija USD — YPF ON 2031 (AA, TIR ref. ~8.5%, lámina 1.000 USD)",
    "RCCJO": "Renta fija USD — Pampa Energía ON 2027 (AA-, TIR ref. ~7.5%, cupón semestral)",
    "MGCHO": "Renta fija USD — MercadoLibre ON 2028 (BBB+, TIR ref. ~7.2%, lámina 1.000 USD)",
    "MGCEO": "Renta fija USD — MercadoLibre ON 2030 (BBB+, TIR ref. ~7.0%, lámina 1.000 USD)",
    # ── ETFs ──────────────────────────────────────────────────────────────────
    "IVW":   "ETF crecimiento — iShares S&P 500 Growth (sesgo hacia empresas de alto crecimiento)",
    "SPY":   "ETF global — S&P 500 (las 500 mayores empresas de EE.UU., eje del portfolio)",
    # ── Defensivos / cuasi-defensivos ─────────────────────────────────────────
    "BRKB":  "Renta variable diversificada — Berkshire Hathaway (Buffett, 60+ empresas)",
    "KO":    "Consumo básico — Coca-Cola (defensivo, dividendo estable hace +60 años)",
    "JNJ":   "Salud — Johnson & Johnson (farmacéutica + medical devices, defensivo)",
    "VZ":    "Telecomunicaciones — Verizon (dividendo alto ~6%, defensivo regulado)",
    "PG":    "Consumo básico — Procter & Gamble (bienes de consumo, dividendo creciente)",
    "COST":  "Retail defensivo — Costco (membresías, flujo recurrente, bajo beta)",
    "CVX":   "Energía — Chevron (dividendo creciente, cobertura inflación, energía integrada)",
    "WMT":   "Retail global — Walmart (defensivo, dividendo, líder distribución EE.UU.)",
    # ── Tech quality ──────────────────────────────────────────────────────────
    "MSFT":  "Tecnología — Microsoft (nube Azure, IA Copilot, software empresarial)",
    "NVDA":  "Tecnología — NVIDIA (líder en GPUs para inteligencia artificial)",
    "META":  "Tecnología — Meta (redes sociales, realidad aumentada, 3B+ usuarios)",
    "AMZN":  "Tecnología/Consumo — Amazon (e-commerce global + AWS cloud)",
    "GOOGL": "Tecnología — Alphabet/Google (búsquedas, YouTube, Google Cloud)",
    "AAPL":  "Tecnología — Apple (iPhones, servicios, ecosistema premium)",
    "JPM":   "Financiero global — JPMorgan Chase (banco líder EE.UU., calidad crediticia alta)",
    # ── Growth agresivo ───────────────────────────────────────────────────────
    "TSLA":  "EV/Tecnología — Tesla (vehículos eléctricos, IA autónoma, crecimiento volátil)",
    "AMD":   "Semiconductores — AMD (GPUs + CPUs, alternativa NVIDIA en IA/datacenter)",
    "PLTR":  "Tecnología — Palantir (análisis de datos masivos, contratos gobierno/defensa)",
    # ── LATAM / regional ──────────────────────────────────────────────────────
    "MELI":  "Tecnología LATAM — MercadoLibre (e-commerce + Mercado Pago, líder AR/BR)",
    "NU":    "Fintech LATAM — Nubank (neobank digital, 100M+ clientes, Brasil/México/Colombia)",
    "GGAL":  "Financiero AR — Grupo Galicia (banco líder Argentina, exposición local)",
    "YPFD":  "Energía AR — YPF (compañía estatal, exposición Vaca Muerta)",
    "VIST":  "Energía AR — Vista Energy (upstream offshore, crecimiento acelerado)",
}

_JUSTIFICACION_DEFAULT = "Activo recomendado para tu perfil — diversificación de cartera"


def generar_primera_cartera(
    capital_ars: float,
    perfil: str,
    ccl: float,
    precios_dict: dict[str, float],
    universo_df: pd.DataFrame | None = None,
    cliente_nombre: str = "",
    df_analisis: pd.DataFrame | None = None,
    favoritos_mes: dict[str, Any] | None = None,
    df_scores: pd.DataFrame | None = None,
) -> RecomendacionResult:
    """
    Genera la primera cartera para un inversor nuevo (sin posiciones previas).

    A diferencia de `recomendar()`, no usa lógica de déficit ni lenguaje de "acercar
    a cartera ideal": asigna el capital PROPORCIONALMENTE según CARTERA_IDEAL[perfil],
    en unidades enteras, con prioridad MEDIA para todos los ítems.

    Renta fija siempre en `compras_recomendadas` (nunca se delega a pendientes por
    falta de precio — resolver_precios() usa paridad_ref×CCL como fallback para
    cualquier ON del catálogo INSTRUMENTOS_RF, incluyendo la selección dinámica).

    Retorna un RecomendacionResult compatible con el renderizado existente en tab_inversor.
    """
    fecha = date.today().isoformat()
    perfil_n = perfil_diagnostico_valido(perfil)
    ccl_f = float(ccl or 0.0)
    cap = max(0.0, float(capital_ars or 0.0))

    if ccl_f <= 0:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=cap,
            capital_disponible_usd=0.0,
            ccl=0.0,
            fecha_recomendacion=fecha,
            alerta_mercado=True,
            mensaje_alerta="CCL inválido. No se puede calcular recomendación confiable.",
            resumen_recomendacion=_trunc("CCL inválido. Revisá el dato de mercado.", 200),
            pct_defensivo_pre=0.0,
        )

    if cap <= 0:
        return RecomendacionResult(
            cliente_nombre=cliente_nombre,
            perfil=perfil_n,
            capital_disponible_ars=0.0,
            capital_disponible_usd=0.0,
            ccl=ccl_f,
            fecha_recomendacion=fecha,
            pct_defensivo_pre=0.0,
            resumen_recomendacion="Ingresá un capital mayor a cero para obtener sugerencias.",
        )

    fav_doc = load_favoritos_mes() if favoritos_mes is None else favoritos_mes
    capital_usd = cap / ccl_f

    # Enriquecer precios con los tickers del ideal (ONs vía paridad_ref×CCL, RV vía scoring)
    precios_dict = _enriquecer_precios_recomendacion(
        precios_dict or {}, perfil_n, ccl_f, universo_df, fav_doc, df_scores=df_scores
    )

    # ── Cartera ideal: 100% DINÁMICA basada en constraints + scoring ──────────
    # Reemplaza el dict CARTERA_IDEAL hardcoded por cálculo dinámico desde
    # core/cartera_optima.py (constraints estructurales + selección por scoring).
    # Si la función dinámica falla por algún motivo, fallback al hardcoded.
    try:
        from core.cartera_optima import cartera_optima_para_perfil
        _ideal_raw = cartera_optima_para_perfil(
            perfil=perfil_n,
            capital_ars=cap,
            ccl=ccl_f,
            df_scores=df_scores,
            precios_ars=precios_dict,
        )
        logger.info("cartera_optima dinámica usada para perfil %s", perfil_n)
    except Exception as _e:
        logger.warning("cartera_optima dinámica falló (%s) — fallback a CARTERA_IDEAL", _e)
        _ideal_raw = CARTERA_IDEAL.get(perfil_n, CARTERA_IDEAL["Moderado"])

    # Separar reserva táctica de Perlas (20%)
    _peso_perlas = float(_ideal_raw.get("_PERLAS_POOL", 0.0))
    _capital_perlas_ars = round(cap * _peso_perlas, 2)
    _capital_core_ars   = cap - _capital_perlas_ars

    # Si la cartera vino dinámica, ya tiene tickers expandidos.
    # Solo expandimos pools si tiene _ON_USD_POOL o _RV_CEDEAR_POOL (fallback).
    if any(k in _ideal_raw for k in ("_ON_USD_POOL", "_RV_CEDEAR_POOL")):
        ideal = _expandir_ideal(
            {k: v for k, v in _ideal_raw.items() if k != "_PERLAS_POOL"},
            perfil_n,
            df_scores=df_scores,
            capital_ars=_capital_core_ars,
            ccl=ccl_f,
            precios_ars=precios_dict,
        )
    else:
        # Cartera ya viene con tickers expandidos desde cartera_optima_para_perfil
        ideal = {k: v for k, v in _ideal_raw.items() if k != "_PERLAS_POOL"}

    # Seleccionar perlas elegibles para este perfil y capital
    _perlas_seleccionadas: list = []
    try:
        from services.perlas_service import seleccionar_perlas
        _perlas_seleccionadas = seleccionar_perlas(
            capital_ars=_capital_perlas_ars,
            ccl=ccl_f,
            perfil=perfil_n,
            precio_actual={k: float(v) for k, v in precios_dict.items() if v},
        )
    except Exception:
        _perlas_seleccionadas = []

    # ── Ordenar tickers: RF primero (por CARTERA_IDEAL defensiva), luego RV descendente por peso
    def _sort_key(item: tuple[str, float]) -> tuple[int, float]:
        tk, w = item
        if tk == "_RENTA_AR":
            return (0, -w)   # RF AR placeholder — primero pero sin ticker real
        if _es_compra_defensiva(tk):
            return (1, -w)   # RF cotizable (PN43O, TLCTO) — segundo
        return (2, -w)       # RV — resto por peso desc

    tickers_ordenados = sorted(
        ((tk, float(w)) for tk, w in ideal.items() if tk != "_RENTA_AR"),
        key=_sort_key,
    )

    compras: list[ItemRecomendacion] = []
    pendientes: list[dict[str, Any]] = []
    # El loop de compras opera SOLO sobre el capital core (80%)
    # Las perlas tienen su propio capital reservado aparte
    capital_restante = _capital_core_ars
    orden = 0

    for tk, ideal_w in tickers_ordenados:
        if capital_restante < 1.0:
            break

        precio = float(precios_dict.get(tk, precios_dict.get(tk.upper(), 0.0)) or 0.0)

        if precio <= 0:
            pendientes.append({
                "ticker": tk,
                "precio_ars": 0.0,
                "falta_ars": 0.0,
                "motivo": "Sin precio ARS disponible — configurar manualmente con tu broker.",
            })
            continue

        # Asignación proporcional al peso ideal
        target_ars = ideal_w * cap
        capital_para = min(capital_restante, target_ars)
        unidades_raw = int(capital_para // precio)

        # ── Lámina mínima: ONs se negocian en lotes (ej. 1.000 VN USD) ──────
        # Nunca comprar menos de `lamina_min` unidades; siempre redondear al
        # múltiplo inferior para no exceder el capital.
        lamina = _lamina_min_on(tk)
        if lamina > 1 and unidades_raw > 0:
            # Redondear a múltiplo de lámina sin exceder el capital
            unidades = (unidades_raw // lamina) * lamina
        else:
            unidades = unidades_raw

        if unidades < 1 or (lamina > 1 and unidades < lamina):
            # No alcanza ni para 1 lote mínimo
            monto_minimo = lamina * precio
            pendientes.append({
                "ticker": tk,
                "precio_ars": precio,
                "falta_ars": max(0.0, monto_minimo - capital_para),
                "motivo": (
                    f"Capital asignado ({capital_para:,.0f} ARS) insuficiente para "
                    f"la lámina mínima de {tk}: {lamina:,} VN USD "
                    f"≈ {monto_minimo:,.0f} ARS. "
                    "Aumentá el monto total para incluirlo."
                ) if lamina > 1 else (
                    f"Capital asignado ({capital_para:,.0f} ARS) insuficiente para "
                    f"1 unidad de {tk} ({precio:,.0f} ARS). "
                    "Aumentá el monto total para incluirlo."
                ),
            })
            continue

        monto_real = unidades * precio
        if monto_real > capital_restante:
            if lamina > 1:
                unidades = (int(capital_restante // precio) // lamina) * lamina
            else:
                unidades = int(capital_restante // precio)
            if unidades < max(1, lamina):
                pendientes.append({
                    "ticker": tk,
                    "precio_ars": precio,
                    "falta_ars": lamina * precio - capital_restante,
                    "motivo": "Capital remanente insuficiente para la lámina mínima.",
                })
                continue
            monto_real = unidades * precio

        capital_restante -= monto_real
        orden += 1
        cat = CLASIFICACION_ACTIVOS.get(tk, CategoriaActivo.OTRO)
        es_rf = _es_compra_defensiva(tk)
        jus = _trunc(
            _JUSTIFICACION_PRIMERA_CARTERA.get(tk, _JUSTIFICACION_DEFAULT),
            200,
        )
        compras.append(
            ItemRecomendacion(
                orden=orden,
                ticker=tk,
                nombre_legible=_nombre_legible(tk, universo_df),
                categoria=cat,
                unidades=unidades,
                precio_ars_estimado=precio,
                monto_ars=monto_real,
                monto_usd=monto_real / ccl_f,
                justificacion=jus,
                impacto_en_balance=_impacto_str(tk, es_rf),
                prioridad=PrioridadAccion.MEDIA,   # nunca CRITICA en primera cartera
                es_activo_nuevo=True,
            )
        )

    # ── Mop-up: redistribuir remanente para que el efectivo libre ≤ 5% del capital ──
    # Regla de negocio: el capital asignado debe invertirse en un 95–100%.
    # El presupuesto de _RENTA_AR (bonos AR, gestión manual vía broker) NO se toca.
    # Estrategia: ordenar compras por precio ASC (cheapest-first) para maximizar
    # la cantidad de unidades que se pueden absorber con el remanente.
    _renta_ar_presupuesto = float(ideal.get("_RENTA_AR", 0.0)) * cap
    _capital_en_titulos = cap - _renta_ar_presupuesto   # base real de la inversión en títulos
    _MAX_EFECTIVO_PCT = 0.05   # regla 95/100%: máximo 5% idle
    _pesos_ideales = {tk: float(w) for tk, w in ideal.items() if tk != "_RENTA_AR"}

    # ── FASE 1: rebalance hacia targets (respetar pesos) ──────────────────────
    # Solo compra tickers underweight, hasta que todos lleguen a su target ±5%.
    for _ in range(len(compras) * 5 + 10):
        _efectivo_libre = capital_restante - _renta_ar_presupuesto
        if _efectivo_libre <= _capital_en_titulos * _MAX_EFECTIVO_PCT or not compras:
            break
        _progreso = False

        def _gap_underweight(item):
            target_pct = _pesos_ideales.get(item.ticker, 0.0)
            actual_pct = item.monto_ars / cap if cap > 0 else 0.0
            return actual_pct - target_pct

        for _item in sorted(compras, key=_gap_underweight):
            _px = _item.precio_ars_estimado
            if _px <= 0:
                continue
            _lam = _lamina_min_on(_item.ticker)
            if _efectivo_libre < _px * _lam:
                continue
            target_pct = _pesos_ideales.get(_item.ticker, 0.0)
            actual_pct = _item.monto_ars / cap if cap > 0 else 0.0
            if target_pct > 0 and actual_pct >= target_pct * 1.05:
                continue
            falta_ars = max(0.0, (target_pct - actual_pct) * cap)
            _extra_max_target = int(falta_ars // _px) if falta_ars > 0 else _lam
            _extra_raw = min(int(_efectivo_libre // _px), max(_lam, _extra_max_target))
            _extra = (_extra_raw // _lam) * _lam
            if _extra >= _lam:
                _item.unidades += _extra
                _item.monto_ars += _extra * _px
                _item.monto_usd += _extra * _px / ccl_f
                capital_restante -= _extra * _px
                _progreso = True
                break
        if not _progreso:
            break

    # ── FASE 2: fill-up controlado del residual del CORE ──────────────────────
    # Si tras la fase 1 quedó >5% del core sin invertir, completar con tickers
    # CERCANOS A SU TARGET (no los más baratos) hasta tope overweight 1.5×.
    # Esto invierte el 95-100% del CORE sin concentrar en el más barato.
    # El 20% de perlas QUEDA aparte (no se toca).
    _OVERWEIGHT_MAX = 1.50
    for _ in range(len(compras) * 5 + 10):
        _efectivo_libre = capital_restante - _renta_ar_presupuesto
        # Umbral relativo al CORE (no al total), porque perlas no se invierten acá
        if _efectivo_libre <= _capital_core_ars * _MAX_EFECTIVO_PCT or not compras:
            break
        _progreso = False

        # Priorizar tickers con MENOR overweight (≈ los que aún están abajo de su target).
        # En empate, los más baratos absorben mejor el residual.
        def _key_fase2(item):
            target_pct = _pesos_ideales.get(item.ticker, 0.0)
            actual_pct = item.monto_ars / cap if cap > 0 else 0.0
            overweight = (actual_pct / target_pct) if target_pct > 0 else 99.0
            return (overweight, item.precio_ars_estimado)

        for _item in sorted(compras, key=_key_fase2):
            _px = _item.precio_ars_estimado
            if _px <= 0:
                continue
            _lam = _lamina_min_on(_item.ticker)
            if _efectivo_libre < _px * _lam:
                continue
            target_pct = _pesos_ideales.get(_item.ticker, 0.0)
            actual_pct = _item.monto_ars / cap if cap > 0 else 0.0
            # No comprar si supera el cap de overweight
            if target_pct > 0 and actual_pct >= target_pct * _OVERWEIGHT_MAX:
                continue
            # Máximo extra dentro del cap
            max_monto_ticker = target_pct * _OVERWEIGHT_MAX * cap if target_pct > 0 else _efectivo_libre
            margen_ow_ars = max_monto_ticker - _item.monto_ars
            _extra_max_ow = int(margen_ow_ars // _px) if margen_ow_ars > 0 else 0
            _extra_max_cash = int(_efectivo_libre // _px)
            _extra_raw = min(_extra_max_ow, _extra_max_cash)
            _extra = (_extra_raw // _lam) * _lam if _lam > 1 else _extra_raw
            if _extra >= max(1, _lam):
                _item.unidades += _extra
                _item.monto_ars += _extra * _px
                _item.monto_usd += _extra * _px / ccl_f
                capital_restante -= _extra * _px
                _progreso = True
                break
        if not _progreso:
            break
        if not _progreso:
            break  # ningún ticker cabe en el residual — se acepta el remanente

    # ── Si _RENTA_AR tiene peso pero no hay RF cotizable con precio → pendiente informativo
    renta_ar_w = float(ideal.get("_RENTA_AR", 0.0))
    if renta_ar_w > 1e-6:
        tiene_rf = any(_es_compra_defensiva(c.ticker) for c in compras)
        if not tiene_rf:
            pendientes.insert(0, {
                "ticker": "_RENTA_AR",
                "precio_ars": 0.0,
                "falta_ars": 0.0,
                "motivo": RENTA_AR_PENDIENTE_MSG,
            })

    # ── Métricas post
    monto_rf_compras = sum(i.monto_ars for i in compras if es_renta_fija(i.ticker))
    pct_post = monto_rf_compras / cap if cap > 0 else 0.0

    _n_perlas = len(_perlas_seleccionadas)
    _perlas_txt = (
        f" · {_n_perlas} perla(s) identificada(s) — ${_capital_perlas_ars:,.0f} ARS reservados."
        if _n_perlas > 0
        else f" · ${_capital_perlas_ars:,.0f} ARS reservados para perlas (esperando oportunidad)."
    )

    resumen = _trunc(
        f"CORE (80%): {len(compras)} activo(s) por ${cap - capital_restante - _capital_perlas_ars:,.0f} ARS "
        f"(~USD {(cap - capital_restante - _capital_perlas_ars) / ccl_f:,.0f}). "
        f"Renta fija ~{pct_post*100:.0f}%."
        + _perlas_txt,
        300,
    )

    return RecomendacionResult(
        cliente_nombre=cliente_nombre,
        perfil=perfil_n,
        capital_disponible_ars=cap,
        capital_disponible_usd=capital_usd,
        ccl=ccl_f,
        fecha_recomendacion=fecha,
        compras_recomendadas=compras,
        pendientes_proxima_inyeccion=pendientes,
        # capital_restante arranca como _capital_core_ars (80%) y baja por cada compra.
        # capital_usado = lo que se gastó del core. capital_remanente = lo no usado del core + perlas.
        capital_usado_ars=_capital_core_ars - capital_restante,
        capital_remanente_ars=capital_restante + _capital_perlas_ars,
        n_compras=len(compras),
        pct_defensivo_post=pct_post,
        pct_defensivo_pre=0.0,
        delta_balance=f"CORE 80%: RF ~{pct_post*100:.0f}% · PERLAS 20%: {_n_perlas} candidatas",
        resumen_recomendacion=resumen,
        capital_perlas_ars=_capital_perlas_ars,
        perlas_seleccionadas=[p.to_dict() for p in _perlas_seleccionadas],
    )
