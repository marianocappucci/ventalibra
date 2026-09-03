"""Anular una venta y devolver productos.

Las dos piezas vienen de los motores: el stock y el estado de la venta de
`libracommerce.usecases.sales` (`cancel_sale`/`return_sale_items`), y el
dinero de `libracore.db.reversiones`. Lo que aporta VentaLibra es la
orquestación entre sus **dos bases**: la venta y el stock viven en el
archivo de LibraCommerce, y la caja y la deuda en el de LibraCore.

Por eso no hay una transacción única que cubra todo, y las dos partes son
idempotentes por separado: `cancel_sale` no repone dos veces y los
movimientos de caja no se duplican por referencia. Un reintento después de
una falla a mitad de camino completa lo que faltaba en vez de duplicar lo
que ya estaba.
"""
from datetime import UTC, date, datetime, timezone
from decimal import Decimal

from libracommerce.domain.sales import Sale
from libracommerce.usecases.sales import cancel_sale, return_sale_items
from libracore.db import reversiones
from libracore.db.core import Conexion

from ..commerce import repositorio
from .cuenta_corriente import MEDIO_CUENTA_CORRIENTE, CuentaCorrienteService


class DevolucionService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)
        self._cc = CuentaCorrienteService(conn)

    def anular(self, sale: Sale, usuario_id: int | None = None,
               turno_id: int | None = None) -> Sale:
        """Deshace una venta entera: repone el stock y saca de la caja lo que
        había entrado.

        El stock va primero. Si algo falla después, queda una venta anulada
        con el dinero sin revertir — visible y corregible reintentando — que
        es preferible a plata devuelta por una venta que sigue viva.
        """
        anulada = cancel_sale(self._repo, sale, datetime.now(UTC))

        cliente_id = None
        if sale.customer_party_id is not None:
            cliente_id = self._cc._cliente_cc(sale.customer_party_id)

        reversiones.revertir_cobro_venta(
            venta_id=sale.id,
            numero=sale.number,
            fecha=date.today().isoformat(),
            # `SalePayment` no tiene id propio: la posición alcanza para que
            # la referencia sea estable entre reintentos, que es lo único
            # que la idempotencia necesita.
            pagos=[
                {"id": i, "medio": pago.method, "monto": float(pago.amount)}
                for i, pago in enumerate(sale.payments)
            ],
            cliente_id=cliente_id,
            usuario_id=usuario_id,
            # Sin el turno, el egreso no entra al arqueo y el cajero cierra
            # contando plata que ya devolvió.
            turno_id=turno_id,
        )
        return anulada

    def devolver(
        self, sale: Sale, devoluciones: dict[int, Decimal], location_id: int,
        medio_pago: str = "efectivo", turno_id: int | None = None,
        usuario_id: int | None = None,
    ) -> tuple[Sale, Decimal]:
        """Devuelve algunas líneas y reintegra su importe.

        `medio_pago` es por dónde vuelve la plata, que no tiene por qué ser
        la misma por la que entró: se puede haber cobrado con tarjeta y
        devolver en efectivo.
        """
        devuelta, importe = return_sale_items(
            self._repo, sale, devoluciones, location_id, datetime.now(UTC),
        )

        cliente_id = None
        if sale.customer_party_id is not None:
            cliente_id = self._cc._cliente_cc(sale.customer_party_id)
        if medio_pago == MEDIO_CUENTA_CORRIENTE and cliente_id is None:
            raise ValueError(
                "para devolver a cuenta corriente la venta tiene que tener cliente"
            )

        reversiones.reintegrar_devolucion(
            venta_id=sale.id,
            numero=sale.number,
            fecha=date.today().isoformat(),
            monto=float(importe),
            medio_pago=medio_pago,
            # La referencia lleva las líneas devueltas: dos devoluciones
            # distintas de la misma venta son dos reintegros, no un
            # duplicado, pero repetir la misma no puede pagar dos veces.
            referencia=_referencia(sale.id, devoluciones),
            cliente_id=cliente_id,
            usuario_id=usuario_id,
            turno_id=turno_id,
        )
        return devuelta, importe


def _referencia(sale_id: int, devoluciones: dict[int, Decimal]) -> str:
    detalle = ",".join(f"{i}x{cantidad}" for i, cantidad in sorted(devoluciones.items()))
    return f"devolucion:venta:{sale_id}:{detalle}"
