"""Cobro con QR de MercadoPago en el mostrador, y la factura que sale sola.

Es el mismo mecanismo que Contalibra tiene en produccion desde el 2026-08-19
(`app/web/routers/ventas.py`), portado a la venta de LibraCommerce. El cliente
REST no se reimplementa: sale de `libracore.mp_api`, que ya lo comparten los
productos de la familia.

## El QR es el cartel impreso de la caja, no una imagen

🔑 **Nada de esto devuelve un QR para mostrar en pantalla.** Es el modelo de
**QR fijo por punto de venta**: el cartel del mostrador no cambia nunca; lo que
esta llamada cambia es *cuanto cobra* cuando alguien lo escanea. Un endpoint
que devolviera una imagen estaria prometiendo otro producto de MercadoPago
(el QR dinamico por venta, que es otra API).

## Por que el poll y no el webhook

Contalibra tiene los dos caminos y el que **funciona** es el poll: en la
instancia real del cliente el webhook no llego nunca (0 POST a
`/webhooks/mercadopago` en el log, contra 5 a `mp-qr`), y hasta el 2026-08-20
era justamente el unico camino que facturaba -- la venta quedaba cobrada y
"Sin facturar".

Aca no hay webhook a proposito, y no es una simplificacion: en este producto la
venta se **confirma despues** de que el pago se acredita (ver el flujo de abajo),
asi que en el momento en que MercadoPago avisaria todavia no hay ninguna venta
confirmada contra la cual acreditar nada. El webhook no tendria que hacer.

## El orden: primero la plata, despues la venta

Contalibra confirma la venta y despues cobra el QR, y eso deja una ventana en
la que hay una venta registrada como cobrada que en realidad nadie pago. Aca es
al reves:

1. El cajero arma el borrador y elige "Mercado Pago" -> `POST /sales/{id}/mp-qr`
   pone el total del borrador en el QR de la caja.
2. El POS pollea `GET /sales/{id}/mp-status` hasta que MercadoPago dice
   `approved`.
3. Recien ahi el POS confirma la venta, que registra caja y --si la instancia
   tiene la automatica prendida-- emite la factura.

El agujero se invierte: si el navegador se muere entre el paso 2 y el 3, la
plata entro y la venta no quedo registrada. Por eso la orden aprobada queda
guardada en `sale_mp_orders` con su `payment_id`: el borrador sigue existiendo
y volver a abrirlo muestra el pago ya acreditado, en vez de perderse.
"""
import logging
import secrets
from datetime import date
from decimal import Decimal

from libracore import config_manager, mp_api

logger = logging.getLogger(__name__)


class MpNoConfigurado(RuntimeError):
    """Faltan las credenciales del QR en Configuracion -> Mercado Pago."""


class MpError(RuntimeError):
    """MercadoPago rechazo la orden."""


class VentaYaCobrada(RuntimeError):
    """Esa venta ya tiene un pago de QR acreditado."""


#: El toggle de la factura automatica. No esta en los DEFAULTS de
#: `libracore.config_manager` --son los genericos de la familia-- asi que viaja
#: como `extra_defaults`, que es el mecanismo que el motor expone para esto.
#: Mismo nombre de clave que Contalibra, para que las dos instancias se lean
#: igual.
EXTRA_DEFAULTS = {"mp_auto_facturar_ventas": False}


def cargar_config() -> dict:
    return config_manager.load(EXTRA_DEFAULTS)


def guardar_config(cfg: dict) -> None:
    config_manager.save(cfg, EXTRA_DEFAULTS)


def credenciales(cfg: dict | None = None) -> tuple[str, str, str]:
    """Access token, user id y pos id. Levanta si falta alguno.

    🔑 Los tres, no solo el token: `crear_orden_qr` mete el `user_id`
    (el collector id de la cuenta) y el `pos_id` (el **external_id** de la
    caja, no su nombre ni su id numerico) en la URL. Con uno vacio la URL se
    arma igual y MercadoPago contesta 404 -- un error que no dice que falta.
    """
    cfg = cfg if cfg is not None else cargar_config()
    token = (cfg.get("mp_access_token") or "").strip()
    user_id = (cfg.get("mp_user_id") or "").strip()
    pos_id = (cfg.get("mp_pos_id") or "").strip()
    if not token or not user_id or not pos_id:
        raise MpNoConfigurado(
            "Falta configurar el Access Token, el User ID y el POS ID de "
            "MercadoPago en Configuracion -> Mercado Pago."
        )
    return token, user_id, pos_id


