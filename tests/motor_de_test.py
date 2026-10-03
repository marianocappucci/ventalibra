"""Contra que motor corre la suite.

Por defecto SQLite en archivos temporales, que es como corrio siempre. Con
`VENTALIBRA_TEST_DATABASE_URL` puesta, la suite entera va a ese motor.

Mismo nombre y misma forma que el de [[medlibra]] y [[gestiolibra]], a
proposito: tres productos de la misma familia no tienen por que elegir el motor
de test de tres maneras distintas.

🔴 **Pero acá el problema no eran solo los tests.** En esos dos, la URL estaba
escrita a mano en los archivos de test y alcanzaba con sacarla. En VentaLibra el
motor quedaba elegido **en el producto**: `app/db.py` abria `sqlite3.connect()`
pelado y `app/main.py` armaba la URL del engine de auth interpolando
`sqlite:///`. O sea que no habia variable que poner: el producto no podia
hablar con otro motor aunque se lo pidieran. Eso se arreglo primero.

**A diferencia de los otros dos, este producto tiene DOS bases**: la del dominio
(LibraCommerce) y la de LibraCore/libraauth. Las dos tienen que ir al mismo
motor o la corrida no prueba lo que dice probar.
"""
import os

#: Se lee UNA vez, al importar: si un test la cambiara a mitad de corrida, la
#: mitad de la suite iria a un motor y la mitad al otro.
TEST_DATABASE_URL = os.environ.get("VENTALIBRA_TEST_DATABASE_URL", "").strip()

# 🔴 **PostgreSQL y nada mas.** Hasta el 2026-08-25 la suite caia a SQLite en
# archivos temporales cuando la variable no estaba, y el CI corria las dos
# pasadas. El modo SQLite se retiro el 2026-08-12 para toda la familia: no
# chequea las FK, tipa dinamicamente y acepta cadenas donde la base pide
# enteros, asi que una corrida verde sobre el no dice nada del motor real.
#
# El guard va ACA y no en el conftest porque este es el unico lugar donde se
# elegia el motor. Con el puesto, `corre_contra_postgres()` seria siempre True,
# asi que se saco junto con los tres `if` que colgaban de ella.
if not TEST_DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "La suite de VentaLibra necesita PostgreSQL: defini "
        "VENTALIBRA_TEST_DATABASE_URL (ej. "
        "postgresql://ventalibra:ventalibra-ci@localhost:5432/ventalibra). "
        "Sin esa variable la suite correria sobre SQLite, que es lo que se "
        "retiro el 2026-08-12: una suite verde sobre SQLite no dice nada "
        "sobre el motor real."
    )


# --- Una base por worker, restaurada desde una plantilla -----------------------
# Cada test arranca de una base **nueva**, y rearmarla desde cero es lo que mas
# cuesta: medido sobre PostgreSQL 16, ~1,6 s por test entre vaciar el schema,
# crear el de auth, `create_app()` (0,8 s) y las dos cadenas de Alembic (0,6 s).
# Con `CREATE DATABASE ... TEMPLATE` la base sale de una copia ya armada, ~0,1 s.
#
# Dos plantillas por worker, armadas la primera vez que se piden:
#
# - **vacia**: solo el schema de auth. Es EXACTAMENTE lo que dejaba antes
#   `limpiar_entre_tests()` (vaciar `public` + `crear_schema_de_auth`), asi que
#   los tests que arman su propia app o prueban migraciones desde cero ven lo
#   mismo que siempre.
# - **armada**: lo que el fixture `admin_client` le hacia a esa base vacia
#   (`create_app` + las cadenas de LibraCore y LibraCommerce). Solo se usa para
#   los tests que piden `admin_client`; su `create_app` posterior es idempotente
#   sobre ella, que es lo que el producto hace en cada arranque.
#
# Y una base **por worker** (`<base>_gw0`, ... y `<base>_main` sin xdist): el
# test anterior deja conexiones vivas y la restauracion borra la base con
# `FORCE`, asi que dos procesos sobre la misma se pisarian en pleno test.
#
# `from motor_de_test import TEST_DATABASE_URL` es como la leen todos los tests,
# asi que reasignarla aca alcanza: ninguno compone la URL por su cuenta.
#
# 🔴 Algunos tests importan `tests.motor_de_test` y otros `motor_de_test`: son DOS
# modulos, y este codigo corre dos veces por proceso. Por eso lo que decide si
# algo ya esta hecho no es una variable de Python sino PostgreSQL (la plantilla
# existe o no) y una variable de entorno (la URL del worker).
#
# Se administra conectado a la base ORIGINAL (un `CREATE DATABASE` va desde
# cualquier base). Pide un rol con CREATEDB; el del servicio de CI es el
# superusuario del contenedor.
import atexit

_BASE_ORIGINAL = TEST_DATABASE_URL
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
# La clave lleva el id del worker: el proceso que lanza a los workers tambien
# importa este modulo (como `main`) y los workers heredan su entorno, asi que una
# clave unica les haria compartir la base del controlador.
_CLAVE_ENV = f"_VENTALIBRA_BASE_DEL_WORKER_{_WORKER}"


def _con_base(url: str, nombre: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).set(database=nombre).render_as_string(hide_password=False)


