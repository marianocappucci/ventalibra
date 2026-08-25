"""Conexion SQLite unica de VentaLibra.

Fase 1: una sola base para el esquema de LibraCommerce (catalogo, inventario,
compras, ventas) y la tabla `users` propia de VentaLibra -- ver
DECISIONS.md ADR-002/ADR-003. No hay pool ni ORM, mismo estilo que
libracommerce/libracore.db.
"""
import sqlite3

from libracommerce.db.schema import init_schema
from libracore.db import core

from .normalizacion_medios import normalizar_dominio
from libracore.db.core import Conexion


def connect(db_path: str):
    """La conexion del dominio, contra una RUTA SQLite o una URL PostgreSQL.

    🔴 Antes esto era un `sqlite3.connect()` pelado, y por eso el producto no
    podia **siquiera intentar** correr contra PostgreSQL: el motor quedaba
    elegido en la linea mas baja de la pila, donde nada lo podia cambiar. Ahora
    delega en `libracore.db.core.conectar()`, que existe desde `v1.18.0`
    justamente para esto y decide por el destino sin tocar la configuracion
    global del proceso.

    Sigue siendo **una sola conexion viva** para todo el proceso, igual que
    antes. Contra PostgreSQL eso anda, pero no es lo que se querria a futuro
    (lo natural seria un pool). Cambiarlo es otro trabajo y no hace falta para
    que el producto se pueda ejercitar contra el motor nuevo, que es lo que
    esta fase necesita.
    """
    if core.es_url_postgres(db_path):
        conn = core.conectar(db_path)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    # Las tablas propias de este producto, por un punto de entrada único. Antes
    # las seis funciones se enumeraban acá, y la baseline de Alembic
    # (`migrations/versions/0001_baseline_ventalibra.py`) llama a esa misma
    # función: enumerarlas en los dos lados haría que una función nueva agregada
    # en uno solo dejara a las instancias nuevas y a las viejas con esquemas
    # distintos, sin fallar.
    #
    # 🔴 Desde esa revisión las seis son de **sólo lectura**: una columna nueva
    # va como revisión de Alembic. Ver `app/schema_propio.py`.
    #
    # Import local: `schema_propio` importa de este módulo, así que arriba
    # cerraría el ciclo.
    from app.schema_propio import init_schema_propio

    init_schema_propio(conn)
    # La grafia vieja de MercadoPago (`mercado_pago`) que este POS escribio
    # desde siempre, pasada a la canonica de la familia. Va DESPUES de crear el
    # schema —necesita las tablas— y en cada arranque, no una sola vez: ver el
    # docstring del modulo para por que.
    normalizar_dominio(conn)
    return conn


def init_users_schema(conn: Conexion) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.commit()


