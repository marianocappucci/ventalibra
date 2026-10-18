"""La conexión del dominio: una por request, y lo que queda de la única de arranque.

🔴 **Una conexión por request (ADR-089).** Hasta ADR-089 este producto sostenía **una sola conexión para toda la app**
(`app.state.conn`, sin pool, abierta al arrancar —su diseño, heredado de SQLite—) y todos los requests de un proceso la
compartían: FastAPI corre los endpoints `def` en un threadpool, así que dos requests concurrentes escribían en la MISMA
transacción (el `rollback()` de uno deshacía el `INSERT` del otro, el `commit()` de uno confirmaba lo que el otro dejó a
medias). Ahora `conexion_del_request` abre una por request y `PorLlamada` abre una por consulta a quien no tiene request
(el gate de módulos, los ganchos del motor, el log); `app.state.conn` queda sólo para el arranque y el mantenimiento
(restore, tests): **ningún request la toca** (`tests/test_ningun_request_usa_la_conexion_global.py`). Es la forma del resto
de la familia: `libracore.db.core.get_connection()` abre, `with` confirma o revierte y cierra.

Lo que sigue es del modelo anterior y se queda mientras exista `app.state.conn`.

## Que un dato repetido no deje la app sin poder escribir

🔴 **El defecto que cierra `conexion_utilizable`.** Contra PostgreSQL un error
**aborta la transaccion**, y toda consulta posterior sobre esa conexion muere
con *"current transaction is aborted, commands ignored until end of transaction
block"*.

Los endpoints que traducen un `IntegrityError` a un HTTP 409 —un codigo de
barras repetido, un SKU repetido, una segunda lista de precios por defecto— son
acciones **normales** de quien carga el catalogo. Sin un `rollback()` entre el
error y el 409, ese 409 se llevaba puesto **todo lo que viniera despues**, hasta
que alguien reiniciara el contenedor.

`services/catalog.py::create_unit` ya lo hacia bien y lo dejo escrito: *"la
conexion es una sola para toda la app, asi que sin este rollback el 409 se lleva
puesto al que escriba despues"*. Lo que faltaba era que valiera para los otros
cuatro caminos, que delegan en el repositorio de LibraCommerce y por eso no
pasaban por ese `except`.

## Por que aca y no en LibraCommerce

Los metodos de escritura del repositorio hacen `execute` + `_commit()` sin
`try`, asi que un `IntegrityError` sube con la transaccion abierta. Arreglarlo
alla lo cerraria para los seis consumidores de una — pero para los otros cinco
seria un no-op: abren y cierran **una conexion por llamada**
(`libracore.db.core.get_connection()`), asi que la transaccion abortada muere
con su conexion y no envenena nada.

El problema es del **modelo de conexion de este producto**, no del repositorio.
Por eso el arreglo vive aca. Si algun dia otro producto adopta una conexion
unica y larga, ahi si conviene subirlo al motor.
"""
import contextlib
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import psycopg
from fastapi import Request
from libracore.db import core
from libracore.db._postgres import ConnectionWrapper, Cursor
from libracore.db.core import Conexion
from psycopg.rows import tuple_row

#: Cómo se abre una conexión nueva del dominio: lo que `create_app` deja en `app.state.abrir_dominio`. El objeto que
#: devuelve es el de la familia (`ConnectionWrapper`): `with` confirma si todo salió bien, revierte si no, y cierra.
Abrir = Callable[[], AbstractContextManager[Conexion]]


def conexion_del_request(request: Request) -> Iterator[Conexion]:
    """Dependencia de FastAPI: **la conexión de este request**, que nadie más usa.

    La abre `app.state.abrir_dominio` y se cierra al terminar el request: se confirma si el endpoint volvió normal y se
    revierte si levantó (una `HTTPException` incluida: un 409 no deja a medias lo que escribió antes de decidirlo). Es la
    transacción del request, de punta a punta, y por eso un request no puede deshacer ni confirmar lo del otro. Los
    servicios que confirman por su cuenta (`CatalogService`) siguen haciéndolo: el `commit()` final es sólo la red.

    Se usa con `Depends(conexion_del_request)`; FastAPI la comparte entre todas las dependencias del mismo request.
    """
    with request.app.state.abrir_dominio() as conn:
        yield conn


