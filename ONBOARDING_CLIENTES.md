# Guía de onboarding — Cliente nuevo en VentaLibra

Esta guía es para vos, Mariano. Describe el proceso completo para dar de alta a un cliente
nuevo de VentaLibra —despensas, autoservicios, comercios de ropa y retail en general— desde la
contratación hasta que está operando.

> **Qué es VentaLibra y qué no.** Es el vertical de **retail**: catálogo, inventario, compras a
> proveedores, ventas y POS, caja por turno, listas de precios, cuenta corriente y reportes. La
> facturación electrónica existe y se vende por plan, pero el centro del producto es el
> mostrador. Si el cliente lo que necesita es contabilidad, el producto es Contalibra; si es un
> restaurante, Restolibra.

---

## Resumen del proceso

1. Recopilar datos del cliente
2. Levantar la instancia
3. Primer acceso
4. Configurar el comercio y las sucursales
5. Cargar catálogo, precios y stock inicial
6. Aplicar el plan contratado
7. Configurar integraciones (ARCA, SMTP) según el plan
8. Crear los usuarios
9. Handoff: primer ingreso con el cliente

---

## 1. Datos a recopilar antes de empezar

| Dato | Para qué sirve |
|------|----------------|
| Razón social / nombre comercial | Aparece en la app y en los comprobantes |
| Slug | Nombre corto sin espacios: define `clientes/<slug>/` y el subdominio |
| CUIT y condición ante IVA | Determina el tipo de comprobante (A, B o C) |
| Domicilio fiscal | Aparece en los comprobantes |
| Plan contratado | Define si tiene facturación |
| Sucursales / depósitos | Dónde se vende y dónde está el stock |
| Catálogo | Listado de productos: si es grande, pedirlo en Excel |
| Precios y listas | Si maneja más de una lista (mayorista/minorista) |
| Stock inicial | Cantidades por depósito al momento de arrancar |
| Proveedores | Los habituales, para poder cargar compras desde el día uno |
| ¿Necesita facturación electrónica? | Si sí: certificado ARCA o guiarlo para generarlo |
| Usuario y contraseña del admin | Para el primer acceso — comunicar por WhatsApp, no por email |

---

## 2. Levantar la instancia

Cada cliente corre en su propio contenedor, aislado en `clientes/<slug>/`, todos compartiendo
la imagen `ventalibra:latest`. El puerto base de este producto es **8082** (los asigna el
provisioning mirando los puertos realmente ocupados del host).

### Setup único del servidor

`nuevo_cliente.py` y `panel_admin.py` son wrappers finos sobre `libracore.provisioning`, y el
Python del sistema del VPS no tiene `pip` por política de Debian (PEP 668). Por eso corren con
un venv dedicado en `/root/ventalibra/.venv-scripts`, **gitignored — no se versiona y no llega
por `git pull`**. Si hay que recrearlo:

```bash
apt-get install -y python3-venv
python3 -m venv /root/ventalibra/.venv-scripts
/root/ventalibra/.venv-scripts/bin/pip install \
  "libracore @ git+ssh://git@github-libracore/marianocappucci/libracore.git@<TAG>"
```

Dos cosas que no son obvias:

- **`<TAG>` es el pin que declara el `pyproject.toml` de *este* repo**, no un número común a
  la familia. Cada producto pinea su propia versión de LibraCore, y el venv del host tiene que
  espejar la suya: si queda atrás, el CLI opera con un motor distinto del que corre la
  instancia. Ya pasó acá: el `.venv-scripts` estaba una versión atrás del pin y frenó un
  deploy.
- **La URL va por SSH (`git+ssh://git@github-libracore/…`), no por HTTPS.** En este VPS el
  `https://` del `pyproject.toml` falla: la autenticación es por deploy key con alias en
  `~/.ssh/config`. `httpx` y el resto de las dependencias entran solas con LibraCore.

> ⚠️ **Si la imagen `ventalibra:latest` todavía no existe**, el build del alta falla al clonar
> las dependencias privadas: `build_image()` corre `docker build` sin `--ssh`. La primera vez
> hay que construirla a mano con el agente compartido del VPS
> (`docker build --ssh default=$SSH_AUTH_SOCK -t ventalibra:latest .`). Con la imagen ya
> construida, el alta funciona sola.

### Alta de un cliente nuevo

En el servidor, desde `/root/ventalibra`:

```bash
./.venv-scripts/bin/python3 scripts/nuevo_cliente.py
```

El wizard pide nombre, slug, puerto, dominio, plan y credenciales de admin; crea
`clientes/<slug>/` (compose + `data/` con base, config y adjuntos aislados), levanta el
contenedor y —si hay dominio— crea el proxy y el certificado en Nginx Proxy Manager.

### Gestión del día a día

```bash
./.venv-scripts/bin/python3 scripts/panel_admin.py            # menú interactivo
./.venv-scripts/bin/python3 scripts/panel_admin.py listar     # instancias, puerto y estado
./.venv-scripts/bin/python3 scripts/panel_admin.py info <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py backup <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py actualizar [slug...]   # sin args = todas
./.venv-scripts/bin/python3 scripts/panel_admin.py pausar <slug>          # banner, sin cortar acceso
./.venv-scripts/bin/python3 scripts/panel_admin.py suspender <slug>       # corta el acceso
```

