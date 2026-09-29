#!/usr/bin/env python3
"""Auditoría de sólo lectura previa a migrar una instancia al modelo jerárquico de sucursales y depósitos
(`app/sucursales_migracion.py`, revisión de Alembic `0007`).

No escribe nada: la conexión es de sólo lectura impuesta por el servidor. Ejecutar primero contra una restauración
del respaldo y contrastar luego con la instancia. La URL de PostgreSQL va por variable de entorno para no dejar
contraseñas en el historial ni en los argumentos visibles del proceso.

    VENTALIBRA_MIGRATION_DB_URL=postgresql://... python scripts/preflight_jerarquia.py \
        [--mapa 2:1,5:3]

`--mapa` es el mismo `depósito:sucursal` que la revisión lee de `VENTALIBRA_DEPOSITOS_A_SUCURSAL`. Sale con
código 0 si la migración puede correr y con 2 si hay un bloqueo. Lo que **no** es un bloqueo pero conviene mirar
(cajas que cambian de sucursal, cierres diarios de un depósito que quedan como estaban, depósitos que van a la
sucursal predeterminada porque nadie dijo otra) sale en el informe.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sucursales_migracion import TIPO_DE_SUCURSAL_VIEJO, parsear_mapa  # noqa: E402


def _abrir(pg_url: str):
    import psycopg

    # Read-only impuesto por el servidor antes de la primera sentencia.
    return psycopg.connect(pg_url, options="-c default_transaction_read_only=on")


def _q(conn, sql: str, params: tuple = ()):
    if conn.__class__.__module__.startswith("psycopg"):
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params).fetchall()


def _existe(conn, tabla: str) -> bool:
    return _q(conn, "SELECT to_regclass(?)", (tabla,))[0][0] is not None


def auditar(conn, mapa: dict[int, int] | None = None) -> dict:
    """Devuelve hechos, avisos y bloqueos; no genera SQL ejecutable ni escribe datos."""
    mapa = mapa or {}
    bloqueos: list[str] = []
    avisos: list[str] = []

    if not _existe(conn, "branches"):
        bloqueos.append("Falta la tabla `branches`: el motor del deploy no es el de las sucursales jerárquicas")
        return {"bloqueos": bloqueos, "avisos": avisos, "apto_para_migrar": False}

    stores = _q(
        conn,
        "SELECT id, name, active, is_default FROM locations WHERE location_type = ? ORDER BY id",
        (TIPO_DE_SUCURSAL_VIEJO,),
    )
    ramas_previas = {r[0] for r in _q(conn, "SELECT id FROM branches")}
    sucursales = [
        {"id": r[0], "nombre": r[1], "activa": bool(r[2]), "default": bool(r[3])} for r in stores
    ]
    for s in sucursales:
        if s["id"] in ramas_previas:
            bloqueos.append(f"Ya existe una sucursal con id {s['id']}: no se puede conservar el id de «{s['nombre']}»")
    if stores and not any(s["activa"] for s in sucursales):
        bloqueos.append("Ninguna sucursal (`store`) está activa: no hay a quién dejar como predeterminada")

    activas = [s for s in sucursales if s["activa"]]
    default = next((s for s in activas if s["default"]), activas[0] if activas else None)

    huerfanos = _q(conn, "SELECT id, name, active FROM locations WHERE branch_id IS NULL AND location_type <> ? ORDER BY id",
                   (TIPO_DE_SUCURSAL_VIEJO,))
    ids_de_sucursal = {s["id"] for s in sucursales} | ramas_previas
    depositos = []
    for did, nombre, activo in huerfanos:
        destino = mapa.get(did, default["id"] if default else None)
        if destino is not None and destino not in ids_de_sucursal:
            bloqueos.append(f"El depósito {did} se asigna a la sucursal {destino}, que no existe")
        depositos.append({
            "id": did, "nombre": nombre, "activo": bool(activo), "sucursal_destino": destino,
            "por_mapa": did in mapa,
        })
    sin_mapa = [d["id"] for d in depositos if not d["por_mapa"]]
    if sin_mapa:
        avisos.append(
            f"{len(sin_mapa)} depósito(s) sin dueño van a la sucursal predeterminada "
            f"({default['nombre'] if default else '?'}): {sin_mapa}. Pasar `--mapa` si alguno es de otra."
        )

    cajas_reasignadas, cierres_sin_dueno = [], []
    if _existe(conn, "cajas"):
        propias = {s["id"] for s in sucursales} | ramas_previas
        for cid, nombre, sid in _q(conn, "SELECT id, nombre, sucursal_id FROM cajas WHERE sucursal_id IS NOT NULL ORDER BY id"):
            if sid in propias:
                continue
            destino = next((d["sucursal_destino"] for d in depositos if d["id"] == sid), None)
            if destino is None:
                avisos.append(f"La caja {cid} («{nombre}») apunta a la ubicación {sid}, que no resuelve a ninguna sucursal")
            else:
                cajas_reasignadas.append({"caja": cid, "nombre": nombre, "de": sid, "a": destino})
    if _existe(conn, "cierres_diarios"):
        propias = {s["id"] for s in sucursales} | ramas_previas
        for sid, n in _q(conn, "SELECT sucursal_id, COUNT(*) FROM cierres_diarios WHERE sucursal_id IS NOT NULL GROUP BY sucursal_id"):
            if sid not in propias:
                cierres_sin_dueno.append({"sucursal_id": sid, "cierres": int(n)})
    if cierres_sin_dueno:
        avisos.append(
            "Hay cierres diarios de un depósito (su numeración es única por sucursal): no se reasignan y "
            f"quedan como estaban: {cierres_sin_dueno}"
        )

    return {
        "sucursales_a_crear": sucursales,
        "sucursal_predeterminada": default,
        "depositos_sin_dueno": depositos,
        "cajas_que_cambian_de_sucursal": cajas_reasignadas,
        "cierres_diarios_de_un_deposito": cierres_sin_dueno,
        "avisos": avisos,
        "bloqueos": bloqueos,
        "apto_para_migrar": not bloqueos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapa", default="", help="depósito:sucursal separados por coma, p. ej. 2:1,5:3")
    args = parser.parse_args()
    pg_url = os.environ.get("VENTALIBRA_MIGRATION_DB_URL")
    if not pg_url:
        parser.error("Falta VENTALIBRA_MIGRATION_DB_URL")
    with _abrir(pg_url) as conn:
        informe = auditar(conn, parsear_mapa(args.mapa))
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0 if informe["apto_para_migrar"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
