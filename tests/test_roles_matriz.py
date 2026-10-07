"""La matriz de permisos de VentaLibra, endpoint por endpoint y rol por rol (ADR-049).

🔑 **Qué hace.** Levanta UNA app con un usuario de cada rol (más el visitante de la demo y un anónimo) y le pega
a CADA operación que publica `openapi.json`, con cada rol. La respuesta se compara con `TABLA`, que dice a
mano quién puede entrar. Es el test que responde «¿el cajero puede ver reportes?» sin leer ningún router.

🔴 **La tabla está escrita a mano y NO se deriva de `app/permisos.py`, a propósito.** Si saliera de ahí, un
cambio en la matriz (por ejemplo dejarle `reportes` al cajero) movería el código y el test juntos, y no se
pondría rojo nunca. Es una segunda declaración, independiente: aflojar una capacidad la contradice: dejarle
`reportes` al cajero pone en rojo su columna de la tabla, `/auth/me` y el archivo de capacidades del frontend (ADR-049).

**Cobertura.** Una operación nueva que la tabla no conoce hace fallar `test_toda_operacion_tiene_fila`: un
router que alguien monta sin decidir quién entra se nota acá. Las filas de la tabla que ya no existen también
fallan (la tabla no se pudre). Hay tres rutas que el motor publica con `include_in_schema=False`
(`OCULTAS`): no salen de `openapi.json`, así que van escritas aparte y se prueban igual. **Lo que este test no
alcanza:** una ruta nueva y oculta del esquema. Sería la única forma de colarse; el `anonimo` de más abajo la
atraparía sólo si se la agrega a `OCULTAS`.

**Cómo se sondea sin hacer daño.** Cada operación se llama con ids inexistentes (`999999`) y, si no es un GET,
con un cuerpo JSON que no es un objeto (`[]`): el rol se chequea ANTES de validar el cuerpo, así que un rol sin permiso da 403 y uno con
permiso da otra cosa (422, 404...) sin ejecutar nada. «Rechazado» es `401` o `403` con `detail == "forbidden"`;
un 403 con otro texto (plan, Términos) no es un rechazo por rol. Las pocas operaciones sin parámetros que sí se
ejecutarían con permiso (un backup, bajar un backup) están en `NO_EJECUTAR`: se prueba que el que no debe
recibe 403 y NO se le pega al que sí debe.
"""
import re

import pytest
from conftest import https_client
from fastapi.testclient import TestClient

from app import permisos

TODOS = frozenset({"admin", "encargado", "vendedor", "cajero", "deposito"})
#: Los grupos de roles que se repiten en la tabla. Cada nombre dice quién, no por qué.
GRUPOS = {
    "ADMIN": frozenset({"admin"}),
    "GERENCIA": frozenset({"admin", "encargado"}),
    "MOSTRADOR": frozenset({"admin", "encargado", "vendedor", "cajero"}),
    "SIN_CAJERO": frozenset({"admin", "encargado", "vendedor"}),
    "GERENCIA_Y_DEPOSITO": frozenset({"admin", "encargado", "deposito"}),
    "TODOS": TODOS,
}
PUBLICA = "PUBLICA"

