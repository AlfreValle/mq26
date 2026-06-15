"""
Snapshot del pipeline de precios (mismo orden que run_mq26) sin Streamlit.
Escribe en debug-0e4ef1.log para depuración. Uso:
  python scripts/debug_pricing_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys
import time as _time_dbg
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
for d in (BASE_DIR, BASE_DIR / "services", BASE_DIR / "core", BASE_DIR / "1_Scripts_Motor"):
    sd = str(d)
    if sd not in sys.path:
        sys.path.insert(0, sd)

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
os.environ.setdefault("MQ26_PASSWORD", os.environ.get("MQ26_PASSWORD", "debug_snapshot"))

import pandas as pd
import services.cartera_service as cs
from core.price_engine import PriceEngine
from data_engine import DataEngine, obtener_ccl

LOG = BASE_DIR / "debug-0e4ef1.log"


def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    payload = {
        "sessionId": "0e4ef1",
        "runId": "snapshot",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(_time_dbg.time() * 1000),
    }
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    engine_data = DataEngine()
    ccl = float(obtener_ccl() or 0.0)
    _agent_dbg("D", "snapshot:ccl", "CCL tras obtener_ccl()", {"ccl": ccl})

    trans = engine_data.cargar_transaccional()
    if trans.empty:
        _agent_dbg(
            "C",
            "snapshot:carga_datos",
            "puerta calculo precios cartera",
            {
                "cartera_activa_preview": "",
                "trans_empty": True,
                "trans_nrows": 0,
                "compute_prices": False,
            },
        )
        return

    carteras = sorted(trans["CARTERA"].dropna().astype(str).unique())
    _agent_dbg(
        "C",
        "snapshot:carga_datos",
        "puerta calculo precios cartera",
        {
            "cartera_activa_preview": "(todas)",
            "trans_empty": False,
            "trans_nrows": int(len(trans)),
            "n_carteras": len(carteras),
            "compute_prices": True,
        },
    )
    _univ_n = (
        int(len(engine_data.universo_df))
        if getattr(engine_data, "universo_df", None) is not None
        and not engine_data.universo_df.empty
        else 0
    )

    for cartera_activa in carteras:
        df_ag = engine_data.agregar_cartera(trans, cartera_activa)
        if df_ag.empty:
            _agent_dbg("C", "snapshot:df_ag", "df_ag vacío", {"cartera": cartera_activa[:120]})
            continue

        tickers_cartera = df_ag["TICKER"].str.upper().tolist()
        precios_dict_live = engine_data.obtener_precios_cartera(tickers_cartera, ccl)
        precios_dict = cs.resolver_precios(
            tickers_cartera, precios_dict_live, ccl, universo_df=engine_data.universo_df
        )
        _n_live = sum(
            1 for t in tickers_cartera if float(precios_dict_live.get(str(t).upper(), 0) or 0) > 0
        )
        _n_res = sum(1 for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) > 0)
        _agent_dbg(
            "B",
            "snapshot:resolver_precios",
            "despues obtener_precios + resolver_precios",
            {
                "cartera": cartera_activa[:120],
                "n_tickers": len(tickers_cartera),
                "tickers": tickers_cartera[:40],
                "n_precio_live_pos": _n_live,
                "n_precio_tras_resolver_pos": _n_res,
                "universo_nrows": _univ_n,
            },
        )
        try:
            _pe = PriceEngine(universo_df=engine_data.universo_df)
            _records = _pe.get_portfolio(tickers_cartera, ccl, precios_live_override=precios_dict)
            price_coverage_pct = _pe.cobertura_pct(_records)
            tickers_sin_precio = _pe.tickers_sin_precio(_records)
            precios_dict = _pe.to_precios_ars(_records)
            _n_pe = sum(1 for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) > 0)
            _sources = {}
            for _tk, _rec in list(_records.items())[:16]:
                _sources[str(_tk)] = getattr(_rec.source, "value", str(_rec.source))
            _agent_dbg(
                "A",
                "snapshot:price_engine_ok",
                "PriceEngine OK",
                {
                    "cartera": cartera_activa[:120],
                    "coverage_pct": price_coverage_pct,
                    "sin_precio": tickers_sin_precio[:30],
                    "n_tras_pe_pos": _n_pe,
                    "sample_sources": _sources,
                },
            )
            if tickers_sin_precio:
                precios_dict = cs.rellenar_precios_desde_ultimo_ppc(
                    trans, cartera_activa, tickers_cartera, precios_dict, float(ccl or 0)
                )
                tickers_sin_precio = [
                    t
                    for t in tickers_cartera
                    if float(precios_dict.get(str(t).upper(), 0) or 0) <= 0
                ]
                price_coverage_pct = (
                    round(
                        100.0 * (len(tickers_cartera) - len(tickers_sin_precio))
                        / len(tickers_cartera),
                        1,
                    )
                    if tickers_cartera
                    else 100.0
                )
                _agent_dbg(
                    "F",
                    "snapshot:ppc_fallback",
                    "tras relleno PPC",
                    {
                        "cartera": cartera_activa[:120],
                        "coverage_pct": price_coverage_pct,
                        "sin_precio": tickers_sin_precio[:30],
                    },
                )
        except Exception as _e_pe:
            _agent_dbg(
                "A",
                "snapshot:price_engine_exc",
                "PriceEngine excepción",
                {
                    "cartera": cartera_activa[:120],
                    "error_type": type(_e_pe).__name__,
                    "error_msg": str(_e_pe)[:500],
                },
            )


if __name__ == "__main__":
    main()
