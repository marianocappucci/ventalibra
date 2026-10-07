"""Las reglas de cajas y turnos de VentaLibra sobre los routers del motor.

Desde la fase 5 de la adopción de los motores (2026-09-26, ADR-032) VentaLibra monta
`libracore.caja_router.build_cajas_router` y `build_turnos_router`, los mismos de Contalibra y Restolibra, y
declara acá lo que lo hace distinto (`libracore` v1.112.0). Son las reglas de las cajas por sucursal
(2026-09-16) y de la baja de cajas (2026-09-26), que ya no viven en
routers propios (`/shifts`, `app/routers/cajas.py`):

**Cajas**
- alta, edición, baja y predeterminada son **de admin** (capacidad `caja.admin`: dar de alta un mostrador es
  configurar el local); la lectura es de quien tiene turno propio (`caja.propia`), que elige la caja al abrir turno;
- toda caja pertenece a una sucursal **activa** (`branches`); un depósito no tiene cajas;
- los medios de pago tienen que ser de `libracore.medios_pago.ELEGIBLES` (422);
- la caja predeterminada es **por sucursal** (el motor la tiene global);
- una caja se **desactiva** en vez de borrarse (si tiene movimientos no se puede eliminar), y no se puede
  desactivar con un turno abierto ni si es la única activa de su sucursal (409); si era la
  predeterminada, la predeterminada pasa a otra activa.

**Turnos**
- el turno es **por usuario y por caja**: se abre sobre UNA caja, y esa caja no admite un segundo turno mientras
  el primero siga abierto (el motor no impone «una caja, un turno»);
- la caja tiene que existir y estar activa;
- abrir con un turno propio ya abierto es 409 (no devuelve el mismo, como hace el motor por defecto: el arqueo
  del primero quedaría partido);
- el arqueo es **sobre `caja_movimientos`** (no sobre las ventas) y **sin la cuenta corriente**: fiar no es
  cobrar. El listado de ventas del turno sale de la capa ERP;
- cada turno de la respuesta trae la caja y la sucursal donde está abierto, que el POS necesita.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from libracommerce.erp import ventas as erp_ventas
from libracore.caja_router import AbrirPayload, CajaPayload, CajaUpdatePayload, OpcionesCajas
from libracore.db import caja as db_caja
from libracore.db import turnos as db_turnos
from libracore.db.core import get_connection

from .auth import get_current_user
from .permisos import condicion, requiere
from .services import cajas as cajas_service
from .services.sucursales import SucursalService

#: El medio de pago que marca una venta a crédito: no es plata que entra en la caja.
MEDIO_CUENTA_CORRIENTE = "cuenta_corriente"

#: Cómo se llega al `SucursalService` de la conexión del dominio. Un callable y no la conexión: la app la
#: reemplaza al restaurar un respaldo (`app.state.conn`), así que se lee en cada pedido.
Sucursales = Callable[[], SucursalService]


def usuario_actual(user: dict = Depends(get_current_user)) -> dict:
    """La sesión con `id` entero. La sesión de este producto trae el id como texto y `build_turnos_router` lo
    compara con `turnos_caja.usuario_id` (un entero) para decidir quién ve qué turno: sin esto, un cajero no
    vería ni el suyo."""
    return {**user, "id": int(user["id"])}


_VE_TODOS_LOS_TURNOS = condicion("turnos.todos")


def usuario_de_turnos(user: dict = Depends(usuario_actual)) -> dict:
    """La sesión, tal como la lee `build_turnos_router`.

    🔴 **El router de turnos del motor decide «quién ve y cierra los turnos ajenos» con `role == "admin"`
    escrito a mano** (`libracore.caja_router._puede_ver` y `listar`), sin ganchos. Con los roles nuevos el
    encargado tiene que ver y cerrar los turnos de todos (capacidad `turnos.todos`), y no es admin. Mientras el
    motor no reciba esa decisión por parámetro, se la damos por el único lado que tiene: a quien tiene la
    capacidad se le presenta `role="admin"` **sólo ante ese router**. La sesión real no cambia, ni las guardas
    (que corren antes y sobre la sesión verdadera), ni ningún otro router.
    """
    return {**user, "role": "admin"} if _VE_TODOS_LOS_TURNOS(user) else user


#: Quién puede pedir el arqueo de un turno que NO abrió: quien ve los turnos de todos (`turnos.todos`) y quien ya recibe
#: el arqueo de todos los turnos en el cierre diario (`cierre_diario`: su vista previa trae uno por turno del día; hoy coincide
#: con `turnos.todos`: admin y encargado).
_VE_ARQUEOS_AJENOS = (condicion("turnos.todos"), condicion("cierre_diario"))


def solo_su_turno_o_todos(request: Request, user: dict = Depends(usuario_actual)) -> None:
    """Guarda de `GET /api/cierre-diario/turno/{turno_id}/ticket`: el arqueo de un turno es de quien lo abrió.

    🔴 **El handler del motor imprime el arqueo de CUALQUIER turno por id** (`libracore.caja_router.ticket_turno`, sin
    mirar la sesión), y la guarda de la ruta (`caja.propia`) sólo dice «este rol tiene turno propio»: un cajero o un
    vendedor podía pedir el ticket de los turnos de otro. Acá se compara `turnos_caja.usuario_id` con la sesión ANTES de
    llegar al handler. Un turno que no existe se deja pasar: el 404 es del motor. El resto de las rutas del router
    (`{cierre_id}`) no traen `turno_id` y no las toca.
    """
    try:
        turno_id = int(request.path_params.get("turno_id"))
    except (TypeError, ValueError):
        return
    if any(puede(user) for puede in _VE_ARQUEOS_AJENOS):
        return
    turno = db_turnos.get_turno(turno_id)
    if turno is not None and turno["usuario_id"] != user["id"]:
        raise HTTPException(403, "No autorizado")


def _validar_medios(medios: list[str]) -> None:
    try:
        cajas_service.validar_medios(medios)
    except cajas_service.MedioDePagoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc


def opciones_de_cajas(sucursales: Sucursales) -> OpcionesCajas:
    def validar_alta(payload: CajaPayload) -> None:
        _validar_medios(payload.medios_pago)
        if payload.sucursal_id is None:
            raise HTTPException(422, "La sucursal es obligatoria.")
        sede = sucursales().get(payload.sucursal_id)
        if sede is None or not sede.active:
            raise HTTPException(422, f"No existe una sucursal activa con id {payload.sucursal_id}.")

    def validar_edicion(payload: CajaUpdatePayload, actual: dict) -> None:
        _validar_medios(payload.medios_pago)
        if payload.activo or not actual.get("activo", 1):
            return  # sólo la baja tiene guardas
        sede = sucursales().get(actual["sucursal_id"]) if actual.get("sucursal_id") else None
        try:
            cajas_service.validar_baja(actual, sucursal_vende=sede is not None)
        except cajas_service.BajaNoPermitida as exc:
            raise HTTPException(409, str(exc)) from exc

    def enriquecer(caja: dict) -> dict:
        sede = sucursales().get(caja["sucursal_id"]) if caja.get("sucursal_id") is not None else None
        return {**caja, "sucursal_nombre": sede.name if sede else None}

    return OpcionesCajas(
        autorizar_escritura=Depends(requiere("caja.admin")),
        validar_alta=validar_alta,
        validar_edicion=validar_edicion,
        al_desactivar=cajas_service.pasar_predeterminada_a_otra_activa,
        predeterminar=cajas_service.marcar_predeterminada,
        enriquecer=enriquecer,
    )


def _sin_fiado(resumen: dict) -> dict:
    """`get_resumen_turno_caja` suma TODOS los medios de `caja_movimientos`, `cuenta_corriente` incluido.

    🔴 **Desde F3 (2026-09-14, ADR-025) eso ya no es un no-op.** La capa ERP (`libracommerce.erp.ventas.
    registrar_venta`) escribe un movimiento por cada medio, cuenta_corriente incluido: lo excluye de
    `/reports/caja` pero NO de `get_resumen_turno_caja`. Sin este filtro el arqueo del cajero mostraría como
    «vendido» plata que nunca entró al cajón. Se filtra acá y no en `libracore.db.turnos`: esa función la
    comparten otros productos (LibraClub) para los que sumar todo es lo esperado.
    """
    pagos = {m: t for m, t in resumen["pagos_por_medio"].items() if m != MEDIO_CUENTA_CORRIENTE}
    return {**resumen, "pagos_por_medio": pagos, "total_ventas": sum(pagos.values())}


def resumen_del_turno(turno_id: int) -> dict:
    """El arqueo sobre la caja, sin fiado, más las ventas del turno (las que muestra la pantalla de turnos del
    kit, `resumen.ventas`) tal como las lee la capa ERP."""
    with get_connection() as conn:
        ventas = erp_ventas.resumen_turno(conn, turno_id)["ventas"]
    return {**_sin_fiado(db_turnos.get_resumen_turno_caja(turno_id)), "ventas": ventas}


def cerrar_turno(turno_id: int, monto_declarado: float, notas: str = "") -> None:
    db_turnos.cerrar_turno_caja(turno_id, monto_declarado, notas)


def validar_apertura_de(sucursales: Sucursales) -> Callable[[AbrirPayload, dict], None]:
    def validar_apertura(payload: AbrirPayload, user: dict) -> None:
        # Obligatoria: en VentaLibra toda venta sale de una caja de una sucursal, así que un turno sin caja no
        # es un caso que el POS pueda pedir (sólo puede EXISTIR de antes: turnos viejos).
        if payload.caja_id is None:
            raise HTTPException(422, "Elegí la caja donde abrir el turno.")
        caja = db_caja.get_caja_config(payload.caja_id)
        if caja is None:
            raise HTTPException(404, "La caja no existe.")
        if not caja.get("activo", True):
            raise HTTPException(422, f"La caja {caja['nombre']!r} está dada de baja.")

        propio = db_turnos.get_turno_activo(int(user["id"]))
        if propio:
            # No se abre uno nuevo encima de otro: el arqueo del primero quedaría partido y ninguno de los dos
            # cerraría bien.
            raise HTTPException(409, f"ya tenés un turno abierto (#{propio['id']})")

        ajeno = db_turnos.turno_abierto_de_caja(payload.caja_id)
        if ajeno:
            raise HTTPException(
                409,
                f"la caja {caja['nombre']!r} ya tiene un turno abierto de "
                f"{ajeno['usuario_nombre']!r} (#{ajeno['id']})",
            )

    return validar_apertura


def enriquecer_turno_de(sucursales: Sucursales) -> Callable[[dict], dict]:
    def enriquecer(turno: dict) -> dict:
        """El turno con la caja y la sucursal donde está abierto, para que el POS no tenga que resolverlas.

        Turnos viejos sin `caja_id` (los de antes de las cajas por sucursal) devuelven `caja`/`sucursal` en
        `None`: no rompen nada, sólo no tienen dónde mostrarlas."""
        caja = db_caja.get_caja_config(turno["caja_id"]) if turno.get("caja_id") else None
        sede = sucursales().get(caja["sucursal_id"]) if caja and caja.get("sucursal_id") is not None else None
        return {
            **turno,
            "caja": (
                {"id": caja["id"], "nombre": caja["nombre"], "punto_venta": caja.get("punto_venta")}
                if caja else None
            ),
            "sucursal": {"id": sede.id, "nombre": sede.name} if sede else None,
        }

    return enriquecer