#: Cada línea: método, ruta tal como la publica el esquema y el grupo que puede entrar.
TABLA = """
# Públicas o de la propia sesión: no las decide el rol (se sondean sólo como anónimo, aparte)
GET    /health                                                          PUBLICA
GET    /auth/captcha                                                    PUBLICA
POST   /auth/login                                                      PUBLICA
POST   /auth/logout                                                     PUBLICA
GET    /auth/me                                                         PUBLICA
POST   /auth/change-password                                            PUBLICA
POST   /auth/verify                                                     PUBLICA
POST   /auth/forgot-password                                            PUBLICA
POST   /auth/reset-password                                             PUBLICA

# Correo (SMTP) y códigos de la demo: el motor los exige admin por dentro; `config`
GET    /admin/smtp                                                      ADMIN
PUT    /admin/smtp                                                      ADMIN
DELETE /admin/smtp                                                      ADMIN
POST   /admin/smtp/probar                                               ADMIN
GET    /terminos                                                        PUBLICA
POST   /terminos/aceptar                                                PUBLICA
GET    /terminos/historial                                              PUBLICA
GET    /admin/demo-codigos                                              ADMIN
POST   /admin/demo-codigos                                              ADMIN
DELETE /admin/demo-codigos/{codigo_id}                                  ADMIN

# Usuarios: `usuarios.admin` (y el token de servicio, ver test_token_de_servicio)
GET    /users                                                           ADMIN
POST   /users                                                           ADMIN
GET    /users/{user_id}                                                 ADMIN
PUT    /users/{user_id}                                                 ADMIN
DELETE /users/{user_id}                                                 ADMIN
PUT    /users/{user_id}/password                                        ADMIN

# ARCA y MercadoPago: `config`
GET    /config/arca                                                     ADMIN
PUT    /config/arca                                                     ADMIN
POST   /config/arca/certificado                                         ADMIN
POST   /config/arca/clave                                               ADMIN
DELETE /config/arca/credenciales                                        ADMIN
GET    /config/arca/estado                                              ADMIN
GET    /config/arca/servicios                                           ADMIN
GET    /config/arca/certificado-info                                    ADMIN
POST   /config/arca/probar                                              ADMIN
GET    /api/config/mercadopago                                          ADMIN
PUT    /api/config/mercadopago                                          ADMIN
DELETE /api/config/mercadopago/credenciales                             ADMIN
POST   /api/config/mercadopago/probar                                   ADMIN
GET    /api/config/mercadopago/qr                                       ADMIN
GET    /api/config/mercadopago/qr/{formato}                             ADMIN

# Categorías y unidades: leer `catalogo.ver`, escribir `config` (sólo admin, ADR-071)
GET    /catalog/categories                                              TODOS
POST   /catalog/categories                                              ADMIN
PUT    /catalog/categories/{category_id}                                ADMIN
GET    /catalog/units                                                   TODOS
POST   /catalog/units                                                   ADMIN

# Ventas y POS: `ventas.pos`
GET    /ventas/{sale_id}/ticket                                         MOSTRADOR
GET    /pos/mp-estado                                                   MOSTRADOR
GET    /ventas/{sale_id}/devuelto                                       MOSTRADOR
GET    /api/ventas/medios-pago                                          MOSTRADOR
GET    /api/ventas                                                      MOSTRADOR
POST   /api/ventas                                                      MOSTRADOR
# La consulta previa del POS (lectura pura: de qué lote saldría cada línea y los avisos de vencimiento, ADR-053): es del POS, `ventas.pos`.
POST   /api/ventas/plan-salida                                          MOSTRADOR
GET    /api/ventas/{vid}                                                MOSTRADOR
POST   /api/ventas/{vid}/anular                                         MOSTRADOR
POST   /api/ventas/{vid}/devolver                                       MOSTRADOR
POST   /api/ventas/{vid}/facturar                                       MOSTRADOR
POST   /api/ventas/{vid}/mp-qr                                          MOSTRADOR
GET    /api/ventas/{vid}/mp-status                                      MOSTRADOR

# Turnos y cajas: `caja.propia`; el ABM de cajas es `caja.admin`
GET    /api/turnos                                                      MOSTRADOR
GET    /api/turnos/actual                                               MOSTRADOR
POST   /api/turnos/abrir                                                MOSTRADOR
GET    /api/turnos/{tid}                                                MOSTRADOR
POST   /api/turnos/{tid}/cerrar                                         MOSTRADOR
GET    /api/cajas                                                       MOSTRADOR
POST   /api/cajas                                                       ADMIN
GET    /api/cajas/medios-disponibles                                    MOSTRADOR
PUT    /api/cajas/{cid}                                                 ADMIN
DELETE /api/cajas/{cid}                                                 ADMIN
POST   /api/cajas/{cid}/set-default                                     ADMIN

# Sucursales y depósitos: leer `catalogo.ver`/`stock.ver`; estructura `sucursales.admin`; transferir `stock.transferir`
GET    /api/sucursales                                                  TODOS
POST   /api/sucursales                                                  ADMIN
GET    /api/sucursales/{sid}                                            TODOS
PUT    /api/sucursales/{sid}                                            ADMIN
POST   /api/sucursales/{sid}/set-default                                ADMIN
POST   /api/sucursales/{sid}/deposito-predeterminado                    ADMIN
GET    /api/depositos                                                   TODOS
POST   /api/depositos                                                   ADMIN
PUT    /api/depositos/{did}                                             ADMIN
DELETE /api/depositos/{did}                                             ADMIN
POST   /api/depositos/{did}/set-default                                 ADMIN
GET    /api/depositos/transferencias                                    TODOS
GET    /api/depositos/{did}/stock                                       TODOS
GET    /api/depositos/stock-producto/{pid}                              TODOS
POST   /api/depositos/transferir                                        GERENCIA_Y_DEPOSITO

# Stock: ver `stock.ver`, ajustar `stock.ajustar`
GET    /api/stock                                                       TODOS
GET    /api/stock/movimientos                                           TODOS
GET    /api/stock/motivos-merma                                         TODOS
GET    /api/stock/tipos                                                 TODOS
GET    /api/stock/{pid}                                                 TODOS
POST   /api/stock/{pid}/ajuste                                          GERENCIA_Y_DEPOSITO

# Productos: leer `catalogo.ver`, escribir `productos.escribir`
GET    /api/productos                                                   TODOS
POST   /api/productos                                                   GERENCIA
GET    /api/productos/unidades                                          TODOS
GET    /api/productos/escanear                                          TODOS
GET    /api/productos/categorias                                        TODOS
POST   /api/productos/categorias                                        GERENCIA
DELETE /api/productos/categorias/{cid}                                  GERENCIA
PUT    /api/productos/{pid}                                             GERENCIA
DELETE /api/productos/{pid}                                             GERENCIA
GET    /api/productos/{pid}/codigos                                     TODOS
POST   /api/productos/{pid}/codigos                                     GERENCIA
GET    /api/productos/{pid}/variantes                                   TODOS
POST   /api/productos/{pid}/variantes                                   GERENCIA
PUT    /api/productos/{pid}/variantes/{vid}                             GERENCIA

# Listas de precio: leer `precios.consultar`, escribir `precios.escribir`
GET    /api/listas-precio                                               MOSTRADOR
POST   /api/listas-precio                                               GERENCIA
PUT    /api/listas-precio/{lista_id}                                    GERENCIA
DELETE /api/listas-precio/{lista_id}                                    GERENCIA
POST   /api/listas-precio/{lista_id}/set-default                        GERENCIA
GET    /api/listas-precio/{lista_id}/items                              MOSTRADOR
PUT    /api/listas-precio/{lista_id}/items                              GERENCIA
POST   /api/listas-precio/{lista_id}/ajuste-porcentual                  GERENCIA
POST   /api/listas-precio/{lista_id}/importar                           GERENCIA
GET    /api/listas-precio/{lista_id}/items/{producto_id}/quiebres       GERENCIA
PUT    /api/listas-precio/{lista_id}/items/{producto_id}/quiebres       GERENCIA
GET    /api/listas-precio/{lista_id}/precio                             MOSTRADOR
POST   /api/listas-precio/{lista_id}/items/{producto_id}/precio-vigente GERENCIA
GET    /api/listas-precio/items/{producto_id}/vigencias                 GERENCIA
DELETE /api/listas-precio/items/{producto_id}/vigencias/{vigencia_id}   GERENCIA

# Promociones y actualización masiva: `precios.escribir` (calcular es `ventas.pos`)
GET    /api/promociones                                                 GERENCIA
POST   /api/promociones                                                 GERENCIA
GET    /api/promociones/{promocion_id}                                  GERENCIA
PUT    /api/promociones/{promocion_id}                                  GERENCIA
DELETE /api/promociones/{promocion_id}                                  GERENCIA
POST   /api/promociones/calcular                                        MOSTRADOR
POST   /api/actualizacion-masiva/precios/preview                        GERENCIA
POST   /api/actualizacion-masiva/precios/aplicar                        GERENCIA

# Proveedores y compras: ver `compras.ver` (también el depósito), escribir `compras.escribir`, recibir `compras.recibir` (no el depósito)
GET    /api/proveedores                                                 GERENCIA_Y_DEPOSITO
POST   /api/proveedores                                                 GERENCIA
PUT    /api/proveedores/{pid}                                           GERENCIA
DELETE /api/proveedores/{pid}                                           GERENCIA
GET    /api/purchase-orders                                             GERENCIA_Y_DEPOSITO
POST   /api/purchase-orders                                             GERENCIA
GET    /api/purchase-orders/{orden_id}                                  GERENCIA_Y_DEPOSITO
POST   /api/purchase-orders/{orden_id}/items                            GERENCIA
POST   /api/purchase-receipts                                           GERENCIA
GET    /api/purchase-receipts                                           GERENCIA_Y_DEPOSITO
GET    /api/purchase-receipts/{recepcion_id}                            GERENCIA_Y_DEPOSITO
POST   /api/purchase-receipts/{recepcion_id}/items                      GERENCIA
POST   /api/purchase-receipts/{recepcion_id}/confirm                    GERENCIA

# Clientes: ver `clientes.ver`, alta `clientes.alta`, resto `clientes.escribir`, lista `clientes.lista_precio`
GET    /api/clientes                                                    MOSTRADOR
POST   /api/clientes                                                    MOSTRADOR
GET    /api/clientes/{cliente_id}                                       SIN_CAJERO
PUT    /api/clientes/{cliente_id}                                       SIN_CAJERO
POST   /api/clientes/{cliente_id}/toggle-auto-facturar                  SIN_CAJERO
POST   /api/clientes/{cliente_id}/alias-facturacion                     SIN_CAJERO
DELETE /api/clientes/{cliente_id}/alias-facturacion/{alias_id}          SIN_CAJERO
POST   /api/clientes/{cliente_id}/desactivar                            SIN_CAJERO
POST   /api/clientes/{cliente_id}/activar                               SIN_CAJERO
GET    /api/clientes/{cliente_id}/lista-precio                          MOSTRADOR
PUT    /api/clientes/{cliente_id}/lista-precio                          GERENCIA

# Cuenta corriente y recibos: `cuenta_corriente`; baja de pago y anular recibo `cobranzas.anular`
GET    /api/cuenta-corriente                                            SIN_CAJERO
GET    /api/cuenta-corriente/cajas                                      SIN_CAJERO
GET    /api/cuenta-corriente/{cliente_id}                               SIN_CAJERO
POST   /api/cuenta-corriente/{cliente_id}/pagar                         SIN_CAJERO
DELETE /api/cuenta-corriente/pagos/{pago_id}                            GERENCIA
GET    /api/recibos                                                     SIN_CAJERO
GET    /api/recibos/{recibo_id}                                         SIN_CAJERO
GET    /api/recibos/{recibo_id}/pdf                                     SIN_CAJERO
POST   /api/recibos/factura/{factura_id}                                SIN_CAJERO
POST   /api/recibos/venta/{venta_id}                                    SIN_CAJERO
POST   /api/recibos/cobranza/{cc_pago_id}                               SIN_CAJERO
POST   /api/recibos/{recibo_id}/anular                                  GERENCIA

# Tesorería: `tesoreria`
GET    /api/tesoreria                                                   GERENCIA
POST   /api/tesoreria/cuentas                                           GERENCIA
GET    /api/tesoreria/cuentas/{cid}                                     GERENCIA
PUT    /api/tesoreria/cuentas/{cid}                                     GERENCIA
DELETE /api/tesoreria/cuentas/{cid}                                     GERENCIA
POST   /api/tesoreria/cuentas/{cid}/movimiento                          GERENCIA
POST   /api/tesoreria/transferencia                                     GERENCIA
DELETE /api/tesoreria/movimientos/{mid}                                 GERENCIA

# Egresos: `egresos`
GET    /api/egresos                                                     GERENCIA
POST   /api/egresos                                                     GERENCIA
GET    /api/egresos/tipos-comprobante                                   GERENCIA
GET    /api/egresos/categorias                                          GERENCIA
POST   /api/egresos/categorias                                          GERENCIA
DELETE /api/egresos/categorias/{cid}                                    GERENCIA
GET    /api/egresos/cajas                                               GERENCIA
GET    /api/egresos/{eid}/pagos                                         GERENCIA
POST   /api/egresos/{eid}/pagar                                         GERENCIA
DELETE /api/egresos/{eid}                                               GERENCIA

# Libros IVA: `libros_iva`
GET    /api/libros-iva                                                  GERENCIA
GET    /libros-iva/export/ventas-cbte                                   GERENCIA
GET    /libros-iva/export/ventas-alicuotas                              GERENCIA
GET    /libros-iva/export/compras-cbte                                  GERENCIA
GET    /libros-iva/export/compras-alicuotas                             GERENCIA

# Dashboard: `dashboard`
GET    /api/dashboard                                                   GERENCIA

# Cierre diario: `cierre_diario`; reabrir `cierre_diario.reabrir`; el ticket del propio turno `caja.propia`
GET    /api/cierre-diario/preview                                       GERENCIA
POST   /api/cierre-diario/cerrar                                        GERENCIA
POST   /api/cierre-diario/{cierre_id}/reabrir                           ADMIN
GET    /api/cierre-diario                                               GERENCIA
GET    /api/cierre-diario/{cierre_id}                                   GERENCIA
GET    /api/cierre-diario/{cierre_id}/ticket                            GERENCIA

# Nota de crédito de una factura con CAE (LibraCore v1.129.0): `facturas.nota_credito`, sólo admin
POST   /api/facturas/{factura_id}/nota-credito                          ADMIN
GET    /api/cierre-diario/turno/{turno_id}/ticket                       MOSTRADOR

# Reportes, margen y reposición: `reportes`, `margen`, `reposicion.ver`
GET    /api/reportes                                                    GERENCIA
GET    /api/reportes/caja-medios                                        GERENCIA
GET    /reportes/export/ventas                                          GERENCIA
GET    /reportes/export/medios                                          GERENCIA
GET    /reportes/export/productos                                       GERENCIA
GET    /reportes/caja-medios/export                                     GERENCIA
GET    /api/reportes/margen                                             GERENCIA
GET    /api/reportes/margen/export/productos                            GERENCIA
GET    /api/reportes/margen/export/periodos                             GERENCIA
GET    /api/reportes/reposicion                                         GERENCIA_Y_DEPOSITO
GET    /api/reportes/reposicion/export                                  GERENCIA_Y_DEPOSITO

# Órdenes de compra en borrador desde la reposición (ADR-057): escribe órdenes, así que pide `reposicion.ver` Y `compras.escribir`: encargado y admin.
POST   /api/reportes/reposicion/ordenes                                 GERENCIA

# Plazo y stock máximo por producto (ADR-055): `reposicion.parametros`, el encargado, el admin y el depósito, para leer y para escribir.
GET    /api/productos/{producto_id}/reposicion                          GERENCIA_Y_DEPOSITO
PUT    /api/productos/{producto_id}/reposicion                          GERENCIA_Y_DEPOSITO
# Mínimo de stock por sucursal (ADR-059): la misma capacidad `reposicion.parametros`, para leer y para escribir.
GET    /api/productos/{producto_id}/reposicion/minimos                  GERENCIA_Y_DEPOSITO
PUT    /api/productos/{producto_id}/reposicion/minimos/{sucursal_id}    GERENCIA_Y_DEPOSITO

# Vencimientos y lotes: ver `vencimientos.ver` y mover (asignar, cargar con lote, dar de baja) `vencimientos.mover`, el encargado y el depósito; marcar
# un producto `vencimientos.marcar`, sólo el encargado. NO el mostrador.
GET    /api/vencimientos                                                GERENCIA_Y_DEPOSITO
GET    /api/vencimientos/export                                         GERENCIA_Y_DEPOSITO
GET    /api/vencimientos/productos/{producto_id}/lotes                  GERENCIA_Y_DEPOSITO
PUT    /api/vencimientos/productos/{producto_id}                        GERENCIA
POST   /api/vencimientos/asignar                                        GERENCIA_Y_DEPOSITO
POST   /api/vencimientos/entrada                                        GERENCIA_Y_DEPOSITO
POST   /api/vencimientos/merma                                          GERENCIA_Y_DEPOSITO

# Balanza, ticket, empresa, backup y resguardo: `config`
GET    /settings/scale                                                  ADMIN
PUT    /settings/scale                                                  ADMIN
DELETE /settings/scale                                                  ADMIN
GET    /settings/ticket                                                 ADMIN
PUT    /settings/ticket                                                 ADMIN
GET    /api/config/empresa                                              ADMIN
PUT    /api/config/empresa                                              ADMIN
POST   /api/config/empresa/logo                                         ADMIN
GET    /api/tema                                                        PUBLICA
PUT    /api/tema                                                        ADMIN
DELETE /api/config/empresa/logo                                         ADMIN
GET    /api/config/backups                                              ADMIN
POST   /api/config/backups                                              ADMIN
GET    /api/config/backups/{filename}                                   ADMIN
GET    /api/config/backup-ahora                                         ADMIN
GET    /api/config/resguardo-externo                                    ADMIN
POST   /api/config/restore                                              ADMIN
GET    /api/config/resguardo-externo/enlace                             ADMIN
DELETE /api/config/resguardo-externo/enlace                             ADMIN
POST   /api/config/resguardo-externo/enlace/{proveedor}                 ADMIN

# Logs: `logs`
GET    /api/logs                                                        ADMIN
"""