def init_sequences_schema(conn: Conexion) -> None:
    """Numeracion propia de VentaLibra (POS-, OC-, REC-).

    Antes reusaba la tabla `local_sequences` del esquema de LibraCommerce
    (infraestructura interna de su especificacion offline) -- rompio al
    pinnear v0.1.2, que la retiro por completo al migrar esa
    responsabilidad a LibraEdge. No depender mas de tablas internas de una
    dependencia que no forman parte de su contrato publico.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sequences (
            name TEXT PRIMARY KEY,
            next_value INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def init_party_billing_schema(conn: Conexion) -> None:
    """Extension de Party para facturacion (cuit/condicion_iva), mismo
    patron que `client_billing` de Gestiolibra: tabla propia con FK a
    parties.id, nunca columnas agregadas al motor generico de LibraCommerce.
    Vive en esta base (no en la de libracore.db/facturacion) porque la FK
    es contra `parties`, que solo existe aca."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS party_billing (
            party_id INTEGER PRIMARY KEY REFERENCES parties(id),
            cuit TEXT,
            condicion_iva TEXT
        );
        """
    )
    conn.commit()


def init_party_roles_schema(conn: Conexion) -> None:
    """Rol con el que se dio de alta una Party (supplier/customer), mismo
    patron que `party_billing`: tabla propia con FK a parties.id, sin
    tocar el esquema generico de LibraCommerce (Party.party_type es
    persona/organizacion, un eje totalmente distinto -- un proveedor
    puede ser persona, un cliente puede ser organizacion).

    Bug real encontrado al construir las pantallas de Proveedores/Clientes
    del frontend: SupplierService.list_all()/CustomerService.list_all()
    listaban *todas* las parties activas sin filtrar, así que un cliente
    aparecía mezclado en la lista de proveedores y viceversa. PK compuesta
    (party_id, role) para no cerrar la puerta a que una misma party tenga
    los dos roles a la vez si hiciera falta más adelante."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS party_roles (
            party_id INTEGER NOT NULL REFERENCES parties(id),
            role TEXT NOT NULL,
            PRIMARY KEY (party_id, role)
        );
        """
    )
    conn.commit()


def init_modules_schema(conn: Conexion) -> None:
    """Tabla de modulos gateables por plan -- variante sqlite3 crudo del
    mismo patron que Contalibra (Gestiolibra/MedLibra usan SQLAlchemy+
    Alembic, pero VentaLibra ya es 100% sqlite3 crudo desde Fase 1).
    Sembrada con todo habilitado -- no bloquea nada hasta que
    plans.aplicar_plan_en_db() achica el acceso (provisioning de un
    cliente real), mismo criterio documentado en gestiolibra/medlibra."""
    from plans import TODOS_LOS_MODULOS

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modulos (
            modulo TEXT PRIMARY KEY,
            habilitado INTEGER NOT NULL DEFAULT 1,
            plan TEXT NOT NULL DEFAULT 'premium'
        );
        """
    )
    for modulo in sorted(TODOS_LOS_MODULOS):
        conn.execute(
            "INSERT OR IGNORE INTO modulos (modulo, habilitado, plan) VALUES (?, 1, 'premium')",
            (modulo,),
        )
    conn.commit()


def init_mp_qr_schema(conn: Conexion) -> None:
    """Las ordenes puestas a cobrar en el QR de MercadoPago de la caja.

    Mismo patron que `party_billing` y `party_roles`: tabla propia de este
    producto con FK contra el esquema de LibraCommerce, sin agregarle columnas
    al motor generico. Contalibra guarda esto en columnas de su tabla `ventas`
    (`mp_order_id`, `mp_payment_id`), pero esa tabla es de LibraCore y aca la
    venta es `sales`, de LibraCommerce -- que es de otro repo y la comparten
    cinco productos.

    🔑 **Una fila por INTENTO, no una por venta.** El `external_reference`
    lleva un sufijo aleatorio y se renueva cada vez que el cajero vuelve a
    poner el monto en el QR: si se reusara, un pago rechazado que MercadoPago
    acredita tarde volveria como aprobado para el intento siguiente, que puede
    ser por otra plata. Es la misma razon por la que LibraClub lo hace asi en
    `servicios/pagos.py::nueva_referencia`.

    `payment_id` y `status` los sella el poll de `GET /sales/{id}/mp-status`.
    Mientras `status` sea `pending` no hay plata: la fila sola no acredita
    nada.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sale_mp_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id),
            external_reference TEXT NOT NULL UNIQUE,
            amount NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sale_mp_orders_sale
            ON sale_mp_orders(sale_id);
        """
    )
    conn.commit()


def next_sequence(conn: Conexion, name: str) -> int:
    row = conn.execute("SELECT next_value FROM sequences WHERE name = ?", (name,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO sequences (name, next_value) VALUES (?, 2)", (name,))
        return 1
    sequence = row[0]
    conn.execute("UPDATE sequences SET next_value = ? WHERE name = ?", (sequence + 1, name))
    return sequence
