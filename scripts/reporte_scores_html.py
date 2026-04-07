#!/usr/bin/env python3
"""
Genera un HTML tabular con el historial reciente de `scores_historicos`.

Uso:
  python scripts/reporte_scores_html.py --out reportes/scores_ultimos.html
  python scripts/reporte_scores_html.py --out /tmp/x.html --days 14

Tipografía: Barlow (Regular / Semibold) vía Google Fonts.
"""
from __future__ import annotations

import argparse
import html as html_module
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fetch_rows(days: int):
    from core.db_manager import ScoreHistorico, get_session

    since = date.today() - timedelta(days=max(1, days))
    with get_session() as s:
        rows = (
            s.query(ScoreHistorico)
            .filter(ScoreHistorico.fecha >= since)
            .order_by(ScoreHistorico.fecha.desc(), ScoreHistorico.ticker)
            .all()
        )
        return [
            {
                "ticker": r.ticker,
                "fecha": r.fecha,
                "score_tecnico": r.score_tecnico,
                "score_fundamental": r.score_fundamental,
                "score_total": r.score_total,
            }
            for r in rows
        ]


def build_html(rows: list[dict], *, title: str = "MQ26 — Historial de scores") -> str:
    esc = html_module.escape
    head = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;800&display=swap" rel="stylesheet"/>
<style>
  body {{ font-family: 'Barlow', sans-serif; margin: 1.5rem; background: #f6f7f9; color: #1a1d24; }}
  h1 {{ font-weight: 800; font-stretch: semi-condensed; font-size: 1.35rem; margin: 0 0 1rem 0; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 960px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  th, td {{ text-align: left; padding: 0.55rem 0.75rem; border-bottom: 1px solid #e8eaef; font-size: 0.92rem; }}
  th {{ font-weight: 600; background: #eef1f6; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  caption {{ caption-side: bottom; padding-top: 0.75rem; font-size: 0.85rem; color: #5c6473; }}
</style>
</head>
<body>
<h1>{esc(title)}</h1>
<table>
<thead><tr><th>Fecha</th><th>Ticker</th><th class="num">Téc.</th><th class="num">Fund.</th><th class="num">Total</th></tr></thead>
<tbody>
"""
    body_rows: list[str] = []
    for r in rows:
        fd = r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"])
        body_rows.append(
            "<tr>"
            f"<td>{esc(fd)}</td>"
            f"<td>{esc(str(r['ticker']))}</td>"
            f"<td class=\"num\">{r['score_tecnico']:.1f}</td>"
            f"<td class=\"num\">{r['score_fundamental']:.1f}</td>"
            f"<td class=\"num\">{r['score_total']:.1f}</td>"
            "</tr>"
        )
    foot = (
        "</tbody>\n<caption>"
        f"{len(rows)} filas</caption>\n</table>\n</body>\n</html>"
    )
    return head + "\n".join(body_rows) + "\n" + foot


def main() -> int:
    ap = argparse.ArgumentParser(description="Reporte HTML scores_historicos")
    ap.add_argument("--out", type=str, required=True, help="Ruta del .html de salida")
    ap.add_argument("--days", type=int, default=30, help="Días hacia atrás desde hoy")
    args = ap.parse_args()

    rows = _fetch_rows(int(args.days))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(rows), encoding="utf-8")
    print(f"Escrito {out} ({len(rows)} filas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
