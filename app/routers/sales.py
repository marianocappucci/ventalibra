from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import get_current_user
from ..modules_gate import get_module_repository
from ..services import billing
from ..services.cuenta_corriente import (
    MEDIO_CUENTA_CORRIENTE,
    CuentaCorrienteService,
    SinCliente,
)
from ..services.customers import CustomerService
from ..services.devoluciones import DevolucionService
from ..services import mp_qr
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


#: Los medios que se cobran escaneando el QR de la caja.
#:
#: 🔴 **Sigue con las dos grafias, y ya no por la misma razon.** Este POS
#: escribia `mercado_pago` con guion bajo; desde el 2026-08-24 escribe
#: `mercadopago`, que es la clave de la familia, y `app/normalizacion_medios.py`
#: pasa a la canonica cualquier fila vieja en cada arranque (ADR-024). O sea que
#: la grafia vieja ya no entra ni queda en esta base.
#:
#: La de aca abajo se conserva igual porque este `frozenset` es un ESPEJO de
#: `libracore.medios_pago.MEDIOS_ELECTRONICOS`, que todavia la lista para el
#: resto de la familia; sacarla de un lado solo dejaria a los dos diciendo
#: cosas distintas. Se va cuando se vaya de alla -- el ultimo paso del trabajo,
#: con el pin de LibraCore subido y despues de verificar que no queden filas en
#: ninguna instancia.
MEDIOS_QR = frozenset({"mercado_pago", "mercadopago"})


def _referencia_del_pago(pago: "PaymentIn", orden_qr: dict | None) -> str:
    """La referencia que se guarda en la linea de pago de la venta.

    Sella el `payment_id` de MercadoPago sobre la linea que se cobro por QR:
    sin eso el pago queda acreditado del lado de MercadoPago y no hay forma de
    saber, mirando la venta, cual de los pagos del dia fue.

    Respeta lo que mande el POS si ya viene con algo: la referencia es un campo
    libre --el numero de lote de la tarjeta, el comprobante de la
    transferencia-- y pisarlo perderia ese dato.
    """
    if pago.referencia:
        return pago.referencia
    if orden_qr is not None and pago.medio in MEDIOS_QR and orden_qr["payment_id"]:
        return f"mp-{orden_qr['payment_id']}"
    return ""


@router.post("", response_model=SaleOut)
def create_sale(data: SaleCreate, request: Request):
    sale = _service(request).create_draft(
        branch_id=data.branch_id, register_id=data.register_id,
        customer_party_id=data.customer_party_id,
    )
    return _to_sale_out(sale)


class SaleListItem(BaseModel):
    id: int
    number: str
    status: str
    total: Decimal
    confirmed_at: str | None
    cliente: str


@router.get("", response_model=list[SaleListItem])
def list_sales(request: Request, limit: int = 50, search: str = ""):
    """Ultimas ventas confirmadas. Es lo que permite encontrar la venta de
    ayer para anularla o devolver algo -- antes no habia forma."""
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
    """Si este mostrador puede cobrar por QR, y si eso factura solo.

    Lo lee el POS para no ofrecer un boton que unicamente puede fallar. **No
    devuelve ninguna credencial**: son tres booleanos colapsados en uno, y este
    router lo puede leer el cajero -- la pantalla que las carga es admin.

    La ruta va antes que `/{sale_id}` en el archivo por prolijidad, pero no
    dependen del orden: `mp/estado` son dos segmentos y `/{sale_id}` uno solo.
    """
    return MpDisponible(
        disponible=mp_qr.esta_configurado(),
        auto_facturar=mp_qr.auto_facturar_prendida()
        and get_module_repository(request).is_enabled("facturacion"),
    )


class MpOrdenOut(BaseModel):
    external_reference: str
    amount: float


@router.post("/{sale_id}/mp-qr", response_model=MpOrdenOut)
async def poner_en_el_qr(sale_id: int, request: Request):
    """Pone el total de este borrador a cobrar en el QR de la caja.

    No devuelve ninguna imagen: el QR es el cartel impreso del mostrador y no
    cambia nunca; lo que cambia es cuanto cobra. Ver `services/mp_qr.py`.
    """
    try:
        sale = _service(request).get(sale_id)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    try:
        orden = await mp_qr.poner_en_el_qr(request.app.state.conn, sale)
    except mp_qr.MpNoConfigurado as exc:
        raise HTTPException(400, str(exc))
    except mp_qr.VentaYaCobrada as exc:
        raise HTTPException(409, str(exc))
    except mp_qr.MpError as exc:
        # 502 y no 500: el que fallo es MercadoPago, y el mensaje lleva su
        # status y su cuerpo adentro -- que es lo unico que le dice al operador
        # si se equivoco de POS ID o si el problema es de ellos.
        raise HTTPException(502, str(exc))
    return MpOrdenOut(**orden)


