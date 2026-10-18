"""Dos requests a la vez no comparten la transacción (ADR-089).

🔴 **El defecto que este archivo fija.** Hasta ADR-089 la app tenía **una sola conexión del dominio** (`app.state.conn`)
para todos los requests de un proceso. FastAPI corre los endpoints `def` en un threadpool, así que dos requests
concurrentes del mismo worker escribían en la MISMA transacción: el `rollback()` de uno (el 409 de un código repetido)
deshacía el `INSERT` que el otro todavía no había confirmado, y el `commit()` de uno confirmaba lo que el otro dejó a
medias. El segundo se llevaba un 200 con un `id` de una fila que no existe. Con 2 workers por instancia (2026-10-17) esto
dejó de ser teórico.

Dos tests:

- **la intercalación exacta**, sin azar: el request A inserta una categoría y espera; el request B choca con una unidad
  repetida y revierte; recién entonces A confirma. Es el peor orden posible y con la conexión compartida pasa siempre.
- **la carga**: varios hilos mezclando altas, unidades repetidas y lecturas. Cada alta que contestó 200 tiene que estar
  en la base, y no puede haber un solo 500.
"""
import threading

import psycopg
import pytest
from libracore.db._postgres import ConnectionWrapper, Cursor
from motor_de_test import TEST_DATABASE_URL

#: Segundos que un hilo espera al otro antes de rendirse: si algo se traba, el test falla en lugar de colgar la corrida.
ESPERA = 20


def _crudo() -> str:
    return TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _categorias_en_la_base() -> set[str]:
    """Lo que ve CUALQUIER otro cliente de la base: una conexión nueva, ajena a la de los requests."""
    with psycopg.connect(_crudo()) as otra:
        return {fila[0] for fila in otra.execute("SELECT name FROM categories").fetchall()}


def test_el_rollback_de_un_request_no_deshace_el_insert_de_otro(admin_client, monkeypatch):
    """A inserta una categoría y, antes de que confirme, B revierte por una unidad repetida. La categoría de A tiene que
    quedar: cada request tiene su propia transacción."""
    admin_client.post("/catalog/units", json={"code": "dup", "name": "Repetida"})   # la primera, para que la segunda choque

    a_inserto = threading.Event()
    b_revirtio = threading.Event()
    execute = Cursor.execute
    rollback = ConnectionWrapper.rollback

    def execute_de_prueba(self, sql, params=None):
        if sql.startswith("INSERT INTO units") and params and params[0] == "dup":
            # B no arranca hasta que A tenga su INSERT pendiente: es lo que fuerza el orden malo.
            assert a_inserto.wait(ESPERA), "A nunca insertó"
        resultado = execute(self, sql, params)
        if sql.startswith("INSERT INTO categories") and params and params[0] == "Fideos":
            a_inserto.set()
            # A no confirma hasta que B haya revertido.
            assert b_revirtio.wait(ESPERA), "B nunca revirtió"
        return resultado

    def rollback_de_prueba(self):
        resultado = rollback(self)
        if a_inserto.is_set():
            b_revirtio.set()
        return resultado

    monkeypatch.setattr(Cursor, "execute", execute_de_prueba)
    monkeypatch.setattr(ConnectionWrapper, "rollback", rollback_de_prueba)

    respuestas = {}

    def pedir(clave, metodo, ruta, cuerpo):
        respuestas[clave] = getattr(admin_client, metodo)(ruta, json=cuerpo)

    hilos = [
        threading.Thread(target=pedir, args=("a", "post", "/catalog/categories", {"name": "Fideos"})),
        threading.Thread(target=pedir, args=("b", "post", "/catalog/units", {"code": "dup", "name": "Otra"})),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(ESPERA * 2)
    assert not any(hilo.is_alive() for hilo in hilos), "un request quedó colgado"
    monkeypatch.undo()

    assert respuestas["b"].status_code == 409, respuestas["b"].text
    assert respuestas["a"].status_code == 200, respuestas["a"].text
    assert "Fideos" in _categorias_en_la_base(), (
        "el request A contestó 200 pero su categoría no está en la base: el rollback del request B se la llevó puesta"
    )


HILOS = 8
VUELTAS = 12


def test_requests_concurrentes_no_pierden_escrituras_ni_dan_500(admin_client):
    """Altas, unidades repetidas y lecturas a la vez, desde varios hilos."""
    admin_client.post("/catalog/units", json={"code": "dup", "name": "Repetida"})
    creadas: list[str] = []
    fallas: list[str] = []
    candado = threading.Lock()
    salida = threading.Barrier(HILOS)

    def trabajar(hilo: int) -> None:
        salida.wait(ESPERA)
        for vuelta in range(VUELTAS):
            nombre = f"cat-{hilo}-{vuelta}"
            try:
                alta = admin_client.post("/catalog/categories", json={"name": nombre})
                repetida = admin_client.post("/catalog/units", json={"code": "dup", "name": "Otra"})
                lista = admin_client.get("/catalog/categories")
            except Exception as exc:   # el TestClient re-levanta el 500 de la app: es una falla, no un hilo que muere en silencio
                with candado:
                    fallas.append(f"{nombre}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            with candado:
                if alta.status_code == 200:
                    creadas.append(nombre)
                else:
                    fallas.append(f"alta {nombre}: {alta.status_code} {alta.text[:120]}")
                if repetida.status_code != 409:
                    fallas.append(f"unidad repetida: {repetida.status_code} {repetida.text[:120]}")
                if lista.status_code != 200:
                    fallas.append(f"lista: {lista.status_code} {lista.text[:120]}")

    hilos = [threading.Thread(target=trabajar, args=(n,)) for n in range(HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(ESPERA * 6)
    assert not any(hilo.is_alive() for hilo in hilos), "un hilo quedó colgado"

    assert not fallas, f"{len(fallas)} respuestas inesperadas, p. ej.: {fallas[:3]}"
    perdidas = sorted(set(creadas) - _categorias_en_la_base())
    assert not perdidas, f"{len(perdidas)} de {len(creadas)} altas dieron 200 y no están en la base, p. ej.: {perdidas[:3]}"


@pytest.mark.parametrize("ruta", ["/catalog/categories", "/catalog/units", "/api/logs"])
def test_las_lecturas_concurrentes_no_chocan(admin_client, ruta):
    """Lecturas a la vez sobre lo que antes compartía el cursor de la conexión única."""
    respuestas: list[int] = []
    candado = threading.Lock()

    def leer() -> None:
        for _ in range(10):
            try:
                estado = admin_client.get(ruta).status_code
            except Exception as exc:
                estado = type(exc).__name__
            with candado:
                respuestas.append(estado)

    hilos = [threading.Thread(target=leer) for _ in range(6)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(ESPERA * 3)
    assert respuestas.count(200) == 60, sorted(set(respuestas))
