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


def corre_contra_postgres() -> bool:
    return TEST_DATABASE_URL.startswith("postgresql")


def _vaciar_schema() -> None:
    """Deja el PostgreSQL compartido como una base nueva.

    Cada test arma su propia app y espera una base limpia. Con archivos
    temporales eso sale gratis; un PostgreSQL es **uno solo y compartido** por
    toda la corrida. Se borra el SCHEMA y no la base: `DROP DATABASE` exige que
    no quede ninguna conexion abierta, y la app del test anterior puede tener
    la suya viva.
    """
    import psycopg

    with psycopg.connect(
        TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1),
        autocommit=True,
    ) as conexion:
        conexion.execute("DROP SCHEMA public CASCADE")
        conexion.execute("CREATE SCHEMA public")


def destino_dominio(ruta_sqlite) -> str:
    """El destino de la base del DOMINIO (las tablas de LibraCommerce)."""
    if not corre_contra_postgres():
        return str(ruta_sqlite)
    _vaciar_schema()
    return TEST_DATABASE_URL


def destino_libracore(ruta_sqlite) -> str:
    """El destino de la base de LIBRACORE/libraauth.

    Contra PostgreSQL es **el mismo** que el del dominio: las dos bases
    conviven en un schema. No se vacia de nuevo — lo hizo `destino_dominio()`
    un momento antes, y vaciar dos veces borraria lo que la app acaba de crear.
    """
    if not corre_contra_postgres():
        return str(ruta_sqlite)
    return TEST_DATABASE_URL
