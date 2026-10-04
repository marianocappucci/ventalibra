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
from libracommerce.web.reposicion_router import (
    build_reposicion_minimos_router,
    build_reposicion_ordenes_router,
    build_reposicion_parametros_router,
    build_reposicion_router,
)
from libracommerce.web.vencimientos_router import build_vencimientos_escritura_router, build_vencimientos_router
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
from libracore.facturas_router import build_nota_de_credito_router
from libracore.libros_iva_router import build_libros_iva_export_router, build_libros_iva_router
from libracore.mp_config_router import build_mp_config_router
from libracore.recibos_router import build_recibos_router
from libracore.reportes_router import build_reportes_export_router, build_reportes_router
from libracore.resguardo_enlace import build_resguardo_enlace_router
from libracore.respaldo import Instancia
from libracore.security_headers import CSP_SPA, SecurityHeadersMiddleware
from libracore.smtp_router import build_smtp_probe_router
from libracore.tema_router import build_tema_admin_router, build_tema_router
from libracore.tesoreria_router import build_tesoreria_router
from libracore.ventas_cobro_router import build_cobro_de_ventas_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import db, db_ventas, venta_facturacion
from .auth import (
    build_session_auth,
    get_current_user,
)
from .cajas_ganchos import (
    cerrar_turno,
    enriquecer_turno_de,
    opciones_de_cajas,
    resumen_del_turno,
    solo_su_turno_o_todos,
    usuario_actual,
    usuario_de_turnos,
    validar_apertura_de,
)
from .compras_ganchos import OPCIONES_DE_COMPRAS, proveedor_del_producto, resolver_proveedor_del_producto
from .costos import SinCostos
from .cuenta_corriente_ganchos import OPCIONES as CC_OPCIONES
from .depositos_ganchos import (
    OPCIONES_DE_STOCK,
    gate_de_transferencias,
    opciones_de_depositos,
    opciones_de_sucursales,
)
from .ganchos import GANCHOS
from .modules_gate import require_module
from .permisos import (
    ROLES,
    requiere,
    requiere_o_servicio,
    requiere_segun_metodo,
    requiere_segun_ruta,
)
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

    # El vocabulario de roles es el de `app/permisos.py` (ADR-049): admin, encargado, vendedor, cajero, deposito y el
    # `staff` heredado. El MISMO `ROLES` se le pasa al router de usuarios, para que alta y edición validen contra lo
    # mismo que el repositorio (y un rol inválido sea 422 y no un 500).
    user_repository = UserRepository(auth_sessions, roles=ROLES)
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

    # Sin `costos.ver` no se ve el costo (ADR-049): filtra las RESPUESTAS de catálogo, stock y compras. Por prefijo de
    # ruta y a prueba de olvidos: ver `app/costos.py`.
    app.add_middleware(SinCostos)

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
        dependencies=[Depends(requiere("config"))],
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

    # 🔴 Los permisos de cada router son CAPACIDADES (`app/permisos.py`, ADR-049), no «admin» o «staff». Un router
    # se monta con `dependencies=[Depends(requiere("..."))]`; si mezcla rutas de gente distinta, con
    # `requiere_segun_metodo` o `requiere_segun_ruta`. La matriz rol -> capacidad vive en `permisos.py`, no acá.
    # `tests/test_roles_matriz.py` falla si aparece una ruta que la tabla no conoce: un router montado sin guarda
    # se nota en la suite.

    # Usuarios acepta ADEMAS el token de servicio (libraauth v0.7.0): es lo
    # unico que el backoffice de la suite necesita y que no puede salir del
    # motor, porque el router de usuarios es propio de cada producto.
    #
    # Deliberadamente solo este: el resto de los routers siguen
    # exigiendo sesion de un usuario del producto. El backoffice no tiene por
    # que poder tocar el resto del dominio, y usar `requiere_o_servicio` en otro
    # router seria ampliar el permiso sin necesidad.
    #
    # Contrato unico de la familia (libraauth v0.43.0, ADR-018): reemplaza a
    # `app/routers/users.py`, que antes se montaba sin `Depends` propio y
    # tomaba el gate de aca mismo -- por eso el guard sigue siendo
    # EXACTAMENTE el mismo (admin o token de servicio; ahora es
    # `requiere_o_servicio("usuarios.admin")`, la misma decision expresada como
    # capacidad), pasado como `admin_guard=` de la factory en vez de en
    # `dependencies=` del `include_router`.
    #
    # 🔴 Roles nuevos (ADR-049): `roles=ROLES` es el MISMO vocabulario con el que
    # se construyo `UserRepository` (arriba); un rol fuera de la lista es 422 en el
    # alta y en la edicion. La factory ya trae las protecciones que este cambio
    # necesita y NO se duplican aca: no dejar la instancia sin admin activo, no
    # borrarse ni desactivarse a uno mismo y no sacarse el rol de admin a uno mismo.
    #
    # 🔴 El `DELETE` ahora responde `204` (antes `200` con `{"ok": true}` --
    # ver README de libraauth, seccion "Router de usuarios unificado"). El
    # frontend de VentaLibra es el shim de `Usuarios` de `libra-ui`, que no
    # mira el cuerpo del borrado (llama `api.del()` y descarta la respuesta):
    # no hay nada que actualizar de este lado.
    app.include_router(build_users_router(
        prefix="/users",
        roles=ROLES,
        admin_guard=requiere_o_servicio("usuarios.admin"),
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
        dependencies=[Depends(requiere("config")), Depends(require_module("facturacion"))],
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
        dependencies=[Depends(requiere("config")), Depends(require_module("facturacion"))],
    )
    # `/catalog/categories` y `/catalog/units`: leerlas es de todos los roles (las pantallas de productos las cargan
    # para sus selectores); crear y editar es configuración (`catalogo.configurar`: admin, y el staff heredado que ya
    # podía; decisión de criterio de ADR-049, viven en Configuración y cambian el vocabulario de todo el local).
    app.include_router(
        catalog.router,
        dependencies=[Depends(requiere_segun_metodo(lectura="catalogo.ver", escritura="catalogo.configurar"))],
    )
    # `GET /ventas/{id}/ticket` y `GET /pos/mp-estado` -- las dos lecturas
    # sueltas que quedaron cuando `/sales` se retiró entero en F4 (ADR-025,
    # ver `app/routers/ventas_extra.py`, que reemplaza a `app/routers/
    # sales.py`). Montado ANTES del catch-all de la SPA (`app/asgi.py`), así
    # que `/ventas/{id}/ticket` gana sobre `/{full_path:path}`.
    app.include_router(ventas_extra.router, dependencies=[Depends(requiere("ventas.pos"))])
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
            # `require_admin` acá (ni una capacidad más estricta que `ventas.pos`); lo custodia
            # `test_un_staff_puede_anular_y_devolver`.
            opciones=OpcionesVentas(
                stock_habilitado=lambda: True,
                hooks=GANCHOS,
                exigir_turno=True,
                caja_con_turno=True,
                # Las promociones vigentes se calculan en el servidor con las líneas que llegan y su
                # ahorro se suma al descuento de la venta (libracommerce v0.25.0, ADR-014; ADR-043).
                promociones=True,
                # La venta guarda el costo vigente de cada línea (`sale_items.unit_cost_snapshot` = `default_cost` de
                # ese momento; NULL si el producto no tiene costo, y los servicios no llevan) para que el margen deje
                # de ser estimado en las ventas nuevas (libracommerce v0.27.0, ADR-016 del motor; ADR-050). Sin
                # backfill: las ventas anteriores siguen en NULL y el reporte de margen las marca `costo_estimado`.
                guardar_costo=True,
                # libracommerce v0.16.2: el modelo viejo (`/sales/{id}/confirm`,
                # retirado) rechazaba estos dos casos antes de confirmar --
                # ADR-020. Con las dos apagadas (el default) `POST /api/ventas`
                # registraba una venta 'pendiente' que nadie iba a acreditar
                # (pago que no cubre el total, sin QR) o un fiado sin cliente,
                # sin nadie a quien atribuirle la deuda.
                exigir_pago_completo=True,
                exigir_cliente_para_fiar=True,
                # Vencimientos y lotes (ADR-053, libracommerce v0.30.0): la venta de un producto marcado «vence» sale por FEFO
                # (eso no depende de esta opción) y, prendida ésta, `POST /api/ventas` y `GET /api/ventas/{id}` agregan la clave
                # `avisos` (lote vencido, por vencer, faltante sin lote) sólo si hay alguno, y existe `POST /api/ventas/plan-salida`
                # (lectura pura: de qué lote saldría cada línea) para que el POS confirme antes de cobrar. Las dos rutas cuelgan
                # del router de ventas, así que heredan `ventas.pos`: quien puede vender puede consultarlo.
                con_avisos_de_vencimiento=True,
            ),
        ),
        dependencies=[Depends(requiere("ventas.pos"))],
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
        dependencies=[Depends(requiere("ventas.pos"))],
    )
    # La nota de crédito de una factura con CAE (`libracore.facturas_router`, ADR-017 del motor): SOLO esa ruta, no
    # los otros once endpoints de comprobantes (alta manual, cobro, borrado), que este producto no usa y que llevarían
    # el cobro sin `turno_id`. La necesita `anular_venta`, que desde libracommerce v0.41.0 no anula una venta con
    # factura CAE sin nota. No toca la caja. Sólo admin: `facturas.nota_credito`.
    app.include_router(
        build_nota_de_credito_router(
            usuario_actual=get_current_user, solo_admin=requiere("facturas.nota_credito"),
        ),
    )
    # Cajas y turnos: los routers del motor (`libracore.caja_router`), los mismos de Contalibra y Restolibra,
    # con las reglas de VentaLibra como ganchos (`app/cajas_ganchos.py`, ADR-032). Reemplazan a `/shifts` y al
    # ABM propio de `/api/cajas`. Leer las cajas y llevar el turno propio es de quien tiene `caja.propia` (se elige la
    # caja al abrir turno); escribir en las cajas es `caja.admin` (sólo admin), lo dice `requiere_segun_metodo` y también
    # `autorizar_escritura`. Los turnos ajenos los ve `turnos.todos` (`usuario_de_turnos`). Las sucursales se leen de
    # `app.state.conn` en cada pedido: la app la reemplaza al restaurar un respaldo.
    def _sucursales() -> SucursalService:
        return SucursalService(app.state.conn)

    app.include_router(
        build_turnos_router(
            usuario_actual=usuario_de_turnos, resumen_turno=resumen_del_turno, cerrar_turno=cerrar_turno,
            validar_apertura=validar_apertura_de(_sucursales), enriquecer=enriquecer_turno_de(_sucursales),
        ),
        dependencies=[Depends(requiere("caja.propia"))],
    )
    app.include_router(
        build_cajas_router(opciones=opciones_de_cajas(_sucursales)),
        dependencies=[Depends(requiere_segun_metodo(lectura="caja.propia", escritura="caja.admin"))],
    )
    # Sucursales/depósitos y stock (fase 6, ADR-033; jerarquía, 2026-09-28): los routers del motor con las reglas de
    # VentaLibra como ganchos (`app/depositos_ganchos.py`). Reemplazan a `/locations` y a `/stock`. Una sucursal es
    # una entidad propia y el stock vive en sus depósitos. Leer es de todos los roles (`catalogo.ver`/`stock.ver`);
    # transferir, de quien mueve mercadería (`stock.transferir`); crear, editar, predeterminar y borrar, de admin
    # (`sucursales.admin`, en la guarda del router y también en `autorizar_escritura`).
    # Un solo local sin el módulo `multisucursal` (plan Básico, ADR-048): el alta de una segunda sucursal y la transferencia
    # entre sucursales dan 403 (`app/depositos_ganchos.py`). `_modulos` lee `app.state.modules` en cada pedido, como
    # `require_module` y `_facturacion_habilitada`: un cambio de plan a mitad de proceso se ve en el pedido siguiente.
    def _modulos():
        return app.state.modules

    app.include_router(
        build_sucursales_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual,
            opciones=opciones_de_sucursales(_sucursales, _modulos),
        ),
        dependencies=[Depends(requiere_segun_metodo(lectura="catalogo.ver", escritura="sucursales.admin"))],
    )
    app.include_router(
        build_depositos_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=opciones_de_depositos(),
        ),
        dependencies=[
            Depends(requiere_segun_ruta(
                ("GET", r"/api/depositos(/.*)?", "stock.ver"),
                ("POST", r"/api/depositos/transferir", "stock.transferir"),
                por_defecto="sucursales.admin",
            )),
            Depends(gate_de_transferencias(lc_get_connection, _modulos)),
        ],
    )
    app.include_router(
        build_stock_router(conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_STOCK),
        # Mirar cuánto hay (y el historial) es de todos los roles; ajustar, de quien maneja la mercadería.
        dependencies=[Depends(requiere_segun_metodo(lectura="stock.ver", escritura="stock.ajustar"))],
    )
    # Productos (fase 7, ADR-034): el router del motor con las reglas de VentaLibra como ganchos
    # (`app/productos_ganchos.py`). Reemplaza a `/catalog/items*` (alta, edición, códigos, variantes y escaneo);
    # `/catalog/units` y `/catalog/categories` siguen siendo la administración de unidades y categorías.
    app.include_router(
        build_productos_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_CATALOGO,
        ),
        # Consultar productos es del mostrador y del depósito; darlos de alta, editarlos o bajarlos, del encargado.
        dependencies=[Depends(requiere_segun_metodo(lectura="catalogo.ver", escritura="productos.escribir"))],
    )
    # Listas de precio (fase 7): CRUD, ítems, ajuste porcentual e importación; quiebres por cantidad; y los precios
    # con vigencia y por sucursal (`/api/listas-precio/...`). Escribir precios es `precios.escribir` (admin y
    # encargado). Reemplazan a `/pricing`, que ninguna pantalla usaba. Las listas se LEEN con `precios.consultar`
    # (la card «Lista de precios» de la ficha del cliente las carga para el selector, y el POS pide el precio de
    # cada línea); crear, editar y borrar es de `precios.escribir`.
    app.include_router(
        build_listas_precio_router(conexion=lc_get_connection),
        dependencies=[Depends(requiere_segun_metodo(lectura="precios.consultar", escritura="precios.escribir"))],
    )
    # El POS le pide el precio de cada línea a la lista predeterminada (`GET .../{id}/precio`, que vive
    # en el router de quiebres): esa ruta se lee con `precios.consultar`; los quiebres y todo lo que escribe
    # siguen siendo de `precios.escribir`.
    #
    # 🔴 Sin esta separación el cajero recibía 403 y el POS caía al precio plano **en silencio**: lo custodia
    # `test_promociones.py` y la tabla de `test_roles_matriz.py`.
    app.include_router(
        build_quiebres_router(conexion=lc_get_connection),
        dependencies=[Depends(requiere_segun_ruta(
            ("GET", r"/api/listas-precio/\d+/precio", "precios.consultar"),
            por_defecto="precios.escribir",
        ))],
    )
    app.include_router(
        build_precios_vigentes_router(conexion=lc_get_connection), dependencies=[Depends(requiere("precios.escribir"))],
    )
    # Promociones (roadmap de producto, 2026-09-28, ADR-043): «llevá N pagá M» y combos. Las reglas las carga quien
    # escribe precios (`precios.escribir`); quien vende sólo calcula qué aplica a su carrito (`POST /calcular`, que
    # sólo lee: `ventas.pos`).
    app.include_router(build_promociones_router(conexion=lc_get_connection), dependencies=[Depends(requiere("precios.escribir"))])
    app.include_router(
        build_promociones_calculo_router(conexion=lc_get_connection), dependencies=[Depends(requiere("ventas.pos"))],
    )
    # Actualización masiva de precios (roadmap de producto, 2026-09-28): sube la planilla de un
    # proveedor y recalcula el precio de venta manteniendo el margen de cada producto -- primer
    # ítem del roadmap, no una adopción de Contalibra/Restolibra (no existía en ningún producto de
    # la familia). De `precios.escribir`, mismo criterio que Listas de precio.
    app.include_router(
        build_actualizacion_precios_router(conexion=lc_get_connection, usuario_actual=usuario_actual),
        dependencies=[Depends(requiere("precios.escribir"))],
    )
    # Proveedores: el router del motor (`libracore.egresos_router`), el mismo de Contalibra y Restolibra
    # sobre la tabla `proveedores` (ADR-030). Reemplaza a `/suppliers`. La baja se guarda: el motor sólo
    # mira los egresos, y acá un proveedor con compras no se elimina (`app/proveedores_guarda.py`). Leerlos es de
    # `compras.ver` (también el depósito, que los lee); escribirlos, de `compras.escribir`.
    app.include_router(
        build_proveedores_router(),
        dependencies=[
            Depends(requiere_segun_metodo(lectura="compras.ver", escritura="compras.escribir")),
            Depends(no_eliminar_con_compras),
        ],
    )
    # Compras (fase 9, ADR-036): el router del motor con la numeración y la traducción de `proveedor_id` de
    # este producto como ganchos (`app/compras_ganchos.py`). Reemplaza a `/purchase-orders`/`/purchase-receipts`
    # propios; el motor los monta bajo `/api` (antes no lo tenían, inconsistente con el resto de la familia).
    #
    # Leer es de `compras.ver`; emitir órdenes de compra, de `compras.escribir`; y la RECEPCIÓN de mercadería
    # (`/api/purchase-receipts`: crear, cargar líneas, confirmar) es de `compras.recibir` (encargado y staff heredado, más
    # admin), NO del depósito: confirmar una recepción fija el costo del producto (`default_cost`) y el depósito no maneja plata.
    app.include_router(
        build_compras_router(conexion=lc_get_connection, usuario_actual=usuario_actual, opciones=OPCIONES_DE_COMPRAS),
        dependencies=[Depends(requiere_segun_ruta(
            ("GET", r"/api/purchase-(orders|receipts)(/.*)?", "compras.ver"),
            ("POST", r"/api/purchase-receipts(/.*)?", "compras.recibir"),
            por_defecto="compras.escribir",
        ))],
    )
    # Clientes: el router del motor (`libracore.clientes_router`), el mismo que montan Contalibra y
    # Restolibra sobre la tabla `clients`. Reemplaza a `/customers` (ADR-029). Leer es de `clientes.ver`; el ALTA
    # (`POST /api/clientes`) de `clientes.alta`, que también tiene el cajero; el resto de lo que escribe (editar,
    # activar, alias de facturación, auto-facturar), de `clientes.escribir`.
    app.include_router(
        build_clientes_router(),
        dependencies=[Depends(requiere_segun_ruta(
            ("GET", r"/api/clientes(/.*)?", "clientes.ver"),
            ("POST", r"/api/clientes", "clientes.alta"),
            por_defecto="clientes.escribir",
        ))],
    )
    # Lista de precios asignada a un cliente (ADR-010 de libracommerce, extraído del add-on
    # mayorista de Contalibra): a diferencia de ahí, acá no hay add-on que gatee -- listas de
    # precio es un módulo siempre libre (fase 7) -- así que se monta con el mismo permiso que el
    # resto de la ficha del cliente. Prende `conListaDePrecio` en `ClienteDetalle.tsx`. Verla es de `clientes.ver`;
    # ASIGNARLA es una decisión de precio (`clientes.lista_precio`: admin, encargado y el staff heredado; el vendedor no).
    app.include_router(
        build_cliente_lista_router(conexion=lc_get_connection),
        dependencies=[Depends(requiere_segun_metodo(lectura="clientes.ver", escritura="clientes.lista_precio"))],
    )
    # Cuenta corriente: el router del motor (`libracore.cuenta_corriente_router`), el mismo de Contalibra y
    # Restolibra, con las reglas de cobro de este producto como `OpcionesCuentaCorriente` (turno obligatorio,
    # caja del turno, baja de pago que anula el movimiento de caja; ver `app/cuenta_corriente_ganchos.py`).
    # Reemplaza a `/accounts` y a `/api/cuenta-corriente` propios (ADR-031). El cajero cobra fiado en el
    # mostrador, asi que no es admin-only. Con los roles de ADR-049 la cuenta corriente es de `cuenta_corriente`
    # (encargado, vendedor y el staff heredado; el cajero NUEVO no la tiene: no figura en lo que el humano le
    # asignó); la baja de un pago sigue siendo la excepción (`solo_admin`, ahora la capacidad `cobranzas.anular`).
    app.include_router(
        build_cuenta_corriente_router(
            usuario_actual=get_current_user, solo_admin=requiere("cobranzas.anular"),
            origen=VENTAS_LIBRACOMMERCE, con_recibos=True, opciones=CC_OPCIONES,
        ),
        dependencies=[Depends(requiere("cuenta_corriente"))],
    )
    # Recibos (fase 14, ADR-040): el router del motor, extraído de Contalibra. Gana de paso listar/detalle,
    # emitir de factura/venta (además de la cobranza que ya llamaban las pantallas de cuenta corriente del
    # kit) y anular (`solo_admin`, ahora la capacidad `cobranzas.anular`). Único gancho: `get_venta` -- las ventas de
    # mostrador de este producto viven en `sales` de LibraCommerce, no en `ventas` del propio esquema del motor.
    app.include_router(
        build_recibos_router(
            usuario_actual=get_current_user, solo_admin=requiere("cobranzas.anular"), get_venta=db_ventas.get_venta,
        ),
        dependencies=[Depends(requiere("cuenta_corriente"))],
    )
    # Consulta de CUIT en ARCA (fase 14, ADR-040): el router del motor, extraído de Contalibra. Activa
    # `conConsultaCuit` en las pantallas de Clientes del kit (ver frontend/src/pages/Clientes*.tsx).
    # Va con el alta de clientes (`clientes.alta`): es lo que la acompaña. Está fuera del esquema OpenAPI (`include_in_schema=False`).
    app.include_router(
        build_consultar_cuit_router(usuario_actual=get_current_user), dependencies=[Depends(requiere("clientes.alta"))],
    )
    # Tesorería (fase 10, ADR-037): el router del motor, sin ganchos -- las cuentas bancarias y sus
    # movimientos son un problema de cualquier comercio, no del modelo de venta de este producto (`libracore`
    # ya trae la tabla, vacía hasta ahora). De `tesoreria` (admin y encargado): es la única instancia de la familia
    # que la deja libre en todos los planes (no gateada por `require_module`, a diferencia de Contalibra).
    app.include_router(build_tesoreria_router(usuario_actual=get_current_user), dependencies=[Depends(requiere("tesoreria"))])
    # Egresos (fase 11, ADR-038): el router del motor, sin ganchos. Complementa a Compras -- Compras
    # repone inventario, Egresos es la contabilidad del pago (alquiler, sueldos, servicios, y también un
    # pago a proveedor que Compras no cubre). De `egresos` (encargado y el staff heredado, además de admin), igual
    # que Compras y Proveedores (mismo criterio de Contalibra); libre en todos los planes, como Tesorería. La baja de un proveedor con
    # egresos ya la guarda el motor (`ValueError` -> 422 en `build_proveedores_router`); la de un proveedor
    # con compras la sigue guardando `app/proveedores_guarda.py`.
    app.include_router(build_egresos_router(usuario_actual=get_current_user), dependencies=[Depends(requiere("egresos"))])
    # Libros IVA (fase 12, ADR-038): ventas ya funciona (las facturas son la tabla `facturas` del motor,
    # que este producto ya escribe desde `venta_facturacion`); compras se completa con Egresos, recién
    # adoptado arriba. De `libros_iva` (admin y encargado): es un reporte contable-fiscal. Los cuatro exports
    # REGINFO van FUERA de `/api` (por eso `vite.config.ts` los suma a `RUTAS_PROPIAS_DEL_BACKEND`, no a
    # `API_PATHS`: `/libros-iva` a secas sigue siendo la pantalla de la SPA).
    app.include_router(build_libros_iva_router(), dependencies=[Depends(requiere("libros_iva"))])
    app.include_router(build_libros_iva_export_router(solo_admin=requiere("libros_iva")))
    # Dashboard (fase 13, ADR-039). Libre en todos los planes desde ADR-048 (decisión del humano, 2026-09-29): el plan
    # se distingue por facturación ARCA y multisucursal, no por el tablero, así que ya no lleva `require_module`.
    # `sin_fiado=True`: mismo motivo que Reportes (fase 8) -- sin esto, "Cobrado del mes" y "Saldo de caja"
    # cuentan una venta a cuenta corriente como plata ya entrada. De `dashboard` (admin y encargado).
    app.include_router(
        build_dashboard_router(usuario_actual=get_current_user, sin_fiado=True),
        dependencies=[Depends(requiere("dashboard"))],
    )
    # Cierre diario: acto registrado y numerado por sucursal (LibraCore
    # v1.101.0+, migración `0009_cierre_diario`, ya en la cadena de este pin).
    # `autorizar_cierre` no se pasa: el gate de ESTE producto es la capacidad `cierre_diario`
    # (admin, encargado y el staff heredado; el cajero NUEVO ya no, ADR-049), y ya cubre TODOS los
    # endpoints del router -- incluido `POST /cerrar` -- por el `dependencies=` de este mismo
    # `include_router`. Con UNA excepción: `GET /turno/{id}/ticket` es el ticket que el POS imprime
    # al cerrar el turno propio, así que lo pide `caja.propia` (el cajero lo necesita).
    # `resolver_sucursal_nombre` cierra sobre `app.state`
    # (no sobre `conn`, la variable local) para seguir viendo la conexión
    # correcta después de un restore de backup (`_reabrir_conexion` la
    # reemplaza, no la muta).
    # `autorizar_reabrir` (LibraCore v1.107.0, "Reabrir día") SÍ se pasa:
    # reabrir un día ya cerrado es más sensible que cerrarlo, así que se le
    # exige la capacidad `cierre_diario.reabrir` (sólo admin) en vez de heredar la del
    # módulo -- sin este parámetro el endpoint `POST /{id}/reabrir` ni se monta.
    def _resolver_sucursal_nombre(sucursal_id: int | None) -> str:
        if sucursal_id is None:
            return ""
        sucursal = SucursalService(app.state.conn).get(sucursal_id)
        return sucursal.name if sucursal else ""

    app.include_router(
        build_cierre_diario_router(
            usuario_actual=get_current_user,
            resolver_sucursal_nombre=_resolver_sucursal_nombre,
            autorizar_reabrir=Depends(requiere("cierre_diario.reabrir")),
        ),
        dependencies=[
            Depends(requiere_segun_ruta(
                ("GET", r"/api/cierre-diario/turno/\d+/ticket", "caja.propia"),
                por_defecto="cierre_diario",
            )),
            # El ticket de un turno es de quien lo abrió (o de quien ve los de todos): ver `solo_su_turno_o_todos`.
            Depends(solo_su_turno_o_todos),
        ],
    )
    # Reportes (fase 8, ADR-035): el router del motor sobre las ventas de LibraCommerce (`libracommerce.erp.reportes`), el mismo que
    # monta Contalibra, con dos variantes: una venta anulada o pendiente de cobro no es una venta (`solo_confirmadas`) y **fiar no es
    # cobrar** (`sin_fiado`: la cuenta corriente no es ingreso de caja, como en el arqueo del turno). Reemplaza a `/reports/*`. Capacidad
    # `reportes` (admin y encargado); los exports CSV (`/reportes/export/*`) van con la sesión por cookie de la SPA.
    reportes = puerto_de_reportes(lc_get_connection, solo_confirmadas=True, sin_fiado=True)
    app.include_router(
        build_reportes_router(reportes=reportes, sin_fiado=True), dependencies=[Depends(requiere("reportes"))],
    )
    app.include_router(
        build_reportes_export_router(sesion=requiere("reportes"), reportes=reportes, sin_fiado=True),
    )
    # Margen y rotación (tanda 1 del roadmap de producto, ADR-046): el router del motor (`libracommerce.web.margen_router`, sólo
    # lectura sobre las líneas de venta: ingreso, costo, margen y unidades por producto y por período, con export CSV). Capacidad
    # `margen` (admin y encargado), como Reportes: el costo y el margen no son del mostrador ni del depósito. Una venta anulada o pendiente de cobro no cuenta y las
    # devoluciones se restan (lo resuelve el motor); fiar SÍ es vender, así que acá no hay `sin_fiado`. Los CSV cuelgan del mismo
    # prefijo, bajo `/api`: no hace falta una ruta más en el proxy de Vite.
    #
    # 🔴 **Sin gate de plan, a propósito (decisión de negocio pendiente).** `require_module("margen")` haría falta si el margen fuera
    # de un plan (`plans.py` anticipa que Premium "tiene margen para reportes"); no se asignó ninguno porque no lo decidió el humano.
    # Mientras tanto queda disponible para todo el que tenga `margen`, igual que Reportes. Para gatearlo: sumar `"margen"` al plan elegido en
    # `plans.py` y `Depends(require_module("margen"))` en este `dependencies=`.
    app.include_router(build_margen_router(conexion=lc_get_connection), dependencies=[Depends(requiere("margen"))])
    # Reposición sugerida (roadmap de producto, B-3, ADR-051): el router del motor (`libracommerce.web.reposicion_router`, v0.28.0; sólo
    # lectura: por producto, cuánto conviene pedir según lo que se vende, lo que hay y lo que ya viene en órdenes abiertas, con export
    # CSV). Capacidad `reposicion.ver` (admin y encargado, como `margen`); sin gate de plan (libre en Básico y Premium, ADR-048). Sólo
    # sugiere: no genera la orden de compra. No lleva costos: `/api/reportes` no está en los prefijos de `SinCostos` (`app/costos.py`)
    # y `tests/test_reposicion.py` fija que ninguna clave de costo viaja.
    app.include_router(
        build_reposicion_router(
            conexion=lc_get_connection, resolver_proveedor=resolver_proveedor_del_producto, proveedor_de=proveedor_del_producto,
        ),
        dependencies=[Depends(requiere("reposicion.ver"))],
    )
    # Plazo de entrega y stock máximo por producto (ADR-055; ADR-020 del motor, libracommerce v0.32.0): `GET`/`PUT /api/productos/{id}/reposicion`.
    # Capacidad `reposicion.parametros` (encargado, admin y depósito) tanto para leer como para escribir; el router no se construye sin dependencias de
    # escritura. Va aparte del payload del producto (que no cambia). Requiere la revisión `0003` del motor (`libracommerce-migrar upgrade`).
    app.include_router(build_reposicion_parametros_router(
        conexion=lc_get_connection,
        dependencias_leer=[Depends(requiere("reposicion.parametros"))],
        dependencias_escribir=[Depends(requiere("reposicion.parametros"))],
        resolver_proveedor=resolver_proveedor_del_producto, proveedor_de=proveedor_del_producto,
    ))
    # Mínimo de stock por sucursal (ADR-059; ADR-024 del motor, libracommerce v0.36.0): `GET /api/productos/{id}/reposicion/minimos` y
    # `PUT .../minimos/{sucursal_id}`. Misma capacidad que el plazo y el techo (`reposicion.parametros`: encargado, admin y depósito), para leer y escribir. Los
    # ids de sucursal son los del motor (los mismos que ya usa el filtro `sucursal_id` de la reposición). Requiere la revisión `0005` del motor.
    app.include_router(build_reposicion_minimos_router(
        conexion=lc_get_connection,
        dependencias_leer=[Depends(requiere("reposicion.parametros"))],
        dependencias_escribir=[Depends(requiere("reposicion.parametros"))],
    ))
    # Órdenes de compra en borrador desde la reposición (ADR-057; ADR-022 del motor, libracommerce v0.34.0): `POST /api/reportes/reposicion/ordenes` crea UNA
    # orden en borrador por proveedor habitual con lo que la reposición sugiere pedir. Nunca envía ni confirma. Escribe órdenes de compra: pide las DOS
    # capacidades, `reposicion.ver` (la pantalla de donde sale) y `compras.escribir` (lo que protege crear una orden en Compras), así que en la práctica es del
    # encargado y el admin; el depósito y el staff no (el staff no ve la reposición). La respuesta lleva costos: sólo la ven quienes tienen `compras.escribir`.
    # Numeración y ids de proveedor, los ganchos de Compras (`app/compras_ganchos.py`).
    app.include_router(build_reposicion_ordenes_router(
        conexion=lc_get_connection, usuario_actual=get_current_user,
        dependencias_escribir=[Depends(requiere("reposicion.ver")), Depends(requiere("compras.escribir"))],
        numerador=OPCIONES_DE_COMPRAS.numerador,
        resolver_proveedor=resolver_proveedor_del_producto, proveedor_de=proveedor_del_producto,
    ))
    # Vencimientos y lotes (roadmap de producto, A-3, ADR-052): los DOS routers del motor (`libracommerce.web.vencimientos_router`, v0.30.0,
    # ADR-018 del motor), que cuelgan de `/api/vencimientos`. Sin gate de plan (libre en Básico y Premium, ADR-048). Desde v0.30.0 (A-4,
    # ADR-053) las salidas de un producto marcado siguen el lote, y las opciones de productos, stock y ventas lo completan (más arriba).
    #   - Lectura (`GET ""`, `/export`, `/productos/{id}/lotes`): `vencimientos.ver` (encargado y depósito). No trae costos.
    #   - Escritura: `usuario_actual` (con `id` entero: sale como `created_by` de los movimientos) y una guarda POR OPERACIÓN, porque el
    #     motor no monta escrituras del ledger sin ellas (la factory falla al construirse): marcar un producto es `vencimientos.marcar`
    #     (sólo el encargado) y asignar un vencimiento, cargar stock con lote y dar de baja un lote, `vencimientos.mover` (encargado y depósito). Encima, a nivel
    #     include, la de lectura: quien escribe tiene que poder ver.
    # 🔴 Sin la revisión Alembic `0002_vencimientos_lotes` del motor el router contesta 503: se aplica con
    # `libracommerce-migrar upgrade --prefijo ventalibra` (compose, `panel_admin.py`, smoke y suite: ver ADR-052).
    app.include_router(
        build_vencimientos_router(conexion=lc_get_connection), dependencies=[Depends(requiere("vencimientos.ver"))],
    )
    app.include_router(
        build_vencimientos_escritura_router(
            conexion=lc_get_connection, usuario_actual=usuario_actual,
            dependencias_marcar=[Depends(requiere("vencimientos.marcar"))],
            # `POST /asignar`, `/entrada` y `/merma` (la baja de un lote) mueven el ledger: `vencimientos.mover`. La baja de un lote estuvo
            # deshabilitada hasta A-4 (ADR-052); con libracommerce v0.30.0 todas las salidas de los productos marcados siguen el lote y se
            # reactivó (ADR-053). La guarda del motor (stock total y saldo «sin lote» negativo heredado) sigue en pie.
            dependencias_movimientos=[Depends(requiere("vencimientos.mover"))],
        ),
        dependencies=[Depends(requiere("vencimientos.ver"))],
    )
    # Configurar la balanza y el ticket es `config` (sólo admin): el POS no
    # necesita leer este router, resuelve las etiquetas contra el backend.
    app.include_router(settings_router.router, dependencies=[Depends(requiere("config"))])

    # Datos de empresa, logo y Datos / Backup (LibraCore v1.11.0).
    #
    # A diferencia de LibraDesk, aca la lectura de empresa TAMBIEN es admin:
    # este producto no genera comprobantes desde el frontend con esos datos —
    # el ticket lo arma el backend—, asi que no hay motivo para abrirla.
    app.include_router(build_empresa_router(), dependencies=[Depends(requiere("config"))])
    app.include_router(build_empresa_admin_router(), dependencies=[Depends(requiere("config"))])

    # El tema de la suite (libracore ADR-012, libra-ui ADR-007/008): los colores que el backoffice de la suite empuja a esta instancia.
    # La lectura es PÚBLICA a propósito —el login también va con los colores de la suite y no expone nada sensible—; la escritura es
    # `config` (sólo admin) O el token de servicio del backoffice (`requiere_o_servicio`, que es quien la usa: pantalla «Apariencia»).
    # 🔴 Con `requiere("config")` a secas el backoffice NO entraría: esa guarda no conoce el token.
    app.include_router(build_tema_router())
    app.include_router(build_tema_admin_router(), dependencies=[Depends(requiere_o_servicio("config"))])

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
        dependencies=[Depends(requiere("config"))],
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
        dependencies=[Depends(requiere("config")), Depends(require_module("resguardo_externo"))],
    )

    # Logs: admin y nada mas. La fila dice quien vendio que y desde que IP
    # entro cada uno. **No** se gatea por plan: un log de auditoria no es una
    # feature vendible.
    #
    # El router lo arma el motor de auth (libraauth v0.10.0) pero el gate lo
    # pone el producto: el vocabulario de roles es de aca. Y la lista de
    # entidades sale del motor comercial, que es de donde sale la actividad.
    app.include_router(
        build_logs_router(entidades_auditadas()), dependencies=[Depends(requiere("logs"))],
    )

    return app
