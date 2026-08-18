"""El cableado de los codigos de acceso a la demo (libraauth v0.26.1).

🔴 **Lo que fija: los TRES cableados de una demo, no uno.** `incluir_demo=True`
hace que `POST /auth/demo` exista, `ensure_demo_user` hace que haya a quien
loguear, y `app.state.demo_codigos` hace que se pueda entrar. Los conecta el
producto, cada uno por su lado, y **el tercero falla cerrado**: sin el, la demo
contesta `503 demo access codes not configured` y no entra nadie.

Ese modo de falla es la razon de este archivo. Un test que solo mirara que la
ruta de la demo existe pasaria en verde con la demo cerrada para todo el mundo.

🔑 **Se prueba por comportamiento, no leyendo `app.routes`.** En esta version
de FastAPI un `include_router` deja un objeto `_IncludedRouter` que no expone
`path` ni sus subrutas, asi que recorrer el arbol de rutas devuelve un conjunto
que **no contiene** las rutas incluidas — que son justo las que hay que mirar.
Un test escrito asi falla aunque el cableado este bien, y el intento de
arreglarlo con `getattr(r, "path", "")` lo vuelve peor: pasa a no fallar nunca.

Por eso cada asercion compara la ruta del ABM contra **una ruta hermana
inventada**: lo que se afirma es que el ABM se comporta distinto de algo que no
existe. Sin ese control, un catch-all que contesta 200 a cualquier cosa haria
pasar el test en una instancia sin ABM.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from motor_de_test import destino_dominio, limpiar_entre_tests

ABM = "/admin/demo-codigos"
INVENTADA = "/admin/demo-codigos-que-no-existe"


def _cliente_con_demo(monkeypatch, tmp_path, *, encendida: bool):
    """Arma la app con (o sin) el entorno de una demo.

    Se arma **dentro del test** y no en una fixture: `create_app()` mira
    `DEMO_MODE`/`DEMO_USERNAME` mientras corre, asi que el entorno tiene que
    estar puesto antes, y una fixture se resolveria demasiado temprano.
    """
    if encendida:
        monkeypatch.setenv("DEMO_MODE", "1")
        monkeypatch.setenv("DEMO_USERNAME", "visitante")
    else:
        monkeypatch.delenv("DEMO_MODE", raising=False)
        monkeypatch.delenv("DEMO_USERNAME", raising=False)
    # Este producto no tiene `fresh_database_url`: arma la app contra un
    # archivo temporal real con `destino_dominio`, y limpia el schema entre
    # tests porque varios arman dos apps sobre la misma base.
    limpiar_entre_tests()
    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    return app, TestClient(app, base_url="https://ventalibra.test")


def test_la_demo_tiene_repositorio_de_codigos(monkeypatch, tmp_path):
    """Sin esto la demo no deja entrar a nadie: falla cerrado."""
    app, _ = _cliente_con_demo(monkeypatch, tmp_path, encendida=True)
    assert getattr(app.state, "demo_codigos", None) is not None


def test_la_demo_publica_el_abm_de_codigos(monkeypatch, tmp_path):
    """Es por donde el backoffice emite los codigos.

    Sin credenciales tiene que rechazar (401/403), **no** dar 404: el 404 es
    lo que contesta una ruta que no existe, y es exactamente lo que devuelve
    la instancia de un cliente.
    """
    _, c = _cliente_con_demo(monkeypatch, tmp_path, encendida=True)
    r = c.get(ABM)
    control = c.get(INVENTADA)
    assert r.status_code != control.status_code, (
        "el ABM contesta igual que una ruta inexistente (%s): no esta montado"
        % control.status_code
    )
    assert r.status_code in (401, 403), r.status_code


def test_la_instancia_de_un_cliente_no_cablea_nada(monkeypatch, tmp_path):
    """El control negativo, que es lo que le da sentido a los dos de arriba.

    Si `demo_username()` devolviera algo siempre, los dos tests anteriores
    pasarian sin probar que el cableado depende de ser una demo.
    """
    app, c = _cliente_con_demo(monkeypatch, tmp_path, encendida=False)
    assert getattr(app.state, "demo_codigos", None) is None
    assert c.get(ABM).status_code == c.get(INVENTADA).status_code
