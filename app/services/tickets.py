"""Ticket impreso de una venta.

El generador de PDF térmico es de LibraCore (`libracore.ticket_generator`,
extraído de Contalibra el 2026-07-28). Acá está sólo el puente: pasar de una
`Sale` de LibraCommerce al dict que ese generador espera.
"""
from decimal import Decimal

from libracore.ticket_generator import generar_ticket_venta

#: Cómo se lee cada medio en el papel. Los que LibraCore ya conoce
#: (`efectivo`, `transferencia`) los traduce él; acá van los propios del POS.
_MEDIOS = {
    "tarjeta_debito": "Tarjeta de débito",
    "tarjeta_credito": "Tarjeta de crédito",
    "mercado_pago": "Mercado Pago",
    "cuenta_corriente": "Cuenta corriente",
}


def ticket_de_venta(sale, cliente_nombre: str = "") -> bytes:
    """PDF del ticket de una venta confirmada, listo para la ticketeadora."""
    return generar_ticket_venta({
        "id": sale.number,
        "fecha": sale.confirmed_at.strftime("%Y-%m-%d %H:%M") if sale.confirmed_at else "",
        "cliente_nombre": cliente_nombre or "Consumidor final",
        "items": [
            {
                "nombre": linea.description_snapshot,
                "cantidad": float(linea.quantity),
                "precio_unitario": float(linea.unit_price),
            }
            for linea in sale.items
        ],
        "descuento": float(sale.discount_total or Decimal("0")),
        "total": float(sale.total),
        "pagos": [
            {
                "medio": _MEDIOS.get(pago.method, pago.method),
                "monto": float(pago.amount),
            }
            for pago in sale.payments
        ],
    })
