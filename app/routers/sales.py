from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..modules_gate import get_module_repository
from ..services import billing
from ..services.cuenta_corriente import (
    MEDIO_CUENTA_CORRIENTE,
    CuentaCorrienteService,
    SinCliente,
)
from ..services.customers import CustomerService
from ..services.tickets import ticket_de_venta
from libracommerce.domain.sales import SalePayment
from libracore.db import turnos as db_turnos

from ..services.sales import InvalidSaleState, SaleNotFound, SaleService

router = APIRouter(prefix="/sales", tags=["sales"])


class SaleCreate(BaseModel):
    branch_id: int | None = None
    register_id: int | None = None
    customer_party_id: int | None = None


class SaleItemCreate(BaseModel):
    item_id: int
    quantity: Decimal
    variant_id: int | None = None
    unit_price: Decimal | None = None
    discount_amount: Decimal = Decimal("0")
    price_list_id: int | None = None


class SaleItemQuantity(BaseModel):
    quantity: Decimal


class PaymentIn(BaseModel):
    medio: str
    monto: Decimal
    # Cuanto entrego el cliente, para calcular el vuelto. Solo tiene sentido
    # en efectivo.
    recibido: Decimal | None = None
    referencia: str = ""


class SaleConfirm(BaseModel):
    location_id: int
    # `medio_pago` es el camino de siempre: un solo medio que cubre el total.
    # `pagos` es el cobro mixto y, si viene, manda. Se conserva el campo
    # viejo porque la mayoria de las ventas de mostrador son de un solo
    # medio y no tiene sentido obligar al POS a armar una lista para eso.
    medio_pago: str = ""
    pagos: list[PaymentIn] = []
    invoice: bool = False


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


def _service(request: Request) -> SaleService:
    return SaleService(request.app.state.conn)


@router.post("", response_model=SaleOut)
def create_sale(data: SaleCreate, request: Request):
    sale = _service(request).create_draft(
        branch_id=data.branch_id, register_id=data.register_id,
        customer_party_id=data.customer_party_id,
    )
    return _to_sale_out(sale)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, request: Request):
    try:
        return _to_sale_out(_service(request).get(sale_id))
    except SaleNotFound:
        raise HTTPException(404, "sale not found")


