"""VentaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
import os

from fastapi import Depends, FastAPI
from libraauth.auditoria import agregar_middleware_de_usuario, build_logs_router
from libraauth.auth_events import AuthEventRepository
from libraauth.bootstrap import ensure_demo_user
from libraauth.demo_codigos import DemoCodigoRepository
from libraauth.migrar import exigir_schema_al_dia
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.session_auth import (
    build_demo_codigos_router,
    build_smtp_settings_router,
    demo_username,
)
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libraauth.terminos import TerminosRepository, build_terminos_router
from libraauth.usuarios import build_users_router
from libracommerce.db.auditoria import ActividadRepository
from libracommerce.db.auditoria import entidades as entidades_auditadas
from libracommerce.web.ventas_router import OpcionesVentas, build_ventas_router
from libracore import config_manager
from libracore.arca_router import build_arca_router
from libracore.caja_router import build_cierre_diario_router
from libracore.config_router import (
    build_backup_router,
    build_empresa_admin_router,
    build_empresa_router,
)
from libracore.db.core import es_url_postgres
from libracore.db.core import get_connection as lc_get_connection
from libracore.db.url_de_instancia import url_de_instancia
from libracore.mp_config_router import build_mp_config_router
from libracore.resguardo_enlace import build_resguardo_enlace_router
from libracore.respaldo import Instancia
from libracore.security_headers import CSP_SPA, SecurityHeadersMiddleware
from libracore.smtp_router import build_smtp_probe_router
from libracore.ventas_cobro_router import build_cobro_de_ventas_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import db, venta_facturacion
from .auth import (
    build_session_auth,
    get_current_user,
    require_admin,
    require_admin_o_servicio,
    require_staff,
)
from .ganchos import GANCHOS, nombre_de_cliente
from .modules_gate import require_module
from .routers import (
    accounts,
    cajas,
    catalog,
    customers,
    health,
    locations,
    medios,
    pricing,
    purchasing,
    reports,
    shifts,
    stock,
    suppliers,
    ventas_extra,
)
from .routers import auth as auth_router
from .routers import (
    settings as settings_router,
)
from .services import billing
from .services import cajas as cajas_service
from .services.locations import LocationService
from .services.modules import ModuleRepository
from .services.users import UserRepository, ensure_default_admin


def _carpeta_de_backups(libracore_db_path: str) -> str:
    """Donde se guardan los ZIP de backup.

    🔴 **Salia de `os.path.dirname(libracore_db_path)`, y con la base en
    PostgreSQL eso no es una carpeta.** `dirname()` de
    `postgresql://usuario:clave@host:5432/base` devuelve
    `postgresql://usuario:clave@host:5432`, y ahi se creaba `backups/`: una
    carpeta **con la contrasena en el nombre**, colgando del directorio de
    trabajo. Es el mismo defecto que ya tenia `billing.configure()`, en otro
    lugar del mismo arranque; se encontro en [[contalibra]] el 2026-08-10, donde
    ademas afectaba a la carpeta de los certificados de ARCA.

    Con la base en PostgreSQL no hay "al lado de la base": se usa `DATA_DIR`.
    """
    if str(libracore_db_path).startswith(("postgresql://", "postgresql+psycopg://")):
        return os.path.join(os.environ.get("DATA_DIR", "./data"), "backups")
    return os.path.join(os.path.dirname(libracore_db_path), "backups")


def _instancia_de_respaldo(
    db_path: str, libracore_db_path: str, logo_dir: str,
) -> Instancia:
    """Que se lleva el backup de esta instancia.

    🔴 **`bases=` es para RUTAS de archivo, y en PostgreSQL las dos variables
    son URLs.** `Instancia.__post_init__` las volvia `Path`, y `_copiar_base`
    hace `if not origen.exists(): return` -- una URL nunca "existe" como
    archivo, asi que las salteaba LAS DOS en silencio: el ZIP salia con los
    logos y ninguna base. `crear_backup()` no fallaba; recien se notaba al
    restaurar (`verificar_backup` levanta `BackupInvalido`, medido en
    ventalibra-dev). Mismo defecto que ya se habia encontrado en
    gestiolibra/medlibra (`app/main.py`) y libradesk (incidente del
    2026-08-09).

    `billing.configure()` ya rechaza cualquier `libracore_db_path` que no sea
    PostgreSQL -- VentaLibra retiro el modo SQLite el 2026-08-12 -- asi que no
    hace falta una rama para archivo, a diferencia de esos tres productos:
    para esta instancia las dos variables son siempre PostgreSQL. Y a
    diferencia de gestiolibra/medlibra (dominio y core en bases separadas, sin
    schema en comun), en VentaLibra son la MISMA base (`_UNA_SOLA_BASE` en
    `libracore.db.url_de_instancia`) salvo que alguien las separe a mano en el
    entorno -- por eso `postgres_extra` solo suma `libracore_db_path` cuando
    de verdad apunta a otra URL: pasarla igual duplicaria el dump de la misma
    base bajo dos nombres distintos dentro del ZIP.
    """
    def _normalizada(url: str) -> str:
        return str(url).replace("postgresql://", "postgresql+psycopg://", 1)

    core_es_otra_base = es_url_postgres(str(libracore_db_path)) and (
        _normalizada(libracore_db_path) != _normalizada(db_path)
    )
    return Instancia(
        nombre="ventalibra",
        postgres_url=db_path,
        postgres_extra=[libracore_db_path] if core_es_otra_base else [],
        directorios=[logo_dir],
    )


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
    libracore_db_path = url_de_instancia(
        "ventalibra", core=True, default="./data/ventalibra_libracore.db"
    )
    billing.configure(libracore_db_path)
    # Cajas por sucursal (2026-09-16): toda sucursal (Location del dominio)
    # tiene al menos una caja, idempotente. `billing.configure()` (via
    # `libracore.db.schema.init_core_schema()`) ya garantiza que exista AL
    # MENOS una caja default en la instancia, sin sucursal, para una base
    # nueva -- acá se reasigna esa caja huérfana al depósito default y se
    # completa lo que falte por sucursal. Corre en cada arranque; en el
    # segundo no crea nada (ver `app/services/cajas.py::
    # asegurar_cajas_de_todas`).
    _sucursales_activas = LocationService(conn).list()
    _sucursal_default = next((s for s in _sucursales_activas if s.is_default), None)
    cajas_service.asegurar_cajas_de_todas(
        [s.id for s in _sucursales_activas],
        _sucursal_default.id if _sucursal_default else None,
    )
    # La URL de SQLAlchemy salia siempre como `sqlite:///...`, aunque el destino
    # fuera una URL PostgreSQL: la interpolacion la convertia en una ruta
    # relativa sin sentido. `postgresql://` se pasa tal cual (con el driver
    # psycopg, que es el de la familia), y `connect_args` es de SQLite.
    if libracore_db_path.startswith(("postgresql://", "postgresql+psycopg://")):
        auth_engine = create_engine(
            libracore_db_path.replace("postgresql://", "postgresql+psycopg://", 1)
        )
    else:
        auth_engine = create_engine(
            f"sqlite:///{libracore_db_path}", connect_args={"check_same_thread": False}
        )
    # 🔴 Las tablas de auth las crea la cadena de LibraAuth (`libraauth-migrar
    # upgrade --prefijo ventalibra --base core`, declarada en
    # `scripts/panel_admin.py`), no el arranque. Desde libraauth v0.45 (2026-09-17)
    # el arranque la EXIGE: si no corrió, la app no levanta y el error dice el
    # comando. Hasta ese día acá había un `AuthBase.metadata.create_all(auth_engine)`
    # que tapaba cualquier camino que se olvidara de migrar.
    exigir_schema_al_dia(auth_engine, prefijo="ventalibra", base="core")

    # Sin `roles=`: el default ("admin","staff") es el vocabulario de VentaLibra.
    auth_sessions = sessionmaker(bind=auth_engine)
    user_repository = UserRepository(auth_sessions)
    ensure_default_admin(user_repository)
    # Crea al visitante de la demo, **solo si esta instancia es una demo**: se
    # guia por `DEMO_MODE` + `DEMO_USERNAME`, las mismas dos variables que
    # registran `POST /auth/demo`. En la instancia de un cliente devuelve None
    # y no toca la base.
    #
    # 🔴 Sin esta llamada la ruta existe y no tiene a quien loguear: contesta
    # `503 demo user not provisioned`. Cablear `incluir_demo=True` en el router
    # no alcanza — la ruta y la siembra las conecta el producto, cada una por
    # su lado.
    ensure_demo_user(user_repository)

    app = FastAPI(title="VentaLibra")

    # 🔴 Colgado de la app para poder SOLTARLO. En produccion la app es una y
    # vive lo que vive el proceso, asi que da igual; en la suite cada test arma
    # una app nueva y este engine deja un pool vivo por test. Contra SQLite no
    # se notaba --un `StaticPool` de una conexion que se recolecta sola--, pero
    # contra PostgreSQL son conexiones TCP que se acumulan hasta
    # `max_connections`, y el sintoma son errores de conexion en tests que no
    # tienen nada que ver con el que los causo.
    app.state.auth_engine = auth_engine
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
    # Terminos y Condiciones del Servicio: la prueba de la aceptacion y lo que
    # enciende el gate. MISMA fabrica de sesiones que el SMTP y los usuarios --
    # la tabla tiene FK a `usuarios`, que no siempre vive en la base del dominio.
    #
    # 🔴 Sin esta linea el gate NO corta y la instancia no falla: se queda sin
    # gate, en silencio. Por eso cada producto tiene un test que lo prueba.
    app.state.terminos = TerminosRepository(auth_sessions)
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

    def _facturacion_habilitada() -> bool:
        """Mismo chequeo que `require_module("facturacion")` (`app.state.
        modules.is_enabled`), pero como `() -> bool` sin request: es lo que
        pide `build_cobro_de_ventas_router` (libracore v1.101.0) para su gate
        interno. Lee `app.state.modules` en cada llamada -- no una foto de
        cuando arrancó la app -- así que un cambio de plan a mitad de proceso
        se refleja en la próxima request, igual que el `Depends` que reemplaza."""
        return app.state.modules.is_enabled("facturacion")

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

    # 🔴 Los headers de seguridad. Se agrega **al final** a proposito: en
    # Starlette el ultimo middleware agregado es el mas externo, asi que asi
    # envuelve a todas las respuestas, incluidas las de error que devuelven los
    # de adentro.
    #
    # `CSP_SPA` y no la CSP por defecto: esa habilita `cdn.jsdelivr.net` para las
    # apps Jinja2, y este producto no carga nada externo. Ver libracore.
    app.add_middleware(SecurityHeadersMiddleware, csp=CSP_SPA)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    # `GET`/`PUT`/`DELETE /admin/smtp`. El router exige rol admin por dentro:
    # quien pueda escribir ahí puede redirigir a dónde salen los enlaces de
    # recuperación de contraseña de todos los usuarios.
    app.include_router(build_smtp_settings_router())
    # `POST /admin/smtp/probar`, del motor: abre la conexion, negocia TLS y
    # hace login.
    #
    # 🔑 Resuelve por el MISMO camino que los envios, y por eso el boton
    # significa algo: un endpoint que probara otra config diria "Conectado"
    # contra un servidor mientras los mails salen por otro. El gate va afuera
    # porque el router del motor no trae ninguno propio, y esto abre una
    # sesion SMTP con las credenciales del cliente.
    app.include_router(
        build_smtp_probe_router(lambda: resolver_smtp_config(auth_sessions)),
        dependencies=[Depends(require_admin)],
    )
    # `GET /terminos`, `POST /terminos/aceptar`, `GET /terminos/historial`.
    # NO se gatea desde afuera: es el unico camino para salir del gate.
    app.include_router(build_terminos_router())
    # `GET`/`POST`/`DELETE /admin/demo-codigos`, **solo en la demo**: es por
    # donde el backoffice emite los codigos que se le pasan a un interesado.
    # Exige rol admin o token de servicio por dentro, igual que el de SMTP.
    #
    # 🔴 El repositorio va contra `auth_sessions`, NO contra `sessions`: la
    # tabla de codigos vive en el mismo engine que `usuarios`, que en este
    # producto no es la base del dominio. Con el factory del dominio, la tabla
    # se crearia en el lugar equivocado y `POST /auth/demo` no encontraria
    # ningun codigo valido.
    #
    # 🔴 Y una instancia demo que llegue aca SIN el repositorio deja de dejar
    # entrar: el endpoint falla cerrado a proposito. Si un dia la demo devuelve
    # `503 demo access codes not configured`, lo que falta es esta linea.
    if demo_username():
        app.state.demo_codigos = DemoCodigoRepository(auth_sessions)
        app.include_router(build_demo_codigos_router())

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
    #
    # Contrato unico de la familia (libraauth v0.43.0, ADR-018): reemplaza a
    # `app/routers/users.py`, que antes se montaba sin `Depends` propio y
    # tomaba el gate de aca mismo -- por eso el guard sigue siendo
    # EXACTAMENTE el mismo (`require_admin_o_servicio`), pasado ahora como
    # `admin_guard=` de la factory en vez de en `dependencies=` del
    # `include_router`. `roles` sin pasar: el default de la factory
    # ("admin", "staff") es el mismo que ya usa `UserRepository` en este
    # producto (ver su construccion, arriba, "Sin `roles=`").
    #
    # 🔴 El `DELETE` ahora responde `204` (antes `200` con `{"ok": true}` --
    # ver README de libraauth, seccion "Router de usuarios unificado"). El
    # frontend de VentaLibra es el shim de `Usuarios` de `libra-ui`, que no
    # mira el cuerpo del borrado (llama `api.del()` y descarta la respuesta):
    # no hay nada que actualizar de este lado.
    app.include_router(build_users_router(
        prefix="/users",
        admin_guard=require_admin_o_servicio,
    ))
    app.include_router(
        # 🔴 `empresa_por_defecto` es el slug con el que `services/billing.py`
        # lee la configuracion de facturacion (`EMPRESA = "venta"`). En una
        # instancia que todavia no facturo no hay fila, y el primer guardado la
        # crea: sin esto la crearia como `default`, donde ese servicio no mira
        # nunca. El PUT contesta 200, la pantalla dice "Guardado", y el primer
        # comprobante falla con "ARCA no esta configurado".
        #
        # La pantalla compartida ya manda el slug, pero un script, el backoffice
        # o un curl no tienen por que saberlo. Ver LibraCore v1.63.0.
        build_arca_router(prefix="/config/arca", empresa_por_defecto=billing.EMPRESA),
        dependencies=admin_only + [Depends(require_module("facturacion"))],
    )
    # MercadoPago, del motor. Reemplaza al `GET`/`PUT /settings/mercadopago`
    # propio, que devolvia el ACCESS TOKEN EN CLARO en el JSON de una pantalla.
    #
    # Escribe las MISMAS claves de `config.json`, asi que `mp_qr` y el POS no se
    # enteran: no hay dato que migrar. Lo que suma es el token enmascarado, el
    # boton que le pregunta a MercadoPago si el token sirve, y una puerta para
    # desconectar la cuenta --con "vacio = no lo toques" no habia otra forma--.
    app.include_router(
        build_mp_config_router(),
        dependencies=admin_only + [Depends(require_module("facturacion"))],
    )
    app.include_router(catalog.router, dependencies=staff_or_admin)
    app.include_router(pricing.router, dependencies=staff_or_admin)
    app.include_router(locations.router, dependencies=staff_or_admin)
    app.include_router(stock.router, dependencies=staff_or_admin)
    # `GET /ventas/{id}/ticket` y `GET /pos/mp-estado` -- las dos lecturas
    # sueltas que quedaron cuando `/sales` se retiró entero en F4 (ADR-025,
    # ver `app/routers/ventas_extra.py`, que reemplaza a `app/routers/
    # sales.py`). Montado ANTES del catch-all de la SPA (`app/asgi.py`), así
    # que `/ventas/{id}/ticket` gana sobre `/{full_path:path}`.
    app.include_router(ventas_extra.router, dependencies=staff_or_admin)
    # `POST`/`GET /api/ventas`, detalle, anular y devolver -- la capa ERP de
    # LibraCommerce (F3 del plan post-P9, ver DECISIONS.md ADR-025). Sin
    # `require_module("ventas")`: catálogo, stock y venta/POS nunca se gatean
    # por plan en este producto (ADR-009), mismo criterio que `sales.router`.
    #
    # `exigir_turno=True`/`caja_con_turno=True`: sin turno abierto no se
    # registra la venta (mismo criterio que el `confirm_sale` legado), y el
    # arqueo por turno de este producto suma `caja_movimientos` por
    # `turno_id` -- sin esto daría siempre cero (ver `app/db_ventas.py`).
    app.include_router(
        build_ventas_router(
            conexion=lc_get_connection,
            usuario_actual=get_current_user,
            # 🔴 SIN `solo_admin`, a propósito. La factory sólo lo usa para
            # gatear `POST /{vid}/anular` y `.../devolver` (verificado en el
            # código instalado, `libracommerce/web/ventas_router.py`: el
            # `gate_anular` que arma con `solo_admin` no cuelga de ninguna
            # otra ruta). Hasta hoy, en este producto, un cajero (staff)
            # podía anular (`/sales/{id}/cancel`, retirado) y devolver
            # (`/sales/{id}/returns`, retirado): el router llevaba `staff_or_
            # admin` y el endpoint en sí sólo pedía `get_current_user`, sin
            # ningún chequeo de rol propio. Se conserva: **decisión del humano del
            # 2026-09-15** ("dejá anular y devolver para el cajero también"). No pasar
            # `require_admin` acá; lo custodia `test_un_staff_puede_anular_y_devolver`.
            opciones=OpcionesVentas(
                stock_habilitado=lambda: True,
                # 🔴 El default del motor busca `cliente_id` en `clients`
                # (LibraCore): acá ese id es un `party_id` de LibraCommerce
                # (D3, ADR-025), así que sin esto `cliente_nombre` quedaba
                # vacío en `POST /api/ventas` -- aunque la venta sí tuviera
                # cliente. Ver `app/ganchos.py::nombre_de_cliente`.
                nombre_de_cliente=nombre_de_cliente,
                hooks=GANCHOS,
                exigir_turno=True,
                caja_con_turno=True,
                # libracommerce v0.16.2: el modelo viejo (`/sales/{id}/confirm`,
                # retirado) rechazaba estos dos casos antes de confirmar --
                # ADR-020. Con las dos apagadas (el default) `POST /api/ventas`
                # registraba una venta 'pendiente' que nadie iba a acreditar
                # (pago que no cubre el total, sin QR) o un fiado sin cliente,
                # sin nadie a quien atribuirle la deuda.
                exigir_pago_completo=True,
                exigir_cliente_para_fiar=True,
            ),
        ),
        dependencies=staff_or_admin,
    )
    # `POST /api/ventas/{vid}/facturar`, `/mp-qr`, `GET /mp-status` -- dinero y
    # comprobantes, de LibraCore (D2: modelo de la familia, venta pendiente +
    # `acreditar_pago_qr`).
    #
    # 🔴 **Hasta libracore v1.100.0 esto montaba `/facturar` APARTE de
    # `/mp-qr`/`/mp-status`, con un `require_module("facturacion")` a mano**:
    # ADR-009 fija que facturar es lo único de esta app condicionado al plan
    # ("catálogo, stock y venta/POS nunca se gatean"), y las tres rutas salían
    # de la MISMA factory (un solo `APIRouter`) -- montar el router entero
    # bajo ese gate apagaba también el cobro por QR (que no factura nada por
    # sí solo) cuando el plan no incluye facturación, y no gatear nada dejaba
    # facturar con el módulo apagado (medido: `POST .../facturar` contestaba
    # 200 igual armando la app con `facturacion` en `False`).
    #
    # v1.101.0 mueve el gate ADENTRO de la factory: `facturacion_habilitada`
    # corre en cada request (no al armar el router), así que sirve el MISMO
    # 403 que daba el `require_module` de acá -- mismo código, misma
    # evaluación por request, sólo cambia el texto del mensaje -- y de paso
    # tapa `mp-status`, que auto-facturaba con la automática prendida aunque
    # el módulo estuviera apagado. Con esto en la factory, el split de router
    # deja de hacer falta: las tres rutas se montan juntas, sin gate externo.
    app.include_router(
        build_cobro_de_ventas_router(
            ventas=venta_facturacion.PUERTO, usuario_actual=get_current_user,
            facturacion_habilitada=_facturacion_habilitada,
        ),
        dependencies=staff_or_admin,
    )
    app.include_router(shifts.router, dependencies=staff_or_admin)
    # Cajas por sucursal: leer es de staff y admin (elige la caja al abrir
    # turno); el propio router agrega `require_admin` en lo que escribe. Va
    # ANTES de `medios.router` para que quede claro que no compite con su
    # `GET /api/cajas/medios-disponibles` -- este router no define esa ruta.
    app.include_router(cajas.router, dependencies=staff_or_admin)
    app.include_router(suppliers.router, dependencies=staff_or_admin)
    app.include_router(purchasing.router, dependencies=staff_or_admin)
    app.include_router(customers.router, dependencies=staff_or_admin)
    # El cajero cobra fiado en el mostrador, asi que no es admin-only.
    app.include_router(accounts.router, dependencies=staff_or_admin)
    # Los medios de pago de los selectores: los del motor, no una copia en el
    # frontend. Misma ruta que `build_cajas_router` de LibraCore, que es la que
    # pide `libra-ui/comercio/medios-pago`.
    app.include_router(medios.router, dependencies=staff_or_admin)
    # Cierre diario: acto registrado y numerado por sucursal (LibraCore
    # v1.101.0+, migración `0009_cierre_diario`, ya en la cadena de este pin).
    # `autorizar_cierre` no se pasa: el gate de ESTE producto para "admin o
    # cajero" es `staff_or_admin`, y ya cubre TODOS los endpoints del router
    # -- incluido `POST /cerrar` -- por el `dependencies=` de este mismo
    # `include_router`. `resolver_sucursal_nombre` cierra sobre `app.state`
    # (no sobre `conn`, la variable local) para seguir viendo la conexión
    # correcta después de un restore de backup (`_reabrir_conexion` la
    # reemplaza, no la muta).
    def _resolver_sucursal_nombre(sucursal_id: int | None) -> str:
        if sucursal_id is None:
            return ""
        loc = LocationService(app.state.conn).get(sucursal_id)
        return loc.name if loc else ""

    app.include_router(
        build_cierre_diario_router(
            usuario_actual=get_current_user,
            resolver_sucursal_nombre=_resolver_sucursal_nombre,
        ),
        dependencies=staff_or_admin,
    )
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
    # dominio y te quedan usuarios de otro momento, o al reves. Ver
    # `_instancia_de_respaldo` para el porque de `postgres_url`/
    # `postgres_extra` en vez de `bases=`.
    instancia = _instancia_de_respaldo(db_path, libracore_db_path, config_manager.LOGO_DIR)

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

    # Una sola variable para los dos routers: el enlace con la nube deja su
    # `rclone.conf` en `<backups_dir>/.resguardo/`, y el cron del host lo busca
    # AL LADO de los ZIP. Si cada router calculara su carpeta por su lado, un
    # cambio en uno solo dejaria el enlace hecho donde el cron no mira.
    backups_dir = _carpeta_de_backups(libracore_db_path)
    app.include_router(
        build_backup_router(
            instancia, backups_dir,
            cerrar_conexiones=_cerrar_conexion,
            reabrir_conexiones=_reabrir_conexion,
        ),
        dependencies=admin_only,
    )
    # Enlace de la copia externa con la nube del cliente (LibraCore v1.93.0):
    # `GET`/`DELETE /api/config/resguardo-externo/enlace`, `POST .../{proveedor}`
    # y `GET .../callback`. La pantalla vive en `/configuracion`, asi que
    # `volver_a` queda en el default del motor.
    #
    # 🔴 Admin Y add-on. `resguardo_externo` es un ADD-ON (`plans.ADDONS`): viene
    # apagado y se prende por instancia desde el backoffice. Sin la fila en
    # `modulos` el gate da 403, que el frontend (libra-ui) muestra como "sin
    # plan" -- ver `ModuleRepository.is_enabled`, que para un add-on trata la
    # falta de fila como apagado y no como prendido.
    app.include_router(
        build_resguardo_enlace_router(backups_dir, carpeta="Resguardo VentaLibra"),
        dependencies=admin_only + [Depends(require_module("resguardo_externo"))],
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
