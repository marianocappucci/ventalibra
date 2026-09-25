"""ABM de cajas por sucursal.

Lectura para staff y admin (elige la caja al abrir turno); alta, edición,
baja y marcar predeterminada son de admin — dar de alta un mostrador es
configurar el local, no operar. El gate general de este router (staff o
admin) lo pone `app/main.py` al montarlo; acá se agrega `require_admin` sólo
en los endpoints que escriben.

`GET /api/cajas/medios-disponibles` sigue siendo de `app/routers/medios.py`
(lo consume `libra-ui/comercio/medios-pago`) — este router no define esa ruta
para no competir con ella.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from libracore.db.caja import ExternalIdMercadoPagoInvalido, PuntoDeVentaRepetido
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..services import cajas as service
from ..services.locations import LocationService, vende

router = APIRouter(prefix="/api/cajas", tags=["cajas"])


class CajaEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = ""
    medios_pago: list[str] = []
    #: El punto de venta de ARCA de ESTE mostrador. `None` deja la caja
    #: usando el de la empresa — el caso de toda instancia con un solo POS.
    punto_venta: int | None = None
    #: ID del POS de MercadoPago de esta caja (no el punto de venta ARCA).
    mp_pos_id: str | None = None


class CajaAlta(CajaEntrada):
    sucursal_id: int


class CajaEdicion(CajaEntrada):
    activo: bool = True


class CajaSalida(BaseModel):
    id: int
    nombre: str
    descripcion: str = ""
    medios_pago: list[str] = []
    punto_venta: int | None = None
    mp_pos_id: str | None = None
    activo: bool = True
    es_default: bool = False
    sucursal_id: int | None = None
    #: Si ya hay un turno abierto en esta caja (de cualquier usuario). El POS
    #: la usa para no ofrecerla al elegir dónde abrir turno.
    tiene_turno_abierto: bool = False


def _salida(c: dict) -> CajaSalida:
    return CajaSalida(
        id=c["id"], nombre=c["nombre"], descripcion=c.get("descripcion") or "",
        medios_pago=c.get("medios_pago") or [], punto_venta=c.get("punto_venta"),
        mp_pos_id=c.get("mp_pos_id"),
        activo=bool(c.get("activo", 1)), es_default=bool(c.get("es_default", 0)),
        sucursal_id=c.get("sucursal_id"),
        tiene_turno_abierto=service.turno_abierto_de(c["id"]) is not None,
    )


def _sucursal_activa(request: Request, sucursal_id: int) -> bool:
    loc = LocationService(request.app.state.conn).get(sucursal_id)
    return loc is not None and loc.active


@router.get("", response_model=list[CajaSalida])
def listar(sucursal_id: int | None = None):
    return [_salida(c) for c in service.listar_cajas(sucursal_id)]


@router.post("", response_model=CajaSalida, status_code=201, dependencies=[Depends(require_admin)])
def crear(datos: CajaAlta, request: Request):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(422, "El nombre es obligatorio.")
    if not _sucursal_activa(request, datos.sucursal_id):
        raise HTTPException(422, f"No existe una sucursal activa con id {datos.sucursal_id}.")
    if not vende(LocationService(request.app.state.conn).get(datos.sucursal_id)):
        raise HTTPException(422, "Sólo una sucursal de venta puede tener cajas; un depósito no vende.")
    try:
        caja = service.crear_caja(
            nombre, datos.descripcion.strip(), datos.medios_pago,
            datos.sucursal_id, punto_venta=datos.punto_venta,
            mp_pos_id=datos.mp_pos_id,
        )
    except service.MedioDePagoInvalido as e:
        raise HTTPException(422, str(e)) from e
    except PuntoDeVentaRepetido as e:
        raise HTTPException(409, str(e)) from e
    except ExternalIdMercadoPagoInvalido as e:
        raise HTTPException(422, str(e)) from e
    return _salida(caja)


@router.put("/{caja_id}", response_model=CajaSalida, dependencies=[Depends(require_admin)])
def editar(caja_id: int, datos: CajaEdicion):
    actual = service.obtener_caja(caja_id)
    if actual is None:
        raise HTTPException(404, "Caja no encontrada")
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(422, "El nombre es obligatorio.")
    try:
        caja = service.actualizar_caja(
            caja_id, nombre, datos.descripcion.strip(), datos.medios_pago,
            datos.activo, punto_venta=datos.punto_venta,
            mp_pos_id=(datos.mp_pos_id if "mp_pos_id" in datos.model_fields_set
                       else actual.get("mp_pos_id")),
        )
    except service.MedioDePagoInvalido as e:
        raise HTTPException(422, str(e)) from e
    except PuntoDeVentaRepetido as e:
        raise HTTPException(409, str(e)) from e
    except ExternalIdMercadoPagoInvalido as e:
        raise HTTPException(422, str(e)) from e
    return _salida(caja)


@router.post("/{caja_id}/predeterminada", response_model=CajaSalida,
            dependencies=[Depends(require_admin)])
def predeterminada(caja_id: int):
    caja = service.marcar_predeterminada(caja_id)
    if caja is None:
        raise HTTPException(404, "Caja no encontrada")
    return _salida(caja)


@router.delete("/{caja_id}", status_code=204, dependencies=[Depends(require_admin)])
def borrar(caja_id: int):
    if service.obtener_caja(caja_id) is None:
        raise HTTPException(404, "Caja no encontrada")
    try:
        service.borrar_caja(caja_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
