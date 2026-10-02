"""La guarda de baja de un proveedor con compras o que es el habitual de un producto (ADR-056).

El router de proveedores del motor (`libracore.egresos_router.build_proveedores_router`) ya impide
eliminar un proveedor con **egresos** (`ValueError` -> 422, desde la fase 11: antes esto no aplicaba,
VentaLibra no tenía egresos). Pero un proveedor puede tener órdenes y recepciones de compra
(`purchase_orders`/`purchase_receipts`, atadas al party espejo) sin tener ni un egreso, y de eso el motor
no sabe nada: sin esta guarda, eliminarlo dejaría compras apuntando a un proveedor que ya no existe. Es
una dependencia del `include_router`, porque la factory no ofrece un gancho para esto.
"""
import re

from fastapi import HTTPException, Request

from .services.proveedores import es_proveedor_habitual, tiene_compras

_BAJA = re.compile(r"^/api/proveedores/(\d+)$")


def no_eliminar_con_compras(request: Request) -> None:
    if request.method != "DELETE":
        return
    coincide = _BAJA.match(request.url.path)
    if not coincide:
        return
    conn, proveedor_id = request.app.state.conn, int(coincide.group(1))
    if tiene_compras(conn, proveedor_id):
        raise HTTPException(409, "No se puede eliminar un proveedor con compras registradas.")
    if es_proveedor_habitual(conn, proveedor_id):
        raise HTTPException(409, "No se puede eliminar un proveedor que es el habitual de algún producto: soltalo primero en la reposición del producto.")
