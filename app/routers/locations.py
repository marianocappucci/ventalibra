from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import require_admin
from ..services import cajas as cajas_service
from ..services.locations import (
    DatosInvalidos,
    FaltaTipoMinimo,
    LocationNotFound,
    LocationService,
    SucursalConTurnoAbierto,
    TipoNoSeCambia,
    vende,
)

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationCreate(BaseModel):
    name: str
    location_type: str = "warehouse"
    branch_id: int | None = None


class LocationUpdate(BaseModel):
    name: str
    location_type: str = "warehouse"
    is_default: bool = False
    active: bool = True


class LocationOut(BaseModel):
    id: int
    name: str
    branch_id: int | None
    location_type: str
    active: bool
    #: 🔴 Agregado 2026-09-14 (F3, ADR-025): el dominio (`Location.is_default`)
    #: ya lo traía -- `LocationOut(**location.__dict__)` lo venía DESCARTANDO
    #: en silencio (Pydantic ignora claves de más). Hace falta desde F3 porque
    #: `POST /api/ventas` ya no recibe `location_id`: descuenta siempre del
    #: default (`erp.stock.descontar_stock_venta`), y sin este campo no hay
    #: forma de que un cliente HTTP (la SPA, `scripts/seed_demo.py`) sepa CUÁL
    #: de los depósitos es ese -- antes no hacía falta saberlo, porque
    #: `/sales/{id}/confirm` dejaba elegir cualquiera.
    is_default: bool


def _service(request: Request) -> LocationService:
    return LocationService(request.app.state.conn)


# Alta y edición, sólo admin (decisión del humano, 2026-09-17): igual que las
# cajas (`routers/cajas.py`). El listado queda con el `staff_or_admin` del
# montaje en `app/main.py`: el POS lo necesita para elegir sucursal al abrir
# turno.
@router.post("", response_model=LocationOut, dependencies=[Depends(require_admin)])
def create_location(data: LocationCreate, request: Request):
    try:
        location = _service(request).create(data.name, data.location_type, data.branch_id)
    except DatosInvalidos as e:
        raise HTTPException(422, str(e)) from e
    # Cajas por sucursal (2026-09-16): una sucursal nueva sin ninguna caja no
    # tiene dónde abrir turno, y el alta de cajas es de admin -- sin esto,
    # quien acaba de crear el Location se queda sin poder vender ahí hasta
    # que alguien entre a la pantalla de Cajas a mano.
    # Un depósito (`warehouse`) no vende: no recibe caja (2026-09-25).
    if vende(location):
        cajas_service.asegurar_caja_de(location.id)
    return LocationOut(**location.__dict__)


@router.get("", response_model=list[LocationOut])
def list_locations(request: Request, incluir_inactivas: bool = False):
    # `incluir_inactivas`: sólo la pantalla de edición (`Sucursales.tsx`) la
    # pide -- el POS y la validación de alta de cajas siguen viendo únicamente
    # activas, que es el default de `LocationService.list()`.
    return [
        LocationOut(**loc.__dict__)
        for loc in _service(request).list(incluir_inactivas=incluir_inactivas)
    ]


@router.put("/{location_id}", response_model=LocationOut, dependencies=[Depends(require_admin)])
def update_location(location_id: int, data: LocationUpdate, request: Request):
    """Sólo admin, como el alta (ver el comentario de `create_location`)."""
    try:
        location = _service(request).update(
            location_id, data.name, data.location_type, data.is_default, data.active,
        )
    except LocationNotFound as e:
        raise HTTPException(404, str(e)) from e
    except DatosInvalidos as e:
        raise HTTPException(422, str(e)) from e
    except (SucursalConTurnoAbierto, FaltaTipoMinimo, TipoNoSeCambia) as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        # Las guardas del motor (`update_deposito`/`set_default_deposito`
        # sobre el depósito default) llegan como `ValueError` lisa: es un
        # conflicto con el estado de otra sucursal, no un dato mal formado.
        raise HTTPException(409, str(e)) from e
    # Un depósito que pasa a `store` empieza a vender: necesita su caja.
    if vende(location):
        cajas_service.asegurar_caja_de(location.id)
    return LocationOut(**location.__dict__)
