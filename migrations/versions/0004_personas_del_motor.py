"""VentaLibra adopta el modelo de personas del motor de Contalibra (fase 1 de la adopción de
los motores, ver wiki/analyses/inventario-adopcion-motores-ventalibra-2026-09-26.md).

Sólo PostgreSQL (mismo criterio que la `0003`).

## Qué es «el modelo del motor»

`libracore` guarda clientes en `clients` y proveedores en `proveedores`; `libracommerce`
(ventas y compras de dominio) apunta a `parties`. Contalibra/Restolibra los hacen convivir con
una convención de ids (`libracommerce/scripts/migrate_from_contalibra.py`, y
`libracore.db.clients._espejar_party`):

- un **cliente es el party de IGUAL id** (`parties.id == clients.id`);
- un **proveedor es el party con id `proveedores.id + 100_000`**.

VentaLibra, en cambio, nació con `parties` como origen y **espejaba** cada cliente en `clients`
por `external_ref = 'party-<id>'`, con ids distintos (medido en dev: los clients 1/2/3 eran los
parties 2/3/4). Ese desalineo es lo que obligaba a los puentes `cliente_cc_de` y
`nombre_de_cliente` de `app/ganchos.py`, y a que `Clientes`/`Proveedores` no pudieran usar los
routers del motor.

## Qué hace `upgrade()`

1. **Clientes.** Para cada party con rol `customer`: usa su `clients` (por `external_ref`) o
   la crea; completa `cuit_dni` / `iva_condition` desde `party_billing` sólo donde están
   vacíos, y baja el cliente si el party está inactivo. El id final del party pasa a ser el
   `clients.id`.
2. **Proveedores.** Para cada party con rol `supplier`: crea su fila en `proveedores`; el id final
   del party es `100_000 + proveedores.id`.
3. **Renumera** los parties y **todo lo que apunta a ellos** (`sales.customer_party_id`,
   `purchase_orders.supplier_party_id`, `purchase_receipts.supplier_party_id`,
   `party_billing.party_id`, `party_roles.party_id`): se sueltan las cinco FK, se mueve todo por
   un espacio de ids temporal (para no chocar consigo mismo: el party 2 pasa a 1 mientras el 1
   pasa a 100001) y se vuelven a crear.
4. Deja la secuencia `parties_id_seq` en el mayor id de cliente.

Un party con **los dos roles** no tiene un id posible (sería cliente y proveedor a la vez): la
migración se detiene con un mensaje, sin tocar nada.

## Qué NO hace

No borra `parties`, `party_roles`, `party_billing` ni `clients.external_ref`: quedan como espejo
y procedencia. Retirarlos es una limpieza posterior, cuando nada los lea.

## Invariantes

Cantidad y totales de ventas; cantidad de órdenes y recepciones de compra por proveedor; saldo
de cuenta corriente de cada cliente (no se toca `cc_*`); `SUM(quantity_delta)` (no se toca).
Ver `tests/test_migracion_0004.py`.

## Locks

`upgrade()`/`downgrade()` toman locks exclusivos (sueltan y recrean FK), así que **corren con la app
parada**. Si no lo están, esperan `LOCK_TIMEOUT` (15 s) y se rinden con un mensaje, sin cambiar nada.

## Reversión

Todo se registra en `_migracion_0004`. `downgrade()` devuelve los ids originales a parties y a
sus hijos, restaura los campos de `clients` que completó, y borra los `clients`/`proveedores` que
creó **sólo si nadie los usa** (movimientos de cuenta corriente, ventas, egresos): un dato real
cargado después del `upgrade()` no se descarta.
"""
import json

from alembic import op
from libracore.db.migraciones import conexion_libracore

revision = "0004_personas_del_motor"
down_revision = "0003_capa_erp"
branch_labels = None
depends_on = None

#: Un proveedor es el party con `proveedores.id + OFFSET_PROVEEDOR` (convención del motor).
OFFSET_PROVEEDOR = 100_000
#: Un party huérfano cuyo id chocaría con uno final se corre a este offset.
OFFSET_HUERFANO = 200_000
#: Espacio temporal para mover ids sin chocar consigo mismo.
TEMPORAL = 10_000_000
#: Cuánto espera esta migración un lock antes de rendirse. Suelta y recrea FK (ACCESS
#: EXCLUSIVE): con la app vieja conectada (`idle in transaction`) esperaría para siempre y, mientras
#: espera, su pedido encola a todas las demás consultas sobre esas tablas. Pasó en la demo el
#: 2026-09-26: casi 9 minutos. Mejor fallar rápido y avisar qué hacer.
LOCK_TIMEOUT = "15s"

#: (tabla, columna, nombre de la FK) de todo lo que apunta a `parties(id)`.
_FKS = (
    ("sales", "customer_party_id", "sales_customer_party_id_fkey"),
    ("purchase_orders", "supplier_party_id", "purchase_orders_supplier_party_id_fkey"),
    ("purchase_receipts", "supplier_party_id", "purchase_receipts_supplier_party_id_fkey"),
    ("party_billing", "party_id", "party_billing_party_id_fkey"),
    ("party_roles", "party_id", "party_roles_party_id_fkey"),
)


