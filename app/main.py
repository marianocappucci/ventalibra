"""TiendaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
from fastapi import Depends, FastAPI

from . import db
from .auth import build_session_auth, require_admin, require_staff
from .routers import auth as auth_router
from .routers import catalog, health, locations, purchasing, sales, stock, suppliers
from .routers import users as users_router
from .services.users import UserRepository, ensure_default_admin


def create_app(db_path: str) -> FastAPI:
    conn = db.connect(db_path)
    user_repository = UserRepository(conn)
    ensure_default_admin(user_repository)

    app = FastAPI(title="TiendaLibra")
    app.state.conn = conn
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)

    app.include_router(health.router)
    app.include_router(auth_router.router)

    admin_only = [Depends(require_admin)]
    staff_or_admin = [Depends(require_staff)]

    app.include_router(users_router.router, dependencies=admin_only)
    app.include_router(catalog.router, dependencies=staff_or_admin)
    app.include_router(locations.router, dependencies=staff_or_admin)
    app.include_router(stock.router, dependencies=staff_or_admin)
    app.include_router(sales.router, dependencies=staff_or_admin)
    app.include_router(suppliers.router, dependencies=staff_or_admin)
    app.include_router(purchasing.router, dependencies=staff_or_admin)

    return app
