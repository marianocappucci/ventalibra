"""Lo que cada rol HACE, de punta a punta (ADR-049).

`test_roles_matriz.py` prueba a quién deja pasar cada guarda. Acá, con permiso en la mano, que el flujo funciona de
verdad para ese rol —vender, llevar el turno, mover mercadería, recibir una compra— y que lo ajeno sigue cerrado. Un
permiso bien puesto en la tabla que rompe el flujo del rol (el POS que necesita un turno, el ticket del cierre del propio
turno, el precio de la lista) se ve acá y no con un cliente.
"""
import pytest
from conftest import https_client
from ventas_helpers import (
    abrir_turno,
    ajustar,
    caja_default,
    con_stock,
    crear_deposito,
    crear_item,
    deposito_default,
    registrar_venta,
    stock,
)


def _entrar(admin_client, rol, usuario=None):
    """Un cliente logueado como un usuario nuevo de ese rol (misma app y base que `admin_client`)."""
    usuario = usuario or f"u-{rol}"
    creado = admin_client.post("/users", json={
        "username": usuario, "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    entrada = cliente.post("/auth/login", json={"username": usuario, "password": "clave-larga-1"})
    assert entrada.status_code == 200, entrada.text
    return cliente


@pytest.mark.parametrize("rol", ["cajero", "vendedor", "encargado", "staff"])
def test_quien_vende_abre_su_turno_vende_y_cierra(admin_client, rol):
    """El POS exige un turno propio abierto (`exigir_turno=True`): quien vende necesita `caja.propia` además de
    `ventas.pos`. Sin eso el vendedor podría entrar al POS y no cobrar nunca."""
    item = crear_item(admin_client)
    deposito = deposito_default(admin_client)
    con_stock(admin_client, item, deposito, "20")
    usuario = _entrar(admin_client, rol)

    turno = abrir_turno(usuario)
    venta = registrar_venta(usuario, item, cantidad="2")
    assert venta["id"]
    assert float(stock(admin_client, item, deposito)) == 18.0

    # El precio de cada línea lo pide el POS a la lista predeterminada, y el promotor de promociones también.
    assert usuario.get("/api/listas-precio").status_code == 200
    assert usuario.post("/api/promociones/calcular", json={"items": []}).status_code != 403

    cierre = usuario.post(f"/api/turnos/{turno}/cerrar", json={"monto_declarado": 3000})
    assert cierre.status_code == 200, cierre.text
    # El ticket del cierre del propio turno es lo que imprime el POS: lo pide `caja.propia` y no `cierre_diario`.
    assert usuario.get(f"/api/cierre-diario/turno/{turno}/ticket").status_code == 200


@pytest.mark.parametrize("rol", ["cajero", "vendedor"])
def test_el_mostrador_puede_devolver_y_anular_pero_no_ver_el_cierre_diario_ni_los_reportes(admin_client, rol):
    """Decisión del humano (2026-09-15): «dejá anular y devolver para el cajero también». Sigue valiendo para los dos
    roles del mostrador; lo que no tienen es el cierre diario de toda la sucursal ni ningún reporte."""
    item = crear_item(admin_client)
    con_stock(admin_client, item, deposito_default(admin_client), "20")
    usuario = _entrar(admin_client, rol)
    abrir_turno(usuario)
    venta = registrar_venta(usuario, item, cantidad="2")

    assert usuario.get(f"/api/ventas/{venta['id']}").status_code == 200
    assert usuario.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "error de carga"}).status_code != 403
    for prohibido in ("/api/cierre-diario/preview", "/api/reportes", "/api/reportes/margen", "/api/dashboard"):
        assert usuario.get(prohibido).status_code == 403, prohibido


def test_el_encargado_ve_y_cierra_los_turnos_de_otros_y_los_demas_no(admin_client):
    """El router de turnos del motor sólo deja ver los turnos ajenos si `role == "admin"` escrito a mano; el encargado no
    lo es, así que `usuario_de_turnos` (app/cajas_ganchos.py) se lo presenta sólo a ese router. Se prueba por
    comportamiento: lo ve y lo cierra el encargado; ni un vendedor ni otro cajero."""
    cajero = _entrar(admin_client, "cajero")
    turno = abrir_turno(cajero)
    encargado = _entrar(admin_client, "encargado")
    vendedor = _entrar(admin_client, "vendedor")
    otro_cajero = _entrar(admin_client, "cajero", "otro-cajero")

    de_todos = encargado.get("/api/turnos").json()["turnos"]
    assert turno in [t["id"] for t in de_todos]
    assert turno not in [t["id"] for t in vendedor.get("/api/turnos").json()["turnos"]]
    assert turno not in [t["id"] for t in otro_cajero.get("/api/turnos").json()["turnos"]]

    assert vendedor.get(f"/api/turnos/{turno}").status_code == 403
    assert otro_cajero.post(f"/api/turnos/{turno}/cerrar", json={"monto_declarado": 0}).status_code == 403
    assert encargado.get(f"/api/turnos/{turno}").status_code == 200
    cierre = encargado.post(f"/api/turnos/{turno}/cerrar", json={"monto_declarado": 0})
    assert cierre.status_code == 200, cierre.text
    # Y la sesión del encargado no se volvió admin: sigue sin usuarios ni configuración.
    assert encargado.get("/users").status_code == 403
    assert encargado.get("/api/config/empresa").status_code == 403


