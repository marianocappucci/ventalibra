"""Configuracion ARCA de VentaLibra (admin-only).

VentaLibra es de instancia unica por cliente -- una sola "empresa" ARCA,
sin lista de empresas para elegir. Certificado/clave se referencian por
path en el filesystem del servidor (mismo patron que medlibra/gestiolibra);
subir el archivo real es tarea manual del admin todavia.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services import billing

router = APIRouter(prefix="/config/arca", tags=["billing"])


class ArcaConfigIn(BaseModel):
    cuit: str
    punto_venta: int
    certificado_path: str
    clave_path: str
    ambiente: str = "homologacion"


class ArcaConfigOut(BaseModel):
    empresa: str
    cuit: str
    punto_venta: int
    ambiente: str
    certificado_path: str
    clave_path: str


def _to_out(cfg: dict) -> ArcaConfigOut:
    return ArcaConfigOut(
        empresa=cfg["empresa"], cuit=cfg["cuit"], punto_venta=cfg["punto_venta"],
        ambiente=cfg["ambiente"], certificado_path=cfg["certificado_path"],
        clave_path=cfg["clave_path"],
    )


@router.get("")
def get_arca_config() -> ArcaConfigOut | None:
    cfg = billing.get_arca_config()
    return _to_out(cfg) if cfg else None


@router.put("", response_model=ArcaConfigOut)
def set_arca_config(data: ArcaConfigIn) -> ArcaConfigOut:
    cfg = billing.set_arca_config(
        data.cuit, data.punto_venta, data.clave_path, data.certificado_path, data.ambiente,
    )
    return _to_out(cfg)
