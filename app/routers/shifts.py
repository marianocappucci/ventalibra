"""Turno de caja del POS.

El turno es lo que hace que el arqueo cierre: sin uno abierto no se puede
cobrar (ver sales.confirm_sale), porque una venta fuera de turno es plata que
queda afuera de todo control de caja.

Se apoya en `libracore.db.turnos`, pero con la variante que arquea sobre
`caja_movimientos` (`get_resumen_turno_caja`/`cerrar_turno_caja`, LibraCore
v0.27.0) en vez de sobre la tabla `ventas` de LibraCore: las ventas de este
producto viven en LibraCommerce, en OTRA base, asi que el resumen clasico le
daria siempre cero.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libracore.db import turnos as db_turnos

from ..auth import get_current_user

router = APIRouter(prefix="/shifts", tags=["shifts"])


class ShiftOpen(BaseModel):
    # Lo que hay en el cajon al empezar: es la base contra la que se arquea.
    monto_inicial: float = 0
    notas: str = ""


class ShiftClose(BaseModel):
    # Lo que el cajero conto a mano al cerrar.
    monto_declarado: float
    notas: str = ""


@router.get("/current")
def turno_actual():
    """Turno abierto, o null. El POS lo consulta al arrancar para saber si
    puede vender o tiene que pedir apertura."""
    turno = db_turnos.get_turno_activo_any()
    if not turno:
        return {"turno": None}
    return {"turno": turno, "resumen": db_turnos.get_resumen_turno_caja(turno["id"])}


@router.post("/open")
def abrir_turno(data: ShiftOpen, user: dict = Depends(get_current_user)):
    abierto = db_turnos.get_turno_activo_any()
    if abierto:
        # No se abre uno nuevo encima de otro: el arqueo del primero quedaria
        # partido y ninguno de los dos cerraria bien.
        raise HTTPException(409, f"ya hay un turno abierto (#{abierto['id']})")
    tid = db_turnos.create_turno(int(user["id"]), data.monto_inicial, data.notas)
    return {"turno": db_turnos.get_turno(tid)}


@router.get("/{turno_id}/summary")
def resumen(turno_id: int):
    turno = db_turnos.get_turno(turno_id)
    if not turno:
        raise HTTPException(404, "turno no encontrado")
    return {"turno": turno, "resumen": db_turnos.get_resumen_turno_caja(turno_id)}


@router.post("/{turno_id}/close")
def cerrar(turno_id: int, data: ShiftClose):
    turno = db_turnos.get_turno(turno_id)
    if not turno:
        raise HTTPException(404, "turno no encontrado")
    if turno["estado"] != "abierto":
        raise HTTPException(409, "el turno ya esta cerrado")
    # El resumen se calcula ANTES de cerrar y se devuelve junto al turno: es
    # lo que el cajero necesita ver para entender la diferencia, y despues de
    # cerrar ya no puede reconstruirlo en pantalla.
    resumen_final = db_turnos.get_resumen_turno_caja(turno_id)
    cerrado = db_turnos.cerrar_turno_caja(turno_id, data.monto_declarado, data.notas)
    return {"turno": cerrado, "resumen": resumen_final}


@router.get("")
def listar(limit: int = 30):
    return db_turnos.get_all_turnos(limit=limit)