#: Rutas que el motor no publica en `openapi.json` (`include_in_schema=False`).
OCULTAS = """
GET    /api/consultar-cuit/{cuit}                     MOSTRADOR
GET    /api/config/empresa/logo                       ADMIN
GET    /api/config/resguardo-externo/enlace/callback  ADMIN
"""

#: Existen sólo si el router de `/auth` se armó, AL IMPORTAR, con `DEMO_MODE` puesto: el import lo hace el
#: conftest antes que cualquier fixture, así que en la suite no están. Son públicas (el auto-login de la demo).
OPCIONALES_PUBLICAS = {("GET", "/auth/demo"), ("POST", "/auth/demo")}

#: Sin parámetros y con efecto real si se las deja pasar: sólo se prueba el rechazo.
NO_EJECUTAR = {
    ("POST", "/api/config/backups"),
    ("GET", "/api/config/backup-ahora"),
}


def _leer(texto: str) -> dict[tuple[str, str], str]:
    filas = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        metodo, ruta, grupo = linea.split()
        assert (metodo, ruta) not in filas, f"fila repetida: {metodo} {ruta}"
        assert grupo == PUBLICA or grupo in GRUPOS, f"grupo desconocido en {metodo} {ruta}: {grupo}"
        filas[(metodo, ruta)] = grupo
    return filas


