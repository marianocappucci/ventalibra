"""Cajas por sucursal: varios mostradores por sede, cada uno con su propio
punto de venta de ARCA y su propia caja por defecto.

Compuesto sobre `libracore.db.caja`, que ya trae la tabla, el arqueo y la
validación de punto de venta repetido (`PuntoDeVentaRepetido`). Lo que agrega
este módulo es lo que es de VentaLibra: la caja por defecto es POR SUCURSAL
(el motor la tiene GLOBAL, `db_caja.set_default_caja`, que sirve a los
productos sin sedes) y la regla "una caja, un turno a la vez" — que tampoco es
del motor: ni LibraClub (la otra instancia con cajas múltiples) la impone, ahí
sólo se evita que UN MISMO usuario tenga dos turnos.

Las sucursales son los `Location` de LibraCommerce, en la base del DOMINIO —
`cajas.sucursal_id` es un entero sin FK (dos bases distintas, ver
`app/services/locations.py`). La validación "existe y está activa" la hace el
router, que sí tiene la conexión del dominio a mano (`request.app.state.conn`).
"""
from __future__ import annotations

from libracore import medios_pago
from libracore.db import caja as db_caja
from libracore.db.caja import PuntoDeVentaRepetido  # noqa: F401  (re-exportado)
from libracore.db.core import get_connection

#: El nombre de la caja que se crea sola para una sucursal que no tenía
#: ninguna — al arrancar (instancias que ya venían andando) y al dar de alta
#: un Location nuevo. Se puede renombrar después; el nombre sólo importa la
#: primera vez.
NOMBRE_DE_LA_PRIMERA_CAJA = "Caja 1"


class MedioDePagoInvalido(ValueError):
    """Un medio de pago que no está en `medios_pago.ELEGIBLES`."""


def _validar_medios(medios: list[str]) -> None:
    for m in medios:
        if m not in medios_pago.ELEGIBLES:
            raise MedioDePagoInvalido(f"Medio de pago desconocido: {m!r}")


def listar_cajas(sucursal_id: int | None = None) -> list[dict]:
    return db_caja.get_all_cajas(sucursal_id=sucursal_id)


def obtener_caja(caja_id: int) -> dict | None:
    return db_caja.get_caja_config(caja_id)


def crear_caja(nombre: str, descripcion: str, medios: list[str], sucursal_id: int,
               punto_venta: int | None = None, mp_pos_id: str | None = None) -> dict:
    """Da de alta una caja en una sucursal. `sucursal_id` es obligatorio acá —
    a diferencia del motor, donde es opcional — porque en VentaLibra toda caja
    pertenece a un mostrador de una sede; la validación de que esa sucursal
    EXISTE y está ACTIVA la hace el router antes de llamar a esta función,
    porque necesita la conexión del dominio.

    Levanta `MedioDePagoInvalido` o `PuntoDeVentaRepetido` (del motor) — el
    router traduce las dos a HTTP.
    """
    _validar_medios(medios)
    cid = db_caja.create_caja_config(
        nombre, descripcion, list(medios), sucursal_id=sucursal_id, punto_venta=punto_venta,
        mp_pos_id=mp_pos_id,
    )
    return db_caja.get_caja_config(cid)


def actualizar_caja(caja_id: int, nombre: str, descripcion: str, medios: list[str],
                    activo: bool, punto_venta: int | None = None,
                    mp_pos_id: str | None = None) -> dict:
    """No cambia `sucursal_id`: una caja no se muda de sede, se da de baja y se
    crea otra donde corresponda — mismo criterio que el resto de la familia
    con las cuentas y los depósitos."""
    _validar_medios(medios)
    db_caja.update_caja_config(
        caja_id, nombre, descripcion, list(medios), 1 if activo else 0,
        punto_venta=punto_venta, mp_pos_id=mp_pos_id,
    )
    return db_caja.get_caja_config(caja_id)


def borrar_caja(caja_id: int) -> None:
    """Levanta `ValueError` si tiene movimientos o es la caja por defecto de
    su sucursal — la guarda es del motor (`db_caja.delete_caja_config`), que
    no filtra por sucursal: alcanza igual, porque `es_default` ya lo puso
    `marcar_predeterminada` en el scope correcto."""
    db_caja.delete_caja_config(caja_id)


def marcar_predeterminada(caja_id: int) -> dict | None:
    """Deja esta caja como la predeterminada **de su sucursal**, sin tocar la
    de las demás.

    🔴 **No se usa `db_caja.set_default_caja` del motor.** Esa función hace
    `UPDATE cajas SET es_default=0` sin filtrar nada: en un producto sin
    sedes (Contalibra, Restolibra) está bien, pero acá le borraría la
    predeterminada a TODAS las demás sucursales. Mismo defecto que ya
    resolvió LibraClub (`app/servicios/caja.py::marcar_predeterminada`) para
    el mismo caso — se calca el patrón acá.

    Las cajas sin sucursal (`sucursal_id IS NULL` — datos viejos, antes de
    esta feature) se tratan como su propio grupo, para no mezclarlas con las
    de una sede real.
    """
    caja = db_caja.get_caja_config(caja_id)
    if caja is None:
        return None
    sucursal_id = caja.get("sucursal_id")
    with get_connection() as conn:
        if sucursal_id is None:
            conn.execute("UPDATE cajas SET es_default=0 WHERE sucursal_id IS NULL")
        else:
            conn.execute("UPDATE cajas SET es_default=0 WHERE sucursal_id=?", (sucursal_id,))
        conn.execute("UPDATE cajas SET es_default=1 WHERE id=?", (caja_id,))
    return db_caja.get_caja_config(caja_id)


