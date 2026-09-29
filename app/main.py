"""VentaLibra app factory: abre la conexion SQLite unica de Fase 1 y monta
los routers con gating por rol (mismo patron que gestiolibra/medlibra:
dependencias en include_router, no por endpoint suelto)."""
import logging
import os

from fastapi import Depends, FastAPI
from libraauth.auditoria import agregar_middleware_de_usuario, build_logs_router
from libraauth.auth_events import AuthEventRepository
from libraauth.bootstrap import ensure_demo_user
from libraauth.demo_codigos import DemoCodigoRepository
from libraauth.migrar import exigir_schema_al_dia
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.secretos import SecretosRepository
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
from libracommerce.erp.reportes import puerto_de_reportes
from libracommerce.web.catalogo_router import (
    build_depositos_router,
    build_productos_router,
    build_stock_router,
    build_sucursales_router,
)
from libracommerce.web.compras_router import build_compras_router
from libracommerce.web.listas_router import (
    build_cliente_lista_router,
    build_listas_precio_router,
    build_precios_vigentes_router,
    build_quiebres_router,
)
from libracommerce.web.margen_router import build_margen_router
from libracommerce.web.planillas_router import build_actualizacion_precios_router
from libracommerce.web.promociones_router import (
    build_promociones_calculo_router,
    build_promociones_router,
)
from libracommerce.web.ventas_router import OpcionesVentas, build_ventas_router
from libracore import config_manager
from libracore.arca_router import build_arca_router
from libracore.caja_router import build_cajas_router, build_cierre_diario_router, build_turnos_router
from libracore.clientes_router import build_clientes_router
from libracore.config_router import (
    build_backup_router,
    build_empresa_admin_router,
    build_empresa_router,
)
from libracore.consultar_cuit_router import build_consultar_cuit_router
from libracore.cuenta_corriente_router import build_cuenta_corriente_router
from libracore.dashboard_router import build_dashboard_router
from libracore.db.core import es_url_postgres
from libracore.db.core import get_connection as lc_get_connection
from libracore.db.cuenta_corriente import VENTAS_LIBRACOMMERCE
from libracore.db.url_de_instancia import url_de_instancia
from libracore.egresos_router import build_egresos_router, build_proveedores_router
from libracore.libros_iva_router import build_libros_iva_export_router, build_libros_iva_router
from libracore.mp_config_router import build_mp_config_router
from libracore.recibos_router import build_recibos_router
from libracore.reportes_router import build_reportes_export_router, build_reportes_router
from libracore.resguardo_enlace import build_resguardo_enlace_router
from libracore.respaldo import Instancia
from libracore.security_headers import CSP_SPA, SecurityHeadersMiddleware
from libracore.smtp_router import build_smtp_probe_router
from libracore.tesoreria_router import build_tesoreria_router
from libracore.ventas_cobro_router import build_cobro_de_ventas_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import db, db_ventas, venta_facturacion
from .auth import (
    build_session_auth,
    get_current_user,
    require_admin,
    require_admin_o_servicio,
    require_staff,
    require_staff_lectura_admin_escritura,
    require_staff_precio_admin_resto,
)
from .cajas_ganchos import (
    cerrar_turno,
    enriquecer_turno_de,
    opciones_de_cajas,
    resumen_del_turno,
    usuario_actual,
    validar_apertura_de,
)
from .compras_ganchos import OPCIONES_DE_COMPRAS
from .cuenta_corriente_ganchos import OPCIONES as CC_OPCIONES
from .depositos_ganchos import OPCIONES_DE_STOCK, opciones_de_depositos, opciones_de_sucursales
from .ganchos import GANCHOS
from .modules_gate import require_module
from .productos_ganchos import OPCIONES_DE_CATALOGO
from .proveedores_guarda import no_eliminar_con_compras
from .routers import auth as auth_router
from .routers import (
    catalog,
    health,
    ventas_extra,
)
from .routers import (
    settings as settings_router,
)
from .services import billing
from .services import cajas as cajas_service
from .services.modules import ModuleRepository
from .services.sucursales import SucursalService
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


_log = logging.getLogger(__name__)


