"""Si esta instancia puede cobrar por QR de MercadoPago, y si eso factura sola.

🔴 **Hasta F4 del plan post-P9 (2026-09-15, DECISIONS.md ADR-025) este módulo
además implementaba el cobro por QR entero** -- el borrador propio con
`sale_mp_orders`, el poll (`estado_del_cobro`) y el aviso de "cobros que
entraron y no quedaron registrados" (`cobros_sin_venta`). D2 reemplazó todo
eso por "el modelo de la familia": venta PENDIENTE + `acreditar_pago_qr`, que
vive en `libracore.ventas_cobro_router` (montado en `app/main.py` como
`/api/ventas/{vid}/mp-qr`/`.../mp-status`). Lo único que sigue haciendo falta
de acá es lo que sigue: el criterio con el que el POS decide si ofrece el
botón de QR y si promete factura automática -- las credenciales y el toggle
viven en el MISMO `config.json` de siempre (`libracore.mp_config_router`
escribe esas mismas claves), así que no hay nada que migrar.

La tabla `sale_mp_orders` NO se borra -- puede haber filas de antes de F3 --
pero desde D2 ningún camino nuevo la escribe ni la lee.
"""
from libracore import config_manager


class MpNoConfigurado(RuntimeError):
    """Faltan las credenciales del QR en Configuracion -> Mercado Pago."""


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