def turno_abierto_de(caja_id: int) -> dict | None:
    """El turno abierto de esa caja (de cualquier usuario), o `None`.

    🔑 **"Una caja, un turno" no es una regla del motor.** Ni siquiera
    LibraClub —la otra instancia con cajas múltiples— la impone: ahí sólo se
    evita que UN MISMO usuario tenga dos turnos abiertos a la vez (ver
    `libraclub/app/servicios/caja.py::abrir_turno`), pero nada impide hoy que
    dos cajeros distintos abran turno en el MISMO mostrador. Acá sí importa —
    dos personas cobrando sobre el mismo cajón mezclan la plata que hace un
    turno, que es justo lo que esta feature vino a separar—, así que se
    valida en el router de este producto (`shifts.py`) y se comparte esta
    consulta con `routers/cajas.py`, que la usa para no ofrecer al abrir una
    caja que ya está en uso.
    """
    with get_connection() as conn:
        row = conn.execute(
            """SELECT t.*, u.nombre AS usuario_nombre
                 FROM turnos_caja t JOIN usuarios u ON u.id = t.usuario_id
                WHERE t.caja_id=? AND t.estado='abierto'
                ORDER BY t.id DESC LIMIT 1""",
            (caja_id,),
        ).fetchone()
    return dict(row) if row else None


def tiene_turno_abierto_en(sucursal_id: int) -> bool:
    """Si alguna caja de esa sucursal tiene un turno abierto, de cualquier
    usuario. La usa `routers/locations.py` para no dejar desactivar una
    sucursal mientras se está vendiendo ahí -- guarda propia de VentaLibra,
    igual que `turno_abierto_de`: el motor (`libracommerce.erp.catalogo`) no
    sabe nada de turnos."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT 1 FROM turnos_caja t
                 JOIN cajas c ON c.id = t.caja_id
                WHERE c.sucursal_id=? AND t.estado='abierto'
                LIMIT 1""",
            (sucursal_id,),
        ).fetchone()
    return row is not None


def asegurar_caja_de(sucursal_id: int) -> dict:
    """La caja de esa sede, creándola —predeterminada— si todavía no tiene
    ninguna. Idempotente: devuelve la primera que ya exista, sin tocar nada.

    Se llama al arrancar la app (para sucursales que ya venían andando, ver
    `asegurar_cajas_de_todas`) y al dar de alta un Location nuevo
    (`routers/locations.py`): sin esto, una sucursal recién creada no tiene
    caja para elegir y nadie puede abrir turno ahí, porque el alta de cajas es
    de admin.
    """
    existentes = listar_cajas(sucursal_id)
    if existentes:
        return existentes[0]
    caja = crear_caja(NOMBRE_DE_LA_PRIMERA_CAJA, "", list(medios_pago.ELEGIBLES), sucursal_id)
    return marcar_predeterminada(caja["id"]) or caja


def reasignar_cajas_sin_sucursal(sucursal_default_id: int | None) -> int:
    """Las cajas con `sucursal_id` NULL pasan al Location default, si existe.

    🔴 En una instancia nueva, la caja huérfana es la "Caja Principal" que
    siembra `libracore.db.schema.init_core_schema()` cuando la tabla `cajas`
    está vacía — no la "Caja VentaLibra" de `services/billing.py::
    configure()`: esa rama corre DESPUÉS, encuentra que `get_default_caja_id()`
    ya no da `None` (`init_core_schema` corrió primero, dentro del mismo
    `configure()`) y nunca llega a crear nada. Cualquier caja de antes de
    esta feature —con cualquier nombre— entra por el mismo camino.

    Idempotente: la segunda corrida no encuentra ninguna para mover — ya
    quedaron todas con `sucursal_id` puesto en la primera.
    """
    if sucursal_default_id is None:
        return 0
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE cajas SET sucursal_id=? WHERE sucursal_id IS NULL",
            (sucursal_default_id,),
        )
        return cur.rowcount or 0


def asegurar_cajas_de_todas(sucursales_activas: list[int], sucursal_default_id: int | None) -> int:
    """Al arrancar: reasigna las cajas huérfanas (ver
    `reasignar_cajas_sin_sucursal`) y garantiza que cada sucursal activa
    tenga al menos una caja (ver `asegurar_caja_de`). Devuelve cuántas cajas
    NUEVAS creó — 0 en una instancia que ya las tiene todas, que es el caso
    de cada arranque salvo el primero.

    Se llama la reasignación ANTES del bucle a propósito: si el Location
    default ya tenía una caja huérfana, después de reasignarla esa sucursal
    ya tiene una y el bucle no crea una segunda de más.
    """
    reasignar_cajas_sin_sucursal(sucursal_default_id)
    creadas = 0
    for sid in sucursales_activas:
        if not listar_cajas(sid):
            asegurar_caja_de(sid)
            creadas += 1
    return creadas
