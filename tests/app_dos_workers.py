"""`app.asgi:app` con la ventana de la carrera ensanchada, para `test_varios_procesos.py`.

Sin el candado, la carrera es «no hay sucursal» (o «no hay caja», o «el admin no existe») -> «crearla»: una ventana de
milisegundos que dos workers arrancando juntos casi nunca pisan en una máquina rápida. Eso haría que el test pase aunque
el candado no esté, y un test que no se pone rojo sin el arreglo no cuida nada. Acá la ventana dura `VENTANA` segundos
entre mirar y escribir, en los tres «si no existe, crear» del arranque que NO son de un motor (la sucursal mínima de
`app/sucursales_migracion.py`, la caja por defecto de `app/services/billing.py` y el admin de libraauth). Lo demás (el
DDL) no necesita ayuda: sobre una base sin las tablas el choque en el catálogo de PostgreSQL pasa solo.

Lo que se mide sigue siendo el código del producto: esto sólo agranda el tiempo entre mirar y escribir.
"""
import time

from libraauth.repository import UserRepository
from libracommerce.erp import catalogo
from libracore.db import caja

VENTANA = 2.0

_lista_original = UserRepository.list
_crear_sucursal_original = catalogo.create_sucursal
_crear_caja_original = caja.create_caja_config


def _lista_lenta(self, *args, **kwargs):
    usuarios = _lista_original(self, *args, **kwargs)
    if not usuarios:
        time.sleep(VENTANA)
    return usuarios


def _crear_sucursal_lenta(*args, **kwargs):
    time.sleep(VENTANA)
    return _crear_sucursal_original(*args, **kwargs)


def _crear_caja_lenta(*args, **kwargs):
    time.sleep(VENTANA)
    return _crear_caja_original(*args, **kwargs)


UserRepository.list = _lista_lenta
catalogo.create_sucursal = _crear_sucursal_lenta
caja.create_caja_config = _crear_caja_lenta

from app.asgi import app  # noqa: E402,F401  (lo consume uvicorn por nombre)
