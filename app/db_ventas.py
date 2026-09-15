"""Shim: las ventas del punto de venta viven en `libracommerce.erp.ventas`
desde F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025).

Mismo patrón que `contalibra/app/db_ventas.py` y `restolibra/app/database.py`:
este módulo abre la conexión, la cierra y le pasa los ganchos y las opciones
que son de este producto (`app/ganchos.py`).

🔴 **Siempre `libracore.db.core.get_connection` -- nunca `app.state.conn`.**
Las factories son por-request, como el resto de la familia; `app/db.py`
sigue existiendo para lo que no migró todavía (catálogo, stock, compras),
pero las ventas nuevas no pasan por esa conexión única.

🔑 `caja_con_turno=True` en los tres lugares que tocan caja
(`crear_venta_directa` en `app/routers/sales_erp.py` -- ver `main.py`,
`anular_venta`, `acreditar_pago_qr`): este producto arquea sumando
`caja_movimientos` por `turno_id` (`app/routers/shifts.py`,
`get_resumen_turno_caja`), a diferencia de Contalibra/Restolibra que arquean
por `venta_links`. Sin esto el arqueo por turno daría siempre cero -- medido
en el relevamiento de F0/F1 del plan (`wiki/analyses/plan-ventalibra-a-libracommerce.md`).
"""
from libracommerce.erp import ventas as _v
from libracore.db.core import get_connection
from libracore.venta_facturacion import PuertoDeVentas

from app.ganchos import GANCHOS


def get_venta(vid: int) -> dict | None:
    with get_connection() as conn:
        return _v.obtener_venta(conn, vid)


def anular_venta(vid: int, usuario_id: int | None = None) -> None:
    with get_connection() as conn:
        try:
            _v.anular_venta(conn, vid, usuario_id=usuario_id, hooks=GANCHOS, caja_con_turno=True)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def devolver_items(vid: int, devoluciones: dict[int, float], deposito_id: int,
                   medio_pago: str = "efectivo", usuario_id: int | None = None) -> dict:
    with get_connection() as conn:
        try:
            resultado = _v.devolver_items(
                conn, vid, devoluciones, deposito_id, medio_pago=medio_pago,
                usuario_id=usuario_id, hooks=GANCHOS, caja_con_turno=True,
            )
            conn.commit()
            return resultado
        except Exception:
            conn.rollback()
            raise


def _escribir(operacion, *args):
    with get_connection() as conn:
        resultado = operacion(conn, *args)
        conn.commit()
        return resultado


def vincular_venta_factura(vid: int, factura_id: int):
    _escribir(_v.vincular_factura, vid, factura_id)


def set_venta_mp_order(venta_id: int, mp_order_id: str) -> None:
    _escribir(_v.set_orden_mp, venta_id, mp_order_id)


def set_venta_mp_payment(venta_id: int, mp_payment_id: str) -> None:
    _escribir(_v.set_pago_mp, venta_id, mp_payment_id)


def add_venta_pago_referencia_mp(venta_id: int, payment_id: str) -> None:
    _escribir(_v.sellar_referencia_mp, venta_id, payment_id)


def vincular_cobros_de_venta(numero: str, factura_id: int) -> int:
    return _escribir(_v.vincular_cobros_de_venta, numero, factura_id)


def acreditar_pago_qr(venta_id: int, payment_id: str, usuario_id: int | None = None) -> bool:
    with get_connection() as conn:
        try:
            acredito = _v.acreditar_pago_qr(
                conn, venta_id, payment_id, usuario_id=usuario_id, hooks=GANCHOS, caja_con_turno=True,
            )
            conn.commit()
            return acredito
        except Exception:
            conn.rollback()
            raise


#: Cómo llega `libracore.venta_facturacion` / `ventas_cobro_router` a las
#: ventas de este producto. Sin `alicuota_de`: el relevamiento de D6 del plan
#: confirmó que el IVA no cambia (siempre 21% default, `IVA_RATE_DEFAULT`) --
#: no hay alícuota propia que traer, a diferencia de Contalibra (que sí recibe
#: ventas con alícuota propia desde otro producto, `ventas_origen_externo`).
PUERTO = PuertoDeVentas(
    obtener=get_venta,
    vincular_factura=vincular_venta_factura,
    vincular_cobros=vincular_cobros_de_venta,
    set_pago_mp=set_venta_mp_payment,
    acreditar=acreditar_pago_qr,
    sellar_referencia_mp=add_venta_pago_referencia_mp,
    set_orden_mp=set_venta_mp_order,
)
