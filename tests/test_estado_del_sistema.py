"""La barra de estado del pie (libracore ADR-075, libra-ui ADR-083): `GET /api/estado-del-sistema`. Quién entra lo prueba
la matriz de roles (fila `TODOS`); acá, qué ve cada uno: el respaldo y la versión del motor sólo quien tiene `config`."""


def test_el_admin_ve_respaldo_y_version_del_motor(admin_client):
    r = admin_client.get("/api/estado-del-sistema")
    assert r.status_code == 200
    datos = r.json()
    assert datos["usuario"]["rol"] == "admin"
    assert datos["libraedge"] is None, "fuera de un nodo y sin nodos registrados no hay nada de LibraEdge"
    assert datos["respaldo"] is not None and datos["version"]["motor"]


def test_el_cajero_no_ve_respaldo_ni_version_del_motor(cajero_client):
    datos = cajero_client.get("/api/estado-del-sistema").json()
    assert datos["usuario"]["rol"] == "cajero"
    assert datos["respaldo"] is None and datos["arca"] is None and datos["version"]["motor"] is None
