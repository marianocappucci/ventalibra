"""Lecturas de venta que quedan fuera de `/api/ventas` (la capa ERP de
LibraCommerce): el ticket térmico y si el mostrador puede cobrar por QR.

Nace en F4 del plan ERP (2026-09-15, DECISIONS.md ADR-025) cuando `/sales` se
retira entero -- ver el `git log` de `app/routers/sales.py`, que este archivo
reemplaza. Dos lecturas sueltas que colgaban de ese router y no tienen dueño
en la capa ERP:

- `GET /ventas/{id}/ticket`: el PDF del ticket térmico. Es la MISMA lectura de
  siempre (`app/services/sales.py::SaleService`, montado sobre el repositorio
  del motor) -- sólo cambia el prefijo, a la ruta que `VentaDetalle`/`Pos.tsx`
  de libra-ui ya piden por default (`rutaDeTicket`). Montado ANTES del
  catch-all de la SPA (`app/spa.py`, agregado en `app/asgi.py` después de
  `create_app()`): FastAPI resuelve por orden de registro, así que esta ruta
  gana sobre `/{full_path:path}` aunque el SPA también sirva `/ventas`.
- `GET /pos/mp-estado`: si esta instancia puede cobrar por QR y si eso
  factura solo. Antes vivía en `/sales/mp/estado`; el nombre cambia porque ya
  no hay ningún `/sales` del que colgar, pero el criterio
  (`app/services/mp_qr.py::esta_configurado`) es el mismo. A propósito NO
  exige el módulo `facturacion` (a diferencia de `GET /api/config/
  mercadopago`, admin-only y gateado por ese módulo): el cajero (staff)
  necesita esto para decidir si ofrece el botón de QR, y cobrar por QR no
  depende del plan de facturación -- sólo emitir sola SÍ, que es justo lo que
  filtra `auto_facturar` de acá abajo.

Una lectura nueva de F4 (no reemplaza nada de `/sales`, que nunca la tuvo):

- `GET /ventas/{id}/devuelto`: cuánto se devolvió ya de esta venta, por
  (producto, variante), y de qué depósito salió originalmente -- lo que la
  pantalla de devolución de `Ventas.tsx` necesita para topear la cantidad y
  proponer el depósito por default. `GET /api/ventas/{id}` (la capa ERP) no
  trae esto: `sale_items.quantity` es el snapshot de lo VENDIDO y nunca
  cambia -- lo devuelto vive sólo en el ledger `stock_movements`
  (`libracommerce.erp.ventas.devolver_items`, `reason_code='devolucion'`), sin
  ningún GET que lo exponga. Se lee acá con el MISMO criterio que ese motor
  usa para validar la devolución (`_COND_VENDIDO`/`_COND_DEVUELTO` en
  `libracommerce/erp/ventas.py`) -- leyendo la tabla, no importando esas
  funciones privadas (`_`) del paquete.

  🔴 **El pozo es por (producto, variante), no por línea.** Si la venta tiene
  dos líneas del mismo producto, las dos comparten un solo tope -- es la
  regla del motor (ver el docstring de `devolver_items`), no una simplificación
  de acá. La pantalla usa esto para no ofrecer de más, pero quien decide de
  verdad sigue siendo `POST /api/ventas/{vid}/devolver`, que aplica la MISMA
  cuenta server-side.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import get_current_user
from ..modules_gate import get_module_repository
from ..services import mp_qr
from ..services.customers import CustomerService
from ..services.sales import SaleNotFound, SaleService
from ..services.tickets import ticket_de_venta

router = APIRouter(tags=["ventas"])


def _service(request: Request) -> SaleService:
    return SaleService(request.app.state.conn)


@router.get("/ventas/{sale_id}/ticket")
def ticket(sale_id: int, request: Request):
    """PDF del ticket térmico de una venta confirmada. Lectura, sin cambios
    de comportamiento desde antes de F3 -- sólo cambió de ruta.

    Sólo confirmadas: un borrador no tiene número de venta cerrado ni pagos,
    y un ticket impreso de algo que todavía se puede modificar es un
    comprobante que miente.
    """
    try:
        sale = _service(request).get(sale_id)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    if sale.status != "confirmed":
        raise HTTPException(409, "solo se imprime el ticket de una venta confirmada")

    nombre = ""
    if sale.customer_party_id is not None:
        cliente = CustomerService(request.app.state.conn).get(sale.customer_party_id)
        nombre = (cliente or {}).get("display_name", "")

    pdf = ticket_de_venta(sale, nombre)
    return Response(
        content=pdf,
        media_type="application/pdf",
        # inline: el POS lo abre para imprimir, no lo baja como archivo.
        headers={"Content-Disposition": f'inline; filename="ticket-{sale.number}.pdf"'},
    )


class MpDisponible(BaseModel):
    #: Si la instancia tiene cargadas las tres credenciales del QR.
    disponible: bool
    #: Si al acreditarse el pago se emite la factura sola.
    auto_facturar: bool


@router.get("/pos/mp-estado", response_model=MpDisponible)
def mp_disponible(request: Request, user: dict = Depends(get_current_user)):
    """Si este mostrador puede cobrar por QR, y si eso factura solo. Lo
    pregunta el POS al abrir la pantalla, una sola vez."""
    return MpDisponible(
        disponible=mp_qr.esta_configurado(user.get("id")),
        auto_facturar=mp_qr.auto_facturar_prendida()
        and get_module_repository(request).is_enabled("facturacion"),
    )


class DevueltoPorClave(BaseModel):
    producto_id: int
    variante_id: int | None
    cantidad: float


class DevueltoOut(BaseModel):
    por_clave: list[DevueltoPorClave]
    #: El depósito de la venta original, si las líneas salieron todas del
    #: mismo -- que es lo normal, un solo POS descuenta de un solo lugar. `None`
    #: si no hubo movimiento de stock que mirar (módulo stock apagado al
    #: vender) o si salieron de más de uno (no debería pasar hoy, pero no se
    #: adivina: la pantalla cae a su default en ese caso).
    deposito_id: int | None


@router.get("/ventas/{sale_id}/devuelto", response_model=DevueltoOut)
def devuelto(sale_id: int, request: Request):
    conn = request.app.state.conn
    por_clave = conn.execute(
        """SELECT item_id, variant_id, SUM(quantity_delta) AS cantidad
             FROM stock_movements
            WHERE source_id = ?
              AND (reason_code = 'devolucion'
                   OR (source_type = 'sale_return' AND movement_type = 'return'))
            GROUP BY item_id, variant_id""",
        (sale_id,),
    ).fetchall()
    depositos = conn.execute(
        """SELECT DISTINCT location_id
             FROM stock_movements
            WHERE source_id = ?
              AND (reason_code = 'venta'
                   OR (source_type = 'sale' AND movement_type = 'sale'))""",
        (sale_id,),
    ).fetchall()
    return DevueltoOut(
        por_clave=[
            DevueltoPorClave(
                producto_id=fila["item_id"], variante_id=fila["variant_id"],
                cantidad=float(fila["cantidad"] or 0),
            )
            for fila in por_clave
        ],
        deposito_id=depositos[0]["location_id"] if len(depositos) == 1 else None,
    )
