"""Gating por plan -- mismo patron byte-a-byte que
gestiolibra/medlibra/app/modules_gate.py."""
from fastapi import Depends, HTTPException, Request

from .services.modules import ModuleRepository


def get_module_repository(request: Request) -> ModuleRepository:
    return request.app.state.modules


def require_module(modulo: str):
    """Dependency factory: 403 si el modulo no esta habilitado para esta
    instancia (plan asignado por scripts/nuevo_cliente.py)."""
    def _dependency(modules: ModuleRepository = Depends(get_module_repository)) -> None:
        if not modules.is_enabled(modulo):
            raise HTTPException(403, f"modulo '{modulo}' no incluido en el plan actual")
    return _dependency
