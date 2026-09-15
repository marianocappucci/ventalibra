"""Cobrar deuda vieja y ver el saldo/movimientos de cuenta corriente.

Desde F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025, D3) fiar ya
no escribe un `cc_debito` explícito: la venta a cuenta corriente se registra
como cualquier otra, con un pago `ventas_pagos.medio='cuenta_corriente'`
(`libracommerce.erp.ventas.registrar_venta`/`crear_venta_directa`, montado en
`app/main.py`) -- ese pago ES la deuda. Lo que este módulo sigue resolviendo
es el puente entre las dos bases para LEER: el cliente de la venta es una
`party` de LibraCommerce y la cuenta corriente vive en LibraCore, así que el
saldo/movimientos/deudores cruzan por `clients.external_ref = party-<id>`
-- el origen `VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF` (libracore v1.100.0),
que reemplaza el cruce directo por id que asume `VENTAS_LIBRACOMMERCE`
(válido para Contalibra/Restolibra, donde `clients.id == parties.id`; NO acá,
ver ADR-025).

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
from libracore.db.core import Conexion
from libracore.recibos import emitir_recibo_cobranza

logger = logging.getLogger("ventalibra.cuenta_corriente")

#: Medio de pago que representa el fiado. Coincide con el que usan
#: Contalibra/Restolibra, que es lo que hace que el saldo se calcule igual.
MEDIO_CUENTA_CORRIENTE = "cuenta_corriente"

#: El cruce venta -> cliente de este producto: por `external_ref`, no por id
#: (ver docstring del módulo). Se declara acá y no se repite `db_cc.` en cada
#: llamada de abajo.
_ORIGEN = db_cc.VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF


class SinCliente(Exception):
    """No se puede fiar a nadie: hace falta saber a quién."""


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

    # ── puente entre las dos bases ───────────────────────────────────────

    def _cliente_cc(self, party_id: int) -> int:
        """El `clients.id` de LibraCore que le corresponde a este party.

        Se crea en la primera compra fiada y se reusa siempre. No espeja la
        cartera: sólo entra quien efectivamente fía.
        """
        row = self._conn.execute(
            "SELECT display_name, tax_id, email, phone FROM parties WHERE id = ?",
            (party_id,),
        ).fetchone()
        if row is None:
            raise SinCliente(f"no existe el cliente {party_id}")
        return db_clients.resolver_cliente_externo(
            f"party-{party_id}",
            row[0],
            cuit_dni=row[1] or "",
            email=row[2] or "",
            phone=row[3] or "",
        )

    # ── cobrar ───────────────────────────────────────────────────────────

    def registrar_cobranza(self, party_id: int, monto: Decimal, medio_pago: str,
                           concepto: str = "", referencia: str = "",
                           turno_id: int | None = None,
                           usuario_id: int | None = None) -> Cobranza:
        """Cobra deuda vieja. Esto SÍ es plata que entra: genera el
        movimiento de caja y queda dentro del turno abierto.

        Y emite el recibo, porque el cliente que vino a pagar está esperando
        el papel. Si la emisión fallara, **el cobro no se revierte**: perder
        el comprobante es molesto, perder el pago es un problema de plata.
        `recibo_id` vuelve en `None` y el botón de la pantalla lo reintenta,
        que es idempotente.
        """
        if monto <= 0:
            raise ValueError("el monto a cobrar debe ser mayor que cero")
        cliente_id = self._cliente_cc(party_id)
        caja_id = db_caja.get_default_caja_id()
        pago_id = db_cc.create_cc_pago(
            cliente_id, float(monto), date.today().isoformat(),
            concepto or "Pago a cuenta", referencia, medio_pago,
            caja_id, usuario_id,
        )
        db_caja.create_caja_movimiento(
            date.today().isoformat(), "ingreso",
            concepto or "Cobranza cuenta corriente", Decimal(str(monto)),
            referencia=referencia or f"cc-pago-{pago_id}",
            medio_pago=medio_pago, turno_id=turno_id,
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
        """Quiénes deben, con su saldo. Devuelve el `party_id` del cliente en
        VentaLibra, no el id interno de LibraCore, para que el consumidor no
        tenga que saber que hay dos bases."""
        salida = []
        for fila in db_cc.get_clientes_con_saldo_cc(origen=_ORIGEN):
            party_id = _party_id_de(fila.get("external_ref"))
            if party_id is None:
                # Un cliente sin `external_ref` no vino de VentaLibra: no
                # debería existir en esta base, pero si aparece no se lo
                # muestra en vez de romper la pantalla.
                continue
            salida.append({
                "party_id": party_id,
                "nombre": fila["name"],
                "saldo": Decimal(str(fila["saldo"])),
            })
        return salida


def _party_id_de(external_ref: str | None) -> int | None:
    if not external_ref or not external_ref.startswith("party-"):
        return None
    try:
        return int(external_ref.removeprefix("party-"))
    except ValueError:
        return None
