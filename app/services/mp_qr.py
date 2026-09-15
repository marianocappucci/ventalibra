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
from datetime import date
from decimal import Decimal

from libracore import config_manager, mp_api

logger = logging.getLogger(__name__)


class MpNoConfigurado(RuntimeError):
    """Faltan las credenciales del QR en Configuracion -> Mercado Pago."""


class MpError(RuntimeError):
    """MercadoPago rechazo la orden."""


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


def cobros_sin_venta(conn) -> list[dict]:
    """Cobros que MercadoPago acredito y cuya venta quedo **sin confirmar**.

    🔴 **Es el agujero que este producto declara en el docstring de arriba y no
    vigilaba nadie.** El orden es "primero la plata, despues la venta", asi que
    si el navegador se muere entre el poll y la confirmacion --se cierra la
    pestana, se corta la luz, el cajero atiende a otro-- la plata entro y la
    venta no quedo registrada.

    La orden aprobada se guarda justamente para eso, pero hasta hoy solo se la
    consultaba **por venta** (`orden_acreditada(conn, sale_id)`): la
    mitigacion funcionaba unicamente si alguien volvia a abrir ESE borrador. Si
    nadie lo abria, la plata estaba en MercadoPago, no estaba en la caja, y no
    habia forma de enterarse.

    Esto los busca al reves: desde el cobro hacia la venta. Ordenados por el
    mas viejo primero, que es el que mas urge.
    """
    filas = conn.execute(
        """SELECT o.id, o.sale_id, o.external_reference, o.amount, o.status,
                  o.payment_id, o.resolved_at, s.number
             FROM sale_mp_orders o
             JOIN sales s ON s.id = o.sale_id
            WHERE o.status = 'approved' AND s.status = 'draft'
            ORDER BY o.resolved_at, o.id"""
    ).fetchall()
    return [
        {
            "id": f[0], "sale_id": f[1], "external_reference": f[2],
            "amount": Decimal(str(f[3])), "status": f[4], "payment_id": f[5],
            "acreditado_el": f[6], "numero": f[7],
        }
        for f in filas
    ]


def _a_dict(fila) -> dict | None:
    if fila is None:
        return None
    return {
        "id": fila[0], "sale_id": fila[1], "external_reference": fila[2],
        "amount": Decimal(str(fila[3])), "status": fila[4], "payment_id": fila[5],
    }


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
