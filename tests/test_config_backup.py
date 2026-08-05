"""Datos de empresa, logo y Datos / Backup — ítems 1, 4 y 5.

El mecanismo es de `libracore` y tiene sus propios tests ahí. Lo que se prueba
**acá** es lo que sólo este producto puede verificar, y es más que en los otros:

1. 🔴 Que el backup traiga **las DOS bases**. VentaLibra guarda `usuarios` en
   la base de LibraCore, separada de la del dominio. Un backup de una sola no
   se puede restaurar —o volvés el dominio y te quedan usuarios de otro
   momento, o al revés— y **no falla**: da un ZIP que se descarga y pesa poco.
2. 🔴 Que después de restaurar, la app sirva los datos **nuevos**. Este
   producto usa sqlite3 crudo con una conexión compartida: sin cerrarla y
   reabrirla, el restore devuelve `ok` y el proceso sigue leyendo el archivo
   viejo.
3. Que la pantalla de logs siga funcionando después de un restore — su
   repositorio se construye una sola vez, al arrancar, con la conexión que el
   restore cierra.
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 40


def _producto(client, nombre="Yerba"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    r = client.post("/catalog/items", json={
        "item_type": "product", "name": nombre, "unit_code": "u",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


# ── 🔴 Las dos bases ──────────────────────────────────────────────────────

def test_el_backup_trae_las_dos_bases(admin_client):
    """La de dominio y la de LibraCore, donde viven los usuarios."""
    _producto(admin_client)

    r = admin_client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        bases = sorted(n for n in z.namelist() if n.startswith("bases/"))

    assert len(bases) == 2, f"esperaba dos bases, vinieron {bases}"
    assert any("libracore" in b for b in bases), f"falta la base de usuarios: {bases}"


def test_el_backup_trae_el_logo(admin_client):
    admin_client.post("/api/config/empresa/logo", files={"logo": ("l.png", _png(), "image/png")})

    r = admin_client.get("/api/config/backup-ahora")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert any(n.startswith("datos/logos/") for n in z.namelist()), z.namelist()


# ── 🔴 Que el restore tenga efecto de verdad ──────────────────────────────

def test_despues_de_restaurar_la_app_sirve_los_datos_nuevos(admin_client):
    """Sin cerrar y reabrir la conexión compartida, el restore devuelve `ok` y
    el proceso sigue leyendo el archivo viejo — sin ninguna señal de error."""
    _producto(admin_client, "Antes del backup")
    copia = admin_client.get("/api/config/backup-ahora").content

    _producto(admin_client, "Después del backup")
    nombres = [i["name"] for i in admin_client.get("/catalog/items").json()]
    assert "Después del backup" in nombres

    r = admin_client.post("/api/config/restore",
                          files={"backup_file": ("b.zip", copia, "application/zip")})
    assert r.status_code == 200, r.text

    nombres = [i["name"] for i in admin_client.get("/catalog/items").json()]
    assert "Antes del backup" in nombres
    assert "Después del backup" not in nombres


def test_la_sesion_sobrevive_al_restore(admin_client):
    """`usuarios` viaja en el backup, así que restaurar reemplaza también la
    base de la sesión. Con el mismo usuario en las dos puntas, la cookie tiene
    que seguir siendo válida — si no, el admin queda afuera de su propio
    sistema justo después de una restauración."""
    copia = admin_client.get("/api/config/backup-ahora").content
    admin_client.post("/api/config/restore",
                      files={"backup_file": ("b.zip", copia, "application/zip")})

    assert admin_client.get("/auth/me").status_code == 200


def test_los_logs_siguen_funcionando_despues_de_un_restore(admin_client):
    """`app.state.auditoria` se construye UNA vez, al arrancar, con la conexión
    que el restore cierra. Sin reconstruirlo, la pantalla de logs consulta una
    conexión cerrada — y es la pantalla que uno abre justo después de un
    restore para ver qué pasó."""
    copia = admin_client.get("/api/config/backup-ahora").content
    admin_client.post("/api/config/restore",
                      files={"backup_file": ("b.zip", copia, "application/zip")})

    assert admin_client.get("/logs").status_code == 200


def test_se_puede_seguir_escribiendo_despues_de_un_restore(admin_client):
    """La conexión nueva tiene que quedar en `app.state.conn`: si quedara la
    cerrada, la primera venta después de restaurar falla."""
    copia = admin_client.get("/api/config/backup-ahora").content
    admin_client.post("/api/config/restore",
                      files={"backup_file": ("b.zip", copia, "application/zip")})

    creado = _producto(admin_client, "Producto de después del restore")
    assert creado["id"]


# ── Empresa y gates ───────────────────────────────────────────────────────

def test_guardar_y_leer_los_datos_de_empresa(admin_client):
    r = admin_client.put("/api/config/empresa", json={
        "empresa_nombre": "Despensa Suipacha", "empresa_cuit": "20-11111111-9",
    })
    assert r.status_code == 200, r.text
    assert admin_client.get("/api/config/empresa").json()["empresa_nombre"] == "Despensa Suipacha"


def test_el_cajero_no_ve_nada_de_configuracion(staff_client):
    """Acá la lectura de empresa **también** es admin, a diferencia de
    LibraDesk: este producto no genera comprobantes desde el frontend con esos
    datos, así que no hay motivo para abrirla."""
    assert staff_client.get("/api/config/empresa").status_code == 403
    assert staff_client.get("/api/config/backups").status_code == 403
    assert staff_client.get("/api/config/backup-ahora").status_code == 403


def test_el_cajero_no_restaura(staff_client):
    r = staff_client.post("/api/config/restore",
                          files={"backup_file": ("b.zip", b"x", "application/zip")})
    assert r.status_code == 403