@router.get("/{sale_id}/ticket")
def ticket(sale_id: int, request: Request):
    """PDF del ticket termico de una venta confirmada.

    Solo confirmadas: un borrador no tiene numero de venta cerrado ni pagos,
    y un ticket impreso de algo que todavia se puede modificar es un
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


class SaleCustomerUpdate(BaseModel):
    customer_party_id: int | None = None


@router.patch("/{sale_id}", response_model=SaleOut)
def set_customer(sale_id: int, data: SaleCustomerUpdate, request: Request):
    """Asigna o quita el cliente de una venta en borrador. El cajero suele
    enterarse de que la venta va fiada recien al cobrar, con las lineas ya
    cargadas."""
    try:
        sale = _service(request).set_customer(
            sale_id, customer_party_id=data.customer_party_id,
        )
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))
    return _to_sale_out(sale)


@router.post("/{sale_id}/items", response_model=SaleOut)
def add_item(sale_id: int, data: SaleItemCreate, request: Request):
    try:
        sale = _service(request).add_item(
            sale_id, item_id=data.item_id, quantity=data.quantity, variant_id=data.variant_id,
            unit_price=data.unit_price, discount_amount=data.discount_amount,
            price_list_id=data.price_list_id,
        )
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))
    except KeyError as exc:
        raise HTTPException(422, str(exc))
    return _to_sale_out(sale)


@router.delete("/{sale_id}/items/{index}", response_model=SaleOut)
def remove_item(sale_id: int, index: int, request: Request):
    """Quita una linea del borrador. `index` es la POSICION en la venta (0
    based), no un id: las lineas no tienen id estable -- ver
    SaleService.remove_item."""
    try:
        sale = _service(request).remove_item(sale_id, index=index)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except IndexError as exc:
        raise HTTPException(404, str(exc))
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))
    return _to_sale_out(sale)


@router.patch("/{sale_id}/items/{index}", response_model=SaleOut)
def update_item_quantity(sale_id: int, index: int, data: SaleItemQuantity, request: Request):
    """Corrige la cantidad de una linea ya cargada, sin borrarla y volver a
    agregarla: el cajero se equivoca tipeando la cantidad mucho mas seguido
    que escaneando el producto equivocado."""
    try:
        sale = _service(request).set_item_quantity(sale_id, index=index, quantity=data.quantity)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except IndexError as exc:
        raise HTTPException(404, str(exc))
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))
    return _to_sale_out(sale)


@router.post("/{sale_id}/confirm", response_model=SaleOut)
async def confirm_sale(sale_id: int, data: SaleConfirm, request: Request):
    # El gating por plan corre aca adentro, no gateando todo el router:
    # confirmar una venta (y su movimiento de caja, siempre) nunca depende
    # del plan -- solo pedir factura sobre esa venta puntual lo hace.
    # Mismo criterio que gestiolibra/medlibra (ver DECISIONS.md ADR-0XX de
    # este repo): el bloqueo tiene que fallar antes de tocar nada, no a
    # mitad de camino.
    if data.invoice and not get_module_repository(request).is_enabled("facturacion"):
        raise HTTPException(403, "modulo 'facturacion' no incluido en el plan actual")

    try:
        payments = tuple(
            SalePayment(
                method=pago.medio, amount=pago.monto,
                received_amount=pago.recibido, reference=pago.referencia,
            )
            for pago in data.pagos
        )
    except ValueError as exc:
        # Reglas del dominio: monto > 0, recibido >= monto.
        raise HTTPException(422, str(exc))

    if not payments and not data.medio_pago:
        raise HTTPException(422, "hay que indicar `medio_pago` o `pagos`")

    # Sin turno abierto no se cobra: una venta fuera de turno es plata que
    # queda afuera del arqueo, y despues no hay forma de explicar la
    # diferencia de caja. Se chequea ANTES de confirmar para no dejar la venta
    # a medio camino (mismo criterio que el gating por plan de arriba).
    turno = db_turnos.get_turno_activo_any()
    if turno is None:
        raise HTTPException(409, "no hay un turno de caja abierto")

    # Fiar necesita saber a quien: no se le puede fiar a consumidor final.
    # Se chequea ACA y no al registrar la deuda, por el mismo motivo que el
    # turno -- si fallara despues de confirmar, la venta quedaria cobrada sin
    # que la deuda exista en ningun lado.
    fia = any(p.method == MEDIO_CUENTA_CORRIENTE for p in payments) \
        or data.medio_pago == MEDIO_CUENTA_CORRIENTE
    if fia:
        try:
            borrador = _service(request).get(sale_id)
        except SaleNotFound:
            raise HTTPException(404, "sale not found")
        if borrador.customer_party_id is None:
            raise HTTPException(
                422,
                "una venta a cuenta corriente necesita un cliente: no se le "
                "puede fiar a consumidor final",
            )

    try:
        sale = _service(request).confirm(
            sale_id, location_id=data.location_id, payments=payments,
        )
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))

    referencia = f"sale-{sale.id}"
    factura = None
    if data.invoice:
        customer_billing = None
        if sale.customer_party_id is not None:
            customer_billing = CustomerService(request.app.state.conn).get_billing(sale.customer_party_id)
        factura = await billing.invoice_sale(customer_billing, sale, referencia)

    # Caja siempre se registra al confirmar una venta cobrada, factures o
    # no -- decision explicita del usuario (ver DECISIONS.md ADR-007):
    # el control de caja es independiente del tema fiscal.
    #
    # Un movimiento POR MEDIO, no uno por venta: en un cobro mixto la caja
    # tiene que poder decir cuanto entro en efectivo y cuanto por tarjeta,
    # que es justamente lo que se arquea. La referencia lleva el medio
    # (`sale-12-efectivo`) porque create_caja_movimiento es idempotente por
    # (referencia, factura_id) y con la misma referencia el segundo medio se
    # perderia en silencio.
    # Lo fiado es la excepcion: no entra a la caja porque no entro plata. Va
    # como deuda del cliente y el movimiento aparece recien cuando la paga
    # (ver services/cuenta_corriente.py). Sumarlo al arqueo dejaria al cajero
    # cuadrando contra un total que no esta en el cajon.
    cc = CuentaCorrienteService(request.app.state.conn)
    factura_id = factura["id"] if factura else None
    if sale.payments:
        for pago in sale.payments:
            if pago.method == MEDIO_CUENTA_CORRIENTE:
                cc.registrar_venta_fiada(
                    sale, pago.amount, f"{referencia}-{pago.method}",
                )
                continue
            billing.record_sale_payment(
                sale, pago.method, f"{referencia}-{pago.method}",
                factura_id=factura_id, monto=pago.amount, turno_id=turno["id"],
            )
    elif data.medio_pago == MEDIO_CUENTA_CORRIENTE:
        cc.registrar_venta_fiada(sale, sale.total, referencia)
    else:
        billing.record_sale_payment(
            sale, data.medio_pago, referencia, factura_id=factura_id, turno_id=turno["id"],
        )

    out = _to_sale_out(sale)
    out.factura = factura
    return out
