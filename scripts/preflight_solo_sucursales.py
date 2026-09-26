#!/usr/bin/env python3
"""Auditoría de sólo lectura previa a migrar ventas de un depósito a una sucursal.

No mueve stock, no cambia el default, no cierra turnos ni borra cajas. Ejecutar
primero contra un respaldo/restauración y contrastar luego con la instancia.
La URL de PostgreSQL se pasa por variable de entorno para no dejar contraseñas
en el historial de comandos ni en los argumentos visibles del proceso.

    VENTALIBRA_MIGRATION_DB_URL=postgresql://... python scripts/preflight_solo_sucursales.py \
      --origen 1 --destino 2

Para SQLite local puede usarse --sqlite /ruta/absoluta/a/copia.db.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path


def _abrir(*, sqlite_path: str | None, pg_url: str | None):
    if sqlite_path:
        # mode=ro evita incluso crear por accidente un archivo inexistente.
        path = Path(sqlite_path).resolve()
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn
    if not pg_url:
        raise ValueError("Se requiere --sqlite o VENTALIBRA_MIGRATION_DB_URL")
    import psycopg

    # Read-only impuesto por el servidor antes de la primera sentencia.
    return psycopg.connect(pg_url, options="-c default_transaction_read_only=on")


def auditar(conn, origen: int, destino: int) -> dict:
    """Devuelve hechos e impedimentos; no genera SQL ejecutable ni escribe datos."""
    if origen == destino:
        raise ValueError("El origen y el destino deben ser distintos")
    filas = conn.execute(
        "SELECT id, name, location_type, active, is_default FROM locations "
        "WHERE id IN (%s, %s)" if conn.__class__.__module__.startswith("psycopg") else
        "SELECT id, name, location_type, active, is_default FROM locations WHERE id IN (?, ?)",
        (origen, destino),
    ).fetchall()
    ubicaciones = {
        int(f[0]): {"id": int(f[0]), "nombre": f[1], "tipo": f[2],
                    "activa": bool(f[3]), "default": bool(f[4])}
        for f in filas
    }
    bloqueos = []
    if origen not in ubicaciones or destino not in ubicaciones:
        bloqueos.append("Origen o destino inexistente")
    if origen in ubicaciones and ubicaciones[origen]["tipo"] != "warehouse":
        bloqueos.append("El origen no es warehouse")
    if destino in ubicaciones and (ubicaciones[destino]["tipo"] != "store" or not ubicaciones[destino]["activa"]):
        bloqueos.append("El destino no es una sucursal store activa")
    if origen in ubicaciones and not ubicaciones[origen]["default"]:
        bloqueos.append("El origen ya no es la ubicación predeterminada; revisar el plan")

    # No suponer que el destino está vacío: el stock se suma al saldo existente.
    # La migración posterior deberá hacerlo vía transferencias del dominio,
    # nunca duplicando ni reescribiendo movimientos históricos.
    params = (origen, destino)
    ph = "%s" if conn.__class__.__module__.startswith("psycopg") else "?"
    saldos = conn.execute(
        "SELECT location_id, item_id, variant_id, SUM(quantity_delta) "
        f"FROM stock_movements WHERE location_id IN ({ph}, {ph}) "
        "GROUP BY location_id, item_id, variant_id "
        "HAVING SUM(quantity_delta) <> 0 ORDER BY location_id, item_id, variant_id",
        params,
    ).fetchall()
    stock = [
        {"ubicacion_id": int(loc), "item_id": int(item), "variante_id": variant,
         "saldo": str(saldo)}
        for loc, item, variant, saldo in saldos
    ]
    negativos = [r for r in stock if r["ubicacion_id"] == origen and Decimal(r["saldo"]) < 0]
    if negativos:
        bloqueos.append(f"El origen tiene {len(negativos)} saldo(s) negativo(s); la transferencia normal no los admite")

    turnos = conn.execute(
        "SELECT t.id, t.caja_id, c.sucursal_id FROM turnos_caja t JOIN cajas c ON c.id = t.caja_id "
        f"WHERE c.sucursal_id IN ({ph}, {ph}) AND t.estado = {ph} ORDER BY t.id",
        (origen, destino, "abierto"),
    ).fetchall()
    abiertos_origen = [t for t in turnos if int(t[2]) == origen]
    abiertos_destino = [t for t in turnos if int(t[2]) == destino]
    if abiertos_origen:
        bloqueos.append(f"El origen tiene {len(abiertos_origen)} turno(s) abierto(s); cerrarlos por la aplicación")
    if abiertos_destino:
        bloqueos.append(f"El destino tiene {len(abiertos_destino)} turno(s) abierto(s); cerrarlos por la aplicación")
    cajas = conn.execute(
        f"SELECT id FROM cajas WHERE sucursal_id = {ph} ORDER BY id", (origen,)
    ).fetchall()
    # No filtrar ni borrar cajas en el preflight: algunas tienen ventas históricas.
    return {
        "origen": ubicaciones.get(origen), "destino": ubicaciones.get(destino),
        "stock": stock, "saldos_negativos_origen": negativos,
        "turnos_abiertos_origen": [{"id": int(t[0]), "caja_id": int(t[1])} for t in abiertos_origen],
        "turnos_abiertos_destino": [{"id": int(t[0]), "caja_id": int(t[1])} for t in abiertos_destino],
        "cajas_historicas_origen": [int(c[0]) for c in cajas],
        "bloqueos": bloqueos, "apto_para_planificar": not bloqueos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", help="Copia SQLite local (sólo lectura)")
    parser.add_argument("--origen", type=int, required=True)
    parser.add_argument("--destino", type=int, required=True)
    args = parser.parse_args()
    pg_url = os.environ.get("VENTALIBRA_MIGRATION_DB_URL")
    if bool(args.sqlite) == bool(pg_url):
        parser.error("Indicar exactamente uno: --sqlite o VENTALIBRA_MIGRATION_DB_URL")
    with _abrir(sqlite_path=args.sqlite, pg_url=pg_url) as conn:
        informe = auditar(conn, args.origen, args.destino)
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0 if informe["apto_para_planificar"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
