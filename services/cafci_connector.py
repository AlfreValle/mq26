"""
services/cafci_connector.py — Conector API CAFCI (cafci.org.ar)
Master Quant 26 | DSS Unificado

API pública y gratuita de la Cámara Argentina de Fondos Comunes de Inversión.
Documentación: https://api.cafci.org.ar/

Endpoints usados:
  GET /fondo                    → lista FCI (paginado; catálogo completo vía listar_todos + caché disco)
  GET /fondo/{id}/ficha         → serie VCP / datos para rendimiento proxy
  (rendimiento)                 → derivado de ficha en `obtener_rendimiento`

Datos obtenidos:
  - Patrimonio neto
  - Cuotaparte (precio unitario)
  - Rendimiento 1M, 3M, 6M, 1Y
  - Tipo de fondo (Renta Fija, Variable, Mixto, etc.)
  - Gerente (Balanz, MAF, FIMA, etc.)
  - Score calculado para modelo 60/20/20
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from difflib import get_close_matches
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.logging_config import get_logger

_log = get_logger(__name__)

BASE_URL   = "https://api.cafci.org.ar"
TIMEOUT    = 15
HEADERS    = {"User-Agent": "MQ26-DSS/1.0 (+https://example.com/contact)"}

# ─── MAPA NOMBRE → ID CAFCI (pre-cacheado para fondos populares) ──────────────
# Actualizar ejecutando: cafci_connector.actualizar_mapa_ids()
MAPA_FONDOS: dict[str, int] = {
    # Renta Fija ARS
    "BALANZ AHORRO":              14,
    "MAF AHORRO ARS":             1,
    "MEGAINVER RENTA FIJA":       8,
    "PIONEER PESOS":              22,
    "PELLEGRINI RENTA":           35,
    "COMPASS AHORRO":             45,
    # Renta Fija USD / Dólar linked
    "FONDOS FIMA USD":            120,
    "BALANZ CAPITAL USD":         115,
    "MEGAINVER DOLAR":            118,
    "MAF RETORNO TOTAL":          122,
    # Renta Variable
    "BALANZ ACCIONES":            200,
    "FIMA ACCIONES":              205,
    "COMPASS GROWTH":             210,
    "PIONEER ACCIONES":           215,
    # Renta Mixta
    "PIONEER MIXTO":              300,
    "MAF MIXTO":                  305,
    # Infraestructura / Cerrados
    "PELLEGRINI INFRAESTR":       400,
}

# Tipos de fondo → sector para scoring
TIPO_A_SECTOR = {
    1: "Renta Fija ARS",
    2: "Renta Variable",
    3: "Renta Mixta",
    4: "Renta Fija USD",
    5: "Infraestructura",
    6: "Mercado de Dinero",
    7: "Retorno Total",
}

# Riesgo estimado por tipo
RIESGO_POR_TIPO = {
    "Mercado de Dinero":  1,
    "Renta Fija ARS":     2,
    "Renta Fija USD":     3,
    "Renta Mixta":        4,
    "Retorno Total":      4,
    "Renta Variable":     5,
    "Infraestructura":    4,
}


# ─── CLIENTE HTTP ────────────────────────────────────────────────────────────

def _get(endpoint: str, params: str = "") -> dict | None:
    url = f"{BASE_URL}{endpoint}{'?' + params if params else ''}"
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        _log.warning("CAFCI API error %s: %s", endpoint, e)
        return None
    except Exception as e:
        _log.error("CAFCI error inesperado %s: %s", endpoint, e)
        return None


# ─── Caché catálogo completo (disco) ───────────────────────────────────────────
_CACHE_DIR = Path(__file__).resolve().parent.parent / "0_Data_Maestra" / "cache_cafci"
_CATALOG_FILE = _CACHE_DIR / "fondos_catalog.json"
_DEFAULT_CATALOG_TTL_SEC = 24 * 3600


def _norm_nombre_fci(nombre: str) -> str:
    s = str(nombre or "").upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_cuit(val: str | None) -> str:
    if not val:
        return ""
    return re.sub(r"[^0-9]", "", str(val))


def _fondo_dict_desde_item(f: dict) -> dict:
    tipo_info = f.get("tipoFondo") or {}
    gerente_info = f.get("gerente") or {}
    cuit = (
        gerente_info.get("cuit")
        or gerente_info.get("cuitCuil")
        or gerente_info.get("cuil")
        or gerente_info.get("cuitGerente")
        or ""
    )
    return {
        "id":            f.get("id"),
        "nombre":        f.get("nombre", ""),
        "tipo_id":       tipo_info.get("id"),
        "tipo":          TIPO_A_SECTOR.get(tipo_info.get("id", 0), "Otros"),
        "gerente":       gerente_info.get("nombre", ""),
        "gerente_cuit":  _norm_cuit(str(cuit) if cuit else ""),
    }


# ─── FUNCIONES PRINCIPALES ───────────────────────────────────────────────────

def listar_fondos(
    tipo_id: int | None = None,
    limit: int = 100,
    page: int | None = None,
) -> list[dict]:
    """
    Lista FCI activos (una página). Para el universo completo usar
    `listar_todos_fondos_activos()` o `obtener_catalogo_fondos_cacheado()`.
    """
    params = f"estado=1&include=gerente,tipoFondo&limit={limit}"
    if tipo_id:
        params += f"&tipoFondoId={tipo_id}"
    if page is not None and page > 0:
        params += f"&page={page}"

    resp = _get("/fondo", params)
    if not resp or "data" not in resp:
        _log.warning("CAFCI: sin datos de listar_fondos")
        return []

    return [_fondo_dict_desde_item(f) for f in resp["data"]]


def listar_todos_fondos_activos(
    tipo_id: int | None = None,
    page_size: int = 400,
    max_pages: int = 80,
) -> list[dict]:
    """
    Acumula páginas hasta vacío o sin IDs nuevos (la API puede ignorar `page`;
    en ese caso se corta en la segunda iteración sin agregados).
    """
    out: list[dict] = []
    seen: set = set()

    for p in range(1, max_pages + 1):
        batch = listar_fondos(tipo_id=tipo_id, limit=page_size, page=p)
        if not batch:
            break
        added = 0
        for item in batch:
            fid = item.get("id")
            if fid is None or fid in seen:
                continue
            seen.add(fid)
            out.append(item)
            added += 1
        if added == 0:
            break
        if len(batch) < page_size:
            break

    if not out:
        batch0 = listar_fondos(tipo_id=tipo_id, limit=min(15_000, page_size * max_pages), page=None)
        for item in batch0:
            fid = item.get("id")
            if fid is None or fid in seen:
                continue
            seen.add(fid)
            out.append(item)

    return out


def obtener_catalogo_fondos_cacheado(
    force_refresh: bool = False,
    ttl_seconds: int | None = None,
) -> list[dict]:
    """
    Devuelve el catálogo completo de fondos activos, con caché en disco (TTL default 24h).
    """
    ttl = ttl_seconds if ttl_seconds is not None else _DEFAULT_CATALOG_TTL_SEC
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and _CATALOG_FILE.exists():
        age = time.time() - _CATALOG_FILE.stat().st_mtime
        if age < ttl:
            try:
                raw = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
                fondos = raw.get("fondos")
                if isinstance(fondos, list) and fondos:
                    return fondos
            except Exception as exc:
                _log.warning("CAFCI: caché de catálogo ilegible: %s", exc)

    fondos = listar_todos_fondos_activos()
    try:
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count":      len(fondos),
            "fondos":     fondos,
        }
        _CATALOG_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _log.info("CAFCI: catálogo guardado (%d fondos)", len(fondos))
    except Exception as exc:
        _log.warning("CAFCI: no se pudo escribir caché: %s", exc)

    return fondos


def resolver_fondo_id_con_mapa(
    nombre_fci: str,
    gerente_cuit: str | None = None,
    catalogo: list[dict] | None = None,
    cutoff_similarity: float = 0.82,
) -> int | None:
    """
    Resuelve ID CAFCI: match exacto/fuzzy sobre claves de `MAPA_FONDOS` (normalizado),
    luego `resolver_fondo_id` sobre el catálogo API / caché.
    """
    want = _norm_nombre_fci(nombre_fci)
    if not want:
        return None
    for label, fid in MAPA_FONDOS.items():
        if _norm_nombre_fci(label) == want:
            return int(fid)
    labels_norm = [_norm_nombre_fci(k) for k in MAPA_FONDOS]
    close_seed = get_close_matches(want, labels_norm, n=1, cutoff=max(0.72, cutoff_similarity - 0.08))
    if close_seed:
        for label, fid in MAPA_FONDOS.items():
            if _norm_nombre_fci(label) == close_seed[0]:
                return int(fid)
    return resolver_fondo_id(
        nombre_fci,
        gerente_cuit=gerente_cuit,
        catalogo=catalogo,
        cutoff_similarity=cutoff_similarity,
    )


def resolver_fondo_id(
    nombre_fci: str,
    gerente_cuit: str | None = None,
    catalogo: list[dict] | None = None,
    cutoff_similarity: float = 0.82,
) -> int | None:
    """
    Resuelve ID numérico CAFCI por nombre (exacto, luego fuzzy) y opcionalmente CUIT del gerente.
    `catalogo`: lista de dict desde API; si None usa caché en disco / descarga.
    """
    cat = catalogo if catalogo is not None else obtener_catalogo_fondos_cacheado()
    if not cat:
        return None

    want_n = _norm_nombre_fci(nombre_fci)
    want_cuit = _norm_cuit(gerente_cuit) if gerente_cuit else ""

    if want_cuit:
        for f in cat:
            if _norm_nombre_fci(f.get("nombre", "")) == want_n and f.get("gerente_cuit") == want_cuit:
                fid = f.get("id")
                return int(fid) if fid is not None else None
        cuit_match = [f for f in cat if f.get("gerente_cuit") == want_cuit]
        pool = cuit_match
    else:
        pool = cat

    for f in pool:
        if _norm_nombre_fci(f.get("nombre", "")) == want_n:
            fid = f.get("id")
            return int(fid) if fid is not None else None

    nombres = [_norm_nombre_fci(f.get("nombre", "")) for f in pool if f.get("nombre")]
    if not nombres:
        return None
    close = get_close_matches(want_n, nombres, n=1, cutoff=cutoff_similarity)
    if not close:
        return None
    target = close[0]
    for f in pool:
        if _norm_nombre_fci(f.get("nombre", "")) == target:
            fid = f.get("id")
            return int(fid) if fid is not None else None
    return None


def obtener_rendimiento(fondo_id: int) -> dict:
    """
    Obtiene el rendimiento histórico de un fondo.
    Devuelve dict con rendimientos a 1M, 3M, 6M, 1Y y datos actuales.
    """
    # Rendimiento de los últimos 365 días
    fecha_desde = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    fecha_hasta = date.today().strftime("%Y-%m-%d")

    params = f"fechaDesde={fecha_desde}&fechaHasta={fecha_hasta}&limit=370"
    resp   = _get(f"/fondo/{fondo_id}/ficha", params)

    if not resp or "data" not in resp or not resp["data"]:
        return _rendimiento_vacio()

    datos = resp["data"]
    cuotapartes = [float(d["vcp"]) for d in datos if d.get("vcp")]

    if len(cuotapartes) < 5:
        return _rendimiento_vacio()

    actual  = cuotapartes[-1]
    hace1m  = cuotapartes[-22]   if len(cuotapartes) > 22  else cuotapartes[0]
    hace3m  = cuotapartes[-66]   if len(cuotapartes) > 66  else cuotapartes[0]
    hace6m  = cuotapartes[-132]  if len(cuotapartes) > 132 else cuotapartes[0]
    hace12m = cuotapartes[0]

    ret_1m  = round((actual / hace1m  - 1) * 100, 2) if hace1m  > 0 else 0
    ret_3m  = round((actual / hace3m  - 1) * 100, 2) if hace3m  > 0 else 0
    ret_6m  = round((actual / hace6m  - 1) * 100, 2) if hace6m  > 0 else 0
    ret_12m = round((actual / hace12m - 1) * 100, 2) if hace12m > 0 else 0

    # Volatilidad (desvío estándar mensual)
    import statistics
    retornos_diarios = [
        (cuotapartes[i] / cuotapartes[i-1] - 1) * 100
        for i in range(1, len(cuotapartes))
        if cuotapartes[i-1] > 0
    ]
    vol = round(statistics.stdev(retornos_diarios) * (22 ** 0.5), 2) if len(retornos_diarios) > 5 else 5.0

    return {
        "cuotaparte_actual": round(actual, 4),
        "ret_1m":            ret_1m,
        "ret_3m":            ret_3m,
        "ret_6m":            ret_6m,
        "ret_12m":           ret_12m,
        "vol_mensual":       vol,
        "sharpe_proxy":      round(ret_12m / vol, 2) if vol > 0 else 0,
        "datos_ok":          True,
    }


def _rendimiento_vacio() -> dict:
    return {
        "cuotaparte_actual": 0,
        "ret_1m": 0, "ret_3m": 0, "ret_6m": 0, "ret_12m": 0,
        "vol_mensual": 10, "sharpe_proxy": 0, "datos_ok": False,
    }


# ─── SCORE FCI CON DATOS REALES ───────────────────────────────────────────────

def score_fci_real(
    nombre_fci: str,
    fondo_id:   int | None = None,
    contexto_inflacion_pct: float = 120.0,  # inflación anual argentina estimada
    gerente_cuit: str | None = None,
) -> tuple[float, dict]:
    """
    Calcula el score del FCI con datos reales de CAFCI (0-100).

    Criterios:
      Rendimiento real (vs inflación)  → 30 pts
      Sharpe proxy                     → 25 pts
      Tipo / perfil de riesgo          → 20 pts
      Consistencia (3M vs 1M)          → 15 pts
      Volatilidad controlada           → 10 pts

    Si no hay `fondo_id`, se usa `resolver_fondo_id_con_mapa` (MAPA + API/listado).
    """
    id_fondo = fondo_id or resolver_fondo_id_con_mapa(nombre_fci, gerente_cuit=gerente_cuit)

    if id_fondo is None:
        # Sin ID conocido → score heurístico
        _log.debug("CAFCI: sin ID para %s, usando heurística", nombre_fci)
        return _score_heuristico(nombre_fci)

    rend = obtener_rendimiento(id_fondo)

    if not rend["datos_ok"]:
        return _score_heuristico(nombre_fci)

    detalle = {"fuente": "CAFCI", "fondo_id": id_fondo}
    score   = 0

    # 1. Rendimiento real anual (ret_12m vs inflación) — 30 pts
    ret_real = rend["ret_12m"] - contexto_inflacion_pct
    if ret_real > 30:        score += 30
    elif ret_real > 15:      score += 24
    elif ret_real > 0:       score += 16
    elif ret_real > -20:     score += 8
    else:                    score += 0
    detalle["ret_12m"]    = rend["ret_12m"]
    detalle["ret_real"]   = round(ret_real, 1)

    # 2. Sharpe proxy — 25 pts
    sp = rend["sharpe_proxy"]
    if sp > 2:               score += 25
    elif sp > 1:             score += 20
    elif sp > 0.5:           score += 14
    elif sp > 0:             score += 8
    else:                    score += 0
    detalle["sharpe"] = sp

    # 3. Tipo de fondo — 20 pts (USD > Mixto > ARS > Variable)
    subtipo = ""
    for frow in obtener_catalogo_fondos_cacheado():
        if frow.get("id") == id_fondo:
            subtipo = str(frow.get("tipo") or "")
            break
    if not subtipo:
        for k, v in MAPA_FONDOS.items():
            if v == id_fondo:
                subtipo = k
                break
    pts_tipo = {"Renta Fija USD": 20, "Mercado de Dinero": 18,
                "Renta Mixta": 15, "Retorno Total": 16,
                "Renta Fija ARS": 12, "Renta Variable": 14,
                "Infraestructura": 17, "Otros": 12}
    score += pts_tipo.get(subtipo, 12)
    detalle["subtipo"] = subtipo

    # 4. Consistencia 3M vs 1M — 15 pts
    if rend["ret_3m"] > 0 and rend["ret_1m"] > 0:
        if rend["ret_1m"] >= rend["ret_3m"] / 3:
            score += 15   # Acelerando
        else:
            score += 8    # Desacelerando
    elif rend["ret_3m"] > 0:
        score += 5
    detalle["ret_3m"] = rend["ret_3m"]
    detalle["ret_1m"] = rend["ret_1m"]

    # 5. Volatilidad — 10 pts
    vol = rend["vol_mensual"]
    if vol < 2:              score += 10
    elif vol < 5:            score += 7
    elif vol < 10:           score += 4
    else:                    score += 0
    detalle["vol"] = vol
    detalle["cuotaparte_actual"] = rend["cuotaparte_actual"]

    return round(min(100.0, float(score)), 1), detalle


def _score_heuristico(nombre: str) -> tuple[float, dict]:
    """Fallback cuando no hay ID de CAFCI disponible."""
    nombre_up = nombre.upper()
    if "USD" in nombre_up or "DOLAR" in nombre_up:
        return 62.0, {"fuente": "heurística", "motivo": "FCI en USD"}
    elif "RENTA FIJA" in nombre_up or "AHORRO" in nombre_up:
        return 52.0, {"fuente": "heurística", "motivo": "Renta Fija ARS"}
    elif "ACCIONES" in nombre_up or "VARIABLE" in nombre_up:
        return 55.0, {"fuente": "heurística", "motivo": "Renta Variable"}
    elif "MIXTO" in nombre_up or "RETORNO" in nombre_up:
        return 57.0, {"fuente": "heurística", "motivo": "Mixto"}
    elif "INFRAESTR" in nombre_up:
        return 60.0, {"fuente": "heurística", "motivo": "Infraestructura"}
    return 50.0, {"fuente": "heurística", "motivo": "Sin datos"}


# ─── SCANNER COMPLETO FCI ────────────────────────────────────────────────────

def escanear_todos_los_fci(
    tipos: list[int] = None,
    top_n: int = 20,
    callback = None,
    max_escaneados: int = 600,
) -> list:
    """
    Escanea FCI desde el catálogo cacheado y devuelve los top_n por score.
    tipos: lista de tipo_id a incluir (None = todos)
    max_escaneados: tope de fondos a puntuar (evita tardes largas).
    """
    fondos = obtener_catalogo_fondos_cacheado()
    if tipos:
        fondos = [f for f in fondos if f.get("tipo_id") in tipos]

    n_score = min(max_escaneados, max(top_n * 3, 50))
    fondos = fondos[:n_score]

    resultados = []
    total = len(fondos)

    for i, fondo in enumerate(fondos):
        if callback:
            callback(i + 1, total, fondo["nombre"])
        try:
            score, detalle = score_fci_real(
                fondo["nombre"],
                fondo_id=fondo["id"],
            )
            resultados.append({
                "Ticker":      fondo["nombre"],
                "Tipo":        "FCI",
                "Sector":      fondo["tipo"],
                "Gerente":     fondo["gerente"],
                "Score_Total": score,
                "Score_Fund":  score,
                "Score_Tec":   50.0,
                "Score_Sector":60.0,
                "RSI":         50,
                "Precio":      detalle.get("cuotaparte_actual", 0),
                "Ret_12M_Pct": detalle.get("ret_12m", 0),
                "Sharpe":      detalle.get("sharpe", 0),
                "Senal":       "🟢 COMPRAR" if score>=70 else "🟡 ACUMULAR" if score>=55 else "⚪ MANTENER",
                "Detalle":     detalle,
            })
            time.sleep(0.2)
        except Exception as e:
            _log.warning("Error escaneando FCI %s: %s", fondo["nombre"], e)

    resultados.sort(key=lambda x: x["Score_Total"], reverse=True)
    return resultados[:top_n]


# ─── ACTUALIZAR MAPA DE IDs ───────────────────────────────────────────────────

def actualizar_mapa_ids(guardar_en: Path | None = None) -> dict[str, int]:
    """
    Descarga todos los fondos de CAFCI y construye el mapa nombre→ID.
    Útil para mantenimiento trimestral. Usa catálogo completo + refresca caché.
    """
    fondos = obtener_catalogo_fondos_cacheado(force_refresh=True)
    mapa   = {_norm_nombre_fci(str(f.get("nombre", ""))): f["id"] for f in fondos if f.get("id")}

    if guardar_en:
        with open(guardar_en, "w", encoding="utf-8") as fp:
            json.dump(mapa, fp, ensure_ascii=False, indent=2)
        _log.info("Mapa CAFCI guardado: %d fondos → %s", len(mapa), guardar_en)

    return mapa