@router.delete("/{sale_id}/mp-qr", status_code=204)
async def bajar_del_qr(sale_id: int, request: Request):
    """Saca del QR la orden de esta venta: el cartel queda sin nada que cobrar.

    🔴 **Sin esto el proximo cliente que escanee paga la venta anterior.** Es
    lo que hay que llamar cuando el cajero cancela el cobro, y el POS lo hace
    tambien al cerrar el dialogo. Idempotente: sin orden pendiente no hace
    nada.
    """
    await mp_qr.bajar_del_qr(request.app.state.conn, sale_id)


class MpEstadoOut(BaseModel):
    #: `approved`, `pending`, `sin_orden`, o el estado crudo de MercadoPago
    #: (`rejected`, `cancelled`, `in_process`).
    status: str
    payment_id: str | None = None


@router.get("/{sale_id}/mp-status", response_model=MpEstadoOut)
async def estado_del_qr(sale_id: int, request: Request):
    """Si el QR de esta venta ya se pago. Lo pollea el POS cada 3 segundos."""
    try:
        estado = await mp_qr.estado_del_cobro(request.app.state.conn, sale_id)
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


class DevolucionLinea(BaseModel):
    #: Posicion de la linea en la venta, no un id: SaleItem no tiene id
    #: propio (ver SaleService.remove_item).
    index: int
    quantity: Decimal


class DevolucionIn(BaseModel):
    lineas: list[DevolucionLinea]
    location_id: int
    #: Por donde vuelve la plata, que no tiene por que ser por donde entro.
    medio_pago: str = "efectivo"


@router.post("/{sale_id}/cancel", response_model=SaleOut)
def cancel_sale_endpoint(sale_id: int, request: Request,
                         user: dict = Depends(get_current_user)):
    """Anula una venta confirmada: repone el stock y saca de la caja lo
    cobrado. Si estaba fiada, le baja la deuda al cliente."""
    try:
        sale = _service(request).get(sale_id)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")

    try:
        anulada = DevolucionService(request.app.state.conn).anular(
            sale,
            usuario_id=int(user["id"]) if user else None,
            # Si hay turno abierto, el egreso entra en su arqueo. Anular sin
            # turno se permite -- la venta hay que poder deshacerla igual --
            # y el movimiento queda sin turno, como cualquier otro de caja
            # registrado fuera de uno.
            turno_id=(db_turnos.get_turno_activo_any() or {}).get("id"),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return _to_sale_out(anulada)


@router.post("/{sale_id}/returns", response_model=SaleOut)
def return_items(sale_id: int, data: DevolucionIn, request: Request,
                 user: dict = Depends(get_current_user)):
    """Devuelve algunas lineas de una venta y reintegra su importe."""
    if not data.lineas:
        raise HTTPException(422, "hay que indicar que lineas se devuelven")

    # Devolver plata es mover la caja: sin turno abierto el reintegro
    # quedaria afuera del arqueo, igual que un cobro.
    turno = db_turnos.get_turno_activo_any()
    if turno is None and data.medio_pago != MEDIO_CUENTA_CORRIENTE:
        raise HTTPException(409, "no hay un turno de caja abierto")

    try:
        sale = _service(request).get(sale_id)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")

    try:
        devuelta, _importe = DevolucionService(request.app.state.conn).devolver(
            sale,
            {linea.index: linea.quantity for linea in data.lineas},
            data.location_id,
            medio_pago=data.medio_pago,
            turno_id=turno["id"] if turno else None,
            usuario_id=int(user["id"]) if user else None,
        )
    except ValueError as exc:
        # Devolver mas de lo vendido, una linea que no existe, un servicio
        # suelto: todos son pedidos invalidos, no fallas del servidor.
        raise HTTPException(422, str(exc))
    return _to_sale_out(devuelta)


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
    puede_facturar = get_module_repository(request).is_enabled("facturacion")
    if data.invoice and not puede_facturar:
        raise HTTPException(403, "modulo 'facturacion' no incluido en el plan actual")

    # El cobro por QR que ya se acredito, si esta venta se cobro asi. De aca
    # salen las dos cosas que el QR le agrega a un confirm normal: la
    # referencia del pago y la factura automatica.
    orden_qr = mp_qr.orden_acreditada(request.app.state.conn, sale_id)

    # 🔑 **La automatica se decide en el backend, no en el checkbox.** Si la
    # resolviera el POS, una instancia con la automatica prendida dependeria de
    # que la pantalla se acuerde de mandar `invoice: true` -- y cualquier otro
    # cliente de la API (el backoffice, un script) cobraria por QR sin
    # facturar, sin que nada avise.
    #
    # Se exige `puede_facturar`: sin el modulo en el plan, la automatica no
    # convierte el cobro en un 403. La venta se confirma igual y queda sin
    # comprobante, que es lo que el plan dice.
    facturar = data.invoice
    if orden_qr is not None and puede_facturar and mp_qr.auto_facturar_prendida():
        facturar = True

    try:
        payments = tuple(
            SalePayment(
                method=pago.medio, amount=pago.monto,
                received_amount=pago.recibido,
                reference=_referencia_del_pago(pago, orden_qr),
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
    if facturar:
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
