"""Conexion SQLite unica de VentaLibra.

Fase 1: una sola base para el esquema de LibraCommerce (catalogo, inventario,
compras, ventas) y la tabla `users` propia de VentaLibra -- ver
DECISIONS.md ADR-002/ADR-003. No hay pool ni ORM, mismo estilo que
libracommerce/libracore.db.
"""
import logging
import sqlite3

from libracommerce.db.schema import init_schema
from libracore.db import core
from libracore.db.core import Conexion

from .normalizacion_medios import normalizar_dominio

logger = logging.getLogger(__name__)


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
    # Sucursales y depósitos (jerarquía, 2026-09-28): migra el modelo plano si lo trae la base (también al
    # restaurar un respaldo viejo) y garantiza una sucursal, un depósito por sucursal y el depósito
    # predeterminado de la instancia. Sin depósito predeterminado, `libracommerce.erp.stock.
    # descontar_stock_venta` —que no recibe depósito en el payload— revienta con `NOT NULL location_id` en
    # la primera venta de una base nueva. Import local: `sucursales_migracion` importa del motor y este
    # módulo se carga antes.
    from .sucursales_migracion import asegurar_minimas

    asegurar_minimas(conn)
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
    cliente real), mismo criterio documentado en gestiolibra/medlibra.

    🔴 **Un modulo NUEVO en una instancia que ya tiene plan se siembra segun ese
    plan, no prendido.** Corre en cada arranque y `INSERT OR IGNORE` solo agrega
    lo que falta: con "todo prendido" un modulo que se suma a `plans.py`
    (`multisucursal`, ADR-048) quedaria abierto en TODAS las instancias
    Basico ya desplegadas hasta que alguien reaplique el plan a mano -- el gate
    existiria y no cortaria. El plan se lee de la propia tabla (la columna
    `plan` que escribe `aplicar_plan_en_db`); solo se actua cuando las filas de
    plan dicen UNO (los add-ons, con `plan='addon'`, no cuentan). Una base recien
    creada, o con planes mezclados o desconocidos, sigue con el sembrado de
    siempre.

    🔴 **Un plan retirado se MIGRA, no solo se avisa** (ADR-072, plan unico). Si las
    filas de plan dicen UN plan y es retirado (`plans.PLANES_RETIRADOS`: `basico`,
    `premium`, `estandar`), este arranque **prende** (`habilitado=1`) los modulos
    del plan vigente y reescribe la etiqueta `plan` de las filas al vigente
    (`unico`), con un `WARNING` que dice que se migro. Una instancia guardada como
    `basico` tiene `facturacion` y `multisucursal` APAGADOS: si el arranque solo
    avisara, quedaria asi para siempre aunque el producto ya no tenga ese plan.
    Solo PRENDE, nunca apaga, y no toca los add-ons (`plan='addon'`): son un
    servicio aparte y se prenden desde el backoffice. Es idempotente: tras la
    migracion la etiqueta ya es la vigente y los arranques siguientes no hacen
    nada."""
    import plans

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modulos (
            modulo TEXT PRIMARY KEY,
            habilitado INTEGER NOT NULL DEFAULT 1,
            plan TEXT NOT NULL DEFAULT 'unico'
        );
        """
    )
    estado = {fila[0]: bool(fila[1]) for fila in conn.execute("SELECT modulo, habilitado FROM modulos").fetchall()}
    existentes = set(estado)
    planes = {
        fila[0] for fila in conn.execute("SELECT DISTINCT plan FROM modulos WHERE plan <> 'addon'").fetchall()
    }
    plan = next(iter(planes)) if len(planes) == 1 else None
    if plan is not None and plan not in plans.PLAN_MODULOS and plan not in plans.PLANES_RETIRADOS:
        plan = None  # un plan que este codigo no conoce: no se adivina
    # Para un plan retirado `plan_vigente` es lo que deja el WARNING (una sola vez por arranque).
    vigente = plans.plan_vigente(plan) if plan is not None else None
    activos = plans.modulos_de_plan(vigente) if vigente is not None else None
    if plan is not None and plan != vigente:
        a_prender = sorted(m for m in activos if estado.get(m) is False)
        conn.execute("UPDATE modulos SET plan = ? WHERE plan = ?", (vigente, plan))
        for modulo in a_prender:
            conn.execute("UPDATE modulos SET habilitado = ? WHERE modulo = ?", (1, modulo))
        logger.warning(
            "Instancia con el plan retirado %r migrada al plan %r (ADR-072): etiqueta reescrita%s.",
            plan, vigente, f" y modulos prendidos: {', '.join(a_prender)}" if a_prender else "",
        )
    for modulo in sorted(plans.TODOS_LOS_MODULOS - existentes):
        habilitado = 1 if activos is None else int(modulo in activos)
        conn.execute(
            "INSERT OR IGNORE INTO modulos (modulo, habilitado, plan) VALUES (?, ?, ?)",
            (modulo, habilitado, vigente or "unico"),
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
    # 🔴 El DEFAULT de `created_at` cambio el 2026-09-11: era CURRENT_TIMESTAMP
    # y pasa a la hora de Argentina de la familia (`libracore.db.schema.AHORA_AR`).
    # Esta funcion es de solo lectura desde la baseline: el cambio aca vale para
    # las bases NUEVAS, y a las existentes las lleva la revision
    # `0002_created_at_hora_ar`. Ver esa revision.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sale_mp_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id),
            external_reference TEXT NOT NULL UNIQUE,
            amount NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','-3 hours')),
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
