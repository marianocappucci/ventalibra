"""Del modelo plano de ubicaciones (sucursal y depósito como pares de `locations`, PR #314) al jerárquico
(`branches` + `locations.branch_id`, `libracommerce` ADR-012/013).

La misma función corre en la revisión de Alembic `0007` (el deploy) y en el arranque de la app, como
`crear_cliente_lista_precio`: una instancia nueva y una vieja convergen por el mismo camino, y correrla dos
veces no hace nada la segunda.

🔑 **Los ids se conservan.** Cada `store` S pasa a ser la sucursal con `id = S.id`, y la propia fila S queda como
su depósito. Con eso `cajas.sucursal_id`, los turnos, los precios por sucursal y los cierres diarios siguen
apuntando a lo mismo sin reescribir historia, y el stock y los `stock_movements` no se mueven (ni hace falta
transferir nada: los saldos negativos que impedían transferir dejan de importar).

Lo que sí se reasigna: los depósitos que no eran sucursal (`warehouse`, sin dueño) van a la sucursal que diga
el mapa o, sin mapa, a la predeterminada; y las cajas de un depósito (hasta el 2026-09-25 cualquier ubicación
podía tener cajas) pasan a la sucursal de ese depósito. Los **cierres diarios** de un depósito no se tocan: su
numeración es única por sucursal y mezclarlos podría chocar; quedan como estaban y el preflight los cuenta.
"""
from __future__ import annotations

import os
from typing import Any

TIPO_DE_DEPOSITO = "warehouse"
TIPO_DE_SUCURSAL_VIEJO = "store"


def _tabla_existe(conn: Any, nombre: str) -> bool:
    return conn.execute("SELECT to_regclass(?)", (nombre,)).fetchone()[0] is not None


def migrar(conn: Any, *, depositos_a_sucursal: dict[int, int] | None = None) -> dict:
    """Idempotente. Devuelve un informe con lo que hizo (todo en cero si no había nada que hacer)."""
    mapa = depositos_a_sucursal or {}
    informe = {"sucursales_creadas": 0, "depositos_asignados": 0, "cajas_reasignadas": 0}

    stores = conn.execute(
        "SELECT id, name, active, is_default FROM locations WHERE location_type = ? ORDER BY id",
        (TIPO_DE_SUCURSAL_VIEJO,),
    ).fetchall()
    for sid, nombre, activa, _es_default in stores:
        if conn.execute("SELECT 1 FROM branches WHERE id = ?", (sid,)).fetchone():
            raise RuntimeError(
                f"Ya existe una sucursal con id {sid}: no se puede conservar el id de la ubicación "
                f"«{nombre}». Revisar a mano antes de migrar."
            )
        conn.execute(
            "INSERT INTO branches (id, name, active, is_default, default_location_id) VALUES (?, ?, ?, 0, ?)",
            (sid, nombre, activa, sid),
        )
        conn.execute(
            "UPDATE locations SET branch_id = ?, location_type = ? WHERE id = ?",
            (sid, TIPO_DE_DEPOSITO, sid),
        )
        informe["sucursales_creadas"] += 1

    if informe["sucursales_creadas"]:
        # Ids explícitos: la secuencia de `branches` no los vio.
        conn.execute(
            "SELECT setval(pg_get_serial_sequence('branches', 'id'), (SELECT MAX(id) FROM branches))"
        )

    if conn.execute("SELECT 1 FROM branches WHERE is_default = 1").fetchone() is None:
        preferida = conn.execute(
            "SELECT b.id FROM branches b JOIN locations l ON l.id = b.id "
            "WHERE b.active = 1 ORDER BY l.is_default DESC, b.id LIMIT 1"
        ).fetchone()
        if preferida:
            conn.execute("UPDATE branches SET is_default = 1 WHERE id = ?", (preferida[0],))

    destino_por_defecto = conn.execute("SELECT id FROM branches WHERE is_default = 1").fetchone()
    huerfanos = conn.execute("SELECT id FROM locations WHERE branch_id IS NULL ORDER BY id").fetchall()
    for (did,) in huerfanos:
        destino = mapa.get(did) or (destino_por_defecto[0] if destino_por_defecto else None)
        if destino is None:
            continue
        if conn.execute("SELECT 1 FROM branches WHERE id = ?", (destino,)).fetchone() is None:
            raise RuntimeError(f"El depósito {did} se asigna a la sucursal {destino}, que no existe.")
        conn.execute("UPDATE locations SET branch_id = ? WHERE id = ?", (destino, did))
        informe["depositos_asignados"] += 1

    if _tabla_existe(conn, "cajas"):
        cur = conn.execute(
            "UPDATE cajas SET sucursal_id = (SELECT l.branch_id FROM locations l WHERE l.id = cajas.sucursal_id) "
            "WHERE sucursal_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM branches b WHERE b.id = cajas.sucursal_id) "
            "AND EXISTS (SELECT 1 FROM locations l WHERE l.id = cajas.sucursal_id AND l.branch_id IS NOT NULL)"
        )
        informe["cajas_reasignadas"] = cur.rowcount or 0
    return informe


def parsear_mapa(texto: str) -> dict[int, int]:
    """`«2:1,5:3»` -> `{2: 1, 5: 3}` (depósito -> sucursal). Vacío -> sin mapa."""
    mapa: dict[int, int] = {}
    for par in filter(None, (p.strip() for p in texto.split(","))):
        deposito, _, sucursal = par.partition(":")
        mapa[int(deposito)] = int(sucursal)
    return mapa


def asegurar_minimas(conn: Any) -> dict:
    """Deja la instancia en el modelo jerárquico y con lo mínimo: migra lo viejo (`migrar`), y garantiza una
    sucursal activa, un depósito activo por cada sucursal activa y un depósito predeterminado de la instancia.

    La llaman `db.connect()` (en cada arranque y al restaurar un respaldo, que puede traer el modelo viejo) y
    nada más: la revisión `0007` llama a `migrar`, que es lo único que necesita un deploy. Las dos leen el mismo
    mapa `VENTALIBRA_DEPOSITOS_A_SUCURSAL`, para que un respaldo viejo converja igual que un deploy."""
    from libracommerce.erp import catalogo

    informe = migrar(conn, depositos_a_sucursal=parsear_mapa(os.environ.get("VENTALIBRA_DEPOSITOS_A_SUCURSAL", "")))
    if conn.execute("SELECT 1 FROM branches WHERE active = 1").fetchone() is None:
        sid = catalogo.create_sucursal(conn, "Sucursal 1")
        catalogo.set_default_sucursal(conn, sid)
        informe["sucursales_creadas"] += 1
    for sid, nombre in conn.execute("SELECT id, name FROM branches WHERE active = 1 ORDER BY id").fetchall():
        if conn.execute("SELECT 1 FROM locations WHERE branch_id = ? AND active = 1", (sid,)).fetchone() is None:
            catalogo.create_deposito(conn, f"Depósito {nombre}", branch_id=sid)
    if conn.execute("SELECT 1 FROM locations WHERE is_default = 1").fetchone() is None:
        de_venta = conn.execute(
            "SELECT b.default_location_id FROM branches b WHERE b.is_default = 1 AND b.default_location_id IS NOT NULL"
        ).fetchone()
        if de_venta:
            catalogo.set_default_deposito(conn, de_venta[0])
    conn.commit()
    return informe