def _crear_bookkeeping(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migracion_0004 (
            id SERIAL PRIMARY KEY,
            accion TEXT NOT NULL,
            referencia_id INTEGER NOT NULL,
            datos TEXT NOT NULL DEFAULT '{}',
            creado_en TIMESTAMP NOT NULL DEFAULT now()
        )
    """)


def _registrar(conn, accion: str, referencia_id: int, datos: dict) -> None:
    conn.execute(
        "INSERT INTO _migracion_0004 (accion, referencia_id, datos) VALUES (?, ?, ?)",
        (accion, referencia_id, json.dumps(datos)),
    )


def _renumerar(conn, mapa: dict[int, int]) -> None:
    """Cambia el id de cada party de `mapa` (viejo -> nuevo) y el de todo lo que lo referencia.

    Suelta las FK, mueve por el espacio temporal (así 2 -> 1 no choca con el 1 que se va a
    100001) y las vuelve a crear. Todo dentro de la misma transacción.
    """
    cambios = {v: n for v, n in mapa.items() if v != n}
    if not cambios:
        return
    # `SET LOCAL` vale sólo para esta transacción: si vence, se revierte todo.
    conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
    try:
        _renumerar_con_lock(conn, cambios)
    except Exception as exc:
        if "lock timeout" in str(exc).lower() or "locknotavailable" in type(exc).__name__.lower():
            raise RuntimeError(
                f"No se consiguió el lock para renumerar las personas en {LOCK_TIMEOUT}: hay conexiones "
                "abiertas contra `sales`/`parties`/`purchase_*` (la app vieja). Esta migración toma locks "
                "exclusivos y tiene que correr con la app PARADA: pará el contenedor y repetí. No se "
                "cambió nada (la transacción se revirtió)."
            ) from exc
        raise


def _renumerar_con_lock(conn, cambios: dict[int, int]) -> None:
    conn.execute("CREATE TEMP TABLE _mapa_personas (viejo BIGINT PRIMARY KEY, nuevo BIGINT NOT NULL)")
    for viejo, nuevo in cambios.items():
        conn.execute("INSERT INTO _mapa_personas (viejo, nuevo) VALUES (?, ?)", (viejo, nuevo))

    for tabla, _col, fk in _FKS:
        conn.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {fk}")

    tablas = [("parties", "id")] + [(t, c) for t, c, _ in _FKS]
    for tabla, col in tablas:
        conn.execute(
            f"UPDATE {tabla} SET {col} = {col} + {TEMPORAL} "
            f"WHERE {col} IN (SELECT viejo FROM _mapa_personas)"
        )
    for tabla, col in tablas:
        conn.execute(
            f"UPDATE {tabla} SET {col} = m.nuevo FROM _mapa_personas m "
            f"WHERE {tabla}.{col} = m.viejo + {TEMPORAL}"
        )

    for tabla, col, fk in _FKS:
        conn.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT {fk} FOREIGN KEY ({col}) REFERENCES parties(id)"
        )
    conn.execute("DROP TABLE _mapa_personas")


def upgrade() -> None:
    conn = conexion_libracore(op.get_bind())
    _crear_bookkeeping(conn)

    ya = conn.execute(
        "SELECT COUNT(*) FROM _migracion_0004 WHERE accion = 'party_renumerado'"
    ).fetchone()[0]
    if ya:
        return  # ya corrió completa sobre esta base

    partes = conn.execute(
        "SELECT id, display_name, tax_id, email, phone, active FROM parties ORDER BY id"
    ).fetchall()
    roles: dict[int, set[str]] = {}
    for party_id, rol in conn.execute("SELECT party_id, role FROM party_roles").fetchall():
        roles.setdefault(int(party_id), set()).add(rol)

    ambos = sorted(p for p, r in roles.items() if {"customer", "supplier"} <= r)
    if ambos:
        raise RuntimeError(
            f"Los parties {ambos} son cliente y proveedor a la vez: no tienen un id posible en el "
            "modelo del motor (cliente = mismo id, proveedor = id + 100.000). Separalos a mano "
            "antes de migrar."
        )

    mapa: dict[int, int] = {}
    for party_id, nombre, tax_id, email, phone, active in partes:
        party_id = int(party_id)
        r = roles.get(party_id, set())
        if "customer" in r:
            fila = conn.execute(
                "SELECT id, cuit_dni, iva_condition, activo FROM clients WHERE external_ref = ?",
                (f"party-{party_id}",),
            ).fetchone()
            billing = conn.execute(
                "SELECT cuit, condicion_iva FROM party_billing WHERE party_id = ?", (party_id,),
            ).fetchone()
            cuit_b = (billing[0] or "") if billing else ""
            iva_b = (billing[1] or "") if billing else ""
            if fila is None:
                cur = conn.execute(
                    "INSERT INTO clients (name, address, cuit_dni, email, phone, iva_condition, "
                    "external_ref, activo) VALUES (?, '', ?, ?, ?, ?, ?, ?)",
                    (nombre, cuit_b or tax_id or "", email or "", phone or "", iva_b,
                     f"party-{party_id}", 1 if active else 0),
                )
                cliente_id = int(cur.lastrowid)
                _registrar(conn, "cliente_creado", cliente_id, {"party_id": party_id})
            else:
                cliente_id, cuit_a, iva_a, activo_a = int(fila[0]), fila[1] or "", fila[2] or "", fila[3]
                antes = {"cuit_dni": cuit_a, "iva_condition": iva_a, "activo": activo_a}
                nuevo_cuit = cuit_a or cuit_b
                nuevo_iva = iva_a or iva_b
                nuevo_activo = 0 if not active else activo_a
                if (nuevo_cuit, nuevo_iva, nuevo_activo) != (cuit_a, iva_a, activo_a):
                    conn.execute(
                        "UPDATE clients SET cuit_dni = ?, iva_condition = ?, activo = ? WHERE id = ?",
                        (nuevo_cuit, nuevo_iva, nuevo_activo, cliente_id),
                    )
                    _registrar(conn, "cliente_completado", cliente_id, antes)
            mapa[party_id] = cliente_id
        elif "supplier" in r:
            cur = conn.execute(
                "INSERT INTO proveedores (nombre, cuit_dni, email, phone, address, iva_condition) "
                "VALUES (?, ?, ?, ?, '', '')",
                (nombre, tax_id or "", email or "", phone or ""),
            )
            proveedor_id = int(cur.lastrowid)
            _registrar(conn, "proveedor_creado", proveedor_id, {"party_id": party_id})
            mapa[party_id] = OFFSET_PROVEEDOR + proveedor_id

    # Un party sin rol conserva su id, salvo que choque con uno final.
    finales = set(mapa.values())
    for party_id, *_ in partes:
        party_id = int(party_id)
        if party_id in mapa:
            continue
        mapa[party_id] = OFFSET_HUERFANO + party_id if party_id in finales else party_id

    _renumerar(conn, mapa)
    for viejo, nuevo in mapa.items():
        if viejo != nuevo:
            _registrar(conn, "party_renumerado", viejo, {"nuevo": nuevo})
    # `party_renumerado` puede no existir si nada cambió de id: dejar constancia igual.
    if all(v == n for v, n in mapa.items()):
        _registrar(conn, "party_renumerado", 0, {"nuevo": 0, "sin_cambios": True})

    conn.execute(
        "SELECT setval(pg_get_serial_sequence('parties', 'id'), "
        "GREATEST((SELECT COALESCE(MAX(id), 1) FROM parties WHERE id < ?), 1))",
        (OFFSET_PROVEEDOR,),
    )
    conn.commit()


def downgrade() -> None:
    conn = conexion_libracore(op.get_bind())
    existe = conn.execute("SELECT to_regclass('_migracion_0004') IS NOT NULL").fetchone()[0]
    if not existe:
        return  # upgrade() nunca corrió sobre esta base: nada que deshacer.

    registros = conn.execute(
        "SELECT id, accion, referencia_id, datos FROM _migracion_0004 ORDER BY id DESC"
    ).fetchall()

    # Primero los ids de los parties (todo el lote junto): nuevo -> viejo.
    inverso = {}
    for _id, accion, referencia_id, datos_raw in registros:
        if accion == "party_renumerado":
            datos = json.loads(datos_raw)
            if not datos.get("sin_cambios"):
                inverso[int(datos["nuevo"])] = int(referencia_id)
    _renumerar(conn, inverso)

    for _id, accion, referencia_id, datos_raw in registros:
        datos = json.loads(datos_raw)
        if accion == "cliente_completado":
            conn.execute(
                "UPDATE clients SET cuit_dni = ?, iva_condition = ?, activo = ? WHERE id = ?",
                (datos["cuit_dni"], datos["iva_condition"], datos["activo"], referencia_id),
            )
        elif accion == "cliente_creado":
            usado = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM cc_debitos WHERE cliente_id = ?) "
                "OR EXISTS(SELECT 1 FROM cc_pagos WHERE cliente_id = ?) "
                "OR EXISTS(SELECT 1 FROM ventas WHERE cliente_id = ?)",
                (referencia_id, referencia_id, referencia_id),
            ).fetchone()[0]
            if usado:
                print(f"[0004 downgrade] el cliente {referencia_id} tiene movimientos propios: no se borra.")
            else:
                conn.execute("DELETE FROM clients WHERE id = ?", (referencia_id,))
        elif accion == "proveedor_creado":
            usado = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM egresos WHERE proveedor_id = ?)", (referencia_id,),
            ).fetchone()[0]
            if usado:
                print(f"[0004 downgrade] el proveedor {referencia_id} tiene egresos: no se borra.")
            else:
                conn.execute("DELETE FROM proveedores WHERE id = ?", (referencia_id,))

    conn.execute("DROP TABLE IF EXISTS _migracion_0004")
    conn.commit()
