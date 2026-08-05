"""VentaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
import os

from fastapi import Depends, FastAPI
from libraauth.auditoria import agregar_middleware_de_usuario, build_logs_router
from libraauth.auth_events import AuthEventRepository
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.session_auth import build_smtp_settings_router
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libracommerce.db.auditoria import ActividadRepository, entidades as entidades_auditadas
from libracore import config_manager
from libracore.config_router import (
    build_backup_router, build_empresa_admin_router, build_empresa_router,
)
from libracore.respaldo import Instancia
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import db
from .auth import build_session_auth, require_admin, require_admin_o_servicio, require_staff
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
    # Config SMTP editable por backoffice (libraauth v0.6.0), con la contraseña
    # cifrada en reposo. Mismo `auth_sessions` que el resto del motor.
    app.state.smtp_settings = SmtpSettingsRepository(auth_sessions)
    app.state.password_reset = PasswordResetService(
        auth_sessions,
        product_name="VentaLibra",
        reset_url_base=os.environ.get(
            "VENTALIBRA_RESET_URL_BASE", "https://dev.ventalibra.com.ar/reset-password"
        ),
        # CALLABLE, no un valor: se resuelve en cada envío. Con un valor fijo,
        # guardar el SMTP por pantalla no tendría efecto hasta recrear el
        # contenedor. Sin nada guardado cae a las variables de entorno, así que
        # la instancia se comporta igual que antes hasta que se cargue algo.
        smtp_config=lambda: resolver_smtp_config(auth_sessions),
    )
    app.state.modules = ModuleRepository(conn)

    # Los dos logs, cada uno contra la base donde ocurre lo que registra.
    #
    # Actividad: la base del DOMINIO, que es donde escriben los repositorios.
    # No cuelga de un flush como en Gestiolibra o MedLibra —este producto no
    # tiene SQLAlchemy en el dominio— sino del repositorio envuelto: ver
    # `app/commerce.py`, que es por donde pasan los diez servicios.
    app.state.auditoria = ActividadRepository(conn)
    # Accesos: la base de LibraCore, la misma donde vive `usuarios` y donde
    # `auth_log` ya existe. Esto no crea la tabla: empieza a escribirla.
    app.state.auth_events = AuthEventRepository(auth_sessions)
    # Sella el usuario de la cookie para que la auditoria sepa quien escribio.
    # Sin esto todo queda a nombre de "Sistema", que no es un error visible.
    agregar_middleware_de_usuario(app)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    # `GET`/`PUT`/`DELETE /admin/smtp`. El router exige rol admin por dentro:
    # quien pueda escribir ahí puede redirigir a dónde salen los enlaces de
    # recuperación de contraseña de todos los usuarios.
    app.include_router(build_smtp_settings_router())

    admin_only = [Depends(require_admin)]
    staff_or_admin = [Depends(require_staff)]

    # Usuarios acepta ADEMAS el token de servicio (libraauth v0.7.0): es lo
    # unico que el backoffice de la suite necesita y que no puede salir del
    # motor, porque el router de usuarios es propio de cada producto.
    #
    # Deliberadamente solo este: el resto de los routers admin-only siguen
    # exigiendo sesion de un usuario del producto. El backoffice no tiene por
    # que poder tocar el resto del dominio, y colgar la dependencia de
    # `admin_only` seria ampliar el permiso sin necesidad.
    app.include_router(users_router.router, dependencies=[Depends(require_admin_o_servicio)])
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

    # Datos de empresa, logo y Datos / Backup (LibraCore v1.11.0).
    #
    # A diferencia de LibraDesk, aca la lectura de empresa TAMBIEN es admin:
    # este producto no genera comprobantes desde el frontend con esos datos —
    # el ticket lo arma el backend—, asi que no hay motivo para abrirla.
    app.include_router(build_empresa_router(), dependencies=admin_only)
    app.include_router(build_empresa_admin_router(), dependencies=admin_only)

    # 🔴 DOS bases, y las dos tienen que entrar al backup: `usuarios` vive en
    # la de LibraCore, separada de la del dominio (ver el comentario largo
    # arriba). Un backup de una sola no se puede restaurar — o volves el
    # dominio y te quedan usuarios de otro momento, o al reves.
    instancia = Instancia(
        nombre="ventalibra",
        bases=[db_path, libracore_db_path],
        directorios=[config_manager.LOGO_DIR],
    )

    def _cerrar_conexion():
        # El dominio es sqlite3 crudo con UNA conexion compartida por toda la
        # app. Sin cerrarla, el restore reemplaza el archivo y el proceso sigue
        # leyendo el inodo viejo — devuelve `ok` y no pasa nada.
        app.state.conn.close()

    def _reabrir_conexion():
        nueva = db.connect(db_path)
        app.state.conn = nueva
        # ⚠️ Los servicios toman la conexion de `request.app.state.conn` en cada
        # request, asi que con reemplazarla alcanza para ellos. Pero
        # `app.state.auditoria` se construyo UNA vez, al arrancar, y se quedo
        # con la conexion vieja: sin esta linea la pantalla de logs consulta
        # una conexion cerrada despues de cada restore.
        app.state.auditoria = ActividadRepository(nueva)
        auth_engine.dispose()

    app.include_router(
        build_backup_router(
            instancia, os.path.join(os.path.dirname(libracore_db_path), "backups"),
            cerrar_conexiones=_cerrar_conexion,
            reabrir_conexiones=_reabrir_conexion,
        ),
        dependencies=admin_only,
    )

    # Logs: admin y nada mas. La fila dice quien vendio que y desde que IP
    # entro cada uno. **No** se gatea por plan: un log de auditoria no es una
    # feature vendible.
    #
    # El router lo arma el motor de auth (libraauth v0.10.0) pero el gate lo
    # pone el producto: el vocabulario de roles es de aca. Y la lista de
    # entidades sale del motor comercial, que es de donde sale la actividad.
    app.include_router(
        build_logs_router(entidades_auditadas()), dependencies=admin_only,
    )

    return app
