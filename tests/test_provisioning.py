"""El provisioning de este producto, atado al código que corre.

Nace el 2026-08-24, de medir los ocho productos de la familia: **seis de ocho**
tenían los dos `configure()` diciendo cosas distintas, siempre en el mismo campo.
Los dos que no divergían eran justamente los dos que ya tenían este archivo.
"""

import importlib
import pathlib
import re

import pytest


def test_los_dos_scripts_configuran_LO_MISMO():
    """El desvío que el comentario de los dos archivos promete que no existe.

    `scripts/nuevo_cliente.py` y `scripts/panel_admin.py` llaman los dos a
    `configure()`, que pisa un `_cfg` **global**, y `libracore.admin.services`
    importa los dos módulos en el mismo proceso. Si dicen cosas distintas, cuál
    gana depende del orden de los imports — o sea que la misma operación sale
    distinta según qué se haya importado antes en ese proceso.

    **Este test nace en rojo.** Al escribirlo, `panel_admin.py` pasaba
    `backup_zip=True` y `nuevo_cliente.py` no.

    Se compara la configuración **entera** con `asdict`, no campo por campo: un
    test que mirara sólo `backup_zip` dejaría pasar el próximo desvío, que va a
    ser en otro campo.
    """
    from dataclasses import asdict

    from libracore.provisioning import get_config

    def config_de(script):
        importlib.reload(importlib.import_module(f"scripts.{script}"))
        return asdict(get_config())

    uno = config_de("nuevo_cliente")
    otro = config_de("panel_admin")

    distintos = {k: (uno[k], otro[k]) for k in uno if uno[k] != otro[k]}
    assert not distintos, f"los dos scripts configuran distinto: {distintos}"


def _bloque_del_servicio_de_dev() -> str:
    """El bloque del servicio `*-dev` del compose del repo, como texto.

    Sin `yaml`: el corte es por indentación —un servicio arranca con dos
    espacios y su cuerpo tiene más—, que es lo que el archivo garantiza.
    """
    raiz = pathlib.Path(__file__).parent.parent
    lineas = (raiz / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    servicios = [i for i, linea in enumerate(lineas)
                 if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", linea)]
    inicio = next((i for i in servicios
                   if lineas[i].strip().rstrip(":").endswith("-dev")), None)
    assert inicio is not None, (
        "el compose del repo no declara ningún servicio `*-dev`: este test "
        "está mirando un archivo que ya no tiene la forma que supone.")
    fin = next((i for i in servicios if i > inicio), len(lineas))
    return "\n".join(lineas[inicio:fin])


def _comando_de_arranque_de_dev() -> str:
    """El **valor** del `command:` del servicio de dev, y nada más.

    🔴 Buscar en el bloque entero no sirve: el 2026-08-25 se midió que un guard
    así **pasa en verde con el paso de migraciones sacado del `command:` y
    dejado en un comentario**. Un comentario que menciona el comando no lo
    corre. Un comentario tampoco matchea `^\s+command:`, porque el `#` va antes
    de la clave.

    Ojo: el sidecar de PostgreSQL de este compose declara **su propio**
    `command:` unas líneas antes, así que hace falta recortar el bloque del
    servicio de dev primero y no tomar el primero del archivo.
    """
    m = re.search(r"^\s+command:\s*(\S.*)$", _bloque_del_servicio_de_dev(), re.MULTILINE)
    assert m, (
        "el servicio de dev del compose no declara `command:`. Si el arranque "
        "pasó a otra forma, este test hay que reescribirlo — no borrarlo.")
    return m.group(1).strip()


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_la_instancia_de_dev_corre_las_mismas_migraciones_que_el_deploy(script):
    """El otro camino, el que `cmd_actualizar` no toca.

    🔴 **La declaración de `migraciones` no cubre `dev`.** El motor corre esos
    comandos al actualizar las instancias de cliente y la demo, que son las que
    el panel administra. La de `dev` la levanta el `docker-compose.yml` de este
    repo, y ahí el paso hay que ponerlo a mano. Se descubrió el 2026-08-25 en
    LibraCargo, cuya instancia de dev estaba una revisión atrás del código que
    servía, con el chequeo de salud en 200.

    Lo que se aserta es que las dos puntas digan **lo mismo y en el mismo
    orden**. Se lee el compose como texto y no se compara contra un literal
    escrito acá: un literal sería una tercera copia, con el mismo problema.
    """
    from libracore.provisioning import get_config

    importlib.reload(importlib.import_module(f"scripts.{script}"))
    declarados = get_config().migraciones
    if not declarados:
        return  # sin cadena declarada no hay nada que exigirle al compose

    arranque = _comando_de_arranque_de_dev()
    cursor = 0
    for comando in declarados:
        texto = " ".join(comando)
        pos = arranque.find(texto, cursor)
        assert pos != -1, (
            f"scripts/{script}.py declara `{texto}` y el servicio de dev del "
            "compose no lo corre" + (" en ese orden" if cursor else "") + ": "
            "la instancia de dev va a quedar con el código nuevo sobre el "
            "esquema viejo."
        )
        cursor = pos + len(texto)


def test_la_instancia_de_dev_declara_el_SMTP_que_el_motor_va_a_buscar():
    """El correo saliente de dev, que este producto tiene **por historia**.

    `resolver_smtp_config` cae al entorno cuando no hay nada guardado en la
    base. Si el compose de dev no declara las variables, esa caída devuelve una
    config vacía: la app levanta igual, `/auth/forgot-password` contesta 200, y
    el mail no sale. No hay error en ningún lado.

    🔴 **No es hipotético: le pasó a LibraClub y a LibraCargo**, que no las
    declaraban y estuvieron meses sin poder mandar un solo mail desde dev. Acá
    estaban desde siempre, y eso es exactamente el motivo de escribir el test —
    lo que nadie exige se puede perder en cualquier limpieza del compose, y el
    modo de fallar no da error.

    🔑 **Se aserta sobre los NOMBRES declarados, no sobre valores.** Los valores
    viven en el `.env` del VPS y no están en el repo; lo que este test puede
    sostener es que el compose los deje pasar. Contar los nombres adentro del
    contenedor **no** distingue configurado de vacío —el default es vacío—, así
    que ese chequeo va acá, sobre el compose, y la comprobación del valor se
    hace autenticando contra el servidor de correo.
    """
    bloque = _bloque_del_servicio_de_dev()
    faltan = [v for v in (
        "LIBRAAUTH_SMTP_HOST", "LIBRAAUTH_SMTP_PORT", "LIBRAAUTH_SMTP_USER",
        "LIBRAAUTH_SMTP_PASSWORD", "LIBRAAUTH_SMTP_FROM_EMAIL",
        "LIBRAAUTH_SMTP_FROM_NAME",
    ) if not re.search(rf"^\s+- {v}=", bloque, re.MULTILINE)]
    assert not faltan, (
        "el servicio de dev del compose no declara " + ", ".join(faltan) + ": "
        "la instancia de dev va a levantar sana y sin poder mandar un solo "
        "mail, sin dar error en ningún lado."
    )
    # El control: que el `- VAR=` de arriba sea capaz de NO matchear. Sin esto,
    # un patrón mal escrito daría la lista vacía y el test pasaría siempre.
    assert re.search(r"^\s+- LIBRAAUTH_SMTP_HOST=", bloque, re.MULTILINE)
    assert not re.search(r"^\s+- LIBRAAUTH_SMTP_INVENTADA=", bloque, re.MULTILINE)
