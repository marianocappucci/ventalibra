"""La guarda de baja de un proveedor con compras.

El router de proveedores del motor (`libracore.egresos_router.build_proveedores_router`) sólo impide
eliminar un proveedor con **egresos**; VentaLibra no tiene egresos sino órdenes y recepciones de compra
(`purchase_orders`/`purchase_receipts`, atadas al party espejo). Sin esta guarda, eliminar un proveedor
dejaría compras apuntando a un proveedor que ya no existe. Es una dependencia del `include_router`,
porque la factory no ofrece un gancho para esto.
"""
import re

from fastapi import HTTPException, Request

from .services.proveedores import tiene_compras

_BAJA = re.compile(r"^/api/proveedores/(\d+)$")


def no_eliminar_con_compras(request: Request) -> None:
    if request.method != "DELETE":
        return
    coincide = _BAJA.match(request.url.path)
    if coincide and tiene_compras(request.app.state.conn, int(coincide.group(1))):
        raise HTTPException(409, "No se puede eliminar un proveedor con compras registradas.")
