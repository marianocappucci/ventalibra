"""Que un dato repetido no deje la app sin poder escribir.

🔴 **El defecto que este modulo cierra.** Este producto sostiene **una sola
conexion para toda la app** (`app.state.conn`, sin pool, abierta al arrancar y
nunca cerrada — es su diseño, heredado de SQLite). Contra PostgreSQL un error
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
from contextlib import contextmanager
import sqlite3


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