def test_el_deposito_maneja_mercaderia_y_recibe_compras_pero_no_vende_ni_toca_plata(admin_client):
    item = crear_item(admin_client, price="1000.00")
    principal = deposito_default(admin_client)
    segundo = crear_deposito(admin_client, "Depósito chico")["id"]
    proveedor = admin_client.post("/api/proveedores", json={"nombre": "Distribuidora SA"}).json()["id"]
    deposito = _entrar(admin_client, "deposito")

    # Ajusta stock y transfiere entre depósitos.
    assert ajustar(deposito, item, principal, 10).status_code == 200
    mover = deposito.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": principal, "destino_id": segundo, "cantidad": 4.0, "observaciones": "",
    })
    assert mover.status_code == 200, mover.text
    assert float(stock(admin_client, item, segundo)) == 4.0

    # Recibe mercadería contra una compra: crea, carga, confirma.
    recepcion = deposito.post("/api/purchase-receipts", json={"proveedor_id": proveedor})
    assert recepcion.status_code == 200, recepcion.text
    rid = recepcion.json()["id"]
    linea = deposito.post(f"/api/purchase-receipts/{rid}/items", json={"item_id": item, "quantity": "5", "unit_cost": "700"})
    assert linea.status_code == 200, linea.text
    assert deposito.post(f"/api/purchase-receipts/{rid}/confirm", json={"deposito_id": principal}).status_code == 200
    # Lee productos y proveedores.
    assert deposito.get("/api/productos").status_code == 200
    assert deposito.get("/api/proveedores").status_code == 200

    # Pero no vende, no tiene caja, no emite órdenes de compra ni mueve plata ni edita productos.
    assert deposito.post("/api/ventas", json={"items": [], "pagos": []}).status_code == 403
    assert deposito.get("/api/cajas").status_code == 403
    assert deposito.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja_default(admin_client)}).status_code == 403
    assert deposito.post("/api/purchase-orders", json={"proveedor_id": proveedor}).status_code == 403
    assert deposito.post("/api/productos", json={"nombre": "X", "unidad": "u", "precio_venta": "1"}).status_code == 403
    for prohibido in ("/api/ventas", "/api/clientes", "/api/tesoreria", "/api/egresos", "/api/reportes", "/api/dashboard"):
        assert deposito.get(prohibido).status_code == 403, prohibido


@pytest.mark.parametrize("rol", ["cajero", "vendedor"])
def test_el_mostrador_consulta_stock_y_precios_pero_no_los_cambia(admin_client, rol):
    item = crear_item(admin_client)
    con_stock(admin_client, item, deposito_default(admin_client), "5")
    usuario = _entrar(admin_client, rol)
    assert usuario.get("/api/stock").status_code == 200
    assert usuario.get(f"/api/stock/{item}").status_code == 200
    assert usuario.get("/api/productos").status_code == 200
    assert usuario.get("/api/listas-precio").status_code == 200
    assert ajustar(usuario, item, deposito_default(admin_client), 1).status_code == 403
    assert usuario.post("/api/listas-precio", json={"nombre": "Mia"}).status_code == 403
    assert usuario.put(f"/api/productos/{item}", json={"nombre": "Otro", "precio_venta": "1"}).status_code == 403


def test_el_encargado_maneja_precios_stock_y_plata_pero_no_la_configuracion(admin_client):
    item = crear_item(admin_client)
    principal = deposito_default(admin_client)
    encargado = _entrar(admin_client, "encargado")
    assert ajustar(encargado, item, principal, 5).status_code == 200
    assert encargado.post("/api/listas-precio", json={"nombre": "Mayorista"}).status_code == 200
    for lectura in ("/api/reportes", "/api/reportes/margen", "/api/dashboard", "/api/tesoreria", "/api/egresos",
                    "/api/libros-iva", "/api/cierre-diario/preview", "/api/cuenta-corriente", "/api/stock"):
        assert encargado.get(lectura).status_code == 200, lectura
    for prohibido in ("/users", "/logs", "/settings/scale", "/api/config/empresa", "/api/config/backups", "/config/arca"):
        assert encargado.get(prohibido).status_code == 403, prohibido
    # La reapertura de un día cerrado es sólo de admin: 403 aunque el cierre no exista.
    assert encargado.post("/api/cierre-diario/999999/reabrir", json={"motivo": "x"}).status_code == 403
    # Ni la estructura del local.
    assert encargado.post("/api/cajas", json={"nombre": "Nueva"}).status_code == 403
    assert encargado.post("/api/sucursales", json={"nombre": "Otra"}).status_code == 403
