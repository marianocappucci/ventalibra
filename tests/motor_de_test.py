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
# El mecanismo (una base por worker de xdist, plantillas, `FORCE` para echar las
# conexiones del test anterior) vive en `libracore.testing.pg_por_worker`; aca
# queda lo propio de VentaLibra: que hay en cada plantilla.
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
# `from motor_de_test import TEST_DATABASE_URL` es como la leen todos los tests,
# asi que reasignarla aca alcanza: ninguno compone la URL por su cuenta.
#
# 🔴 Algunos tests importan `tests.motor_de_test` y otros `motor_de_test`: son DOS
# modulos y este codigo corre dos veces por proceso. `base_por_worker` es
# idempotente a proposito, asi que no recrea la base la segunda vez.
from libracore.testing.pg_por_worker import base_por_worker  # noqa: E402

_PG = base_por_worker("ventalibra", TEST_DATABASE_URL)
TEST_DATABASE_URL = _PG.url


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

    🔴 **Se borra la base con `FORCE` y no se hace un `DROP SCHEMA`.** Este producto
    abre **una conexion viva por app** (`db.connect()`, sin pool) y no la cierra
    nunca: es su diseno, heredado de SQLite. Contra PostgreSQL esa conexion queda
    *idle in transaction* sosteniendo locks, y un `DROP SCHEMA` **se cuelga
    esperandola** -- medido: 20 minutos sin avanzar, con la corrida entera
    detras. `FORCE` echa a esas conexiones, que son de apps que ese test ya no usa.
    """
    if construir_armada is None:
        _PG.restaurar("vacia", _construir_vacia)
    else:
        _PG.restaurar("armada", construir_armada)


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
