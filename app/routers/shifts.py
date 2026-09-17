"""Turno de caja del POS.

El turno es lo que hace que el arqueo cierre: sin uno abierto no se puede
cobrar (ver libracommerce.web.ventas_router, `exigir_turno=True` en
app/main.py), porque una venta fuera de turno es plata que queda afuera de
todo control de caja.

🔴 **Desde la feature de cajas por sucursal (2026-09-16) el turno es POR
USUARIO Y POR CAJA, no compartido.** Hasta esa fecha toda la instancia tenía
un único mostrador y el turno era uno solo para todos (`get_turno_activo_any`,
ver `app/ganchos.py`): con dos locales vendiendo a la vez eso mezclaba la
plata de los dos. Ahora cada cajero abre turno en UNA caja, y esa caja no
admite un segundo turno mientras el primero siga abierto — la valida este
router, no el motor (ver `app/services/cajas.py::turno_abierto_de`: ni
siquiera LibraClub, la otra instancia con cajas múltiples, impone esa regla).

Se apoya en `libracore.db.turnos`, pero con la variante que arquea sobre
`caja_movimientos` (`get_resumen_turno_caja`/`cerrar_turno_caja`, LibraCore
v0.27.0) en vez de sobre la tabla `ventas` de LibraCore: las ventas de este
producto viven en LibraCommerce, en OTRA base, asi que el resumen clasico le
daria siempre cero.

✅ **Que `deposito_id` de `POST /api/ventas` (y de la devolución) sea la
sucursal de la caja del turno lo valida el backend desde el 2026-09-17**:
libracommerce v0.17.0 agregó el gancho `Hooks.validar_deposito`, y
`app/ganchos.py::validar_deposito` lo usa (422 si no corresponde). Hasta esa
fecha lo garantizaba sólo el POS (`frontend/src/pages/Pos.tsx`, que fija la
sucursal a la de la caja del turno), y eso sigue igual.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from libracore.db import caja as db_caja
from libracore.db import turnos as db_turnos
from libracore.db.cierre_diario import DiaCerradoError
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import cajas as cajas_service
from ..services.cuenta_corriente import MEDIO_CUENTA_CORRIENTE
from ..services.locations import LocationService

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _sin_fiado(resumen: dict) -> dict:
    """`get_resumen_turno_caja` suma TODOS los medios de `caja_movimientos`,
    `cuenta_corriente` incluido.

    🔴 **Desde F3 (2026-09-14, DECISIONS.md ADR-025) eso ya no es un no-op.**
    El modelo viejo (`services/cuenta_corriente.py::registrar_venta_fiada`,
    retirado) nunca escribía un movimiento de caja para el fiado -- ADR-020:
    "fiar no es cobrar". La capa ERP nueva (`libracommerce.erp.ventas.
    registrar_venta`) sí escribe uno por cada medio, cuenta_corriente
    incluido -- lo excluye del `/reports/caja` (`get_caja_resumen`, que usa
    `sql_no_es_cuenta_corriente`) pero NO de `get_resumen_turno_caja`, que es
    lo que arma ESTE router. Sin este filtro, el arqueo del cajero mostraría
    como "vendido" plata que nunca entró al cajón.

    Se filtra acá, en el router propio de VentaLibra, y no en
    `libracore.db.turnos`: esa función la comparten otros productos
    (LibraClub) para los que sumar todo es lo esperado.
    """
    pagos = {m: t for m, t in resumen["pagos_por_medio"].items() if m != MEDIO_CUENTA_CORRIENTE}
    return {**resumen, "pagos_por_medio": pagos, "total_ventas": sum(pagos.values())}


def _enriquecer(turno: dict, request: Request) -> dict:
    """El turno con la caja y la sucursal donde está abierto, para que el POS
    no tenga que resolverlas por su cuenta.

    Turnos viejos sin `caja_id` (los que había antes de esta feature, o
    turnos de productos sin cajas múltiples) devuelven `caja`/`sucursal` en
    `None` — no rompen nada, sólo no tienen dónde mostrarlas."""
    caja = db_caja.get_caja_config(turno["caja_id"]) if turno.get("caja_id") else None
    sucursal = None
    if caja and caja.get("sucursal_id") is not None:
        loc = LocationService(request.app.state.conn).get(caja["sucursal_id"])
        if loc:
            sucursal = {"id": loc.id, "nombre": loc.name}
    return {
        **turno,
        "caja": (
            {"id": caja["id"], "nombre": caja["nombre"], "punto_venta": caja.get("punto_venta")}
            if caja else None
        ),
        "sucursal": sucursal,
    }


class ShiftOpen(BaseModel):
    # Lo que hay en el cajon al empezar: es la base contra la que se arquea.
    monto_inicial: float = 0
    notas: str = ""
    #: Sobre qué mostrador se abre. Obligatorio: en VentaLibra toda venta
    #: sale de una caja de una sucursal, así que un turno sin caja no es un
    #: caso que el POS pueda pedir — sólo puede EXISTIR de antes (ver el
    #: docstring del módulo).
    caja_id: int


class ShiftClose(BaseModel):
    # Lo que el cajero conto a mano al cerrar.
    monto_declarado: float
    notas: str = ""


@router.get("/current")
def turno_actual(request: Request, user: dict = Depends(get_current_user)):
    """Turno abierto de QUIEN PIDE, o null. El POS lo consulta al arrancar
    para saber si puede vender o tiene que pedir apertura.

    🔴 Antes era `get_turno_activo_any()` (el turno de TODA la instancia,
    compartido). Con varias cajas por sucursal cada cajero tiene el suyo."""
    turno = db_turnos.get_turno_activo(int(user["id"]))
    if not turno:
        return {"turno": None}
    return {
        "turno": _enriquecer(turno, request),
        "resumen": _sin_fiado(db_turnos.get_resumen_turno_caja(turno["id"])),
    }


@router.post("/open")
def abrir_turno(data: ShiftOpen, request: Request, user: dict = Depends(get_current_user)):
    caja = db_caja.get_caja_config(data.caja_id)
    if caja is None:
        raise HTTPException(404, "La caja no existe.")
    if not caja.get("activo", True):
        raise HTTPException(422, f"La caja {caja['nombre']!r} está dada de baja.")

    propio = db_turnos.get_turno_activo(int(user["id"]))
    if propio:
        # No se abre uno nuevo encima de otro: el arqueo del primero quedaria
        # partido y ninguno de los dos cerraria bien.
        raise HTTPException(409, f"ya tenés un turno abierto (#{propio['id']})")

    ajeno = cajas_service.turno_abierto_de(data.caja_id)
    if ajeno:
        raise HTTPException(
            409,
            f"la caja {caja['nombre']!r} ya tiene un turno abierto de "
            f"{ajeno['usuario_nombre']!r} (#{ajeno['id']})",
        )

    try:
        tid = db_turnos.create_turno(int(user["id"]), data.monto_inicial, data.notas,
                                     caja_id=data.caja_id)
    except DiaCerradoError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"turno": _enriquecer(db_turnos.get_turno(tid), request)}


@router.get("/{turno_id}/summary")
def resumen(turno_id: int, request: Request):
    turno = db_turnos.get_turno(turno_id)
    if not turno:
        raise HTTPException(404, "turno no encontrado")
    return {
        "turno": _enriquecer(turno, request),
        "resumen": _sin_fiado(db_turnos.get_resumen_turno_caja(turno_id)),
    }


@router.post("/{turno_id}/close")
def cerrar(turno_id: int, data: ShiftClose, request: Request):
    """Cierra el turno. Quién puede: **sin restricción propia** — así estaba
    antes de esta feature (cualquiera con sesión de staff/admin podía cerrar
    cualquier turno, no sólo el suyo) y se conserva tal cual: achicarlo a
    "dueño o admin" es un cambio de permisos que no pidió esta tarea."""
    turno = db_turnos.get_turno(turno_id)
    if not turno:
        raise HTTPException(404, "turno no encontrado")
    if turno["estado"] != "abierto":
        raise HTTPException(409, "el turno ya esta cerrado")
    # El resumen se calcula ANTES de cerrar y se devuelve junto al turno: es
    # lo que el cajero necesita ver para entender la diferencia, y despues de
    # cerrar ya no puede reconstruirlo en pantalla.
    resumen_final = _sin_fiado(db_turnos.get_resumen_turno_caja(turno_id))
    cerrado = db_turnos.cerrar_turno_caja(turno_id, data.monto_declarado, data.notas)
    return {"turno": _enriquecer(cerrado, request), "resumen": resumen_final}


@router.get("")
def listar(request: Request, limit: int = 30):
    return [_enriquecer(t, request) for t in db_turnos.get_all_turnos(limit=limit)]
