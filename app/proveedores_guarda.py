"""La guarda de baja de un proveedor con compras o que es el habitual de un producto (ADR-056).

El router de proveedores del motor (`libracore.egresos_router.build_proveedores_router`) ya impide
eliminar un proveedor con **egresos** (`ValueError` -> 422, desde la fase 11: antes esto no aplicaba,
VentaLibra no tenía egresos). Pero un proveedor puede tener órdenes y recepciones de compra
(`purchase_orders`/`purchase_receipts`, atadas al party espejo) sin tener ni un egreso, y de eso el motor
no sabe nada: sin esta guarda, eliminarlo dejaría compras apuntando a un proveedor que ya no existe. Es
una dependencia del `include_router`, porque la factory no ofrece un gancho para esto.

## Compras y nodos (ADR-093)

Dos guardas más, por la misma razón (la factory del motor no tiene ganchos):

- `proveedores_solo_en_el_central`: en un nodo el alta, la edición y la baja de proveedores son 409 `solo_en_el_central`: los
  proveedores se cargan en la versión web y bajan por el espejo.
- `party_al_guardar`: en el central, al dar de alta o editar un proveedor crea o refresca su party (`id = proveedores.id +
  100000`), que es a lo que apuntan las órdenes y recepciones de compra y lo que baja al nodo. Es una dependencia con `yield`:
  corre cuando el alta o la edición ya se hizo bien (si el motor contestó 404 o 422, no corre). 🔴 **Lo que haría el motor con
  un gancho `al_guardar` de `build_proveedores_router`**; mientras no exista, este es el único camino sin escribir SQL por fuera.
"""
import logging
import re

from fastapi import HTTPException, Request
from libracore.db.core import get_connection

from .offline import compras_solo_en_el_central, nodo
from .services.proveedores import es_proveedor_habitual, sincronizar_parties_de_proveedores, tiene_compras

logger = logging.getLogger(__name__)

_BAJA = re.compile(r"^/api/proveedores/(\d+)$")
_ESCRIBE = re.compile(r"^/api/proveedores(/\d+)?$")


def no_eliminar_con_compras(request: Request) -> None:
    if request.method != "DELETE":
        return
    coincide = _BAJA.match(request.url.path)
    if not coincide:
        return
    proveedor_id = int(coincide.group(1))
    # Una conexión propia y sólo para la baja: la guarda cuelga de todo el router y casi todos sus pedidos no la necesitan.
    with request.app.state.abrir_dominio() as conn:
        if tiene_compras(conn, proveedor_id):
            raise HTTPException(409, "No se puede eliminar un proveedor con compras registradas.")
        if es_proveedor_habitual(conn, proveedor_id):
            raise HTTPException(409, "No se puede eliminar un proveedor que es el habitual de algún producto: soltalo primero en la reposición del producto.")


def proveedores_solo_en_el_central(request: Request) -> None:
    """En un nodo, escribir proveedores es 409 `solo_en_el_central`. Leerlos (el nodo los espeja) sigue igual."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    compras_solo_en_el_central()


def party_al_guardar(request: Request):
    """Dependencia con `yield`: tras un alta (`POST`) o una edición (`PUT`) del proveedor, crea o refresca su party.

    Refresca **todos** los proveedores (`sincronizar_parties_de_proveedores`) y no sólo el guardado: el alta no devuelve el id al
    producto antes de contestar, y la sincronización no reescribe lo que ya está al día. Fuera del central no hace nada. Si
    falla, el proveedor ya está guardado: se registra y no se convierte en un 500 (`party_de_proveedor` lo asegura de todos modos
    antes de la primera orden)."""
    yield
    if nodo() is not None or request.method not in ("POST", "PUT") or not _ESCRIBE.match(request.url.path):
        return
    try:
        # La conexión de LibraCore y no `abrir_dominio`: es la misma base (`_UNA_SOLA_BASE`) y es la que usan los routers de Compras.
        with get_connection() as conn:
            sincronizar_parties_de_proveedores(conn)
            conn.commit()
    except Exception:  # el proveedor ya se guardó; esto se completa en la próxima orden o en el backfill
        logger.exception("No se pudo sincronizar el party del proveedor guardado")
