# Convenciones — VentaLibra

Reglas específicas del código y del repositorio. Las instrucciones generales
del ecosistema siguen en `AGENTS.md`/`CLAUDE.md` y la wiki
(`wiki/concepts/estandares-desarrollo.md`).

## Código

- Python 3.12, sin ORM para la persistencia propia (sqlite3 crudo, igual que
  LibraCommerce/LibraCore). No introducir SQLAlchemy solo para la tabla
  `users` — ver `DECISIONS.md` ADR-002.
- No duplicar dominio ya resuelto en LibraCommerce (catálogo, inventario,
  compras, ventas). El código propio de este repo es: HTTP, auth, y
  orquestación de casos de uso entre motores (ej. venta confirmada → stock).
- `Decimal` para cantidades/importes, nunca `float`.

## Tests

- Contra archivos SQLite temporales reales, nunca mocks ni bases en memoria
  compartidas entre tests (estándar de la familia para todo lo que toca
  LibraGenda/LibraCommerce).
- Cobertura mínima por feature: camino feliz + al menos un error de dominio
  traducido a HTTP (404/409/422 según corresponda).

## Git y ramas

- `develop`: desarrollo e integración.
- `main`: producción (se crea cuando haya un primer corte deployable).
- Remoto `origin` en HTTPS plana + `credential.helper '!gh auth
  git-credential'` — nunca un PAT embebido en la URL (ver incidente
  Restolibra 2026-07-25 en la wiki).

## Seguridad y configuración

- No hardcodear secretos. `VENTALIBRA_ADMIN_PASSWORD` obligatorio en
  producción (`ENV=production`), la app no arranca sin él.
- Contraseñas: PBKDF2-SHA256, 260k iteraciones, salt por password,
  comparación en tiempo constante, hash señuelo contra enumeración de
  usuarios — mismo algoritmo que el resto de la familia.

## Dónde se arregla (regla de la familia, 2026-10-03)

**El arreglo de fondo vive siempre en el motor** (`libracore`; `libracommerce` y `libra-ui` para
lo suyo), **nunca en este repo.** Lo que otro producto comparte o podría compartir —el protocolo
con ARCA, las reglas fiscales y sus validaciones, las guardas contra duplicados, la numeración, la
cuenta corriente, los componentes de pantalla compartidos— se escribe y se arregla en el motor.
Este repo sólo aporta **costuras** (los hooks que el motor ya expone) y lo suyo: pantallas,
textos y su modelo de datos propio. Si falta la costura, se agrega al motor; si el arreglo hace
falta antes, igual se hace en el motor (PR y tag) y acá se sube el pin: nada «provisorio» en este
repo. Un hueco que se encuentra acá se busca en los demás productos antes de darlo por acotado.
Detalle y motivo: `reglas/producto.md` del wiki.