def esta_configurado() -> bool:
    """Si esta instancia puede cobrar por QR. Lo lee el POS para no ofrecer un
    boton que solo puede fallar."""
    try:
        credenciales()
    except MpNoConfigurado:
        return False
    return True


def auto_facturar_prendida(cfg: dict | None = None) -> bool:
    cfg = cfg if cfg is not None else cargar_config()
    return bool(cfg.get("mp_auto_facturar_ventas"))


# ── La orden en la caja ──────────────────────────────────────────────────


def nueva_referencia(sale_id: int) -> str:
    """La referencia externa que viaja a MercadoPago y vuelve con el pago.

    Lleva el id de la venta **y** un sufijo aleatorio. El id solo no alcanza:
    un pago rechazado se reintenta, y un pago viejo de ese mismo borrador
    volveria como aprobado en la busqueda del intento nuevo -- por otra plata,
    si entre medio se agrego una linea.
    """
    return f"vl-{sale_id}-{secrets.token_hex(6)}"


def orden_vigente(conn, sale_id: int) -> dict | None:
    """El ultimo intento de esta venta, aprobado o no."""
    fila = conn.execute(
        """SELECT id, sale_id, external_reference, amount, status, payment_id
             FROM sale_mp_orders
            WHERE sale_id = ?
            ORDER BY id DESC
            LIMIT 1""",
        (sale_id,),
    ).fetchone()
    return _a_dict(fila)


def orden_acreditada(conn, sale_id: int) -> dict | None:
    """El intento aprobado de esta venta, si lo hay.

    Se busca por `status` y no "el ultimo": el aprobado puede no ser el ultimo
    si despues alguien volvio a apretar el boton.
    """
    fila = conn.execute(
        """SELECT id, sale_id, external_reference, amount, status, payment_id
             FROM sale_mp_orders
            WHERE sale_id = ? AND status = 'approved'
            ORDER BY id DESC
            LIMIT 1""",
        (sale_id,),
    ).fetchone()
    return _a_dict(fila)


def _a_dict(fila) -> dict | None:
    if fila is None:
        return None
    return {
        "id": fila[0], "sale_id": fila[1], "external_reference": fila[2],
        "amount": Decimal(str(fila[3])), "status": fila[4], "payment_id": fila[5],
    }


async def poner_en_el_qr(conn, sale) -> dict:
    """Pone el total de esta venta a cobrar en el QR de la caja.

    Levanta `VentaYaCobrada` si ya hay un pago acreditado: volver a poner el
    monto rotaria la referencia y dejaria el pago ya cobrado sin nada que lo
    ate a la venta.
    """
    if orden_acreditada(conn, sale.id) is not None:
        raise VentaYaCobrada(f"La venta {sale.id} ya tiene un pago de QR acreditado.")

    total = Decimal(str(sale.total))
    if total <= 0:
        raise MpError("No hay nada que cobrar: el total de la venta es cero.")

    token, user_id, pos_id = credenciales()
    referencia = nueva_referencia(sale.id)

    try:
        await mp_api.crear_orden_qr(
            user_id=user_id,
            pos_id=pos_id,
            access_token=token,
            external_reference=referencia,
            titulo=f"Venta {sale.number}",
            items=_items_para_mp(sale),
            total=float(total),
        )
    except RuntimeError as exc:
        # `crear_orden_qr` levanta RuntimeError con el status y el cuerpo de
        # MercadoPago adentro. Se propaga tal cual: el 404 de un POS ID que no
        # existe es lo unico que le dice al operador que se equivoco de dato.
        raise MpError(str(exc)) from exc

    conn.execute(
        """INSERT INTO sale_mp_orders (sale_id, external_reference, amount, status)
           VALUES (?, ?, ?, 'pending')""",
        (sale.id, referencia, float(total)),
    )
    conn.commit()
    logger.info("Venta %s puesta en el QR de la caja por %s (ref %s)",
                sale.id, total, referencia)
    return {"external_reference": referencia, "amount": float(total)}


