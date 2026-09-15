"""Facturacion/caja para VentaLibra, compuesto sobre libracore.db.

libracore.db es sqlite3 crudo, sin capa de abstraccion -- una conexion
propia, separada de la base principal de LibraCommerce/users/sequences
(ver DECISIONS.md ADR-007). VentaLibra es de instancia unica por cliente
(arquitectura silo), asi que hay una sola "empresa" ARCA -- una constante
fija, no una tabla de empresas. Mismo patron que
medlibra/app/services/billing.py y gestiolibra/app/services/billing.py.

A diferencia de esos dos productos (donde caja solo se toca si hay
factura, seña+saldo de un turno), en retail toda venta cobrada debe
quedar en caja sin importar si se factura o no -- decision explicita del
usuario, 2026-07-25.
"""
from libracore.db import caja as db_caja
from libracore.db import core as libracore_core
from libracore.db.schema import init_core_schema

from ..normalizacion_medios import normalizar_libracore

EMPRESA = "venta"


def configure(db_path: str) -> None:
    """Llamar una vez al arrancar la app: configura libracore.db contra su
    propio archivo SQLite (independiente de la base principal) y asegura
    que el schema compartido y una caja por defecto existan."""
    # 🔴 **Este producto corre sobre PostgreSQL y nada mas.** La guarda va aca,
    # en el arranque del producto, y no dentro de `libracore.db.core`: el motor
    # tiene que poder abrir un SQLite igual, porque de eso vive la herramienta
    # de diagnostico `python -m libracore.db.schema_dump`, que vuelca el schema
    # de un archivo viejo o de la base de LibraEdge. La regla "este producto no
    # habla con otro motor" es del producto, no del motor.
    #
    # Aca habia un `if not es_url_postgres(...)` que salteaba el `makedirs`
    # cuando el destino era una URL. Existia para evitar un defecto medido: con
    # una URL, `os.path.dirname()` devuelve `postgresql://usuario:clave@host` y
    # `makedirs` lo creaba como carpeta --- **la contrasena escrita en el nombre
    # de un directorio**, que ademas caia dentro del checkout bind-mounteado y
    # se colaba en la imagen del siguiente build. Encontrado el 2026-08-10.
    #
    # Con la guarda ese camino no existe: si no hay ruta de archivo posible, no
    # hay carpeta que crear ni defecto que evitar. El bloque entero se va.
    if not libracore_core.es_url_postgres(str(db_path)):
        raise RuntimeError(
            f"VentaLibra corre solo sobre PostgreSQL y recibio {db_path!r}, que es una "
            "ruta de archivo. El modo SQLite se retiro el 2026-08-12: no chequea "
            "las FK, tipa dinamicamente y acepta cadenas donde la base pide "
            "enteros."
        )
    libracore_core.configure(db_path)
    conn = libracore_core.get_connection()
    try:
        init_core_schema(conn)
        conn.commit()
        # F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025): la
        # capa ERP de LibraCommerce. La migracion `0003` los aplica sobre
        # una instancia YA EXISTENTE, pero una base nueva (la de la suite,
        # `admin_client`; o un cliente que se onboardea de cero) nunca corre
        # esa revision -- nace ya con el schema de `init_*_schema()`. Sin
        # esto acá, cualquier venta con un pago fallaria con
        # `ForeignKeyViolation` contra `ventas_pagos_venta_id_fkey`, que
        # sigue apuntando a la tabla `ventas` legada de LibraCore. Mismo
        # patron que `app/database.py::init_db()` de Contalibra/Restolibra:
        # las dos funciones son idempotentes, así que correrlas en cada
        # arranque es un no-op sobre una base que ya las tiene.
        from libracommerce.erp.schema import crear_venta_links
        from libracommerce.erp.ventas import repuntar_fk_ventas_pagos

        crear_venta_links(conn)
        repuntar_fk_ventas_pagos(conn)
        # La otra mitad de la normalizacion de grafias: caja, cuenta corriente,
        # egresos y recibos viven en ESTA base, que contra SQLite es un archivo
        # distinto del dominio. Ver `app/normalizacion_medios.py`.
        normalizar_libracore(conn)
    finally:
        conn.close()
    if db_caja.get_default_caja_id() is None:
        caja_id = db_caja.create_caja_config(
            "Caja VentaLibra", "", list(db_caja.MEDIOS_PAGO_LABELS),
        )
        db_caja.set_default_caja(caja_id)


#: 🔴 Este módulo tenía `get_arca_config`/`set_arca_config`, `invoice_sale` y
#: `record_sale_payment` -- del camino LEGADO (`POST /sales/{id}/confirm`,
#: IVA fijo al 21%, retirado a 410 en F3, ver `app/routers/sales.py`). Sin
#: caller: `GET`/`PUT /config/arca` los sirve `libracore.arca_router.
#: build_arca_router` (montado en `app/main.py` con `empresa_por_defecto=
#: billing.EMPRESA`, la única pieza de este módulo que sigue usando), que
#: lee/escribe `libracore.db.arca_config` directo -- nunca llamó a estas dos
#: funciones (sus tests, `test_get_arca_config_defaults_to_none`/`test_set_
#: and_get_arca_config` en `tests/test_billing.py`, pegan sobre ese router
#: por HTTP y siguen vivos igual). Facturar y anotar la caja de una venta
#: nueva son `app/venta_facturacion.py` (D2/D6, `libracore.venta_
#: facturacion`) y `libracommerce.erp.ventas.registrar_venta`,
#: respectivamente. Borrado en F3 (2026-09-14, ADR-025).
