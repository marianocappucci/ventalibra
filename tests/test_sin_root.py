"""La imagen no corre como root, y el contenedor no puede ganar privilegios.

Relevamiento de seguridad de la VPS del 2026-10-10, punto 8: seis de los ocho productos
corrían como `uid 0` dentro del contenedor (medido el 2026-10-15 en la VPS). Con un RCE en la
app, el atacante era root sobre la imagen y sobre los datos del cliente. LibraCargo y LibraClub
ya corrían como `uid 10001`; este producto sigue el mismo modelo.

Hay que fijar tres cosas, y fallan por separado:

  1. el `USER` de la etapa final del Dockerfile (lo que hace que el proceso no sea root);
  2. que el uid sea **10001 fijo**: el deploy (`libracore.provisioning.sin_root`) le hace
     `chown` a la carpeta `data/` de cada instancia con ESE número, y un `useradd` sin `-u`
     elegiría otro y dejaría la app sin poder escribir sus PDF, `arca_ta`, `errores/` ni backups;
  3. `no-new-privileges` en el compose de dev (el de las instancias lo genera el motor).

Se leen los archivos y no se construye la imagen: es lo que se puede verificar sin las deploy
keys de los motores privados. Que el proceso arranque de verdad como 10001 se mide con la
imagen construida (`docker run --rm <imagen> id -u`).
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SERVICIO_DEV = "ventalibra-dev"
UID = "10001"
ROOT = {"root", "0", "0:0", "root:root", "root:0", "0:root"}


def _etapa_final() -> list[tuple[str, str]]:
    """`[(INSTRUCCION, resto)]` de la última etapa del Dockerfile, sin comentarios y con las
    continuaciones (`\\`) ya unidas."""
    crudo = (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines()
    logicas, acumulada = [], ""
    for linea in crudo:
        if not acumulada and (not linea.strip() or linea.lstrip().startswith("#")):
            continue
        if linea.lstrip().startswith("#"):  # comentario en medio de una continuación
            continue
        acumulada += linea.rstrip()
        if acumulada.endswith("\\"):
            acumulada = acumulada[:-1] + " "
            continue
        logicas.append(acumulada.strip())
        acumulada = ""
    instrucciones = []
    for logica in logicas:
        instr, _, resto = logica.partition(" ")
        instrucciones.append((instr.upper(), resto.strip()))
    ultima_from = max(i for i, (instr, _) in enumerate(instrucciones) if instr == "FROM")
    return instrucciones[ultima_from:]


def _indice_del_ultimo_user(etapa: list[tuple[str, str]]) -> int:
    indices = [i for i, (instr, _) in enumerate(etapa) if instr == "USER"]
    assert indices, "la etapa final del Dockerfile no declara USER: el proceso corre como root"
    return indices[-1]


def _run_del_useradd() -> str:
    runs = [resto for instr, resto in _etapa_final() if instr == "RUN" and "useradd" in resto]
    assert runs, "ningún RUN crea el usuario (useradd)"
    return runs[0]


def test_la_etapa_final_corre_con_un_usuario_que_no_es_root():
    usuarios = [resto.strip() for instr, resto in _etapa_final() if instr == "USER"]
    assert usuarios, "la etapa final del Dockerfile no declara USER: el proceso corre como root"
    assert usuarios[-1].lower() not in ROOT, f"el USER final es root ({usuarios[-1]!r})"


def test_el_user_va_antes_del_cmd():
    etapa = _etapa_final()
    instrucciones = [instr for instr, _ in etapa]
    assert "CMD" in instrucciones
    assert _indice_del_ultimo_user(etapa) < instrucciones.index("CMD")


def test_el_usuario_se_crea_con_el_uid_fijo_de_la_familia():
    assert re.search(rf"useradd\b[^&|;]*-u\s*{UID}\b", _run_del_useradd()), (
        f"el useradd no fija el uid {UID}: el deploy le hace chown a data/ con ese número"
    )


def test_data_nace_en_la_imagen_con_el_dueño_correcto():
    """Docker le copia el dueño de la carpeta de la imagen a un volumen NUEVO. Sin esto, un
    `data/` recién creado quedaría de root y el proceso, que ya no lo es, no podría escribirlo."""
    run = _run_del_useradd()
    assert "mkdir -p /app/data" in run
    assert re.search(rf"chown\s+(-R\s+)?{UID}:{UID}\s+[^&|;]*/app/data", run)


def test_no_hay_run_despues_del_user():
    """Un `RUN` después del `USER` corre sin privilegios: lo que necesite root falla recién en el
    build, o peor, instala en un lugar que la app no usa."""
    etapa = _etapa_final()
    posteriores = [resto[:60] for instr, resto in etapa[_indice_del_ultimo_user(etapa) + 1:] if instr == "RUN"]
    assert not posteriores, f"RUN después del USER: {posteriores}"


def _bloque_del_servicio(texto: str, servicio: str) -> str:
    """El texto del servicio `servicio` del compose, con los anchors `<<: *x` expandidos."""
    lineas = texto.splitlines()
    inicio = next(i for i, l in enumerate(lineas) if re.fullmatch(rf"  {re.escape(servicio)}:\s*", l))
    fin = inicio + 1
    while fin < len(lineas) and not re.match(r"^\S|^  \S", lineas[fin]):
        fin += 1
    bloque = "\n".join(lineas[inicio:fin])
    for ancla in re.findall(r"<<:\s*\*(\S+)", bloque):
        m = re.search(rf"^x-\S+:\s*&{re.escape(ancla)}\s*\n((?:[ \t].*\n|\n)*)", texto, re.MULTILINE)
        assert m, f"no encuentro el anchor &{ancla}"
        bloque += "\n" + m.group(1)
    return bloque


def test_el_compose_de_dev_no_deja_ganar_privilegios():
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    bloque = _bloque_del_servicio(texto, SERVICIO_DEV)
    assert re.search(r"^\s+security_opt:\s*\n\s+-\s*no-new-privileges:true\s*$", bloque, re.MULTILINE), (
        f"el servicio {SERVICIO_DEV} no declara security_opt: no-new-privileges:true"
    )
