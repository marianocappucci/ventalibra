"""VentaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
import os

from fastapi import Depends, FastAPI
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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

    # `usuarios` (libraauth) vive en la base de LIBRACORE, no en la del dominio.
    #
    # Es deliberado y se pago aprendiendolo: 11 tablas de libracore
    # (facturas, ventas, caja_movimientos, turnos_caja, egresos, egresos_pagos,
    # movimientos_stock, movimientos_tesoreria, cc_pagos, remitos, presupuestos)
    # declaran `usuario_id REFERENCES usuarios(id)`, y esas FK resuelven contra
    # la tabla que este en SU MISMO archivo. Moverla a la base del dominio
    # rompia `create_turno` con FOREIGN KEY constraint failed -- se descubrio
    # justamente con la suite de VentaLibra, que es el unico producto con turnos
    # de caja. Ver wiki/entities/libraauth.md.
    #
    # Este engine es la unica pieza SQLAlchemy del producto (el resto es sqlite3
    # crudo, app/db.py) y no mueve ni un dato: las filas ya estan ahi.
    libracore_db_path = os.environ.get(
        "VENTALIBRA_LIBRACORE_DB_PATH", "./data/ventalibra_libracore.db"
    )
    billing.configure(libracore_db_path)
    auth_engine = create_engine(
        f"sqlite:///{libracore_db_path}", connect_args={"check_same_thread": False}
    )
    AuthBase.metadata.create_all(auth_engine)

    # Sin `roles=`: el default ("admin","staff") es el vocabulario de VentaLibra.
    auth_sessions = sessionmaker(bind=auth_engine)
    user_repository = UserRepository(auth_sessions)
    ensure_default_admin(user_repository)

    app = FastAPI(title="VentaLibra")
    app.state.conn = conn
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)
    # Recuperación de contraseña por correo (libraauth v0.5.0). Usa el mismo
    # session_factory que el UserRepository: la tabla de tokens tiene FK a
    # `usuarios`. Sin SMTP configurado la app levanta igual y el endpoint
    # devuelve 503.
    app.state.password_reset = PasswordResetService(
        auth_sessions,
        product_name="VentaLibra",
        reset_url_base=os.environ.get(
            "VENTALIBRA_RESET_URL_BASE", "https://dev.ventalibra.com.ar/reset-password"
        ),
    )
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
