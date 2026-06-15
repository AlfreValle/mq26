#!/usr/bin/env python3
"""
Envío masivo del reporte mensual HTML (MQ26) por correo.

Uso:
  python scripts/enviar_reportes_mensuales.py --map destinatarios.json
  python scripts/enviar_reportes_mensuales.py --dry-run --map destinatarios.json

El JSON debe ser un objeto { "<cliente_id>": "email@dominio.com", ... }.
Alternativa: variable de entorno MQ26_REPORTES_DESTINATARIOS con el mismo JSON.

Códigos de salida:
  0 — ningún envío falló (o dry-run sin errores de validación).
  1 — al menos un destino falló o mapa inválido / vacío.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def _resolve_ccl() -> float:
    raw = (os.environ.get("CCL_FALLBACK_OVERRIDE") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    try:
        import config as cfg

        return float(getattr(cfg, "CCL_FALLBACK", 1500.0))
    except Exception:
        return 1500.0


def _metricas_desde_fila(row: pd.Series, ccl: float) -> dict:
    perf = row.get("Perfil", "Moderado")
    cap_usd = float(row.get("Capital_USD", 0.0) or 0.0)
    valor_ars = cap_usd * ccl if ccl > 0 else 0.0
    return {
        "valor_ars": valor_ars,
        "valor_usd": cap_usd,
        "pnl_ars": 0.0,
        "pnl_pct": 0.0,
        "pnl_mes_pct": 0.0,
        "sharpe": 0.0,
        "perfil_ref": str(perf),
    }


def cargar_mapa_destinatarios(path: str | None) -> dict[int, str]:
    raw_json: str | None = None
    if path:
        raw_json = Path(path).read_text(encoding="utf-8")
    else:
        raw_json = (os.environ.get("MQ26_REPORTES_DESTINATARIOS") or "").strip() or None
    if not raw_json:
        return {}
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        raise ValueError("El mapa debe ser un objeto JSON {id: email}.")
    out: dict[int, str] = {}
    for k, v in data.items():
        out[int(k)] = str(v).strip()
    return out


def procesar_reportes_mensuales(
    tenant_id: str,
    dest_map: dict[int, str],
    *,
    dry_run: bool = False,
) -> list[tuple[int, str, bool, str]]:
    """
    Por cada (cliente_id, email) genera HTML con generar_reporte_mensual_html y envía (si no dry-run).
    Devuelve lista de (cliente_id, email, ok, mensaje).
    """
    from core import db_manager as dbm
    from services.email_sender import enviar_email_gmail
    from services.reporte_mensual import generar_reporte_mensual_html

    dbm.init_db()
    df = dbm.obtener_clientes_df(tenant_id)
    ccl = _resolve_ccl()
    try:
        ccl_bd = dbm.obtener_config("ccl_fallback", None)
        if ccl_bd is not None and float(ccl_bd) > 0:
            ccl = float(ccl_bd)
    except Exception:
        pass

    results: list[tuple[int, str, bool, str]] = []
    for cid, email in sorted(dest_map.items()):
        if not email:
            results.append((cid, email, False, "email vacío"))
            continue
        ids_set = set(int(x) for x in df["ID"].tolist()) if not df.empty else set()
        if cid not in ids_set:
            results.append((cid, email, False, "cliente_id no existe en tenant"))
            continue
        row = df[df["ID"].astype(int) == cid].iloc[0]
        nombre = str(row.get("Nombre", f"Cliente {cid}"))
        perfil = str(row.get("Perfil", "Moderado"))
        metricas = _metricas_desde_fila(row, ccl)
        html = generar_reporte_mensual_html(
            nombre,
            nombre,
            perfil,
            pd.DataFrame(),
            pd.DataFrame(),
            metricas,
            [],
            ccl,
            mes_año="",
        )
        asunto = f"Reporte mensual MQ26 — {nombre}"
        if dry_run:
            logger.info("[dry-run] id=%s email=%s asunto=%s html_bytes=%s", cid, email, asunto, len(html))
            results.append((cid, email, True, "dry-run"))
            continue
        ok, msg = enviar_email_gmail(email, asunto, html)
        results.append((cid, email, ok, msg))
        if not ok:
            logger.error("Fallo envío cliente_id=%s: %s", cid, msg)
    return results


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Envío masivo de reportes mensuales MQ26.")
    p.add_argument("--tenant", default=os.environ.get("MQ26_DB_TENANT_ID", "default"), help="Tenant ID")
    p.add_argument("--map", dest="map_path", default=None, help="Ruta JSON cliente_id -> email")
    p.add_argument("--dry-run", action="store_true", help="Solo validar y loguear; no SMTP")
    args = p.parse_args(argv)

    try:
        dest = cargar_mapa_destinatarios(args.map_path)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.error("Mapa inválido: %s", e)
        return 1
    if not dest:
        logger.error("Sin destinatarios: usá --map o MQ26_REPORTES_DESTINATARIOS.")
        return 1

    rows = procesar_reportes_mensuales(args.tenant, dest, dry_run=args.dry_run)
    failures = sum(1 for _cid, _em, ok, _m in rows if not ok)
    for cid, em, ok, msg in rows:
        logger.info("%s cliente_id=%s email=%s — %s", "OK" if ok else "FAIL", cid, em, msg)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
