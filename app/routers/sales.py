import asyncio
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..modules_gate import get_module_repository
from ..services import mp_qr
from ..services.customers import CustomerService
from ..services.sales import SaleNotFound, SaleService
from ..services.tickets import ticket_de_venta

router = APIRouter(prefix="/sales", tags=["sales"])

#: F3 del plan post-P9 (2026-09-14, DECISIONS.md ADR-025): las ventas nuevas
#: se registran contra `/api/ventas` (la capa ERP de LibraCommerce montada en
#: `app/main.py`). Este router queda de SÓLO LECTURA: las escrituras de abajo
#: (crear, agregar/quitar líneas, confirmar, anular, devolver, poner/sacar del
#: QR) contestan 410 apuntando ahí. Lo que sigue siendo legible es lo que ya
#: era un GET -- últimas ventas, detalle, ticket y el estado del cobro por
#: QR -- porque nada de eso cambió de lugar: la venta vieja y la nueva viven
#: en la MISMA tabla `sales`.
#:
#: 🔴 **F3 no se despliega sola** (ver ADR-025): el POS (`Pos.tsx`) le sigue
#: pegando a ESTE router hasta F4. Este 410 recién se ejercita cuando F4 lo
#: mueva a `/api/ventas` -- hasta entonces, desplegar F3 sin F4 dejaría al
#: POS sin poder vender.
_MENSAJE_RETIRADA = (
    "Esta escritura se retiró en F3 del plan post-P9: usá /api/ventas "
    "(ver DECISIONS.md ADR-025)."
)


def _retirada() -> None:
    raise HTTPException(410, _MENSAJE_RETIRADA)


def _service(request: Request) -> SaleService:
    return SaleService(request.app.state.conn)


class SaleItemOut(BaseModel):
    kind: str
    item_id: int | None
    variant_id: int | None
    description_snapshot: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal


class SalePaymentOut(BaseModel):
    medio: str
    monto: Decimal
    recibido: Decimal | None
    vuelto: Decimal
    referencia: str


class SaleOut(BaseModel):
    id: int
    number: str
    status: str
    items: list[SaleItemOut]
    pagos: list[SalePaymentOut] = []
    vuelto_total: Decimal = Decimal("0")
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    confirmed_at: str | None
    factura: dict | None = None


def _to_sale_out(sale) -> SaleOut:
    return SaleOut(
        id=sale.id, number=sale.number, status=sale.status,
        items=[
            SaleItemOut(
                kind=item.kind, item_id=item.item_id, variant_id=item.variant_id,
                description_snapshot=item.description_snapshot,
                quantity=item.quantity, unit_price=item.unit_price,
                discount_amount=item.discount_amount, tax_amount=item.tax_amount,
                line_total=item.line_total,
            )
            for item in sale.items
        ],
        pagos=[
            SalePaymentOut(
                medio=payment.method, monto=payment.amount,
                recibido=payment.received_amount, vuelto=payment.change,
                referencia=payment.reference,
            )
            for payment in sale.payments
        ],
        vuelto_total=sale.change_due(),
        subtotal=sale.subtotal, discount_total=sale.discount_total,
        tax_total=sale.tax_total, total=sale.total,
        confirmed_at=sale.confirmed_at.isoformat() if sale.confirmed_at else None,
    )


@router.post("", status_code=410)
def create_sale(request: Request) -> None:  # noqa: ARG001
    """410: crear una venta ahora es `POST /api/ventas`."""
    _retirada()


class SaleListItem(BaseModel):
    id: int
    number: str
    status: str
    total: Decimal
    confirmed_at: str | None
    cliente: str


@router.get("", response_model=list[SaleListItem])
def list_sales(request: Request, limit: int = 50, search: str = ""):
    """Últimas ventas confirmadas -- lectura, sigue viva. Muestra ventas
    viejas y nuevas por igual: las dos viven en `sales`."""
    return [SaleListItem(**venta) for venta in _service(request).list_recent(
        limit=limit, search=search,
    )]


class MpDisponible(BaseModel):
    #: Si la instancia tiene cargadas las tres credenciales del QR.
    disponible: bool
    #: Si al acreditarse el pago se emite la factura sola.
    auto_facturar: bool


@router.get("/mp/estado", response_model=MpDisponible)
def mp_disponible(request: Request):
    """Si este mostrador puede cobrar por QR, y si eso factura solo. Lectura,
    sigue viva -- la lee tanto el POS legado como el nuevo."""
    return MpDisponible(
        disponible=mp_qr.esta_configurado(),
        auto_facturar=mp_qr.auto_facturar_prendida()
        and get_module_repository(request).is_enabled("facturacion"),
    )


