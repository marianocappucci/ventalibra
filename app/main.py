"""VentaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
import os

from fastapi import Depends, FastAPI

from . import db
from .auth import build_session_auth, require_admin, require_staff
from .modules_gate import require_module
from .routers import auth as auth_router
from .routers import billing as billing_router
from .routers import (
    accounts, catalog, customers, health, locations, pricing, purchasing, reports,
    sales, settings as settings_router, shifts, stock, suppliers,
)
from .routers import users as users_router
from .services import billing
from .services.modules import ModuleRepository
from .services.users import UserRepository, ensure_default_admin


def create_app(db_path: str) -> FastAPI:
    conn = db.connect(db_path)
    # libracore.db.core debe configurarse antes de que UserRepository (que
    # ahora delega en libracore.db.usuarios, ver services/users.py) haga su
    # primera consulta -- orden invertido respecto de antes de la migracion.
    billing.configure(os.environ.get("VENTALIBRA_LIBRACORE_DB_PATH", "./data/ventalibra_libracore.db"))
    user_repository = UserRepository()
    ensure_default_admin(user_repository)

    app = FastAPI(title="VentaLibra")
    app.state.conn = conn
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)
    app.state.modules = ModuleRepository(conn)

    app.include_router(health.router)
    app.include_router(auth_router.router)

    admin_only = [Depends(require_admin)]
    staff_or_admin = [Depends(require_staff)]

    app.include_router(users_router.router, dependencies=admin_only)
    app.include_router(
        billing_router.router, dependencies=admin_only + [Depends(require_module("facturacion"))],
    )
    app.include_router(catalog.router, dependencies=staff_or_admin)
    app.include_router(pricing.router, dependencies=staff_or_admin)
    app.include_router(locations.router, dependencies=staff_or_admin)
    app.include_router(stock.router, dependencies=staff_or_admin)
    app.include_router(sales.router, dependencies=staff_or_admin)
    app.include_router(shifts.router, dependencies=staff_or_admin)
    app.include_router(suppliers.router, dependencies=staff_or_admin)
    app.include_router(purchasing.router, dependencies=staff_or_admin)
    app.include_router(customers.router, dependencies=staff_or_admin)
    # El cajero cobra fiado en el mostrador, asi que no es admin-only.
    app.include_router(accounts.router, dependencies=staff_or_admin)
    app.include_router(reports.router, dependencies=admin_only)
    # Configurar la balanza es del dueno del local, no del cajero: el POS no
    # necesita leer este router, resuelve las etiquetas contra el backend.
    app.include_router(settings_router.router, dependencies=admin_only)

    return app
