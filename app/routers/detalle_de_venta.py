"""`GET /api/ventas/{id}` con `factura_pendiente`: el detalle del motor más la bandeja del nodo offline (ADR-090).

En un nodo de LibraEdge sin conexión la factura de una venta queda en la bandeja de comprobantes pendientes y sale sola al
volver (libracore ADR-074). La pantalla (libra-ui ADR-077) lo dice («Quedó para facturar») leyendo `factura_pendiente`
del detalle: la fila abierta de la bandeja, o `null`. Fuera de un nodo es siempre `null`.

🔑 **No se reescribe el detalle: se envuelve el del motor.** El de `build_ventas_router` trae las promociones y los
avisos de vencimiento (`OpcionesVentas.promociones` y `con_avisos_de_vencimiento`, que este producto prende). RestoLibra
lo reescribió porque no prende ninguna de las dos; acá copiarlo dejaría dos detalles que se separan con el próximo
cambio del motor. Así que se toma el endpoint de la ruta del router ya armado y se le suma la clave. La guarda por turno
(`solo_sus_turnos`, ADR-068) cuelga de las `dependencies` de esa ruta y no del endpoint: quien monta este router le pone
la misma (`build_guarda_de_venta`).

Se monta **antes** que el router del motor: gana el mismo path. `{vid:int}` sólo toma números, así
`GET /api/ventas/medios-pago` y las demás rutas fijas siguen yendo al motor.
"""

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app import venta_facturacion


def _detalle_del_motor(ventas_router: APIRouter):
    prefijo = ventas_router.prefix
    for ruta in ventas_router.routes:
        if isinstance(ruta, APIRoute) and ruta.path == f"{prefijo}/{{vid}}" and "GET" in ruta.methods:
            return ruta.endpoint
    raise RuntimeError(
        f"el router de ventas del motor no tiene `GET {prefijo}/{{vid}}`: no se puede sumar `factura_pendiente`"
    )


def build_detalle_con_factura_pendiente(ventas_router: APIRouter) -> APIRouter:
    """Un router con sólo `GET <prefijo>/{vid:int}`: el detalle de `ventas_router` más `factura_pendiente`."""
    detalle_del_motor = _detalle_del_motor(ventas_router)
    router = APIRouter(prefix=ventas_router.prefix, tags=["ventas"])

    @router.get("/{vid:int}")
    def detalle(vid: int):
        venta = detalle_del_motor(vid=vid)
        venta["factura_pendiente"] = venta_facturacion.pendiente_de_facturar(vid)
        return venta

    return router