class PorLlamada:
    """Un repositorio o servicio que **abre su propia conexión en cada llamada** y la cierra al volver.

    Es para lo que se consulta sin tener un request a mano: el gate de módulos (`app.state.modules`, que lee el motor en
    cada request), el log (`app.state.auditoria`) y los ganchos de sucursales que reciben los routers del motor. Antes
    guardaban la conexión única de la app; ahora cada método es `with abrir() as conn: clase(conn).metodo(...)`, el mismo
    gesto que hacen los routers del motor (`with conexion() as conn`). Lo que devuelve el método ya está leído cuando la
    conexión se cierra: ninguno de estos servicios devuelve un cursor.

    Sólo expone los **métodos públicos** de `clase`: un atributo que no es un método (o uno privado) levanta
    `AttributeError`, como el objeto real, en lugar de abrir una conexión para nada.
    """

    def __init__(self, clase: Callable[[Conexion], object], abrir: Abrir):
        self._clase = clase
        self._abrir = abrir

    def __getattr__(self, nombre: str):
        if nombre.startswith("_") or not callable(getattr(self._clase, nombre, None)):
            raise AttributeError(nombre)

        def llamar(*args, **kwargs):
            with self._abrir() as conn:
                return getattr(self._clase(conn), nombre)(*args, **kwargs)

        llamar.__name__ = nombre
        return llamar


@contextmanager
def conexion_utilizable(conn):
    """Deja `conn` usable si la operacion de adentro falla.

    No traga el error: lo vuelve a levantar para que el router lo traduzca al
    409 que corresponde. Lo unico que agrega es el `rollback()`, que contra
    PostgreSQL es lo que separa *"este dato esta repetido"* de *"la app dejo de
    escribir"*.
    """
    try:
        yield
    except sqlite3.Error:
        conn.rollback()
        raise


#: Un `SELECT` común (o un `PRAGMA`, que el adaptador ignora o traduce a lectura): no deja nada pendiente en la
#: transacción, así que si la conexión muere se puede repetir en otra.
_LECTURA = re.compile(r"\s*(SELECT|PRAGMA)\b", re.IGNORECASE)
#: ...salvo que tome locks o avance una secuencia: eso es un efecto que se perdería con la conexión.
_CON_EFECTO = re.compile(
    r"\bFOR\s+(NO\s+KEY\s+)?(UPDATE|SHARE)\b|\bFOR\s+KEY\s+SHARE\b|\b(nextval|setval|pg_\w*advisory\w*)\s*\(",
    re.IGNORECASE,
)


def _es_lectura(sql: str) -> bool:
    return bool(_LECTURA.match(sql)) and not _CON_EFECTO.search(sql)


