"""Ticket impreso de una venta.

El generador de PDF térmico es de LibraCore (`libracore.ticket_generator`,
extraído de Contalibra el 2026-07-28). Acá está sólo el puente: pasar de una
`Sale` de LibraCommerce al dict que ese generador espera.
"""
from decimal import Decimal

from libracore import medios_pago
from libracore.ticket_generator import generar_ticket_venta

# 🔴 Aca habia un `_MEDIOS` propio con cuatro claves. Era una de las 28 copias
# del vocabulario de la familia, y la unica razon por la que existia --que
# LibraCore no conocia `tarjeta_debito` ni `tarjeta_credito`-- dejo de valer el
# 2026-08-24: ahora estan en la lista canonica.
#
# `medios_pago.label()` las cubre a las cuatro y a las grafias historicas que
# el motor todavia conoce (`tarjeta`, `debito`, `credito`, `cuenta corriente`),
# asi que un ticket REIMPRESO de una venta vieja sale bien igual.
#
# ⚠️ `mercado_pago` ya NO esta entre ellas: salio del motor en `v1.52.0` despues
# de migrar las filas que la tenian (cero en las 24 instancias, verificado). Si
# alguna vez aparece en el papel, no es un ticket viejo: es que algo volvio a
# escribirla. `label()` la devuelve cruda justamente para que se vea.
# Ver wiki/concepts/medios-de-pago-familia-libra.md.

def ticket_de_venta(sale, cliente_nombre: str = "") -> bytes:
    """PDF del ticket de una venta confirmada, listo para la ticketeadora."""
    return generar_ticket_venta({
        "id": sale.number,
        # 🔴 ISO a proposito, y NO es una fuga del formato visible: este string
        # es la ENTRADA que espera `libracore.ticket_generator`, que le aplica
        # `fmt_fecha` y termina imprimiendo `11-03-2026 14:30`. Verificado sobre
        # el texto del PDF generado, no leyendo el codigo -- leyendo solo este
        # archivo el strftime parece una fuga y no lo es.
        #
        # Cuidado al tocarlo: `fmt_fecha` da vuelta el ISO, pero con cualquier
        # otra forma es un pass-through. Con `%d-%m-%Y` el papel sale igual (por
        # casualidad, no porque este bien encaminado) y con un formato de barras
        # sale CON barras, que es lo que la convencion prohibe. El test
        # `tests/test_ticket_fecha_visible.py` afirma sobre el papel justamente
        # para agarrar ese caso.
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
                "medio": medios_pago.label(pago.method),
                "monto": float(pago.amount),
            }
            for pago in sale.payments
        ],
    })