def _items_para_mp(sale) -> list[dict]:
    """Las lineas de la venta en la forma que espera `crear_orden_qr`.

    Van los precios FINALES, no los netos: es lo que el cliente ve en la app de
    MercadoPago al escanear y tiene que coincidir con lo que dice el visor de
    la caja. El desglose de IVA es cosa de la factura, no del cobro.
    """
    return [
        {
            "producto_id": item.item_id,
            "nombre": item.description_snapshot,
            "qty": float(item.quantity),
            "precio": float(item.unit_price),
            "subtotal": float(item.line_total),
        }
        for item in sale.items
    ]


async def bajar_del_qr(conn, sale_id: int) -> bool:
    """Saca la orden del QR: el cartel de la caja queda sin nada que cobrar.

    🔴 **Es lo que evita que el proximo cliente pague la venta anterior.** Una
    orden que queda puesta sigue cobrando ese monto a quien escanee, aunque el
    cajero haya cancelado la venta hace media hora. Contalibra no llama nunca a
    `eliminar_orden_qr` -- no tiene call sites en todo el repo -- y por eso
    depende de que el cliente siguiente no escanee antes de que el cajero
    cargue la venta nueva.

    Devuelve si habia algo que bajar. No levanta si falta configuracion: se
    llama al cancelar, y hacer fallar una cancelacion por eso seria peor.
    """
    orden = orden_vigente(conn, sale_id)
    # `pending` y no "distinto de approved": una orden ya cancelada tampoco se
    # vuelve a bajar. El POS llama a esto al cerrar el dialogo, asi que dos
    # bajas seguidas son el caso normal y no un error -- pero cada una es un
    # DELETE contra MercadoPago.
    if orden is None or orden["status"] != "pending":
        return False
    try:
        token, user_id, pos_id = credenciales()
    except MpNoConfigurado:
        return False
    await mp_api.eliminar_orden_qr(user_id, pos_id, token)
    conn.execute(
        "UPDATE sale_mp_orders SET status = 'cancelled', resolved_at = ? WHERE id = ?",
        (date.today().isoformat(), orden["id"]),
    )
    conn.commit()
    return True


async def estado_del_cobro(conn, sale_id: int) -> dict:
    """Si el QR de esta venta ya se pago. Sella el `payment_id` cuando si.

    Es un GET con efectos, igual que el de Contalibra: sin sellar la
    referencia, el pago queda acreditado en MercadoPago y sin nada que lo ate a
    la venta. Sellar dos veces no hace nada -- el `UPDATE` es por id y el
    segundo poll ya entra por la rama de arriba.
    """
    acreditada = orden_acreditada(conn, sale_id)
    if acreditada is not None:
        return {"status": "approved", "payment_id": acreditada["payment_id"]}

    orden = orden_vigente(conn, sale_id)
    if orden is None:
        return {"status": "sin_orden", "payment_id": None}

    token, _user_id, _pos_id = credenciales()
    try:
        pago = await mp_api.buscar_pago_por_referencia(orden["external_reference"], token)
    except Exception as exc:
        raise MpError(f"No se pudo consultar el pago en MercadoPago: {exc}") from exc

    if not pago:
        return {"status": "pending", "payment_id": None}

    estado = pago.get("status", "pending")
    if estado != "approved":
        return {"status": estado, "payment_id": None}

    payment_id = str(pago["id"])
    conn.execute(
        """UPDATE sale_mp_orders
              SET status = 'approved', payment_id = ?, resolved_at = ?
            WHERE id = ?""",
        (payment_id, date.today().isoformat(), orden["id"]),
    )
    conn.commit()
    logger.info("Venta %s acreditada por QR, payment_id=%s", sale_id, payment_id)
    return {"status": "approved", "payment_id": payment_id}