class ConexionRenovable(ConnectionWrapper):
    """La conexión única del dominio, que se renueva en el lugar si el servidor la mató (ADR-044 de libracore).

    🔴 **El defecto que cierra.** Con `uvicorn --workers N` cada proceso tiene SU conexión (`app.state.conn`). Un restore en
    caliente lo atiende un worker, y el intercambio de bases (`respaldo_postgres.intercambiar`) **termina las conexiones
    de la base viva**: la del worker que lo atendió la reabre `_reabrir_conexion`, pero las de los otros quedan muertas
    (`terminating connection due to administrator command`) y cada request que las toca daba 500 hasta que alguien
    reiniciaba el contenedor. `libracore.respaldo_postgres.vigilar_pools` no las ve: sólo mira los pools de SQLAlchemy, y el
    `pool_pre_ping=True` de ADR-044 es de los engines (`auth_engine` lo lleva). Esta conexión no tiene pool.

    **Cómo se renueva** (el equivalente al `pool_pre_ping` para una conexión sola):

    - Si la conexión **se rompió** (`broken`: el servidor la cortó, y psycopg lo sabe recién tras el primer error), la
      siguiente operación abre otra antes de empezar.
    - Si el error es justo ése, el de la conexión cortada, y **la transacción en curso no tenía nada pendiente** (sólo
      `SELECT` comunes desde el último `commit`/`rollback`), se abre otra y **se reintenta una vez**: no hay nada que se
      pierda. Es lo que le pasa al primer pedido del worker que no atendió el restore, y por eso no lo ve como un 500. Ojo
      que esta conexión casi nunca está `IDLE`: una lectura deja la transacción abierta (*idle in transaction*), así que
      el criterio no es el estado de la conexión sino lo que se escribió en ella.
    - Si **había escrituras pendientes** no se reintenta: se pierden con la conexión (el servidor las deshace), y repetir
      sólo el último statement confirmaría el resto a medias. El error sube, y la transacción que cruzó la muerte **no se
      confirma**: el siguiente `commit()` levanta `OperationalError` en lugar de confirmar lo que quedó (una conexión
      compartida por hilos puede renovarla un hilo mientras otro tiene su transacción a medias).
    - Un `commit()` que falla por la conexión muerta no se reintenta: no se sabe si llegó.
    - Una conexión **cerrada a mano** (`close()`, como hace `_cerrar_conexion` antes del intercambio) NO se reabre sola:
      sigue cerrada hasta que `renovar()` la reabra, así que un pedido que llega a mitad del restore no se cuela.

    Es **el mismo objeto** antes y después: `ModuleRepository`, `ActividadRepository` y todo lo que lo guardó siguen
    apuntando a una conexión viva, que es lo que `_reabrir_conexion` no lograba reemplazándola (el `app.state.modules`
    de después de un restore tenía la vieja, ya cerrada).

    Va en el producto y no en `libracore.db.core` porque hoy es el único de la familia con una conexión única y larga
    (ver el docstring del módulo): los demás abren una por llamada o usan un engine con pool. Si otro la adopta, sube.
    """

    def __init__(self, destino: str):
        super().__init__(core.conectar(destino)._connection)
        self._destino = destino
        self._renovando = threading.Lock()
        self._escribio = False       # hay escrituras (o locks) pendientes en la transacción en curso
        self._perdida = False        # la transacción en curso cruzó una renovación con escrituras pendientes

    def renovar(self, vieja=None) -> None:
        """Abre una conexión nueva y cierra la anterior. Con `vieja`, sólo si nadie la renovó ya (dos hilos que ven la
        misma rota no abren dos conexiones)."""
        with self._renovando:
            if vieja is not None and self._connection is not vieja:
                return
            anterior = self._connection
            self._connection = core.conectar(self._destino)._connection
            self._con_id = {}
            self._perdida = self._escribio     # lo pendiente murió con la conexión: que no se confirme el resto
            self._escribio = False
            with contextlib.suppress(Exception):
                anterior.close()

    def cursor(self):
        if self._connection.broken:
            self.renovar(self._connection)
        return _CursorRenovable(self)

    def commit(self):
        if self._perdida:
            self._perdida = False
            super().rollback()
            raise sqlite3.OperationalError(
                "la transaccion empezo en una conexion que se corto: no se confirma lo que quedo a medias"
            )
        super().commit()
        self._escribio = False

    def rollback(self):
        # En una conexión rota el servidor ya deshizo todo lo que no se confirmó: no hay nada que deshacer, y el
        # `rollback()` de psycopg levantaría otro error encima del que se está manejando (`conexion_utilizable`).
        self._perdida = False
        self._escribio = False
        if self._connection.broken:
            return
        super().rollback()


class _CursorRenovable(Cursor):
    """El cursor de `ConexionRenovable`: reintenta una vez, con la conexión renovada, si la conexión murió y no había
    nada pendiente en su transacción."""

    def execute(self, sql, params=None):
        return self._con_renovacion(Cursor.execute, _es_lectura(sql), sql, params)

    def executemany(self, sql, params):
        return self._con_renovacion(Cursor.executemany, False, sql, params)

    def _con_renovacion(self, metodo, es_lectura, *args):
        conexion = self._connection
        viva = conexion._connection
        try:
            resultado = metodo(self, *args)
        except (psycopg.Error, sqlite3.Error):
            if not viva.broken or conexion._escribio:
                raise
            conexion.renovar(viva)
            self._cursor = conexion._connection.cursor(row_factory=tuple_row)
            resultado = metodo(self, *args)
        if not es_lectura:
            conexion._escribio = True
        return resultado
