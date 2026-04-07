#!/usr/bin/env python3
"""
Persiste scores MOD-23 (técnico / fundamental / total) en `scores_historicos`.

Uso:
  python scripts/actualizar_scores_diario.py
  python scripts/actualizar_scores_diario.py --dry-run --limit 5
  python scripts/actualizar_scores_diario.py --tickers GGAL,MELI

Tickers por defecto: activos con `activo=True` y tipo en CEDEAR, ACCION, ETF, FCI.
Override: variable `MQ26_SCORES_TICKERS` (comma-separated) o `--tickers`.

Salida: 0 si no hubo errores de proceso; 1 si falló al menos un ticker (se registran en log).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_TIPOS_SCORE = frozenset({"CEDEAR", "ACCION", "ETF", "FCI"})


def _parse_tickers_arg(raw: str | None) -> list[tuple[str, str]]:
    """Lista de (ticker_local, tipo). Sin DB: solo CEDEAR por defecto."""
    if not raw:
        return []
    out: list[tuple[str, str]] = []
    for part in raw.replace(";", ",").split(","):
        t = part.strip().upper()
        if t:
            out.append((t, "CEDEAR"))
    return out


def _pairs_from_db(limit: int | None) -> list[tuple[str, str]]:
    from core.db_manager import get_activos_df

    df = get_activos_df(only_active=True)
    if df.empty:
        return []
    df = df[df["tipo"].astype(str).str.upper().isin(_TIPOS_SCORE)]
    pairs = [
        (str(r["ticker_local"]).upper().strip(), str(r["tipo"]).upper().strip())
        for _, r in df.iterrows()
        if str(r.get("ticker_local", "")).strip()
    ]
    pairs.sort(key=lambda x: x[0])
    if limit is not None and limit > 0:
        pairs = pairs[:limit]
    return pairs


def run_scores_batch(
    fecha: date,
    pairs: list[tuple[str, str]],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Calcula score por ticker y persiste con upsert.
    Returns: (exitosos, fallidos)
    """
    from core.db_manager import upsert_score_historico
    from services.scoring_engine import calcular_score_total

    ok = err = 0
    for ticker, tipo in pairs:
        if dry_run:
            logger.info("[dry-run] %s (%s)", ticker, tipo)
            ok += 1
            continue
        try:
            r = calcular_score_total(ticker, tipo)
            st = float(r.get("Score_Tec", 0) or 0)
            sf = float(r.get("Score_Fund", 0) or 0)
            stot = float(r.get("Score_Total", 0) or 0)
            upsert_score_historico(ticker, fecha, st, sf, stot)
            ok += 1
        except Exception as e:
            logger.warning("Score falló %s (%s): %s", ticker, tipo, e)
            err += 1
    return ok, err


def main() -> int:
    ap = argparse.ArgumentParser(description="Scores diarios → scores_historicos")
    ap.add_argument("--fecha", type=str, default="", help="YYYY-MM-DD (default: hoy)")
    ap.add_argument("--dry-run", action="store_true", help="No escribe BD ni llama al motor")
    ap.add_argument("--limit", type=int, default=0, help="Máximo de tickers (0 = sin límite)")
    ap.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Lista comma-separated (tipo CEDEAR implícito)",
    )
    args = ap.parse_args()

    if args.fecha.strip():
        try:
            y, m, d = args.fecha.strip().split("-")
            fecha = date(int(y), int(m), int(d))
        except Exception:
            logger.error("Fecha inválida: use YYYY-MM-DD")
            return 1
    else:
        fecha = date.today()

    env_tickers = (os.environ.get("MQ26_SCORES_TICKERS") or "").strip()
    pairs = _parse_tickers_arg(args.tickers.strip() or env_tickers)
    if not pairs:
        lim = args.limit if args.limit > 0 else None
        pairs = _pairs_from_db(lim)
    elif args.limit > 0:
        pairs = pairs[: args.limit]

    if not pairs:
        logger.error(
            "No hay tickers (BD vacía o sin activos). "
            "Definí --tickers o MQ26_SCORES_TICKERS o cargá el universo."
        )
        return 1

    ok, bad = run_scores_batch(fecha, pairs, dry_run=args.dry_run)
    logger.info("Scores %s: OK=%s errores=%s", fecha.isoformat(), ok, bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
