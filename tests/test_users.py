"""El ABM de usuarios: cambiarle la contraseña a otro, y el correo del alta.

Los dos llegaron el 2026-08-18, por un agujero que se encontró en LibraDesk y
que VentaLibra tenía igual: un usuario que olvida su contraseña no tiene forma
de recuperarla, y el administrador no tiene forma de ponerle una nueva. Se
arreglan los cuatro productos que comparten la pantalla `Usuarios` de
`libra-ui`, para que la acción exista en todos y no dé 404 en la mitad.

Gestiolibra y MedLibra ya tenían el endpoint (sin pantalla que lo llamara);
LibraDesk y VentaLibra no lo tenían. La forma es la de ellos: `PUT
/users/{id}/password`, cuerpo `{"password": ...}`, 204.
"""
from fastapi.testclient import TestClient

from conftest import https_client


def _alta_de_staff(client: TestClient, **extra) -> dict:
    body = {"username": "cristina", "name": "Cristina", "password": "vieja123",
            "role": "staff"}
    body.update(extra)
    r = client.post("/users", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_el_admin_le_cambia_la_contrasena_a_otro_usuario(admin_client: TestClient):
    """Se asiertan las DOS puntas: que la vieja deja de entrar y que la nueva
    entra. Con sólo la segunda, un endpoint que no hiciera nada y un login que
    aceptara cualquier cosa darían el mismo verde."""
    creado = _alta_de_staff(admin_client)

    r = admin_client.put(f"/users/{creado['id']}/password", json={"password": "nueva456"})
    assert r.status_code == 204

    otro = https_client(admin_client.app)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 401
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "nueva456"}).status_code == 200


def test_la_contrasena_vacia_se_rechaza_y_no_cambia_nada(admin_client: TestClient):
    """No alcanza con asertar el 422: un endpoint que devolviera 422 *después*
    de haber hasheado el vacío daría el mismo código y la cuenta quedaría
    abierta. Lo que prueba la guarda es que la anterior sigue entrando."""
    creado = _alta_de_staff(admin_client)

    for vacia in ("", "   "):
        r = admin_client.put(f"/users/{creado['id']}/password", json={"password": vacia})
        assert r.status_code == 422, f"{vacia!r} tendría que rechazarse"

    otro = https_client(admin_client.app)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 200


def test_no_hay_minimo_de_longitud(admin_client: TestClient):
    """Deliberado, y por eso tiene test: el endpoint existe para destrabar a
    alguien que quedó afuera, y un mínimo que el administrador no puede cumplir
    en el momento lo manda de vuelta a la base de datos. Si algún día se agrega
    una política, que sea una decisión y no un descuido — esto se pone rojo."""
    creado = _alta_de_staff(admin_client)

    assert admin_client.put(
        f"/users/{creado['id']}/password", json={"password": "x"},
    ).status_code == 204
    assert https_client(admin_client.app).post("/auth/login", json={
        "username": "cristina", "password": "x"}).status_code == 200


def test_contrasena_de_usuario_inexistente_devuelve_404(admin_client: TestClient):
    """Se asierta el cuerpo y no sólo el código: este producto sirve la SPA con
    un catch-all, así que una ruta que no existe también puede contestar 404 —
    un assert sobre el status daría verde con el endpoint sin escribir."""
    r = admin_client.put("/users/9999/password", json={"password": "loquesea"})
    assert r.status_code == 404
    assert r.json() == {"detail": "user not found"}


def test_staff_no_puede_cambiarle_la_contrasena_a_nadie(
    admin_client: TestClient, staff_client: TestClient,
):
    """El router entero cuelga de `require_admin_o_servicio`, así que la ruta
    nueva hereda el gate. Se cubre igual: el día que alguien monte este
    endpoint aparte, el gate se pierde sin que nada avise."""
    victima = _alta_de_staff(admin_client, username="victima")
    r = staff_client.put(f"/users/{victima['id']}/password", json={"password": "tomada"})
    assert r.status_code == 403


def test_el_email_del_alta_se_guarda_y_se_devuelve(admin_client: TestClient):
    creado = _alta_de_staff(admin_client, email="cristina@empresa.com")
    assert creado["email"] == "cristina@empresa.com"

    listado = admin_client.get("/users").json()
    guardado = next(u for u in listado if u["username"] == "cristina")
    assert guardado["email"] == "cristina@empresa.com"


def test_editar_nombre_o_rol_no_borra_el_email(admin_client: TestClient):
    """La razón por la que `UserUpdate.email` es `None` y no `""`.

    El toggle de activo/inactivo de la grilla manda el cuerpo entero sin tocar
    el correo. Con un default vacío, desactivar a alguien le borraba el mail en
    silencio — y el mail es lo único que permite recuperar la contraseña.
    """
    creado = _alta_de_staff(admin_client, email="cristina@empresa.com")

    r = admin_client.put(f"/users/{creado['id']}", json={
        "name": "Cristina G.", "role": "staff", "active": False})
    assert r.status_code == 200
    assert r.json()["email"] == "cristina@empresa.com"
    assert r.json()["name"] == "Cristina G."


def test_el_email_se_puede_vaciar_pidiendolo(admin_client: TestClient):
    """La contracara: `""` explícito sí lo borra. Sin esto, un correo cargado
    mal no se podría sacar nunca."""
    creado = _alta_de_staff(admin_client, email="mal@escrito.com")

    r = admin_client.put(f"/users/{creado['id']}", json={
        "name": "Cristina", "role": "staff", "active": True, "email": ""})
    assert r.status_code == 200
    assert r.json()["email"] == ""
