"""
scripts/migrate_to_domain_dbs.py — Migración a bases de datos por dominio

Mueve los datos de:
  - 0_Data_Maestra/dss_master.db   (4 clientes reales, 141 transacciones históricas)
  - 0_Data_Maestra/master_quant.db (2 clientes test, 51 ops, 50 alertas, config)
  - 0_Data_Maestra/Maestra_Transaccional.csv (51 operaciones)

hacia las nuevas bases de datos por dominio:
  - 0_Data_Maestra/db_clientes.db
  - 0_Data_Maestra/db_auth.db
  - 0_Data_Maestra/db_portfolio.db
  - 0_Data_Maestra/db_mercado.db
  - 0_Data_Maestra/db_config.db
  - 0_Data_Maestra/db_auditoria.db

Ejecutar una sola vez:
    python scripts/migrate_to_domain_dbs.py

Es idempotente: duplicados son detectados y saltados.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path

# ── Setup paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "0_Data_Maestra"
DSS_DB   = DATA_DIR / "dss_master.db"
MQ_DB    = DATA_DIR / "master_quant.db"
CSV_TRANSAC = DATA_DIR / "Maestra_Transaccional.csv"

# Inicializar dominios (crea archivos y tablas)
from core.db_domains import init_all_domains, ALL_DOMAINS, CLIENTES, AUTH, PORTFOLIO, MERCADO, CONFIG, AUDITORIA
import core.db_clientes   # noqa: F401 — registra modelos
import core.db_auth       # noqa: F401
import core.db_portfolio  # noqa: F401
import core.db_mercado    # noqa: F401
import core.db_config     # noqa: F401
import core.db_auditoria  # noqa: F401
init_all_domains()

_SEPARADOR = "─" * 60

def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")

def _skip(msg: str) -> None:
    print(f"  ⟳  {msg} (ya existe, saltado)")

def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}")

def _section(title: str) -> None:
    print(f"\n{_SEPARADOR}\n  {title}\n{_SEPARADOR}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Migrar CLIENTES
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_clientes() -> dict[str, dict[int, int]]:
    """
    Migra clientes de DSS y master_quant a db_clientes.db.
    Retorna mapa {fuente: {old_id: new_id}} para cross-reference.
    """
    _section("MIGRAR CLIENTES → db_clientes.db")
    from core.db_clientes import Cliente

    id_map: dict[str, dict[int, int]] = {"dss": {}, "mq": {}}

    sources = []
    if DSS_DB.exists():
        sources.append(("dss", DSS_DB,
            "SELECT id, nombre, perfil_riesgo, capital_usd FROM clientes"))
    if MQ_DB.exists():
        sources.append(("mq", MQ_DB,
            "SELECT id, nombre, perfil_riesgo, horizonte_label, capital_usd, tipo_cliente FROM clientes"))

    for fuente, db_path, query in sources:
        con = sqlite3.connect(str(db_path))
        rows = con.execute(query).fetchall()
        con.close()

        for row in rows:
            old_id = row[0]
            nombre = str(row[1]).strip()
            perfil = str(row[2]) if len(row) > 2 else "Moderado"
            horiz  = str(row[3]) if fuente == "mq" and len(row) > 3 else "1 año"
            cap    = float(row[4] if fuente == "mq" and len(row) > 4 else (row[3] if len(row) > 3 else 0.0) or 0.0)
            tipo   = str(row[5]) if fuente == "mq" and len(row) > 5 else "Persona"

            with CLIENTES.session() as s:
                exists = (
                    s.query(Cliente)
                    .filter(Cliente.nombre == nombre, Cliente.tenant_id == "default")
                    .first()
                )
                if exists:
                    id_map[fuente][old_id] = exists.id
                    _skip(f"[{fuente}] cliente '{nombre}' (id_old={old_id} → new_id={exists.id})")
                    continue

                c = Cliente(
                    nombre=nombre,
                    perfil_riesgo=perfil,
                    horizonte_label=horiz,
                    capital_usd=cap,
                    tipo_cliente=tipo,
                    tenant_id="default",
                )
                s.add(c)
                s.flush()
                id_map[fuente][old_id] = c.id
                _ok(f"[{fuente}] cliente '{nombre}' (id_old={old_id} → new_id={c.id})")

    return id_map


# ─────────────────────────────────────────────────────────────────────────────
# 2. Migrar ACTIVOS (universo de instrumentos)
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_activos() -> dict[str, dict[int, str]]:
    """
    Migra activos de DSS y master_quant a db_portfolio.db.
    Retorna {fuente: {old_activo_id: ticker_local}} para cross-reference.
    """
    _section("MIGRAR ACTIVOS → db_portfolio.db")
    from core.db_portfolio import Activo

    activo_map: dict[str, dict[int, str]] = {"dss": {}, "mq": {}}

    sources = []
    if DSS_DB.exists():
        sources.append(("dss", DSS_DB, """
            SELECT id, tipo, ticker_local, ticker_yf, nombre, ratio, sector, pais
            FROM activos"""))
    if MQ_DB.exists():
        sources.append(("mq", MQ_DB, """
            SELECT id, tipo, ticker_local, ticker_yf, nombre, ratio, sector, pais,
                   cupon_anual, vencimiento, calificacion, ley, moneda
            FROM activos"""))

    for fuente, db_path, query in sources:
        con = sqlite3.connect(str(db_path))
        rows = con.execute(query).fetchall()
        con.close()

        for row in rows:
            old_id = row[0]
            tipo   = str(row[1] or "CEDEAR")
            tl     = str(row[2] or "").upper().strip()
            ty     = str(row[3] or tl)
            nombre = str(row[4] or "")
            ratio  = float(row[5] or 1.0)
            sector = str(row[6] or "")
            pais   = str(row[7] or "Estados Unidos")
            cupon  = float(row[8]) if fuente == "mq" and len(row) > 8 and row[8] else None
            vcto   = str(row[9])[:10] if fuente == "mq" and len(row) > 9 and row[9] else None
            cal    = str(row[10]) if fuente == "mq" and len(row) > 10 and row[10] else None
            ley    = str(row[11]) if fuente == "mq" and len(row) > 11 and row[11] else None
            moneda = str(row[12]) if fuente == "mq" and len(row) > 12 and row[12] else "USD"

            if not tl:
                continue

            activo_map[fuente][old_id] = tl

            with PORTFOLIO.session() as s:
                exists = s.query(Activo).filter(Activo.ticker_local == tl).first()
                if exists:
                    _skip(f"[{fuente}] activo {tl} (id_old={old_id})")
                    continue

                extra = {}
                if cupon is not None:
                    extra["cupon_anual"] = cupon
                if vcto:
                    try:
                        extra["vencimiento"] = datetime.date.fromisoformat(vcto)
                    except ValueError:
                        pass
                if cal:
                    extra["calificacion"] = cal
                if ley:
                    extra["ley"] = ley

                act = Activo(
                    ticker_local=tl, ticker_yf=ty, tipo=tipo,
                    nombre=nombre, ratio=ratio, sector=sector,
                    pais=pais, moneda=moneda, **extra,
                )
                s.add(act)
                _ok(f"[{fuente}] activo {tl} ({tipo}) (id_old={old_id})")

    return activo_map


# ─────────────────────────────────────────────────────────────────────────────
# 3. Migrar TRANSACCIONES (DSS: tabla transacciones)
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_transacciones_dss(
    cliente_map: dict[int, int],
    activo_map: dict[int, str],
) -> int:
    """Migra las 141 transacciones históricas de dss_master.db."""
    if not DSS_DB.exists():
        return 0
    _section("MIGRAR TRANSACCIONES DSS → db_portfolio.db")
    from core.db_portfolio import TransaccionalOperacion

    con = sqlite3.connect(str(DSS_DB))
    rows = con.execute("""
        SELECT t.id, t.cliente_id, t.activo_id, t.fecha, t.tipo_op,
               t.nominales, t.precio_bruto_ars, t.total_neto_ars, t.notas,
               a.ticker_local, c.nombre
        FROM transacciones t
        LEFT JOIN activos a ON a.id = t.activo_id
        LEFT JOIN clientes c ON c.id = t.cliente_id
    """).fetchall()
    con.close()

    imported = 0
    for row in rows:
        (old_id, cli_old, act_old, fecha_raw, tipo_op,
         nominales, precio_ars, total_neto, notas,
         ticker, cli_nombre) = row

        new_cli_id = cliente_map.get(cli_old)
        ticker_l   = activo_map.get(act_old, str(ticker or "").upper().strip())
        if not ticker_l:
            _warn(f"Transacción DSS id={old_id}: activo_id={act_old} sin ticker — saltado")
            continue

        try:
            fecha = datetime.date.fromisoformat(str(fecha_raw)[:10])
        except ValueError:
            _warn(f"Transacción DSS id={old_id}: fecha inválida '{fecha_raw}' — saltado")
            continue

        cartera = f"{cli_nombre or 'Sin nombre'} | DSS"
        tipo_op_norm = "COMPRA" if str(tipo_op).upper() in ("COMPRA", "BUY") else "VENTA"

        with PORTFOLIO.session() as s:
            exists = (
                s.query(TransaccionalOperacion)
                .filter(
                    TransaccionalOperacion.ticker == ticker_l,
                    TransaccionalOperacion.fecha_compra == fecha,
                    TransaccionalOperacion.cantidad == float(nominales or 0),
                    TransaccionalOperacion.ppc_ars == float(precio_ars or 0),
                )
                .first()
            )
            if exists:
                _skip(f"trans DSS id={old_id} {ticker_l} {fecha}")
                continue

            s.add(TransaccionalOperacion(
                cartera=cartera,
                fecha_compra=fecha,
                ticker=ticker_l,
                cantidad=float(nominales or 0),
                ppc_ars=float(precio_ars or 0),
                ppc_usd=0.0,
                tipo=tipo_op_norm,
                tenant_id="default",
            ))
            imported += 1

    _ok(f"Transacciones DSS importadas: {imported} de {len(rows)}")
    return imported


# ─────────────────────────────────────────────────────────────────────────────
# 4. Migrar TRANSACCIONAL_OPERACIONES (master_quant)
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_transaccional_ops() -> int:
    """Migra las 51 operaciones de transaccional_operaciones en master_quant."""
    if not MQ_DB.exists():
        return 0
    _section("MIGRAR TRANSACCIONAL_OPERACIONES → db_portfolio.db")
    from core.db_portfolio import TransaccionalOperacion

    con = sqlite3.connect(str(MQ_DB))
    rows = con.execute("""
        SELECT cartera, fecha_compra, ticker, cantidad, ppc_usd, ppc_ars,
               tipo, lamina_vn, moneda_precio
        FROM transaccional_operaciones
    """).fetchall()
    con.close()

    imported = 0
    for row in rows:
        (cartera, fecha_raw, ticker, cantidad,
         ppc_usd, ppc_ars, tipo, lamina_vn, moneda) = row

        try:
            fecha = datetime.date.fromisoformat(str(fecha_raw)[:10])
        except ValueError:
            continue

        ticker = str(ticker or "").upper().strip()
        if not ticker:
            continue

        with PORTFOLIO.session() as s:
            exists = (
                s.query(TransaccionalOperacion)
                .filter(
                    TransaccionalOperacion.cartera == cartera,
                    TransaccionalOperacion.fecha_compra == fecha,
                    TransaccionalOperacion.ticker == ticker,
                    TransaccionalOperacion.cantidad == float(cantidad or 0),
                )
                .first()
            )
            if exists:
                _skip(f"transop {ticker} {fecha} ({cartera[:30]}...)")
                continue

            lam = float(lamina_vn) if lamina_vn and str(lamina_vn) not in ("", "None", "nan") else None
            s.add(TransaccionalOperacion(
                cartera=str(cartera or ""),
                fecha_compra=fecha,
                ticker=ticker,
                cantidad=float(cantidad or 0),
                ppc_usd=float(ppc_usd or 0),
                ppc_ars=float(ppc_ars or 0),
                tipo=str(tipo or "CEDEAR"),
                lamina_vn=lam,
                moneda_precio=str(moneda or "ARS"),
                tenant_id="default",
            ))
            imported += 1

    _ok(f"Operaciones master_quant importadas: {imported} de {len(rows)}")
    return imported


# ─────────────────────────────────────────────────────────────────────────────
# 5. Migrar CSV Maestra_Transaccional
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_csv() -> int:
    if not CSV_TRANSAC.exists():
        _warn("Maestra_Transaccional.csv no encontrado — saltado")
        return 0
    _section("MIGRAR CSV → db_portfolio.db")
    from core.db_portfolio import importar_desde_csv
    n = importar_desde_csv(CSV_TRANSAC)
    _ok(f"Operaciones CSV importadas: {n}")
    return n


# ─────────────────────────────────────────────────────────────────────────────
# 6. Migrar ALERTAS y RECOMENDACIONES AUDITORIA
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_auditoria() -> None:
    if not MQ_DB.exists():
        return
    _section("MIGRAR ALERTAS & RECOMENDACIONES → db_auditoria.db")
    from core.db_auditoria import AlertaLog, RecomendacionAuditoria

    con = sqlite3.connect(str(MQ_DB))

    alertas = con.execute("""
        SELECT cliente_id, tipo_alerta, ticker, mensaje, enviada, usuario, created_at
        FROM alertas_log
    """).fetchall()

    # Columnas reales en master_quant: evento, origen, cliente_id, cliente_nombre,
    # tenant_id, actor, correlation_id, cartera, perfil, capital_ars, filas, payload_json, timestamp
    recom = con.execute("""
        SELECT evento, origen, cliente_id, cliente_nombre,
               perfil, capital_ars, payload_json, actor, timestamp
        FROM recomendaciones_auditoria
    """).fetchall()
    con.close()

    with AUDITORIA.session() as s:
        existing_alertas = s.query(AlertaLog).count()
        existing_recom   = s.query(RecomendacionAuditoria).count()

    if existing_alertas == 0:
        with AUDITORIA.session() as s:
            for row in alertas:
                (cli_id, tipo, ticker, msg, enviada, usuario, ts) = row
                s.add(AlertaLog(
                    cliente_id=cli_id, tipo_alerta=tipo or "",
                    ticker=(ticker or "").upper(), mensaje=msg or "",
                    enviada=bool(enviada), usuario=usuario or "",
                    tenant_id="default",
                ))
        _ok(f"Alertas migradas: {len(alertas)}")
    else:
        _skip(f"alertas_log ({existing_alertas} existentes)")

    if existing_recom == 0:
        with AUDITORIA.session() as s:
            for row in recom:
                (evento, origen, cli_id, cli_nombre,
                 perfil, cap_ars, payload_json, actor, ts) = row
                s.add(RecomendacionAuditoria(
                    evento=evento or "", origen=origen or "",
                    cliente_id=cli_id, cliente_nombre=cli_nombre or "",
                    capital_ars=cap_ars,
                    perfil=perfil or "",
                    resultado_json=payload_json or "{}",
                    usuario=actor or "", tenant_id="default",
                ))
        _ok(f"Recomendaciones migradas: {len(recom)}")
    else:
        _skip(f"recomendaciones_auditoria ({existing_recom} existentes)")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Migrar CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_config() -> None:
    if not MQ_DB.exists():
        return
    _section("MIGRAR CONFIGURACION → db_config.db")
    from core.db_config import guardar_config, obtener_config

    con = sqlite3.connect(str(MQ_DB))
    rows = con.execute("SELECT clave, valor FROM configuracion").fetchall()
    con.close()

    for (clave, valor) in rows:
        existing = obtener_config(clave)
        if existing is not None:
            _skip(f"config[{clave}]")
            continue
        guardar_config(clave, valor)
        _ok(f"config[{clave}] = {str(valor)[:40]}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Migrar PRECIOS FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_precios_fallback() -> None:
    if not MQ_DB.exists():
        return
    _section("MIGRAR PRECIOS FALLBACK → db_mercado.db")
    from core.db_mercado import guardar_precio_fallback

    con = sqlite3.connect(str(MQ_DB))
    rows = con.execute("SELECT ticker, precio_ars, fuente FROM precios_fallback").fetchall()
    con.close()

    for (ticker, precio, fuente) in rows:
        if ticker and precio and float(precio) > 0:
            guardar_precio_fallback(ticker, float(precio), fuente or "migrado")
            _ok(f"precio_fallback {ticker} = {precio:.2f} ARS")

    if not rows:
        _warn("No hay precios_fallback en master_quant.db")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Resumen final
# ─────────────────────────────────────────────────────────────────────────────

def _print_resumen() -> None:
    print(f"\n{'═' * 60}")
    print("  RESUMEN BASES DE DATOS POR DOMINIO")
    print(f"{'═' * 60}")
    for domain in ALL_DOMAINS:
        path = Path(domain.path)
        size_kb = path.stat().st_size / 1024 if path.exists() else 0
        con = sqlite3.connect(str(path))
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        rows_total = 0
        table_info = []
        for (t,) in tables:
            n = con.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
            rows_total += n
            table_info.append(f"{t}({n})")
        con.close()
        print(f"\n  {domain.nombre:<15} {size_kb:>7.1f} KB   {rows_total:>5} rows")
        for ti in table_info:
            print(f"    └─ {ti}")
    print(f"\n{'═' * 60}")
    print("  Archivos LEGACY (pueden archivarse):")
    for legacy in [DSS_DB, MQ_DB]:
        if legacy.exists():
            kb = legacy.stat().st_size / 1024
            print(f"    {legacy.name:<30} {kb:.1f} KB — migrado, mantener como backup")
    print(f"{'═' * 60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   MQ26 — Migración a bases de datos por dominio          ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    print(f"  Fuentes: {DSS_DB.name}, {MQ_DB.name}, {CSV_TRANSAC.name}")
    print(f"  Destino: {DATA_DIR}\n")

    # Paso 1: clientes
    id_maps = _migrate_clientes()

    # Paso 2: activos
    activo_maps = _migrate_activos()

    # Paso 3: transacciones históricas DSS (141 trades)
    _migrate_transacciones_dss(id_maps["dss"], activo_maps["dss"])

    # Paso 4: transaccional_operaciones de master_quant (51 ops)
    _migrate_transaccional_ops()

    # Paso 5: CSV (deduplicado automáticamente)
    _migrate_csv()

    # Paso 6: alertas + recomendaciones
    _migrate_auditoria()

    # Paso 7: configuración
    _migrate_config()

    # Paso 8: precios fallback
    _migrate_precios_fallback()

    # Resumen
    _print_resumen()

    print("  ✅  Migración completada. Bases de datos por dominio listas.")
    print("  📌  Mantené los archivos legacy como backup hasta verificar.")
    print()


if __name__ == "__main__":
    main()
