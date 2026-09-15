"""Ticket impreso de una venta.

El generador de PDF térmico es de LibraCore (`libracore.ticket_generator`,
extraído de Contalibra el 2026-07-28). Acá está sólo el puente: pasar de una
`Sale` de LibraCommerce al dict que ese generador espera.
"""
from datetime import UTC, timedelta, timezone
from decimal import Decimal

from libracore import medios_pago
from libracore.ticket_generator import generar_ticket_venta

#: America/Argentina/Buenos_Aires, UTC-3 fijo -- mismo criterio que
#: `libracore.db.core._ar_now()` y `app/services/sales.py`.
_AR = timezone(timedelta(hours=-3))

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
    fecha = ""
    if sale.confirmed_at:
        dt = sale.confirmed_at
        # 🔴 Naive = UTC real (así lo escribía el `confirm_sale` legado con
        # `datetime.now(UTC)`, y así lo sigue leyendo `libracore.pdf_generator.
        # fecha_de_documento` para cualquier otro comprobante de la familia) --
        # NUNCA `astimezone()` sobre un naive: Python lo toma como hora del
        # sistema, no como UTC, y da un resultado distinto según dónde corra
        # el proceso. Una venta nueva ya llega aware (F3, `app/services/
        # sales.py::_con_pagos_y_fecha`, etiquetada `-03:00` de verdad).
        dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        fecha = dt.astimezone(_AR).strftime("%Y-%m-%d %H:%M")
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
        #
        # 🔴 Y va convertido a hora de Argentina ANTES del strftime -- no es lo
        # mismo que la entrada ISO de arriba: `fmt_fecha`/`fecha_de_documento`
        # (`libracore.pdf_generator`) no convierten ninguna zona, sólo reordenan
        # o interpretan texto sin zona como UTC. El MISMO string se usa para lo
        # IMPRESO y para sellar `/CreationDate` (ver `fijar_fecha_documento`),
        # así que no se puede tener las dos cosas "bien" a la vez -- manda lo
        # impreso, que es lo que ve el cliente; el sello sólo tiene que ser
        # determinístico para que reimprimir dé el mismo PDF (ver
        # `test_el_ticket_se_puede_reimprimir`).
        "fecha": fecha,
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
