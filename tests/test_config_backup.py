"""Configuracion de empresa y quien puede tocarla.

🔴 **Este archivo tenia seis tests mas, y un `pytestmark` de modulo que
salteaba TODO cuando la suite corria contra PostgreSQL.** Esos seis respaldaban
y restauraban ARCHIVOS de base, algo que contra PostgreSQL no existe --- el
backup de una instancia PostgreSQL es otro mecanismo, con `pg_dump`.

Se sacaron el 2026-08-25, junto con el retiro de SQLite de la suite. **No se
pierde cobertura**: el respaldo por archivos vive en `libracore.respaldo` y esta
cubierto ahi --- `tests/test_respaldo.py` (17 casos), con
`test_respaldo_postgres.py` (9) para el camino de `pg_dump`. Los seis de aca
eran una copia que ademas ya no podia correr.

🔑 **Los tres que quedan nunca tuvieron nada que ver con SQLite**: prueban los
datos de empresa y que un cajero no pueda ver ni restaurar nada. Los barrio el
`pytestmark` de modulo, y por eso llevaban tiempo sin correr contra el motor
real sin que nada lo dijera.
"""


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