Lo mismo por navegador desde el backoffice, en **https://admin.ventalibra.com.ar**.

### Migrar la base antes de desplegar una versión nueva

**Paso obligatorio de todo deploy que traiga una versión nueva de LibraCore**, y va
**antes** de `actualizar` — que levanta los contenedores con el código nuevo apenas
termina el build.

Las tablas del motor —`clients`, facturación, caja, recibos— las define LibraCore, no
este repo, y su schema evoluciona con una cadena de migraciones de Alembic. Cuando sube
el pin de `libracore` en `pyproject.toml`, el código nuevo puede esperar columnas que la
base todavía no tiene.

> 🔴 **Sin este paso, el código nuevo escribe contra un schema viejo.** Y no falla al
> arrancar, que es lo que lo hace peligroso: falla más tarde, cuando alguien toca la
> pantalla que usa la columna nueva — y para entonces la instancia ya está sirviendo.

**Setup único**: `migrar_instancias.sh` vive en el repo de LibraCore, en `scripts/` —
**fuera del paquete Python**, así que no lo trae `pip install libracore` (el mismo
motivo por el que hace falta el `.venv-scripts`) ni el `git pull` de este repo:

```bash
git clone git@github-libracore:marianocappucci/libracore.git /root/libracore
```

El alias `github-libracore` ya está en el `~/.ssh/config` del VPS, apuntando a la deploy
key de solo lectura de ese repo.

**En cada deploy**, desde `/root/ventalibra` y después del `git pull`:

```bash
git -C /root/libracore pull

# 1. DRY-RUN (es el default): dice qué instancias encontró y contra qué base iría
LIBRACORE_REF=v1.29.0 /root/libracore/scripts/migrar_instancias.sh \
  ventalibra-dev ventalibra-demo

# 2. Revisada la lista, aplicar:
LIBRACORE_REF=v1.29.0 /root/libracore/scripts/migrar_instancias.sh --si \
  ventalibra-dev ventalibra-demo
```

El dry-run imprime, sin tocar nada:

```
LibraCore ref: v1.29.0
MODO DRY-RUN — nada se va a modificar (pasá --si para aplicar)

→ ventalibra-dev
    base: postgresql://***:***@ventalibra-postgres:5432/ventalibra
    red:  ventalibra-dev-datos
→ ventalibra-demo
    base: postgresql://***:***@ventalibra-demo-postgres:5432/ventalibra
    red:  ventalibra-demo-datos
```

Dos cosas que no son obvias, las mismas dos del `.venv-scripts`:

- **`LIBRACORE_REF` es el tag que pinea el `pyproject.toml` de _este_ repo**
  (`grep libracore pyproject.toml`), no un número común a la familia. Cada producto
  pinea su propia versión del motor.
- **Los argumentos son nombres de contenedor, no slugs.** Hoy las instancias son
  `ventalibra-dev` y `ventalibra-demo`; **al dar de alta un cliente hay que sumarlo a
  la lista**, porque el script migra sólo lo que se le pasa.

> **El dry-run no es una formalidad.** La lista sale de inspeccionar contenedores, así
> que una instancia de cliente pasada por error se migra igual que una de dev. Mirar la
> lista antes de `--si`. Sobre una instancia de cliente, backup primero
> (`panel_admin.py backup <slug>`).

> 🔴 **Por qué un contenedor efímero y no `alembic` en el host.** El destino es
> `postgresql://…@ventalibra-postgres:5432/…`, y ese nombre es un **alias de la red de
> Docker** del sidecar de datos: desde afuera de esa red no existe. Correr las
> migraciones derecho en el host falla con *"could not translate host name"*. El script
> las corre adosado a la misma red que la instancia, y enmascara siempre las URLs — la
> de PostgreSQL lleva la contraseña del sidecar adentro.

### DNS y dominio

- El wildcard `*.ventalibra.com.ar` ya apunta al VPS: **no hay que tocar DNS** por cliente.
- El subdominio es `<slug>.ventalibra.com.ar`, y el proxy + SSL los crea el alta.
- Para gestionarlos a mano: `panel_admin.py npm-crear | npm-eliminar | npm-listar`.

> ⚠️ **Al dar de baja una instancia, el proxy no se va solo.** `eliminar` baja el contenedor y
> borra el directorio, nada más. Correr **`npm-eliminar <slug>` antes**, porque después no
> queda `cliente.json` de donde leer el dominio — y ese comando depende de que el campo
> `domain` esté cargado ahí.

---

## 3. Primer acceso

```
URL: https://<slug>.ventalibra.com.ar
Usuario: el que definiste en el alta
Contraseña: la que definiste — comunicarla por WhatsApp
```

---

## 4. Configurar el comercio