def migrar_secretos() -> dict:
    """Saca de `config.json` los secretos que quedaron en claro. Idempotente.

    Corre en cada arranque (dentro de `create_app()`, justo despues de
    enchufar el almacen), asi la migracion de una instancia viva **es su
    deploy**. Loguea NOMBRES de claves, nunca valores: un log con el secreto
    lo muda del archivo a una superficie peor, porque los logs se copian y se
    mandan.

    Si cifrar falla, el `config.json` **no se toca** -la instancia sigue
    cobrando con la credencial que tiene- y se loguea como error, que es lo
    que despues ve la sonda `auditar_secretos.py`.
    """
    informe = config_manager.migrar_secretos_al_almacen()
    if informe["migradas"]:
        _log.warning(
            "secretos movidos de config.json al almacen cifrado: %s",
            ", ".join(informe["migradas"]),
        )
    if informe["ya_estaban"]:
        _log.warning(
            "config.json tenia una copia vieja de %s; se vacio (el almacen manda)",
            ", ".join(informe["ya_estaban"]),
        )
    if informe["fallaron"]:
        _log.error(
            "no se pudieron cifrar y QUEDAN EN CLARO en config.json: %s",
            ", ".join(f"{k} ({v})" for k, v in informe["fallaron"].items()),
        )
    return informe


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
    # Cajas por sucursal (2026-09-16): toda sucursal (`branches`, del dominio)
    # tiene al menos una caja, idempotente. `billing.configure()` (via
    # `libracore.db.schema.init_core_schema()`) ya garantiza que exista AL
    # MENOS una caja default en la instancia, sin sucursal, para una base
    # nueva -- acá se reasigna esa caja huérfana al depósito default y se
    # completa lo que falte por sucursal. Corre en cada arranque; en el
    # segundo no crea nada (ver `app/services/cajas.py::
    # asegurar_cajas_de_todas`).
    # La sucursal y el depósito mínimos los garantiza `db.connect()` (ya corrió arriba).
    _sucursales_activas = SucursalService(conn).list()
    _sucursal_default = next((s for s in _sucursales_activas if s.is_default), None)
    cajas_service.asegurar_cajas_de_todas(
        [s.id for s in _sucursales_activas],
        (_sucursal_default or next(iter(_sucursales_activas), None)).id
        if _sucursales_activas else None,
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

    # 🔴 Los secretos de terceros de `config.json` -el access token y la firma
    # de webhook de MercadoPago; el camino de `email_smtp_password` esta
    # muerto en VentaLibra (0 usos de `email_smtp` en `app/`) pero se engancha
    # igual, por consistencia con el resto de la familia- dejan de vivir en
    # texto plano (libracore v1.108.0 + libraauth v0.46.0, 2026-09-17). Se
    # enchufa ACA porque es donde nace `auth_sessions`, que apunta a la base de
    # LibraCore/libraauth (NO la del dominio: VentaLibra es el caso que la
    # receta marca aparte). La tabla `secretos_instancia` la crea la revision
    # `0002` de la cadena de libraauth -no un `create_all`-, y
    # `exigir_schema_al_dia()` de arriba ya no deja levantar la app si esa
    # revision no se aplico.
    #
    # LibraCore no importa libraauth: recibe el almacen. Por eso el enganche es
    # del producto, que es el unico que tiene los dos paquetes.
    #
    # Desde aca, `config_manager.load()` sigue devolviendo el secreto en claro
    # a sus consumidores, pero lo trae de la base cifrada y no del archivo. La
    # migracion de lo que ya estaba en el JSON corre en `migrar_secretos()`,
    # llamada mas abajo.
    _secretos = SecretosRepository(auth_sessions)
    config_manager.usar_almacen_de_secretos(_secretos)
    migrar_secretos()

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
    app.state.secretos = _secretos
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
                hooks=GANCHOS,
                exigir_turno=True,
                caja_con_turno=True,
                # Las promociones vigentes se calculan en el servidor con las líneas que llegan y su
                # ahorro se suma al descuento de la venta (libracommerce v0.25.0, ADR-014; ADR-043).
                promociones=True,
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
    # Cajas y turnos: los routers del motor (`libracore.caja_router`), los mismos de Contalibra y Restolibra,
    # con las reglas de VentaLibra como ganchos (`app/cajas_ganchos.py`, ADR-032). Reemplazan a `/shifts` y al
    # ABM propio de `/api/cajas`. Leer es de staff y admin (se elige la caja al abrir turno); escribir en las
    # cajas es de admin, lo dice `autorizar_escritura`. Las sucursales se leen de `app.state.conn` en cada
    # pedido: la app la reemplaza al restaurar un respaldo.
    def _sucursales() -> SucursalService:
        return SucursalService(app.state.conn)

    app.include_router(
        build_turnos_router(
            usuario_actual=usuario_actual, resumen_turno=resumen_del_turno, cerrar_turno=cerrar_turno,
            validar_apertura=validar_apertura_de(_sucursales), enriquecer=enriquecer_turno_de(_sucursales),
        ),
        dependencies=staff_or_admin,
    )
    app.include_router(build_cajas_router(opciones=opciones_de_cajas(_sucursales)), dependencies=staff_or_admin)
    # Sucursales/depósitos y stock (fase 6, ADR-033; jerarquía, 2026-09-28): los routers del motor con las reglas de
    # VentaLibra como ganchos (`app/depositos_ganchos.py`). Reemplazan a `/locations` y a `/stock`. Una sucursal es
    # una entidad propia y el stock vive en sus depósitos. Leer y transferir es de staff y admin; crear, editar,
    # predeterminar y borrar, de admin (`autorizar_escritura`).
    app.include_router(
        build_sucursales_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual,
            opciones=opciones_de_sucursales(_sucursales),
        ),
        dependencies=staff_or_admin,
    )
    app.include_router(
        build_depositos_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=opciones_de_depositos(),
        ),
        dependencies=staff_or_admin,
    )
    app.include_router(
        build_stock_router(conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_STOCK),
        dependencies=staff_or_admin,
    )
    # Productos (fase 7, ADR-034): el router del motor con las reglas de VentaLibra como ganchos
    # (`app/productos_ganchos.py`). Reemplaza a `/catalog/items*` (alta, edición, códigos, variantes y escaneo);
    # `/catalog/units` y `/catalog/categories` siguen siendo la administración de unidades y categorías.
    app.include_router(
        build_productos_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_CATALOGO,
        ),
        dependencies=staff_or_admin,
    )
    # Listas de precio (fase 7): CRUD, ítems, ajuste porcentual e importación; quiebres por cantidad; y los precios
    # con vigencia y por sucursal (`/api/listas-precio/...`). Configurar precios es de admin. Reemplazan a
    # `/pricing`, que ninguna pantalla usaba. Las listas se LEEN también con rol staff (la card «Lista de precios»
    # de la ficha del cliente las carga para el selector); crear, editar y borrar sigue siendo de admin.
    app.include_router(
        build_listas_precio_router(conexion=lc_get_connection),
        dependencies=[Depends(require_staff_lectura_admin_escritura)],
    )
    # El POS le pide el precio de cada línea a la lista predeterminada (`GET .../{id}/precio`, que vive
    # en el router de quiebres): esa ruta se lee también con staff; los quiebres y todo lo que escribe
    # siguen siendo de admin (`require_staff_precio_admin_resto`).
    app.include_router(
        build_quiebres_router(conexion=lc_get_connection),
        dependencies=[Depends(require_staff_precio_admin_resto)],
    )
    app.include_router(build_precios_vigentes_router(conexion=lc_get_connection), dependencies=admin_only)
    # Promociones (roadmap de producto, 2026-09-28, ADR-043): «llevá N pagá M» y combos. Las reglas se
    # cargan como admin; el cajero sólo calcula qué aplica a su carrito (`POST /calcular`, que sólo lee).
    app.include_router(build_promociones_router(conexion=lc_get_connection), dependencies=admin_only)
    app.include_router(build_promociones_calculo_router(conexion=lc_get_connection), dependencies=staff_or_admin)
    # Actualización masiva de precios (roadmap de producto, 2026-09-28): sube la planilla de un
    # proveedor y recalcula el precio de venta manteniendo el margen de cada producto -- primer
    # ítem del roadmap, no una adopción de Contalibra/Restolibra (no existía en ningún producto de
    # la familia). De admin, mismo criterio que Listas de precio.
    app.include_router(
        build_actualizacion_precios_router(conexion=lc_get_connection, usuario_actual=usuario_actual),
        dependencies=admin_only,
    )
    # Proveedores: el router del motor (`libracore.egresos_router`), el mismo de Contalibra y Restolibra
    # sobre la tabla `proveedores` (ADR-030). Reemplaza a `/suppliers`. La baja se guarda: el motor sólo
    # mira los egresos, y acá un proveedor con compras no se elimina (`app/proveedores_guarda.py`).
    app.include_router(
        build_proveedores_router(), dependencies=[*staff_or_admin, Depends(no_eliminar_con_compras)],
    )
    # Compras (fase 9, ADR-036): el router del motor con la numeración y la traducción de `proveedor_id` de
    # este producto como ganchos (`app/compras_ganchos.py`). Reemplaza a `/purchase-orders`/`/purchase-receipts`
    # propios; el motor los monta bajo `/api` (antes no lo tenían, inconsistente con el resto de la familia).
    app.include_router(
        build_compras_router(conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_COMPRAS),
        dependencies=staff_or_admin,
    )
    # Clientes: el router del motor (`libracore.clientes_router`), el mismo que montan Contalibra y
    # Restolibra sobre la tabla `clients`. Reemplaza a `/customers` (ADR-029). Permisos como los del
    # resto del POS: staff o admin.
    app.include_router(build_clientes_router(), dependencies=staff_or_admin)
    # Lista de precios asignada a un cliente (ADR-010 de libracommerce, extraído del add-on
    # mayorista de Contalibra): a diferencia de ahí, acá no hay add-on que gatee -- listas de
    # precio es un módulo siempre libre (fase 7) -- así que se monta con el mismo permiso que el
    # resto de la ficha del cliente. Prende `conListaDePrecio` en `ClienteDetalle.tsx`.
    app.include_router(build_cliente_lista_router(conexion=lc_get_connection), dependencies=staff_or_admin)
    # Cuenta corriente: el router del motor (`libracore.cuenta_corriente_router`), el mismo de Contalibra y
    # Restolibra, con las reglas de cobro de este producto como `OpcionesCuentaCorriente` (turno obligatorio,
    # caja del turno, baja de pago que anula el movimiento de caja; ver `app/cuenta_corriente_ganchos.py`).
    # Reemplaza a `/accounts` y a `/api/cuenta-corriente` propios (ADR-031). El cajero cobra fiado en el
    # mostrador, asi que no es admin-only; la baja de un pago sí lo es (`solo_admin`).
    app.include_router(
        build_cuenta_corriente_router(
            usuario_actual=get_current_user, solo_admin=require_admin,
            origen=VENTAS_LIBRACOMMERCE, con_recibos=True, opciones=CC_OPCIONES,
        ),
        dependencies=staff_or_admin,
    )
    # Recibos (fase 14, ADR-040): el router del motor, extraído de Contalibra. Gana de paso listar/detalle,
    # emitir de factura/venta (además de la cobranza que ya llamaban las pantallas de cuenta corriente del
    # kit) y anular (sólo admin, `solo_admin`). Único gancho: `get_venta` -- las ventas de mostrador de
    # este producto viven en `sales` de LibraCommerce, no en `ventas` del propio esquema del motor.
    app.include_router(
        build_recibos_router(usuario_actual=get_current_user, solo_admin=require_admin, get_venta=db_ventas.get_venta),
        dependencies=staff_or_admin,
    )
    # Consulta de CUIT en ARCA (fase 14, ADR-040): el router del motor, extraído de Contalibra. Activa
    # `conConsultaCuit` en las pantallas de Clientes del kit (ver frontend/src/pages/Clientes*.tsx).
    app.include_router(build_consultar_cuit_router(usuario_actual=get_current_user), dependencies=staff_or_admin)
    # Tesorería (fase 10, ADR-037): el router del motor, sin ganchos -- las cuentas bancarias y sus
    # movimientos son un problema de cualquier comercio, no del modelo de venta de este producto (`libracore`
    # ya trae la tabla, vacía hasta ahora). De admin: es la única instancia de la familia que la deja libre
    # en todos los planes (no gateada por `require_module`, a diferencia de Contalibra).
    app.include_router(build_tesoreria_router(usuario_actual=get_current_user), dependencies=admin_only)
    # Egresos (fase 11, ADR-038): el router del motor, sin ganchos. Complementa a Compras -- Compras
    # repone inventario, Egresos es la contabilidad del pago (alquiler, sueldos, servicios, y también un
    # pago a proveedor que Compras no cubre). De staff y admin, igual que Compras y Proveedores (mismo
    # criterio de Contalibra); libre en todos los planes, como Tesorería. La baja de un proveedor con
    # egresos ya la guarda el motor (`ValueError` -> 422 en `build_proveedores_router`); la de un proveedor
    # con compras la sigue guardando `app/proveedores_guarda.py`.
    app.include_router(build_egresos_router(usuario_actual=get_current_user), dependencies=staff_or_admin)
    # Libros IVA (fase 12, ADR-038): ventas ya funciona (las facturas son la tabla `facturas` del motor,
    # que este producto ya escribe desde `venta_facturacion`); compras se completa con Egresos, recién
    # adoptado arriba. De admin, como en Contalibra: es un reporte contable-fiscal. Los cuatro exports
    # REGINFO van FUERA de `/api` (por eso `vite.config.ts` los suma a `RUTAS_PROPIAS_DEL_BACKEND`, no a
    # `API_PATHS`: `/libros-iva` a secas sigue siendo la pantalla de la SPA).
    app.include_router(build_libros_iva_router(), dependencies=admin_only)
    app.include_router(build_libros_iva_export_router(solo_admin=require_admin))
    # Dashboard (fase 13, ADR-039): a diferencia de Tesorería/Egresos/Libros IVA, éste sí es el módulo que
    # `plans.py` venía anticipando desde antes de construirse ("Premium queda con margen para dashboard").
    # `sin_fiado=True`: mismo motivo que Reportes (fase 8) -- sin esto, "Cobrado del mes" y "Saldo de caja"
    # cuentan una venta a cuenta corriente como plata ya entrada. De admin, como Reportes y Caja por medio.
    app.include_router(
        build_dashboard_router(usuario_actual=get_current_user, sin_fiado=True),
        dependencies=admin_only + [Depends(require_module("dashboard"))],
    )
    # Cierre diario: acto registrado y numerado por sucursal (LibraCore
    # v1.101.0+, migración `0009_cierre_diario`, ya en la cadena de este pin).
    # `autorizar_cierre` no se pasa: el gate de ESTE producto para "admin o
    # cajero" es `staff_or_admin`, y ya cubre TODOS los endpoints del router
    # -- incluido `POST /cerrar` -- por el `dependencies=` de este mismo
    # `include_router`. `resolver_sucursal_nombre` cierra sobre `app.state`
    # (no sobre `conn`, la variable local) para seguir viendo la conexión
    # correcta después de un restore de backup (`_reabrir_conexion` la
    # reemplaza, no la muta).
    # `autorizar_reabrir` (LibraCore v1.107.0, "Reabrir día") SÍ se pasa:
    # reabrir un día ya cerrado es más sensible que cerrarlo, así que se le
    # exige `require_admin` en vez de heredar el `staff_or_admin` del módulo
    # -- sin este parámetro el endpoint `POST /{id}/reabrir` ni se monta.
    def _resolver_sucursal_nombre(sucursal_id: int | None) -> str:
        if sucursal_id is None:
            return ""
        sucursal = SucursalService(app.state.conn).get(sucursal_id)
        return sucursal.name if sucursal else ""

    app.include_router(
        build_cierre_diario_router(
            usuario_actual=get_current_user,
            resolver_sucursal_nombre=_resolver_sucursal_nombre,
            autorizar_reabrir=Depends(require_admin),
        ),
        dependencies=staff_or_admin,
    )
    # Reportes (fase 8, ADR-035): el router del motor sobre las ventas de LibraCommerce (`libracommerce.erp.reportes`), el mismo que
    # monta Contalibra, con dos variantes: una venta anulada o pendiente de cobro no es una venta (`solo_confirmadas`) y **fiar no es
    # cobrar** (`sin_fiado`: la cuenta corriente no es ingreso de caja, como en el arqueo del turno). Reemplaza a `/reports/*`. Sólo
    # admin, como antes; los exports CSV (`/reportes/export/*`) van con la sesión por cookie de la SPA.
    reportes = puerto_de_reportes(lc_get_connection, solo_confirmadas=True, sin_fiado=True)
    app.include_router(
        build_reportes_router(reportes=reportes, sin_fiado=True), dependencies=admin_only,
    )
    app.include_router(
        build_reportes_export_router(sesion=require_admin, reportes=reportes, sin_fiado=True),
    )
    # Margen y rotación (tanda 1 del roadmap de producto, ADR-046): el router del motor (`libracommerce.web.margen_router`, sólo
    # lectura sobre las líneas de venta: ingreso, costo, margen y unidades por producto y por período, con export CSV). Sólo admin,
    # como Reportes: el costo y el margen son del dueño, no del cajero. Una venta anulada o pendiente de cobro no cuenta y las
    # devoluciones se restan (lo resuelve el motor); fiar SÍ es vender, así que acá no hay `sin_fiado`. Los CSV cuelgan del mismo
    # prefijo, bajo `/api`: no hace falta una ruta más en el proxy de Vite.
    #
    # 🔴 **Sin gate de plan, a propósito (decisión de negocio pendiente).** `require_module("margen")` haría falta si el margen fuera
    # de un plan (`plans.py` anticipa que Premium "tiene margen para reportes"); no se asignó ninguno porque no lo decidió el humano.
    # Mientras tanto queda disponible para todo admin, igual que Reportes. Para gatearlo: sumar `"margen"` al plan elegido en
    # `plans.py` y `Depends(require_module("margen"))` en este `dependencies=`.
    app.include_router(build_margen_router(conexion=lc_get_connection), dependencies=admin_only)
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
