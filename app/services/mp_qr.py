"""Si esta instancia puede cobrar por QR de MercadoPago, y si eso factura sola.

🔴 **Hasta F4 del plan post-P9 (2026-09-15, DECISIONS.md ADR-025) este módulo
además implementaba el cobro por QR entero** -- el borrador propio con
`sale_mp_orders`, el poll (`estado_del_cobro`) y el aviso de "cobros que
entraron y no quedaron registrados" (`cobros_sin_venta`). D2 reemplazó todo
eso por "el modelo de la familia": venta PENDIENTE + `acreditar_pago_qr`, que
vive en `libracore.ventas_cobro_router` (montado en `app/main.py` como
`/api/ventas/{vid}/mp-qr`/`.../mp-status`). Lo único que sigue haciendo falta
de acá es lo que sigue: el criterio con el que el POS decide si ofrece el
botón de QR y si promete factura automática.

🔴 **Y desde P9-M3 (QR por caja, 2026-09-24) el `mp_pos_id` ya no es un dato
de instancia**: vive en cada caja (`cajas.mp_pos_id`), y el cobro por QR lo
resuelve `libracore.db.caja.mp_pos_id_con_fallback()` -- usuario -> turno ->
caja, con fallback a la configuración de instancia sólo cuando hay exactamente
una caja. Por eso `esta_configurado()` pide el `usuario_id`: sin él no se
puede mirar la caja activa. El access token y el `mp_user_id` siguen a nivel
instancia (`libracore.mp_config_router` escribe esas mismas claves), y el
`credenciales()` que quedó sin llamadores se retiró: el que arma la URL del
QR es el router del motor, con su propio resolver.

La tabla `sale_mp_orders` NO se borra -- puede haber filas de antes de F3 --
pero desde D2 ningún camino nuevo la escribe ni la lee.
"""
from libracore import config_manager
from libracore.db import caja as db_caja

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


def esta_configurado(usuario_id: int | None = None) -> bool:
    """Si esta instancia puede cobrar por QR. Lo lee el POS para no ofrecer un
    boton que solo puede fallar.

    Requiere `usuario_id` cuando se quiere validar la caja activa; sin él,
    sólo valida que existan Access Token y User ID a nivel instancia.
    """
    cfg = cargar_config()
    token = (cfg.get("mp_access_token") or "").strip()
    user_id = (cfg.get("mp_user_id") or "").strip()
    if not token or not user_id:
        return False
    if usuario_id is None:
        # Sin usuario no podemos mirar la caja activa; al menos token+user_id.
        return True
    return db_caja.mp_pos_id_con_fallback(usuario_id, cfg.get("mp_pos_id")) is not None


def auto_facturar_prendida(cfg: dict | None = None) -> bool:
    cfg = cfg if cfg is not None else cargar_config()
    return bool(cfg.get("mp_auto_facturar_ventas"))
