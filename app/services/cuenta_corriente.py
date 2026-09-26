"""Cobrar deuda vieja y ver el saldo/movimientos de cuenta corriente.

Desde F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025, D3) fiar ya
no escribe un `cc_debito` explícito: la venta a cuenta corriente se registra
como cualquier otra, con un pago `ventas_pagos.medio='cuenta_corriente'`
(`libracommerce.erp.ventas.registrar_venta`/`crear_venta_directa`, montado en
`app/main.py`) -- ese pago ES la deuda. Lo que este módulo sigue resolviendo
es leer desde las dos bases: el cliente de la venta es una `party` de
LibraCommerce y la cuenta corriente vive en LibraCore. Desde la `0004`
(2026-09-26) VentaLibra sigue la misma convención que Contalibra y
Restolibra: **`clients.id == parties.id`**, así que el saldo, los movimientos y
los deudores cruzan por id con el origen `VENTAS_LIBRACOMMERCE` del motor. Antes
cruzaban por `clients.external_ref = party-<id>` (`..._POR_EXTERNAL_REF`, ADR-025).

`cc_debitos` sigue existiendo y `get_cc_saldo` lo sigue sumando (para lo que
la migración `0003` no reclasificó como duplicado, y para cualquier deuda
que se cargue a mano desde el backoffice) -- no se retira la tabla ni el
mecanismo, sólo dejó de ser el camino de escritura de una venta fiada.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from libracore.db import caja as db_caja
from libracore.db import clients as db_clients
from libracore.db import cuenta_corriente as db_cc
from libracore.db import recibos as db_recibos
from libracore.db.core import Conexion
from libracore.recibos import emitir_recibo_cobranza

logger = logging.getLogger("ventalibra.cuenta_corriente")

#: Medio de pago que representa el fiado. Coincide con el que usan
#: Contalibra/Restolibra, que es lo que hace que el saldo se calcule igual.
MEDIO_CUENTA_CORRIENTE = "cuenta_corriente"

#: El cruce venta -> cliente: por id, igual que Contalibra y Restolibra (ver
#: docstring del módulo). Se declara acá y no se repite `db_cc.` en cada llamada.
_ORIGEN = db_cc.VENTAS_LIBRACOMMERCE


class SinCliente(Exception):
    """No se puede fiar a nadie: hace falta saber a quién."""


class SinPago(Exception):
    """No hay pago a cuenta con ese id."""


class SinMovimientoDeCaja(Exception):
    """El pago no tiene un movimiento de caja identificable por su tag."""


class Cobranza(NamedTuple):
    """Lo que dejó un cobro: el pago y su comprobante.

    `recibo_id` puede venir en `None` si la emisión falló — el cobro es
    válido igual, ver `registrar_cobranza`."""

    pago_id: int
    recibo_id: int | None


class CuentaCorrienteService:
    def __init__(self, conn: Conexion):
        # La conexión es la de LibraCommerce (clientes y ventas). LibraCore
        # abre la suya por su cuenta, contra el otro archivo.
        self._conn = conn

    # ── el cliente ───────────────────────────────────────────────────────

    def _cliente_cc(self, cliente_id: int) -> int:
        """El `clients.id` (que es también el id del party). Falla si no existe."""
        if db_clients.get_client(cliente_id) is None:
            raise SinCliente(f"no existe el cliente {cliente_id}")
        return cliente_id

    # ── cobrar ───────────────────────────────────────────────────────────

    def registrar_cobranza(self, party_id: int, monto: Decimal, medio_pago: str,
                           concepto: str = "", referencia: str = "",
                           turno_id: int | None = None,
                           usuario_id: int | None = None,
                           fecha: str | None = None,
                           caja_id: int | None = None) -> Cobranza:
        """Cobra deuda vieja. Esto SÍ es plata que entra: genera el
        movimiento de caja y queda dentro del turno abierto.

        Y emite el recibo, porque el cliente que vino a pagar está esperando
        el papel. Si la emisión fallara, **el cobro no se revierte**: perder
        el comprobante es molesto, perder el pago es un problema de plata.
        `recibo_id` vuelve en `None` y el botón de la pantalla lo reintenta,
        que es idempotente.

        `fecha` y `caja_id` son para el router del kit
        (`/api/cuenta-corriente`), que las trae del formulario; el router
        `/accounts/{party_id}/payments` no las pasa y queda el comportamiento
        de siempre: hoy, y la caja que `create_caja_movimiento` deduce del
        `turno_id` -- que es el arqueo de este producto.
        """
        if monto <= 0:
            raise ValueError("el monto a cobrar debe ser mayor que cero")
        cliente_id = self._cliente_cc(party_id)
        dia = fecha or date.today().isoformat()
        pago_id = db_cc.create_cc_pago(
            cliente_id, float(monto), dia,
            concepto or "Pago a cuenta", referencia, medio_pago,
            caja_id or db_caja.get_default_caja_id(), usuario_id,
        )
        db_caja.create_caja_movimiento(
            dia, "ingreso",
            concepto or "Cobranza cuenta corriente", Decimal(str(monto)),
            # 🔴 La referencia del movimiento es SIEMPRE el tag
            # `cc-pago-<id>`, no la que escribió el usuario (esa vive en
            # `cc_pagos`, visible en la cuenta y en el recibo). Es lo que
            # permite darle de baja al pago después: se busca el ingreso por
            # esta referencia y se ANULA (un movimiento de caja no se borra,
            # pedido del humano 2026-08-28). Si acá se colara la referencia
            # del usuario, la baja no encontraría el ingreso y el arqueo
            # quedaría contando plata que ya no existe.
            referencia=f"cc-pago-{pago_id}",
            medio_pago=medio_pago, turno_id=turno_id, caja_id=caja_id,
        )

        recibo_id = None
        try:
            recibo_id = emitir_recibo_cobranza(pago_id, usuario_id=usuario_id)["id"]
        except Exception:
            logger.exception("no se pudo emitir el recibo del cc_pago %s", pago_id)

        return Cobranza(pago_id=pago_id, recibo_id=recibo_id)

    # ── consultar ────────────────────────────────────────────────────────

    def saldo(self, party_id: int) -> Decimal:
        cliente_id = self._cliente_cc(party_id)
        return Decimal(str(db_cc.get_cc_saldo(cliente_id, origen=_ORIGEN)))

    def movimientos(self, party_id: int) -> list[dict]:
        cliente_id = self._cliente_cc(party_id)
        return db_cc.get_cc_movimientos(cliente_id, origen=_ORIGEN)

    def deudores(self) -> list[dict]:
        """Quiénes deben, con su saldo. `party_id` es el id del cliente (el mismo
        en `clients` y en `parties`)."""
        salida = []
        for fila in db_cc.get_clientes_con_saldo_cc(origen=_ORIGEN):
            salida.append({
                "party_id": fila["id"],
                "nombre": fila["name"],
                "saldo": Decimal(str(fila["saldo"])),
            })
        return salida

    # ── contrato del kit (`/api/cuenta-corriente`) ────────────────────────
    #
    # Las pantallas del kit (`libra-ui/comercio/CuentaCorriente*`, las mismas
    # que montan Contalibra y Restolibra) consumen NÚMEROS: comparan
    # `saldo > 0` y suman montos en el navegador. Así que acá todo sale como
    # `float`, no como `Decimal`-string como en el router `/accounts`, donde
    # la pantalla propia convertía con `Number()` al mostrar.

    def listado_kit(self) -> dict:
        """Lo que `GET /api/cuenta-corriente` del kit espera: `clientes` con
        el mismo formato que `get_clientes_con_saldo_cc` del motor (`id`,
        `name`, `cuit_dni`, `saldo`) y `total_deuda` para el cartel. La clave
        `id` es el id del cliente, que es lo que el kit manda a la pantalla
        detalle."""
        clientes = []
        total_deuda = 0.0
        for fila in db_cc.get_clientes_con_saldo_cc(origen=_ORIGEN):
            saldo = float(fila["saldo"])
            clientes.append({
                "id": fila["id"],
                "name": fila["name"],
                "cuit_dni": fila.get("cuit_dni") or "",
                "saldo": saldo,
            })
            if saldo > 0:
                total_deuda += saldo
        return {"clientes": clientes, "total_deuda": total_deuda}

    def detalle_kit(self, party_id: int) -> dict:
        """Lo que `GET /api/cuenta-corriente/{id}` del kit espera: el cliente
        con los campos que muestra la pantalla, los movimientos crudos del
        motor (que ya traen `usuario_nombre`, `venta_id`, `factura_id`...) y
        el saldo."""
        cliente_id = self._cliente_cc(party_id)
        fila = db_clients.get_client(cliente_id)
        return {
            "cliente": {
                "id": cliente_id,
                "name": fila["name"],
                "cuit_dni": fila.get("cuit_dni") or "",
            },
            "movimientos": db_cc.get_cc_movimientos(cliente_id, origen=_ORIGEN),
            "saldo": float(db_cc.get_cc_saldo(cliente_id, origen=_ORIGEN)),
        }

    def eliminar_pago(self, pago_id: int, usuario_id: int | None = None) -> None:
        """Da de baja un pago a cuenta (el kit lo ofrece sólo a un admin).

        🔴 Tres pasos, en este orden:
        1. se **anulan** los recibos del pago (no se borran: el número quedó
           consumido y el papel pudo haber salido);
        2. se **anula** el movimiento de caja del ingreso, buscándolo por la
           referencia `cc-pago-<id>` que `registrar_cobranza` graba siempre.
           En este producto un movimiento de caja no se borra (pedido del
           humano, 2026-08-28): anulado, la fila queda para auditar y sale de
           los totales del arqueo;
        3. recién entonces se borra el pago.

        Los pagos creados antes del tag (los que colocaban la referencia del
        usuario en el movimiento) no se pueden identificar: se rechazan con
        `SinMovimientoDeCaja` en vez de dejar un ingreso huérfano en el
        arqueo.
        """
        pago = db_cc.get_cc_pago(pago_id)
        if pago is None:
            raise SinPago(f"no existe el pago {pago_id}")

        for recibo in db_recibos.get_recibos_de_origen(db_recibos.ORIGEN_CC_PAGO, pago_id):
            db_recibos.anular_recibo(
                recibo["id"], motivo="Se elimino el pago que lo origino",
                usuario_id=usuario_id,
            )

        tag = f"cc-pago-{pago_id}"
        movimientos = [
            m for m in db_caja.get_caja_movimientos(
                desde=pago["fecha"], hasta=pago["fecha"], limit=500)
            if m["referencia"] == tag
        ]
        if not movimientos:
            raise SinMovimientoDeCaja(
                f"el pago {pago_id} no tiene un movimiento de caja "
                "identificable: no se da de baja automáticamente"
            )
        for mov in movimientos:
            db_caja.anular_caja_movimiento(mov["id"])

        db_cc.delete_cc_pago(pago_id)