def _nombre_base() -> str:
    from sqlalchemy.engine import make_url

    return make_url(_BASE_ORIGINAL).database


def _sql_admin(*sentencias: str) -> None:
    import psycopg

    admin = _BASE_ORIGINAL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(admin, autocommit=True) as conexion:
        for sentencia in sentencias:
            conexion.execute(sentencia)


def _existe_base(nombre: str) -> bool:
    import psycopg

    admin = _BASE_ORIGINAL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(admin, autocommit=True) as conexion:
        return conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone() is not None


_BASE_WORKER = f"{_nombre_base()}_{_WORKER}"
_PLANTILLA_VACIA = f"{_BASE_WORKER}_vacia"
_PLANTILLA_ARMADA = f"{_BASE_WORKER}_armada"


def _soltar_todo() -> None:
    # `FORCE` porque la app del ultimo test deja su conexion viva (ver mas abajo).
    _sql_admin(*(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)' for n in (_BASE_WORKER, _PLANTILLA_VACIA, _PLANTILLA_ARMADA)))


if _ya := os.environ.get(_CLAVE_ENV):
    TEST_DATABASE_URL = _ya
else:
    _soltar_todo()  # restos de una corrida interrumpida
    _sql_admin(f'CREATE DATABASE "{_BASE_WORKER}"')
    atexit.register(_soltar_todo)
    TEST_DATABASE_URL = _con_base(_BASE_ORIGINAL, _BASE_WORKER)
    os.environ[_CLAVE_ENV] = TEST_DATABASE_URL


def _asegurar_plantilla(nombre: str, construir) -> None:
    """Arma la plantilla `nombre` si no existe: crea la base, la llena con `construir(url)` y la suelta.

    `CREATE DATABASE ... TEMPLATE` falla si queda **alguien** conectado a la
    plantilla, y `construir` (que levanta una app) deja su conexion viva: por
    eso se las termina al final. Si algo falla a medias se borra, para que la
    proxima vez no se tome una plantilla incompleta por buena.
    """
    if _existe_base(nombre):
        return
    _sql_admin(f'CREATE DATABASE "{nombre}"')
    try:
        construir(_con_base(_BASE_ORIGINAL, nombre))
        _sql_admin(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{nombre}' AND pid <> pg_backend_pid()"
        )
    except BaseException:
        _sql_admin(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
        raise


def _construir_vacia(url: str) -> None:
    # Desde libraauth v0.45 el arranque exige la cadena de auth en vez de crear
    # sus tablas: es el orden del deploy (libraauth antes que las tablas de
    # LibraCore, que tienen FK a `usuarios`).
    from libraauth.testing import crear_schema_de_auth

    crear_schema_de_auth(url)


def limpiar_entre_tests(construir_armada=None) -> None:
    """Deja la base del worker como nueva UNA VEZ POR TEST. La llama la fixture autouse.

    Sin argumentos: la base **vacia** (solo el schema de auth). Con
    `construir_armada` (una funcion `url -> None` que deja la base como la deja
    `admin_client`): la base **armada**, que se construye la primera vez.

    🔴 No puede ir dentro de `destino_dominio()`, que fue el primer intento:
    varios tests arman **dos apps** y ahi la segunda le vaciaba la base por
    debajo a la primera -- 229 errores de *schema "public" does not exist*.

    🔴 **`DROP DATABASE ... WITH (FORCE)` y no un `DROP SCHEMA`.** Este producto
    abre **una conexion viva por app** (`db.connect()`, sin pool) y no la cierra
    nunca: es su diseno, heredado de SQLite. Contra PostgreSQL esa conexion queda
    *idle in transaction* sosteniendo locks, y un `DROP SCHEMA` **se cuelga
    esperandola** -- medido: 20 minutos sin avanzar, con la corrida entera
    detras. `FORCE` echa a esas conexiones y borra, que es correcto para un
    arnes de test: son conexiones de apps que ese test ya no usa.
    """
    if construir_armada is None:
        plantilla = _PLANTILLA_VACIA
        _asegurar_plantilla(plantilla, _construir_vacia)
    else:
        plantilla = _PLANTILLA_ARMADA
        _asegurar_plantilla(plantilla, construir_armada)
    _sql_admin(
        f'DROP DATABASE IF EXISTS "{_BASE_WORKER}" WITH (FORCE)',
        f'CREATE DATABASE "{_BASE_WORKER}" TEMPLATE "{plantilla}"',
    )


def destino_dominio(ruta_sqlite) -> str:  # noqa: ARG001
    """El destino de la base del DOMINIO (las tablas de LibraCommerce).

    No limpia nada: de eso se encarga `limpiar_entre_tests()`, una vez por test.
    """
    return TEST_DATABASE_URL


def destino_libracore(ruta_sqlite) -> str:  # noqa: ARG001
    """El destino de la base de LIBRACORE/libraauth.

    Contra PostgreSQL es **el mismo** que el del dominio: las dos bases
    conviven en un schema. No se vacia de nuevo — lo hizo `destino_dominio()`
    un momento antes, y vaciar dos veces borraria lo que la app acaba de crear.
    """
    return TEST_DATABASE_URL