FILAS = _leer(TABLA)
FILAS_OCULTAS = _leer(OCULTAS)
PRIVADAS = {op: g for op, g in {**FILAS, **FILAS_OCULTAS}.items() if g != PUBLICA}


# ── La instancia con un usuario de cada rol ──────────────────────────────────


@pytest.fixture
def _demo_encendida(monkeypatch):
    """Antes que `admin_client`: la app mira estas variables al armarse. Con la demo, además, el visitante entra
    por el login común (`DEMO_PASSWORD`) y existe el ABM de códigos, que también hay que cubrir."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")
    monkeypatch.setenv("DEMO_PASSWORD", "clave-de-la-demo")


@pytest.fixture
def instancia(_demo_encendida, admin_client):
    """`{rol: cliente logueado}` para los cinco roles, más `demo` (el visitante) y `anonimo` (sin sesión)."""
    from app.database import set_addon

    app = admin_client.app
    # El resguardo con la nube es un add-on apagado por defecto y su gate daría 403 al admin también: sin
    # prenderlo, esas cuatro rutas no distinguirían «sin permiso» de «sin plan».
    set_addon("resguardo_externo", True)
    clientes = {"admin": admin_client}
    abiertos = []
    try:
        for rol in sorted(TODOS - {"admin"}):
            creado = admin_client.post("/users", json={
                "username": f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol,
            })
            assert creado.status_code == 201, creado.text
            clientes[rol] = _entrar(app, abiertos, f"u-{rol}", "clave-larga-1")
        clientes["demo"] = _entrar(app, abiertos, "visitante", "clave-de-la-demo")
        clientes["anonimo"] = https_client(app)
        abiertos.append(clientes["anonimo"])
        yield clientes
    finally:
        for c in abiertos:
            c.close()


def _entrar(app, abiertos: list, usuario: str, clave: str) -> TestClient:
    cliente = https_client(app)
    abiertos.append(cliente)
    respuesta = cliente.post("/auth/login", json={"username": usuario, "password": clave})
    assert respuesta.status_code == 200, respuesta.text
    return cliente


def _sondear(cliente: TestClient, metodo: str, plantilla: str):
    ruta = re.sub(r"\{[^}]+\}", "999999", plantilla)
    if metodo == "GET":
        return cliente.get(ruta)
    return cliente.request(metodo, ruta, content=b"[]", headers={"content-type": "application/json"})


def _detalle(respuesta) -> str:
    try:
        detalle = respuesta.json().get("detail")
    except ValueError:
        return ""
    return detalle if isinstance(detalle, str) else ""


def _rechazada_por_rol(respuesta) -> bool:
    return respuesta.status_code == 401 or (respuesta.status_code == 403 and _detalle(respuesta) == "forbidden")


def _desvios(cliente: TestClient, quien: str, permitidas: dict[tuple[str, str], frozenset[str]]) -> list[str]:
    """Las operaciones donde `cliente` recibió otra cosa que lo que dice la tabla."""
    desvios = []
    for (metodo, ruta), roles in sorted(permitidas.items()):
        debe_entrar = quien in roles
        if debe_entrar and (metodo, ruta) in NO_EJECUTAR:
            continue
        rechazada = _rechazada_por_rol(_sondear(cliente, metodo, ruta))
        if rechazada == debe_entrar:
            desvios.append(f"{quien} {metodo} {ruta}: {'debía entrar y lo rechazaron' if debe_entrar else 'NO debía entrar y pasó'}")
    return desvios


def _permitidas() -> dict[tuple[str, str], frozenset[str]]:
    return {op: GRUPOS[g] for op, g in PRIVADAS.items()}


# ── Cobertura: la tabla y la aplicación dicen lo mismo ───────────────────────


def _operaciones_publicadas(cliente: TestClient) -> set[tuple[str, str]]:
    esquema = cliente.get("/openapi.json").json()
    return {
        (metodo.upper(), ruta)
        for ruta, operaciones in esquema["paths"].items()
        for metodo in operaciones
        if metodo.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }


def test_toda_operacion_tiene_fila(instancia):
    """Un router nuevo, o una ruta nueva en uno viejo, sin decidir quién entra, hace fallar ESTE test.

    Y al revés: una fila cuya operación ya no existe (renombrada, retirada) también: la tabla es una
    declaración viva, no un registro histórico."""
    publicadas = _operaciones_publicadas(instancia["admin"]) - OPCIONALES_PUBLICAS
    sin_fila = sorted(publicadas - set(FILAS))
    sin_ruta = sorted(set(FILAS) - publicadas)
    assert not sin_fila, f"operaciones sin fila en TABLA (¿quién puede llamarlas?): {sin_fila}"
    assert not sin_ruta, f"filas de TABLA que la app ya no publica: {sin_ruta}"


def test_el_anonimo_no_pasa_por_ninguna_ruta_privada(instancia):
    """Sin sesión, 401 en todo lo que no es público. Es lo que atrapa un router montado SIN guarda (incluido uno
    de las rutas ocultas del esquema, que están en `OCULTAS`)."""
    abiertas = [
        f"{metodo} {ruta} -> {r.status_code}"
        for (metodo, ruta) in sorted(PRIVADAS)
        if (r := _sondear(instancia["anonimo"], metodo, ruta)).status_code != 401
    ]
    assert not abiertas, f"rutas privadas que un anónimo no recibe con 401: {abiertas}"


# ── La tabla, un rol por vez ──────────────────────────────────────────────────


@pytest.mark.parametrize("rol", sorted(TODOS))
def test_cada_rol_entra_solo_donde_la_tabla_dice(instancia, rol):
    """El rol × todos los endpoints: 200-ish (cualquier cosa menos el rechazo por rol) donde la tabla lo
    permite, 403 donde no. Es la tabla parametrizada de la matriz de ADR-049."""
    desvios = _desvios(instancia[rol], rol, _permitidas())
    assert not desvios, "\n" + "\n".join(desvios)


def test_el_visitante_de_la_demo_ve_todo_y_no_escribe_nada_de_mas(instancia):
    """La demo entra como `encargado` (ADR-070; antes `staff`) y libraauth le abre la LECTURA de cualquier cerrojo de rol
    (2026-08-06, pedido del humano: «que muestre todos los menús como si fuera admin aunque no deje modificar»).

    Preservado con los roles nuevos porque `requiere()` se arma sobre `json_api_require_role`: lee todo lo que
    lee un admin, y para escribir vale lo que vale para `encargado`."""
    demo = instancia["demo"]
    desvios = []
    for (metodo, ruta), roles in sorted(_permitidas().items()):
        if (metodo, ruta) in NO_EJECUTAR:
            continue
        rechazada = _rechazada_por_rol(_sondear(demo, metodo, ruta))
        debe_entrar = metodo == "GET" or "encargado" in roles
        if rechazada == debe_entrar:
            desvios.append(f"demo {metodo} {ruta}: {'debía pasar' if debe_entrar else 'NO debía pasar'}")
    assert not desvios, "\n" + "\n".join(desvios)


# ── La matriz en sí (`app/permisos.py`) ──────────────────────────────────────


def test_la_matriz_admite_solo_roles_conocidos_y_admin_es_implicito():
    for capacidad in permisos.CAPACIDADES:
        roles = permisos.roles_con(capacidad)
        assert "admin" in roles, f"admin tiene que tener {capacidad}: es «todo»"
        assert set(roles) <= set(permisos.ROLES)
    assert set(permisos.capacidades_de("admin")) == set(permisos.CAPACIDADES)
    assert permisos.capacidades_de("un-rol-que-no-existe") == []
    assert permisos.capacidades_de(None) == []


def test_una_capacidad_mal_escrita_falla_al_armar_la_guarda_y_no_deja_una_ruta_abierta():
    with pytest.raises(KeyError):
        permisos.requiere("reportess")
    with pytest.raises(KeyError):
        permisos.requiere_segun_metodo(lectura="reportes", escritura="no.existe")


def test_staff_se_retiro_del_vocabulario_y_con_el_la_capacidad_que_era_solo_suya():
    """ADR-071: `staff` ya no es un rol ni lista capacidades, y `catalogo.configurar` (la API de unidades y categorías, que sólo
    existía para él) se eliminó: esa escritura pide `config`, o sea sólo admin."""
    assert "staff" not in permisos.ROLES
    assert "staff" not in permisos.matriz_por_rol()
    assert permisos.capacidades_de("staff") == []
    assert "catalogo.configurar" not in permisos.CAPACIDADES
    for capacidad in permisos.CAPACIDADES:
        assert "staff" not in permisos.roles_con(capacidad), capacidad


def test_quien_puede_ajustar_stock_tambien_puede_mover_lotes():
    """`OpcionesStock.con_lotes` está apagada (`app/depositos_ganchos.py`): el ajuste de stock ignora el lote. Si algún día se
    prende, un rol con `stock.ajustar` y sin `vencimientos.mover` alteraría lotes por la ruta alternativa; mientras tanto, que
    no exista ese rol es lo que mantiene la puerta cerrada."""
    assert set(permisos.roles_con("stock.ajustar")) <= set(permisos.roles_con("vencimientos.mover"))


def test_lo_que_el_humano_dejo_solo_para_admin_sigue_siendo_solo_de_admin():
    """Escrito a mano (ADR-049): el encargado NO tiene usuarios, configuración, logs, la estructura del local ni la
    reapertura de un día cerrado; y ningún rol nuevo tiene lo que era exclusivo de admin salvo el encargado con lo
    que se le dio a propósito."""
    solo_admin = {"usuarios.admin", "config", "logs", "sucursales.admin", "caja.admin", "cierre_diario.reabrir",
                  "facturas.nota_credito"}
    for capacidad in solo_admin:
        assert permisos.roles_con(capacidad) == ("admin",), capacidad
    for rol in ("encargado", "vendedor", "cajero", "deposito"):
        assert not solo_admin & set(permisos.capacidades_de(rol)), rol


def test_toda_capacidad_tiene_una_guarda_montada(admin_client):
    """Una capacidad que ningún router usa es un permiso que se creyó dar y no rige. Las de sólo-SPA se exceptúan
    a mano y por nombre."""
    usadas = permisos.capacidades_usadas()
    sin_guarda = set(permisos.CAPACIDADES) - usadas - permisos.SOLO_SPA
    assert not sin_guarda, f"capacidades que ninguna guarda exige: {sorted(sin_guarda)}"
    assert not (usadas & permisos.SOLO_SPA), "una capacidad de sólo-SPA tiene guarda: ya no es de sólo-SPA"


# ── Lo que la SPA recibe ─────────────────────────────────────────────────────


def test_auth_me_y_login_traen_las_capacidades_del_rol(instancia):
    for rol in sorted(TODOS):
        me = instancia[rol].get("/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["capacidades"] == permisos.capacidades_de(rol)
        assert me.json()["role"] == rol
    # Escrito a mano: lo que NO le llega al cajero ni al depósito.
    cajero = set(instancia["cajero"].get("/auth/me").json()["capacidades"])
    assert "ventas.pos" in cajero and "caja.propia" in cajero
    assert not cajero & {"reportes", "margen", "reposicion.ver", "dashboard", "cierre_diario", "tesoreria", "cuenta_corriente",
                         "vencimientos.ver", "vencimientos.marcar", "vencimientos.mover", "reposicion.parametros"}
    # ADR-054: su menú es el mostrador (POS, ventas para reimprimir, turnos); las pantallas de gestión no se le ofrecen.
    assert not cajero & {"catalogo.pantalla", "stock.pantalla", "clientes.pantalla", "proveedores.pantalla"}
    deposito = set(instancia["deposito"].get("/auth/me").json()["capacidades"])
    assert {"stock.ver", "stock.ajustar", "stock.transferir", "compras.ver", "vencimientos.ver", "vencimientos.mover", "reposicion.ver", "reposicion.parametros"} <= deposito
    # No recibe compras: confirmar una recepción fija el costo del producto, y el depósito no maneja plata.
    assert not deposito & {"ventas.pos", "caja.propia", "reportes", "margen", "tesoreria", "clientes.ver", "compras.recibir", "costos.ver", "vencimientos.marcar"}
    login = https_client(instancia["admin"].app).post(
        "/auth/login", json={"username": "u-cajero", "password": "clave-larga-1"},
    )
    assert login.json()["capacidades"] == permisos.capacidades_de("cajero")


def test_el_visitante_de_la_demo_conserva_su_rol_y_la_bandera(instancia):
    me = instancia["demo"].get("/auth/me").json()
    assert me["role"] == "encargado"
    assert me["demo_readonly"] is True
    assert me["capacidades"] == permisos.capacidades_de("encargado")


def _ts(ruta: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "frontend" / "src" / ruta).read_text(encoding="utf-8")


def test_la_spa_conoce_las_mismas_capacidades_y_roles_que_el_backend():
    """`frontend/src/lib/permisos.ts` repite los NOMBRES (no la matriz). Si se separan, la SPA esconde o muestra lo que
    el backend ya no dice: se nota acá y no en producción."""
    ts = _ts("lib/permisos.ts")
    bloque = ts[ts.index("export const CAPACIDADES = ["):ts.index("] as const")]
    assert set(re.findall(r"'([a-z_.]+)'", bloque)) == set(permisos.CAPACIDADES)
    roles_ts = re.findall(r"value: '([a-z]+)'", ts[ts.index("export const ROLES_DE_USUARIO"):])
    assert sorted(roles_ts) == sorted(permisos.ROLES)


def test_el_archivo_de_capacidades_de_los_tests_del_frontend_es_el_de_permisos():
    """Los tests de vitest arman un usuario de cada rol con `capacidades-por-rol.json`, generado desde la matriz. Si la
    matriz cambia y el archivo no, la SPA se probaría contra una matriz que ya no existe."""
    import json

    archivo = json.loads(_ts("test/capacidades-por-rol.json"))
    assert archivo == permisos.matriz_por_rol(), (
        "regenerarlo: python -m app.permisos > frontend/src/test/capacidades-por-rol.json"
    )


# ── El `staff` retirado, por nombre ──────────────────────────────────────────


def test_un_staff_de_una_base_vieja_no_entra_a_ninguna_ruta_privada(instancia):
    """ADR-071: si una base vieja conserva un usuario `staff`, el rol no abre NINGUNA operación de la tabla (ni siquiera lo
    que hacía antes de los roles): cada una le da el rechazo por rol. Se inserta saltando la validación del router."""
    from libraauth.repository import UserRepository

    app = instancia["admin"].app
    viejo = UserRepository(app.state.users.session_factory, roles=(*permisos.ROLES, "staff"))
    viejo.create(username="u-staff", name="Staff", password="clave-larga-1", role="staff")
    abiertos = []
    try:
        staff = _entrar(app, abiertos, "u-staff", "clave-larga-1")
        abiertas = [
            f"staff {metodo} {ruta}: pasó"
            for (metodo, ruta) in sorted(PRIVADAS)
            if not _rechazada_por_rol(_sondear(staff, metodo, ruta))
        ]
        assert not abiertas, "\n" + "\n".join(abiertas)
    finally:
        for c in abiertos:
            c.close()
