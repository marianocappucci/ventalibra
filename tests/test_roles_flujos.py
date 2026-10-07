"""Lo que cada rol HACE, de punta a punta (ADR-049).

`test_roles_matriz.py` prueba a quién deja pasar cada guarda. Acá, con permiso en la mano, que el flujo funciona de
verdad para ese rol —vender, llevar el turno, mover mercadería, recibir una compra (el encargado)— y que lo ajeno sigue cerrado. Un
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


@pytest.mark.parametrize("rol", ["cajero", "vendedor", "encargado"])
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


def test_el_mostrador_ve_solo_las_ventas_de_sus_turnos(admin_client):
    """ADR-068 (libracommerce ADR-038; decisión del humano, 2026-10-07): el cajero y el vendedor listan, abren, anulan,
    devuelven, facturan y reimprimen sólo las ventas de los turnos de caja que abrieron, abiertos o cerrados; una ajena es
    404, como una que no existe. El encargado (`ventas.todas`) ve todas."""
    item = crear_item(admin_client)
    con_stock(admin_client, item, deposito_default(admin_client), "20")
    cajero = _entrar(admin_client, "cajero")
    vendedor = _entrar(admin_client, "vendedor")
    turno_del_cajero = abrir_turno(cajero)
    del_cajero = registrar_venta(cajero, item, cantidad="1")
    # Un turno cerrado sigue siendo suyo: la venta de ayer la puede devolver quien la cobró.
    assert cajero.post(f"/api/turnos/{turno_del_cajero}/cerrar", json={"monto_declarado": 0}).status_code == 200
    abrir_turno(vendedor)
    del_vendedor = registrar_venta(vendedor, item, cantidad="1")

    def ids(cliente):
        r = cliente.get("/api/ventas")
        assert r.status_code == 200, r.text
        return {v["id"] for v in r.json()}

    assert ids(cajero) == {del_cajero["id"]}
    assert ids(vendedor) == {del_vendedor["id"]}
    assert ids(_entrar(admin_client, "encargado")) >= {del_cajero["id"], del_vendedor["id"]}
    assert ids(admin_client) >= {del_cajero["id"], del_vendedor["id"]}

    for cliente, propia, ajena in ((cajero, del_cajero, del_vendedor), (vendedor, del_vendedor, del_cajero)):
        assert cliente.get(f"/api/ventas/{propia['id']}").status_code == 200
        assert cliente.get(f"/ventas/{propia['id']}/ticket").status_code == 200
        for ruta in (f"/api/ventas/{ajena['id']}", f"/ventas/{ajena['id']}/ticket",
                     f"/ventas/{ajena['id']}/devuelto", f"/api/ventas/{ajena['id']}/mp-status"):
            r = cliente.get(ruta)
            assert r.status_code == 404, (ruta, r.status_code, r.text)
        for ruta in (f"/api/ventas/{ajena['id']}/anular", f"/api/ventas/{ajena['id']}/facturar",
                     f"/api/ventas/{ajena['id']}/mp-qr"):
            r = cliente.post(ruta, json={})
            assert r.status_code == 404, (ruta, r.status_code, r.text)
    # Nada de lo ajeno se tocó.
    assert admin_client.get(f"/api/ventas/{del_vendedor['id']}").json()["estado"] == "cobrada"
    # La propia del turno ya cerrado, sí: el cajero la anula.
    assert cajero.post(f"/api/ventas/{del_cajero['id']}/anular", json={}).status_code == 200


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


def test_el_ticket_de_un_turno_es_de_quien_lo_abrio_y_de_quien_ve_los_de_todos(admin_client):
    """`GET /api/cierre-diario/turno/{id}/ticket`: el handler del motor imprime el arqueo de CUALQUIER turno por id, y la
    guarda de la ruta (`caja.propia`) no mira de quién es. Antes un cajero o un vendedor pedía el arqueo de los turnos de
    otro (medido con dos usuarios reales); ahora `solo_su_turno_o_todos` compara `turnos_caja.usuario_id` con la sesión
    ANTES de llegar al handler. Lo ajeno sólo lo ve `turnos.todos` (admin y encargado)."""
    cajero = _entrar(admin_client, "cajero")
    vendedor = _entrar(admin_client, "vendedor")
    del_cajero = abrir_turno(cajero)
    assert cajero.post(f"/api/turnos/{del_cajero}/cerrar", json={"monto_declarado": 0}).status_code == 200
    del_vendedor = abrir_turno(vendedor)
    assert vendedor.post(f"/api/turnos/{del_vendedor}/cerrar", json={"monto_declarado": 0}).status_code == 200
    abierto_de_otro = abrir_turno(vendedor)  # sigue abierto: el motor daría 409 y contaría que existe

    def ticket(cliente, turno):
        return cliente.get(f"/api/cierre-diario/turno/{turno}/ticket")

    # Lo propio: sí.
    assert ticket(cajero, del_cajero).status_code == 200
    assert ticket(vendedor, del_vendedor).status_code == 200
    # Lo ajeno, con dos usuarios reales: no, en los dos sentidos (y el motor ni se entera de si está abierto).
    assert ticket(cajero, del_vendedor).status_code == 403
    assert ticket(vendedor, del_cajero).status_code == 403
    assert ticket(cajero, abierto_de_otro).status_code == 403
    assert ticket(vendedor, del_vendedor + 1000).status_code == 404  # turno inexistente: el 404 del motor
    assert ticket(cajero, del_cajero).headers["content-type"] == "application/pdf"
    # Quien ve los turnos de todos, sí.
    otro = _entrar(admin_client, "encargado")
    assert ticket(otro, del_cajero).status_code == 200
    assert ticket(otro, del_vendedor).status_code == 200
    assert ticket(admin_client, del_cajero).status_code == 200
    # El depósito no tiene turnos (403 por rol) y sin sesión, 401.
    assert ticket(_entrar(admin_client, "deposito"), del_cajero).status_code == 403
    assert ticket(https_client(admin_client.app), del_cajero).status_code == 401


def test_el_deposito_maneja_mercaderia_y_lee_compras_pero_no_las_recibe_ni_vende_ni_toca_plata(admin_client):
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

    # Lee productos, proveedores y las órdenes y recepciones de compra, pero NO las recibe (lo hace el encargado: confirmar
    # una recepción fija el costo del producto). El ciclo completo de recibir está en `test_el_encargado_recibe_compras`.
    assert deposito.get("/api/productos").status_code == 200
    assert deposito.get("/api/proveedores").status_code == 200
    assert deposito.get("/api/purchase-orders").status_code == 200
    assert deposito.get("/api/purchase-receipts").status_code == 200
    assert deposito.post("/api/purchase-receipts", json={"proveedor_id": proveedor}).status_code == 403

    # Pero no vende, no tiene caja, no emite órdenes de compra ni mueve plata ni edita productos.
    assert deposito.post("/api/ventas", json={"items": [], "pagos": []}).status_code == 403
    assert deposito.get("/api/cajas").status_code == 403
    assert deposito.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja_default(admin_client)}).status_code == 403
    assert deposito.post("/api/purchase-orders", json={"proveedor_id": proveedor}).status_code == 403
    assert deposito.post("/api/productos", json={"nombre": "X", "unidad": "u", "precio_venta": "1"}).status_code == 403
    for prohibido in ("/api/ventas", "/api/clientes", "/api/tesoreria", "/api/egresos", "/api/reportes", "/api/dashboard"):
        assert deposito.get(prohibido).status_code == 403, prohibido


def test_el_encargado_recibe_compras_y_el_costo_queda_en_el_producto(admin_client):
    """Recibir mercadería es del encargado: crea la recepción, carga la línea y confirma, y el stock sube y
    el costo recibido queda como costo del producto."""
    item = crear_item(admin_client)
    principal = deposito_default(admin_client)
    proveedor = admin_client.post("/api/proveedores", json={"nombre": "Distribuidora SA"}).json()["id"]
    usuario = _entrar(admin_client, "encargado")
    recepcion = usuario.post("/api/purchase-receipts", json={"proveedor_id": proveedor})
    assert recepcion.status_code == 200, recepcion.text
    rid = recepcion.json()["id"]
    linea = usuario.post(f"/api/purchase-receipts/{rid}/items", json={"item_id": item, "quantity": "5", "unit_cost": "700"})
    assert linea.status_code == 200, linea.text
    assert usuario.post(f"/api/purchase-receipts/{rid}/confirm", json={"deposito_id": principal}).status_code == 200
    assert float(stock(admin_client, item, principal)) == 5.0
    assert admin_client.get(f"/api/stock/{item}").json()["producto"]["precio_costo"] == 700.0


@pytest.mark.parametrize("rol", ["cajero", "vendedor"])
def test_el_mostrador_puede_fiar_desde_el_pos_y_el_cajero_no_ve_saldos_recibos_ni_cobranzas(admin_client, rol):
    """Decisión del humano (2026-09-29): el cajero SIGUE fiando en el mostrador (ADR-031), pero no ve saldos, recibos ni cobranzas.

    Para fiar, el POS sólo usa `GET /api/clientes` (elegir a quién, `clientes.ver`) y `POST /api/ventas` con el medio
    `cuenta_corriente` y el cliente (`ventas.pos`): la deuda la asienta el servidor. Ninguna de las dos abre la cuenta corriente,
    así que no hace falta una capacidad más: `cuenta_corriente` (saldos, cobrar, recibos) sigue siendo del vendedor y el encargado. Medido: el cajero fiaba con 200 antes de este test y su lectura de saldos era 403."""
    item = crear_item(admin_client)
    con_stock(admin_client, item, deposito_default(admin_client), "20")
    cliente = admin_client.post("/api/clientes", json={"name": "Doña Rosa"}).json()["id"]
    usuario = _entrar(admin_client, rol)
    abrir_turno(usuario)
    assert any(c["id"] == cliente for c in usuario.get("/api/clientes").json())
    # La ficha (con facturas, presupuestos y remitos) es del vendedor, no del cajero (ADR-069).
    ficha = usuario.get(f"/api/clientes/{cliente}")
    assert ficha.status_code == (403 if rol == "cajero" else 200), ficha.text
    if rol == "vendedor":
        assert {"facturas", "presupuestos", "remitos"} <= set(ficha.json())

    venta = registrar_venta(
        usuario, item, cantidad="2", cliente_id=cliente, pagos=[{"medio": "cuenta_corriente", "monto": 3000.0}],
    )
    assert venta["estado"] == "cobrada"
    saldos = admin_client.get("/api/cuenta-corriente").json()
    assert next(c for c in saldos["clientes"] if c["id"] == cliente)["saldo"] == 3000.0  # la deuda quedó asentada

    lectura = [
        "/api/cuenta-corriente", f"/api/cuenta-corriente/{cliente}", "/api/cuenta-corriente/cajas", "/api/recibos",
        "/api/recibos/999999", "/api/recibos/999999/pdf",
    ]
    escritura = [
        ("POST", f"/api/cuenta-corriente/{cliente}/pagar", {"monto": 100, "medio": "efectivo"}),
        ("DELETE", "/api/cuenta-corriente/pagos/999999", None),
        ("POST", "/api/recibos/999999/anular", {"motivo": "x"}),
        ("POST", f"/api/recibos/venta/{venta['id']}", {}),
    ]
    if rol == "cajero":
        for url in lectura:
            assert usuario.get(url).status_code == 403, url
        for metodo, url, cuerpo in escritura:
            assert usuario.request(metodo, url, json=cuerpo).status_code == 403, (metodo, url)
    else:  # el vendedor no cambia: ve y cobra la cuenta corriente, pero no da de baja pagos ni anula recibos
        assert usuario.get("/api/cuenta-corriente").status_code == 200
        assert usuario.get(f"/api/cuenta-corriente/{cliente}").status_code == 200
        assert usuario.get("/api/recibos").status_code == 200
        assert usuario.request("DELETE", "/api/cuenta-corriente/pagos/999999").status_code == 403
        assert usuario.post("/api/recibos/999999/anular", json={"motivo": "x"}).status_code == 403


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
    for prohibido in ("/users", "/api/logs", "/settings/scale", "/api/config/empresa", "/api/config/backups", "/config/arca"):
        assert encargado.get(prohibido).status_code == 403, prohibido
    # La reapertura de un día cerrado es sólo de admin: 403 aunque el cierre no exista.
    assert encargado.post("/api/cierre-diario/999999/reabrir", json={"motivo": "x"}).status_code == 403
    # Ni la estructura del local.
    assert encargado.post("/api/cajas", json={"nombre": "Nueva"}).status_code == 403
    assert encargado.post("/api/sucursales", json={"nombre": "Otra"}).status_code == 403
