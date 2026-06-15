#!/usr/bin/env python3
"""
Smoke HTTP contra MQ26 desplegado (o local).

Uso:
  python scripts/smoke_produccion.py
  python scripts/smoke_produccion.py --base-url https://mq26-production.up.railway.app

Requiere: requests (requirements.txt).
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke: GET /_stcore/health")
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8502",
        help="URL base sin barra final (default: Streamlit local 8502)",
    )
    p.add_argument("--timeout", type=float, default=30.0, help="Timeout por request")
    args = p.parse_args()
    base = str(args.base_url).rstrip("/")
    url = urljoin(base + "/", "_stcore/health")
    try:
        import requests
    except ImportError:
        print("ERROR: pip install requests", file=sys.stderr)
        return 2
    try:
        r = requests.get(url, timeout=args.timeout)
    except requests.RequestException as e:
        print(f"FAIL: {url} → {e}", file=sys.stderr)
        return 1
    if r.status_code != 200:
        print(f"FAIL: {url} → HTTP {r.status_code}", file=sys.stderr)
        return 1
    print(f"OK: {url} → HTTP {r.status_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