class MpCobroHuerfanoOut(BaseModel):
    """Un cobro que entró y cuya venta quedó sin confirmar."""
    sale_id: int
    numero: str | None = None
    amount: float
    payment_id: str | None = None
    external_reference: str
    #: Cuándo lo acreditó MercadoPago. El más viejo es el que más urge.
    acreditado_el: str | None = None


@router.get("/mp/cobros-sin-venta", response_model=list[MpCobroHuerfanoOut])
def mp_cobros_sin_venta(request: Request):
    """Los cobros del camino VIEJO de QR (`sale_mp_orders`) que entraron y
    cuya venta quedó sin confirmar. Lectura, sigue viva -- pero D2 dejó de
    escribir esa tabla para ventas nuevas (0 filas en dev/demo, ver ADR-025):
    esto sólo puede encontrar algo de antes de F3."""
    return mp_qr.cobros_sin_venta(request.app.state.conn)


@router.post("/{sale_id}/mp-qr", status_code=410)
def poner_en_el_qr(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: el QR de una venta nueva es `POST /api/ventas/{vid}/mp-qr`."""
    _retirada()


@router.delete("/{sale_id}/mp-qr", status_code=410)
def bajar_del_qr(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: no hay equivalente de "bajar del QR" en el modelo nuevo (D2: la
    venta pendiente se acredita o se abandona; el cartel es fijo por caja)."""
    _retirada()


class MpEstadoOut(BaseModel):
    #: `approved`, `pending`, `sin_orden`, o el estado crudo de MercadoPago
    #: (`rejected`, `cancelled`, `in_process`).
    status: str
    payment_id: str | None = None


@router.get("/{sale_id}/mp-status", response_model=MpEstadoOut)
def estado_del_qr(sale_id: int, request: Request):
    """Si el QR VIEJO de esta venta ya se pagó. Lectura, sigue viva -- para
    una venta nueva no hay nada que encontrar acá (usar
    `GET /api/ventas/{vid}/mp-status`, del motor)."""
    try:
        estado = asyncio.run(mp_qr.estado_del_cobro(request.app.state.conn, sale_id))
    except mp_qr.MpNoConfigurado as exc:
        raise HTTPException(400, str(exc))
    except mp_qr.MpError as exc:
        raise HTTPException(502, str(exc))
    return MpEstadoOut(**estado)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, request: Request):
    try:
        return _to_sale_out(_service(request).get(sale_id))
    except SaleNotFound:
        raise HTTPException(404, "sale not found")


@router.post("/{sale_id}/cancel", status_code=410)
def cancel_sale_endpoint(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: anular una venta ahora es `POST /api/ventas/{vid}/anular`."""
    _retirada()


@router.post("/{sale_id}/returns", status_code=410)
def return_items(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: devolver líneas ahora es `POST /api/ventas/{vid}/devolver`."""
    _retirada()


@router.get("/{sale_id}/ticket")
def ticket(sale_id: int, request: Request):
    """PDF del ticket térmico de una venta confirmada. Lectura, sigue viva
    para ventas viejas y nuevas por igual.

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


@router.patch("/{sale_id}", status_code=410)
def set_customer(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: asignar cliente a una venta ahora se hace al registrarla en
    `POST /api/ventas` (D1: el POS arma la venta en el navegador y la
    registra en una sola llamada, ya con el cliente elegido)."""
    _retirada()


@router.post("/{sale_id}/items", status_code=410)
def add_item(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: no hay más venta en borrador por posición (D1)."""
    _retirada()


@router.delete("/{sale_id}/items/{index}", status_code=410)
def remove_item(sale_id: int, index: int, request: Request) -> None:  # noqa: ARG001
    """410: no hay más venta en borrador por posición (D1)."""
    _retirada()


@router.patch("/{sale_id}/items/{index}", status_code=410)
def update_item_quantity(sale_id: int, index: int, request: Request) -> None:  # noqa: ARG001
    """410: no hay más venta en borrador por posición (D1)."""
    _retirada()


@router.post("/{sale_id}/confirm", status_code=410)
def confirm_sale(sale_id: int, request: Request) -> None:  # noqa: ARG001
    """410: confirmar una venta ahora es `POST /api/ventas` (D1: una sola
    llamada, sin borrador previo)."""
    _retirada()