- [ ] **Datos del comercio**: razón social, CUIT, domicilio, condición ante IVA
- [ ] **Sucursales y depósitos**: al menos uno; el stock se lleva por depósito
- [ ] **Logo**, si va a emitir comprobantes con membrete

---

## 5. Catálogo, precios y stock

Este es el paso pesado del onboarding de retail, y conviene hacerlo **antes** de la
capacitación:

- [ ] Cargar el **catálogo** (si son muchos productos, pedir el listado en Excel)
- [ ] Definir **listas de precios** si maneja más de una
- [ ] Cargar el **stock inicial** por depósito
- [ ] Cargar los **proveedores** habituales
- [ ] Verificar que un producto se encuentre por código y por nombre en el POS

> **Cargar también algún caso de borde, no sólo el caso feliz**: un producto con stock en cero
> y otro bajo el mínimo. Son las pantallas que el cliente va a mirar todos los días, y vacías
> no se pueden revisar.

---

## 6. Plan y módulos

| Plan | Precio | Qué habilita |
|------|--------|--------------|
| Básico | $20.000 | Catálogo, inventario, compras, ventas/POS y caja |
| Estándar | $35.000 | Todo lo anterior + **facturación** |
| Premium | $55.000 | Igual que Estándar por ahora — queda con margen para dashboard y reportes |

> **El core no se gatea**: catálogo, inventario, ventas, compras y caja están en todos los
> planes (caja por decisión de negocio, `DECISIONS.md` ADR-007). Hoy el único módulo gateado es
> `facturacion`. La fuente de verdad es `plans.py` de este repo.
>
> ⚠️ **Premium y Estándar habilitan lo mismo hoy.** Es real, no un error de esta guía: el
> escalón Premium existe para cuando se construyan dashboard y reportes. Tenerlo en cuenta al
> vender.

---

## 7. Integraciones

### ARCA / facturación electrónica (plan Estándar en adelante)

La configuración vive en `/config/arca` de la instancia: certificado `.crt`, clave `.key`, CUIT
y punto de venta. El punto de venta tiene que estar habilitado en AFIP como "Facturación
electrónica — Web Services". Probar en **homologación** y recién después pasar a producción.

### Correo saliente (SMTP)

Se configura por instancia desde el backoffice (**Configuración → SMTP** en
`admin.ventalibra.com.ar`), no dentro de la app. Para Gmail hay que usar una contraseña de
aplicación.

> VentaLibra **no tiene integración con MercadoPago**. Si el cliente la pide, el producto que
> la tiene es Contalibra/Restolibra.

---

## 8. Usuarios

- [ ] Crear el usuario **admin** para el dueño o encargado
- [ ] Crear un usuario por cada persona que atienda el mostrador
- [ ] Comunicar las credenciales de forma segura

El admin inicial de la instancia sale de las variables `VENTALIBRA_ADMIN_*` que fija el alta;
los demás se crean desde la pantalla de usuarios.

---

## 9. Handoff con el cliente

1. **Ingresar** — URL, usuario, contraseña
2. **Abrir el turno de caja**
3. **Hacer una venta** en el POS, buscando el producto por código y por nombre
4. **Cobrar** y ver el movimiento en caja
5. **Cargar una compra** a un proveedor y ver cómo impacta el stock
6. **Emitir una factura** de prueba (en homologación, si tiene ARCA)
7. **Cerrar el turno** y ver el resumen
8. **Reportes** del día
9. Mostrar cómo dar de alta un producto y un cliente

Al terminar:

- [ ] Cambiar la contraseña del admin por una que defina el cliente
- [ ] Confirmar que puede vender y cerrar caja sin ayuda
- [ ] Pasar ARCA a producción si corresponde

---

## 10. Post-onboarding (primera semana)

- [ ] Contactarlo a los 2-3 días
- [ ] Verificar que el stock siga cuadrando después de la primera semana de ventas
- [ ] Verificar que la facturación esté saliendo, si tiene ARCA
- [ ] Recordarle descargar un backup manual

---

## Checklist resumen

```
DATOS
[ ] Razón social, CUIT, domicilio, IVA recopilados
[ ] Plan definido
[ ] Catálogo, listas de precios y stock inicial conseguidos

INSTANCIA
[ ] Levantada y accesible por HTTPS
[ ] Login funciona

CONFIGURACIÓN
[ ] Datos del comercio completos
[ ] Sucursales y depósitos cargados
[ ] Catálogo, precios y stock inicial cargados
[ ] Proveedores cargados
[ ] Plan aplicado y módulos correctos
[ ] ARCA en homologación probada (si aplica)
[ ] SMTP configurado y probado (si aplica)

USUARIOS
[ ] admin creado
[ ] Usuarios de mostrador creados

CAPACITACIÓN
[ ] Handoff hecho
[ ] El cliente vende y cierra caja solo
[ ] ARCA en producción (si aplica)

POST-ONBOARDING
[ ] Seguimiento a los 3 días
[ ] Stock verificado contra la realidad
```

---

## Contacto de soporte

- WhatsApp: +54 9 11 2775-2983
- Email: soporte@ventalibra.com.ar
