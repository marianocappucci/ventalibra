"""Conexion SQLite unica de VentaLibra.

Fase 1: una sola base para el esquema de LibraCommerce (catalogo, inventario,
compras, ventas) y la tabla `users` propia de VentaLibra -- ver
DECISIONS.md ADR-002/ADR-003. No hay pool ni ORM, mismo estilo que
libracommerce/libracore.db.
"""
import sqlite3

from libracommerce.db.schema import init_schema
from libracore.db import core


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
    init_users_schema(conn)
    init_sequences_schema(conn)
    init_party_billing_schema(conn)
    init_party_roles_schema(conn)
    init_modules_schema(conn)
    return conn


def init_users_schema(conn: sqlite3.Connection) -> None:
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


def init_sequences_schema(conn: sqlite3.Connection) -> None:
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


def init_party_billing_schema(conn: sqlite3.Connection) -> None:
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


def init_party_roles_schema(conn: sqlite3.Connection) -> None:
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


def init_modules_schema(conn: sqlite3.Connection) -> None:
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


def next_sequence(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT next_value FROM sequences WHERE name = ?", (name,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO sequences (name, next_value) VALUES (?, 2)", (name,))
        return 1
    sequence = row[0]
    conn.execute("UPDATE sequences SET next_value = ? WHERE name = ?", (sequence + 1, name))
    return sequence
