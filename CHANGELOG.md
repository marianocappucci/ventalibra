# Changelog — VentaLibra

Cambios funcionales y releases publicados. Para tareas internas usar
`TASKS.md` y para operaciones del wiki usar `log.md` (repo de wiki).

## [Unreleased]

- **`libra-ui` v0.116.6** (2026-10-05; antes v0.116.5). Las tablas ya no rearman sus celdas cada vez que la pantalla se actualiza: quien usa el teclado no pierde el foco al tildar una casilla, y un clic que coincide con una actualización llega igual. Sin migración.

- **`libra-ui` v0.116.5** (2026-10-05; antes v0.116.4). En el teléfono el botón del menú mide 44 px (medía 28); en la tabla de Ventas el número de venta ya no se corta con «…». Sin migración.

- **La X de cierre de los diálogos y los selectores de la devolución, cómodos para el dedo** (2026-10-05). En pantallas de menos de 1024 px la X de todos los diálogos tiene 44 px de área táctil (el icono no cambia de lugar ni de tamaño; medía 16×16) y los selectores «Depósito» y «Devolver por» del diálogo de devolución miden 44 px de alto (medían 36).

- **Ninguna pantalla scrollea de costado en el teléfono: `libra-ui` v0.116.4** (2026-10-05; antes v0.116.2). Libros IVA, Configuración, Transferencias, Reportes, Cajas, Tesorería, Logs, Promociones y Sucursales ensanchaban la página en un móvil (hasta 522 px de más, medido en Chromium contra dev); ahora entran en cualquier ancho. La vista previa del ticket (Configuración) conserva el ancho real del papel y scrollea dentro de su tarjeta.
- **Logs se puede recargar:** el endpoint pasa de `/logs` a `/api/logs`. En `/logs` tapaba la ruta de la pantalla: un F5 o un link pegado mostraba el JSON crudo en vez de la pantalla.

- **«Devolver productos» de 44 px en el teléfono** (2026-10-05). El botón del detalle de la venta y los dos de su diálogo miden 44 px de alto en pantallas de menos de 1024 px, como los demás botones del detalle; en escritorio, iguales.

- **libracore `v1.131.0`** (2026-10-05; antes `v1.130.0`). La nota de crédito **total** de una FCE se frena antes de pedirle el número a ARCA (`POST /api/facturas/{id}/nota-credito` sin `importe` → 422): ARCA sólo deja anular una FCE si el comprador la rechazó (`10154`) y una nota por el total supera su saldo (`10184`). La de una FCE va siempre por un importe menor que el saldo. Sin migración.

- **`libra-ui` v0.116.2** (2026-10-05; antes v0.116.1). En el detalle de la venta, en pantallas de menos de 1024 px, los botones (Ticket, Volver, Facturar, Emitir nota de crédito, Anular venta y los del diálogo de la nota) miden 44 px de alto, cómodos para el dedo; en escritorio, iguales. Sin migración.

- **`libra-ui` v0.116.1** (2026-10-05; antes v0.116.0). En las tarjetas de Stock y de Ventas (la vista de pantallas angostas) los botones de acción miden 44 px, cómodos para el dedo; en la tabla de Ventas el total de 7 dígitos se lee entero. Sin migración.

- **`libra-ui` v0.116.0** (2026-10-05; antes v0.115.1). **La lista de Ventas sin scroll horizontal:** la tabla de siempre cuando entra en el ancho que hay y una tarjeta por venta (número que lleva al detalle, fecha y cliente, estado, total, medios de pago, factura y los mismos botones) cuando no; las pestañas Todas / Sin facturar / Facturadas pasan a dos líneas en pantallas angostas. Sin migración.

- **Nota de crédito parcial en el motor: `libracore` v1.130.0 y `libracommerce` v0.44.0** (2026-10-05; antes v1.129.0 y v0.42.0). Una factura con CAE se puede acreditar en **varias notas** (`POST /api/facturas/{id}/nota-credito` con `{"importe": ...}`; sin él, la nota total de siempre) y la suma nunca supera su total. Anular una venta facturada exige que **las notas sumen** el total de la factura (no alcanza con una parcial), y el detalle de la venta trae `factura_total` y `factura_saldo_acreditable`. La pantalla con el importe llega con `libra-ui` v0.115.x (PR aparte). Sin migración.

- **`libra-ui` v0.115.1** (2026-10-05; antes v0.114.2). Los encabezados de columna largos (el nombre de un depósito) se cortan con «…» y llevan el nombre entero en el `title`; el diálogo de ajuste de stock muestra «11 kg» o «11,5 kg» y no «11.000 UN»; un solo `<main>` en la pantalla. Trae también la **nota de crédito parcial** en el detalle de la venta (0.115.0): **con este motor (libracommerce v0.42.0) no se activa**, necesita el saldo acreditable que manda libracommerce v0.44.0, y sin él todo sigue como antes (nota total). Sin migración.

- **`libra-ui` v0.114.2** (2026-10-04; antes v0.114.1). Stock sin scroll horizontal también con un depósito de nombre largo (el chip se trunca y la cantidad siempre se ve) y con una referencia larga en el historial; el total ámbar «Bajo mínimo» pasa el contraste (WCAG AA); la tabla del detalle de venta no desborda a 768 px con importes de 7 dígitos. Sin migración.

- **`libra-ui` v0.114.1 y `libracommerce` v0.42.0** (2026-10-04; antes v0.113.1 y v0.41.0). **Stock sin scroll horizontal:** la tabla de siempre cuando entra en el ancho que hay y tarjetas por producto (stock por depósito, total, estado, acciones, ordenar por) cuando no; el aviso de stock bajo y el historial de movimientos tampoco ensanchan la página. **Ventas:** la columna Estado muestra «Descartada», «Devuelta» y «Dev. parcial» en vez del nombre técnico. **Detalle de la venta:** reabrir una venta cuya factura ya tiene su nota de crédito ya no vuelve a ofrecer emitirla (el motor trae `nota_credito_display`, ADR-034), el error se anuncia con `role="alert"` y la tabla de artículos no scrollea de costado en un móvil. El motor suma además la v0.41.1 (la revisión 0005 no supone que el arranque ya creó `branches`, ADR-033). Sin migración nueva.

- **`libra-ui` v0.113.1** (2026-10-04; antes v0.113.0). Arregla una regresión de v0.112.3: en el móvil, elegir un nombre largo en los selects de sucursal, categoría o proveedor de Reposición ensanchaba la página (scroll horizontal). Sin migración.

- **`libra-ui` v0.113.0: el botón «Emitir nota de crédito» en el detalle de la venta** (2026-10-04; antes v0.112.3). Con la factura autorizada por ARCA (`factura_cae`), el detalle avisa que hace falta la nota antes de anular y, a quien tiene la capacidad `facturas.nota_credito` (admin), le ofrece el botón (confirmación; `POST /api/facturas/{id}/nota-credito`). El cajero, que puede anular, ve el aviso y no el botón: se la pide a un administrador. No anula sola. Cierra el hueco de la entrada de la nota de crédito, que hasta ahora sólo se emitía por la API. Sin factura, o con una factura sin CAE, la pantalla no cambia. **No verificado en navegador.** Sin migración.

- **`libra-ui` v0.112.3** (2026-10-04; antes v0.112.2). Los selects de sucursal, categoría y proveedor de Reposición llevan el nombre completo de la opción elegida en el `title` (el valor se cortaba) y son más anchos (todo el ancho en móvil, `w-64` desde `sm`). Sin migración.

- **Nota de crédito de una factura con CAE** (2026-10-04; `libracore` v1.129.0 y `libracommerce` v0.41.0, antes v1.127.0 y v0.40.2). Nueva ruta `POST /api/facturas/{id}/nota-credito`, **solo admin** (capacidad `facturas.nota_credito`): emite la nota de crédito total autorizada por ARCA, asociada a su factura. Es la ruta del motor y **solo esa**: no se montan los otros once endpoints del router de comprobantes. **Cambia el comportamiento de anular:** una venta cuya factura tiene CAE ya no se anula (`409`, el texto dice qué hacer) hasta que un admin emite la nota; con la nota emitida se anula como siempre y la cuenta corriente no se acredita dos veces. Una venta sin factura, o con una factura sin CAE, se anula igual que antes. Sin migración. **Todavía no hay botón**: la nota se emite por la API hasta que `libra-ui` lo sume en el detalle de la venta.

- **`libra-ui` v0.112.2 y `libracommerce` v0.40.2** (2026-10-04; antes v0.112.1 y v0.40.1). La fila de botones del encabezado de Reposición envuelve en el móvil: con «Generar órdenes en borrador» el «CSV» se salía de la tarjeta y la página ganaba scroll horizontal a 390, 360 y 320 px. En el motor, una categoría nueva de `update_producto` se crea dentro de su transacción. Sin migración.

- **`libracommerce` v0.40.1 y `libra-ui` v0.112.1** (2026-10-04; antes v0.40.0 y v0.112.0). `repo.transaction()` pasa a ser reentrante por conexión (un `update_producto` dentro de una transacción ya no confirma lo de la exterior; ADR-031 de libracommerce). El diálogo de códigos anuncia su error como alerta y el select «Tipo» no corta su texto. Sin migración.

- **libracore `v1.126.0`** (2026-10-04; antes `v1.125.0`). Suma el nucleo `libracore.notas_de_credito` (este producto todavia no lo usa); la guarda del CUIT del receptor deja de bloquear las notas (ARCA autoriza la nota de credito a un CUIT que no cierra, igual que la factura). Sin migración.

- **libracore `v1.124.0`** (2026-10-04; antes `v1.123.0`). La guarda del CUIT del receptor (`arca_wsfe.problema_del_receptor`, que `solicitar_cae` corre antes de llamar a ARCA): CUIT de 11 digitos en clase A y FCE, y verificador valido en toda clase. El endpoint de notas no lo monta este producto. Sin migración.

- **Vencimientos y lotes, etapa 2: la venta descuenta del lote que vence primero, la carga de vencimientos y los avisos en el POS** (2026-09-30, ADR-053).
  Con `libracommerce` v0.30.0 y `libra-ui` v0.92.0: en un producto marcado «vence», la **venta, la anulación, la devolución, la transferencia, el ajuste y las
  salidas manuales siguen el lote** (vence primero, sale primero; el stock «sin lote» sale último; un lote vencido se vende con aviso). La devolución de un
  perecedero va a merma (no vuelve al estante). **Cargar vencimientos:** el producto tiene un interruptor «Vence» (lo marca el encargado), al recibir una compra
  se carga lote y vencimiento por línea y la pantalla de Vencimientos tiene «Cargar stock con lote». **POS:** antes de cobrar avisa si el carrito lleva mercadería
  de un lote vencido o por vencer y pregunta «¿Vender igual?» (no bloquea: si la consulta falla o tarda más de 1,5 s se cobra igual), y la venta cobrada muestra esos avisos.
  **La baja de un lote (merma) vuelve a estar habilitada** (encargado y depósito). El ajuste de stock con lote por API (`lot_code` en `POST /api/stock/{id}/ajuste`) **no se habilita**: se ignora, y la carga con lote es sólo por Vencimientos (encargado y depósito; el staff heredado no). 🔴 Límite: lo vendido **antes** de esta versión sigue «sin lote»; un producto con saldo
  «sin lote» negativo heredado no deja dar de baja sus lotes (409) hasta conciliar con el conteo físico. La pantalla de Vencimientos todavía muestra el aviso fijo de que el saldo
  por lote puede ser mayor al real (ya no es cierto para lo nuevo; pedido al kit). Sin migración nueva. Requiere `libracommerce` v0.30.0 y `libra-ui` v0.92.0 (pines subidos).

- **Vencimientos y lotes: qué vence, qué lote sacar y qué stock no tiene fecha** (2026-09-30, ADR-052). Pantalla nueva `/vencimientos` (menú
  «Vencimientos y lotes»): los lotes que vencen en los próximos días (15 por defecto) o ya vencieron, con los días que faltan, y el stock
  «sin lote» de los productos marcados; filtra por sucursal y categoría y se exporta a CSV. Se puede **ponerle lote y vencimiento** al stock que
  no lo tiene y **marcar qué productos vencen** (los que no se marcan no cambian en nada). Las escrituras piden
  una clave por intento: un reintento no descuenta dos veces. El **encargado** hace todo; el **depósito** ve y asigna vencimiento pero
  no marca; el mostrador no lo ve (capacidades nuevas `vencimientos.ver`, `vencimientos.marcar` y `vencimientos.mover`). Libre en Básico y
  Premium; no muestra costos. 🔴 **Limitación hasta que las ventas descuenten por lote (A-4):** las ventas, devoluciones, ajustes y
  transferencias siguen restando del stock «sin lote», así que en un producto marcado el saldo por lote **puede ser mayor al real** (la
  pantalla lo avisa); la forma segura de usarlo es marcar el producto, asignar vencimiento a lo que hay y dar de baja lo que vence con el ajuste de stock.
  🔴 **La baja de un lote está deshabilitada hasta esa etapa:** la pantalla muestra el botón «Dar de baja (merma)» pero el servidor contesta 409 con
  el motivo (hoy el saldo de un lote puede incluir unidades ya vendidas y mermarlo las descontaría dos veces); se habilita cuando las ventas
  descuenten por lote. Los CSV neutralizan fórmulas.
  **Con migración:** una revisión nueva de `libracommerce` (`0002_vencimientos_lotes`: una columna en productos y un índice del ledger) que el
  deploy aplica con `libracommerce-migrar upgrade --prefijo ventalibra` (ya está declarado); sin ella la pantalla contesta 503. Requiere
  `libracommerce` v0.29.1 y `libra-ui` v0.91.0 (pines subidos).

- **Reposición sugerida: qué pedir y cuánto, por producto** (2026-09-30, ADR-051). Pantalla nueva `/reposicion` (menú «Reposición sugerida»,
  admin y encargado, capacidad nueva `reposicion.ver`): según lo que se vendió en los últimos días (30 por defecto), lo que hay y lo que
  ya se pidió en órdenes de compra abiertas, sugiere cuánto reponer de cada producto, cuidando el stock mínimo; filtra por sucursal y
  categoría, se puede ordenar por cualquier columna y exportar a CSV (`GET /api/reportes/reposicion` y `/export` del motor). Marca los
  productos con posible quiebre (rotación subestimada) y los que no tienen ventas. Sólo lectura: **sugiere, no genera la orden de compra**.
  El stock mínimo es uno por producto (no por sucursal). Libre en Básico y Premium; no muestra costos. Sin migración. Requiere
  `libracommerce` v0.28.0 y `libra-ui` v0.90.0 (pines subidos).

- **La venta guarda el costo de cada línea: el margen deja de ser estimado en las ventas nuevas** (2026-09-29, ADR-050). Cada venta
  registrada desde ahora guarda el costo vigente del producto (`sale_items.unit_cost_snapshot`), así que el margen y rotación usan el
  costo de aquella venta y un cambio posterior de costo ya no lo reescribe. Un producto sin costo cargado queda sin costo guardado (y el
  reporte lo sigue marcando «sin costo»). **Sin backfill:** las ventas anteriores siguen con el costo de hoy y marcadas como estimadas.
  Sin migración. Requiere `libracommerce` v0.27.0 (pin subido).

- **Roles de usuario: admin, encargado, vendedor, cajero y depósito** (2026-09-29, ADR-049). Además de `admin` y `staff`, la
  pantalla de Usuarios ofrece **encargado** (todo menos usuarios, configuración, logs, estructura del local y reabrir un día),
  **vendedor** (POS, ventas, clientes, cuenta corriente y recibos, consulta de stock y precios), **cajero** (POS, su turno y su caja,
  consulta de stock y precios, clientes en lectura y alta) y **depósito** (stock, ajustes y transferencias, y lectura de órdenes y recepciones
  de compra sin importes; **no recibe compras**, lo hace el encargado; sin POS y sin plata). Cada rol ve en el menú sólo lo suyo, y una ruta que no es suya lo lleva a su pantalla inicial (el POS, o el stock
  para el depósito). **`staff` no se migra ni se borra**: sigue siendo un rol válido con exactamente los permisos de siempre («heredado;
  migrar a un rol concreto»), y el visitante de la demo conserva la lectura de todo. La matriz vive en `app/permisos.py`;
  `/auth/login` y `/auth/me` traen `capacidades`. Un rol inválido es 422 al crear o editar un usuario; sigue sin poderse dejar la
  instancia sin admin ni sacarse el rol a uno mismo. Sin migración. **Cambios para quien ya usaba el mostrador**: el cajero nuevo
  sigue fiando desde el POS pero no ve saldos, recibos ni cobranzas (cobrar deudas es del vendedor y el encargado), y no tiene cierre
  diario (el `staff` de antes conserva todo).
  **Costos**: la capacidad nueva `costos.ver` (admin, encargado y el `staff` heredado) decide quién ve lo que cuesta la mercadería. Sin
  ella, la API no manda `precio_costo` (productos, stock, listas de precio) ni `unit_cost` y subtotal (órdenes y recepciones de compra):
  el vendedor y el cajero no ven costos y el depósito ve las cantidades de la recepción sin importes. **El ticket de un turno**
  (`/api/cierre-diario/turno/{id}/ticket`) es de quien lo abrió (o de quien ve los turnos de todos): un cajero o un vendedor ya no puede
  pedir el de otro. **Recibir compras** es del encargado (y del `staff` heredado): confirmar una recepción fija el costo del producto,
  y un depósito, que no ve plata, podía cambiarlo con una recepción arbitraria. **Pendiente conocido** (ADR-049): la columna «Precio
  costo» de Productos muestra `$ NaN` a los roles sin `costos.ver`.

- **El mapa `VENTALIBRA_DEPOSITOS_A_SUCURSAL` también se aplica al arrancar y al restaurar un respaldo anterior a la jerarquía** (2026-09-29, ADR-044).
  Antes sólo lo leía la revisión `0007`, y `db.connect()` mandaba los depósitos sin sucursal a la predeterminada aunque el mapa dijera otra.
  Con un mapa mal escrito o que apunta a una sucursal inexistente, `connect()` ahora falla igual que la `0007`, pero sólo si hay depósitos huérfanos que asignar.
- **Tests de las pantallas de Clientes y Proveedores del kit**: el formulario no está suelto antes de abrirlo y aparece y desaparece con el diálogo.
- **Dos planes: Básico (un solo local) y Premium (facturación ARCA + multisucursal)** (2026-09-29, ADR-048). Básico ($20.000) es un
  solo local —una sucursal con los depósitos que necesite— y tiene todo lo demás libre; Premium ($55.000) suma la facturación ARCA y la
  multisucursal. El Dashboard **deja de ser de un plan**: se abre en los dos, igual que Margen, Etiquetas, Tesorería, Egresos y Libros
  IVA. Sin el módulo `multisucursal`, dar de alta (o reactivar) una segunda sucursal y transferir mercadería entre sucursales dan 403 con
  un mensaje que lo explica; transferir entre depósitos de la misma sucursal sigue libre, y una instalación que ya tenga varias
  sucursales las sigue viendo, editando y vendiendo. El plan Estándar deja de existir: una instancia que lo tenga guardado se trata como
  Premium, avisando en el log. La pantalla avisa «disponible en Premium» en Sucursales, Transferencias, la configuración de ARCA y el
  casillero «Emitir factura» del POS. `/auth/login` y `/auth/me` traen `modulos`. Sin migración. Reemplaza al PR #344.

- **Margen y rotación por producto y por período** (2026-09-29, ADR-046). Pantalla nueva `/margen` (admin, menú «Margen y rotación»):
  ingreso, costo, margen ($ y %) y unidades por producto y por período (día, semana o mes), ordenable por cada columna y con export CSV,
  sobre `GET /api/reportes/margen` del motor. Una venta anulada o pendiente de cobro no cuenta y las devoluciones se restan. **El costo
  es el actual del producto, no el del momento de la venta** (la venta todavía no lo guardaba; desde ADR-050 lo guarda): la pantalla avisa qué productos usan un costo
  estimado y cuáles no tienen costo cargado. Sin migración. Sin gate de plan hasta que se decida en cuál va.
  Requiere `libracommerce` v0.26.0 y `libra-ui` v0.87.0 (pines subidos).
- **Etiquetas de góndola** (2026-09-29, ADR-047). Nueva pantalla `/etiquetas` (de admin): se eligen productos —todos,
  por categoría o buscando— y se arma una hoja A4 para imprimir, con nombre, precio y código de barras de cada uno
  (EAN-13/EAN-8 si el código lo es, Code 128 para el resto). El precio es el que cobra el POS: el de la lista
  predeterminada, con el del producto de respaldo; se puede elegir otra lista. De sólo lectura, sin endpoint ni migración.
  Requiere `libra-ui` v0.88.0.

- **Sucursal y depósito son entidades distintas** (2026-09-28, ADR-044). Hasta hoy una sucursal y un depósito eran la
  misma fila y cualquiera de las dos tenía stock; ahora una sucursal agrupa depósitos y **el stock vive sólo en el
  depósito**. Toda sucursal nace con su primer depósito (que es el de venta), puede tener varios, y no se da de baja
  con existencias. La venta descuenta del depósito de venta de la sucursal del turno. La migración conserva los ids de
  las sucursales, así que cajas, turnos, precios y stock no se reescriben; `scripts/preflight_jerarquia.py` audita antes de
  migrar. Pantallas nuevas del kit (`Sucursales`, `SucursalDetalle`) y `/depositos/:id` para el stock de un depósito.
  Requiere `libracommerce` v0.25.0 o posterior y `libra-ui` v0.85.0.

- **Cuentas corrientes con la pantalla del kit** (2026-09-24). Hasta hoy este
  producto era el único de la familia sin la normalización P9-M4: su pantalla
  propia (`/cuentas-corrientes`) era una copia vieja, sin el detalle por
  cliente, sin el pago desde la pantalla y sin la baja de pago. Ahora monta
  las mismas pantallas que Contalibra y Restolibra
  (`libra-ui/comercio/CuentaCorriente` + `CuentaCorrienteDetalle`), con el
  contrato que el kit llama a fuego:
  - `app/routers/cuenta_corriente_api.py` (nuevo) -- `GET/POST
    /api/cuenta-corriente…` + `POST /api/recibos/cobranza/{id}` y
    `GET /api/recibos/{id}/pdf` (estas delegan en los handlers de
    `/accounts/receipts/...`: misma operación idempotente, mismo PDF). El
    negocio no se copió: lo sirven `CuentaCorrienteService` y las reglas de
    siempre.
  - Reglas de VentaLibra conservadas, ahora también por el kit: el cobro
    **exige turno abierto** (409) y cae en la **caja del turno** de quien
    cobra -- `GET /api/cuenta-corriente/cajas` ofrece sólo esa caja, y si
    `caja_id` viene con otra es 422, porque el arqueo de otra caja no lo
    contaría. `cuenta_corriente` no es un medio de cobro (422), igual que en
    `CobranzaIn`.
  - `CuentaCorrienteService.registrar_cobranza` acepta `fecha` y `caja_id`
    (las trae el formulario del kit) y desde acá la referencia del movimiento
    de caja es **siempre** `cc-pago-<id>` -- la que escribió el usuario queda
    en `cc_pagos`, visible en la cuenta y en el recibo. Es lo que hace
    encontrable el ingreso a la hora de dar el pago de baja; los pagos viejos
    (con referencia escrita a mano) no se pueden identificar y la baja los
    rechaza con 409 en vez de dejar un ingreso huérfano en el arqueo.
  - `DELETE /api/cuenta-corriente/pagos/{pago_id}` (admin): anula los recibos
    del pago, **anula** -- no borra, pedido del humano 2026-08-28 -- el
    movimiento de caja y recién entonces borra el pago; el arqueo vuelve a
    dar lo que hay en el cajón y el saldo vuelve a la cuenta.
  - `frontend/src/pages/CuentasCorrientes.tsx` ahora es el montaje del kit;
    `CuentaCorrienteDetalle.tsx` (nueva) monta el detalle con `esAdmin` según
    el rol y `conRecibos`. Rutas: `/cuenta-corriente/:id` (detalle) y dos
    redirecciones -- `/cuenta-corriente` -> `/cuentas-corrientes` y
    `/clientes/:id` -> `/clientes` -- para los links fijos del kit ("Volver",
    "Ficha cliente"; la ficha es un pendiente de este producto). Los
    endpoints de `/accounts` quedan como estaban: lo que cambia es la
    pantalla, no la API vieja.
  - Tests: `tests/test_cuenta_corriente_kit.py` (contrato completo: listado
    con montos como números -- el kit suma saldos en el navegador--, detalle,
    pago con turno/caja, baja con anulacion y arqueo, recibos por la ruta del
    kit) y `frontend/src/test/cuenta-corriente-kit.test.tsx` (rutas y
    redirecciones).

- **libracore `v1.110.0` y libra-ui `v0.74.0`: el `mp_pos_id` de MercadoPago
  pasa a ser por caja** (2026-09-24, P9-M3). Antes el QR cobraba con el POS
  configurado a nivel instancia (un solo QR de mostrador para toda la
  sucursal, aunque hubiera dos cajeros); ahora cada caja tiene su
  `mp_pos_id` (`cajas.mp_pos_id`, migración `0012_mp_pos_id_por_caja` de la
  cadena del pin) y el cobro lo resuelve `libracore.db.caja.
  mp_pos_id_con_fallback()`: usuario -> turno -> caja, con fallback a la
  configuración de instancia sólo cuando hay exactamente una caja.
  - `app/services/mp_qr.py` -- `esta_configurado(usuario_id)` mira la caja
    activa del usuario; `credenciales()`/`MpNoConfigurado` se retiraron (la
    URL del QR la arma el router del motor). `GET /api/ventas/pos/mp-estado`
    pide ahora la sesión (`Depends(get_current_user)`) porque sin usuario no
    hay caja activa que mirar.
  - Pendiente conocido: la pantalla de cajas de ESTE producto sigue siendo la
    propia (`frontend/src/pages/Cajas.tsx`), que aún no tiene el campo
    `mp_pos_id` -- el editor por caja lo trae `libra-ui/comercio/Cajas`, que
    este producto todavía no monta. Mientras tanto el dato se carga por API
    (`PUT /api/cajas/{id}` con `mp_pos_id`; cuidado: omitir el campo en un
    PUT lo limpia, `CajaUpdatePayload.mp_pos_id` por defecto es `None`).

- **libracore `v1.109.0` y libra-ui `v0.73.2`** (2026-09-17). La copia externa
  del backup sale cifrada con `rclone crypt`, o no sale —eso corre en el host y
  ya está desplegado ahí—. Lo que llega con este pin: la pantalla *Datos /
  Backup* nombra la **clave privada de ARCA** y dice que la copia externa va
  cifrada; el estado deja de dar "al día" una copia que subió sin cifrar; y el
  botón de backup arma el mismo ZIP que el cron (todas las carpetas de `data/`,
  `arca_certs/` incluida).

- **POS: buscar por nombre en la caja no distinguía mayúsculas/acentos, y
  había que apretar Enter para ver algo.** Reportado por el humano: «Cono
  Simple» no aparecía escribiendo «CONO SIMPLE» ni «cono simple». El defecto
  era de PostgreSQL, no del código: `LIKE` es sensible a mayúsculas ahí (en
  SQLite no, por eso pasó desapercibido hasta correr contra el motor real).
  - `app/services/catalog.py::CatalogService.list_items` -- la comparación
    ahora es `LOWER(REPLACE(REPLACE(...(name)...))) LIKE ?`, con el mismo
    término normalizado del lado Python (`_sin_acentos`/`_columna_sin_acentos`,
    tabla `_QUITAR_ACENTOS`): sin distinguir mayúsculas NI acentos («cafe»
    encuentra «Café» y viceversa, decisión del humano), con **todos** los
    términos en cualquier orden («simple cono» encuentra «Cono Simple») y
    espacios de sobra que no cuentan. Se usa `REPLACE`+`LOWER` -- no
    `translate()` de PostgreSQL, que SQLite no trae de fábrica -- y **no** se
    instaló `unaccent` (nada de `CREATE EXTENSION`, es una dependencia nueva
    de despliegue que las instancias pueden no poder correr). Se revisaron
    las demás búsquedas de texto del backend (`grep -rn "LIKE" app/`):
    clientes y proveedores no filtran por texto en el backend, y el otro
    `LIKE` que hay (`app/normalizacion_medios.py`) es una migración de datos
    por columna, no una búsqueda escrita por una persona -- no se tocó.
  - `frontend/src/pages/Pos.tsx` -- al tipear en el campo de escaneo, un
    desplegable bajo el campo (no el modal `ElegirCandidato`, que sí se
    sigue usando cuando el Enter matchea por nombre y hay más de un
    resultado: un `Dialog` de Radix atrapa el foco, y el lector de código de
    barras necesita que el foco no se mueva) muestra coincidencias desde 2
    caracteres, con debounce de 250 ms y guarda por secuencia (no
    `AbortController`: `api.get` de `libra-ui` no lo acepta) para que una
    respuesta vieja no pise a una más nueva. El Enter sigue haciendo
    exactamente lo de siempre -- código exacto primero, después el nombre --
    y las sugerencias no se lo comen ni le roban el foco al campo. Elegir una
    agrega el producto por el mismo camino de siempre (`elegirItem`,
    variantes y multiplicador `3 * …` incluidos), limpia el campo y devuelve
    el foco.
- **Reabrir día: un admin puede anular un cierre diario, con motivo.**
  Pedido del humano: en dev, una sucursal con el día cerrado no podía abrir
  turno, y no había forma de destrabarla sin tocar la base a mano.
  - LibraCore `v1.106.1` → `v1.107.0` (`libracore.db.cierre_diario.
    reabrir_dia`, migración `0011_reabrir_cierre_diario`).
    `POST /api/cierre-diario/{cierre_id}/reabrir` (body `{motivo}`) sólo se
    monta porque `app/main.py` pasa `autorizar_reabrir=Depends(require_admin)`
    -- **sólo admin**, a diferencia de cerrar el día, que sigue siendo
    "admin o cajero" (`staff_or_admin`). 404 si el cierre no existe, 409 si ya
    estaba anulado o si hay un cierre posterior activo de la misma sucursal,
    422 con motivo vacío.
  - `listar_cierres`/`get_cierre` suman `anulado_en`, `anulado_por`,
    `motivo_anulacion`; `preview.ya_cerrado` ignora los cierres anulados, así
    que reabrir el día destraba la apertura de turnos de inmediato.
  - En Cierre diario, «Cierres anteriores» muestra un cierre anulado con
    badge «Anulado» y quién/cuándo/por qué lo reabrió; uno activo tiene un
    botón «Reabrir día» **visible sólo para admin**, con diálogo de motivo
    obligatorio.
- **Se puede editar una sucursal, y el POS deja claro cómo elegir en cuál
  trabajar.** Sucursales se podían crear pero no modificar, y no había forma
  visible de elegir sobre cuál operar -- eso último ya se resolvía al abrir
  turno en el POS (`AbrirTurno`); lo que faltaba era la edición y hacer visible
  cómo cambiar.
  - `PUT /locations/{id}` (`app/routers/locations.py`), gateado igual que el
    alta: ningún `Depends` propio, sólo el `staff_or_admin` que pone
    `app/main.py` al montar el router. Edita nombre, tipo, `is_default` y
    `active`.
  - 🔑 **No reimplementa las guardas de default.** Las sucursales de
    VentaLibra SON los `Location` de LibraCommerce, y el motor ya las tiene
    (`libracommerce.erp.catalogo.update_deposito`/`set_default_deposito`,
    v0.17.0): "a lo sumo una default" y "no desactivar la default" (409). Lo
    único propio de acá es el 409 por sucursal con un turno de caja abierto
    (`SucursalConTurnoAbierto`, `app/services/cajas.py::
    tiene_turno_abierto_en`) -- el motor no sabe qué es un turno. 422 si el
    nombre o el tipo quedan vacíos tras `strip()`; 404 si no existe.
  - `GET /locations` suma el parámetro opcional `incluir_inactivas` (default
    `false`, no cambia nada para el POS ni el alta de cajas): sin él, una
    sucursal recién desactivada desaparecía de la pantalla de edición y no
    había forma de reactivarla.
  - Botón «Editar» (ícono lápiz) por fila en Sucursales, con diálogo (nombre,
    tipo, predeterminada, activa) que muestra el `detail` del 409/422 tal
    cual.
  - En el POS, el encabezado con turno abierto (`Sucursal X · Caja Y`) suma un
    `title` -- "Para trabajar en otra sucursal, cerrá el turno." -- en vez de
    un botón «Cambiar» nuevo: el botón «Cerrar turno» ya hace exactamente eso,
    a un click de distancia: un segundo control repetiría la misma acción.
- **Categorías: pantalla propia en Configuración, y columna en Productos.**
  El catálogo tenía alta de categoría (`POST /catalog/categories`) desde
  antes, pero ningún lugar para editarla ni para verla en el listado de
  productos — el pedido original: *"el programa no tiene de dónde sacar las
  categorías"*. Ahora:
  - `PUT /catalog/categories/{category_id}` (`app/routers/catalog.py`),
    mismo gateo que el resto del router (`dependencies=staff_or_admin` en
    `app/main.py`). Edita nombre y activa/inactiva; `parent_id` queda
    afuera — ninguna pantalla del producto expone jerarquía todavía.
  - Nombre no vacío y no repetido entre categorías **activas** — mismo
    criterio en el alta y la edición (`CatalogService._validar_category_name`,
    nueva excepción `CategoryInvalido` → 422). 🔴 El `UNIQUE(parent_id, name)`
    de la tabla (`libracommerce/db/schema.py`) no alcanzaba solo: SQL no
    considera dos `NULL` iguales entre sí, y esta pantalla no expone
    jerarquía (`parent_id` siempre `None` en el flujo real), así que dos
    categorías con el mismo nombre pasaban ese `UNIQUE` sin chocar. El
    chequeo se hizo en el servicio, contra las activas — desactivar una
    categoría libera su nombre para reusarlo.
  - Desactivar una categoría con productos activos está permitido: el
    producto conserva su categoría (no se toca `catalog_items`), sólo deja
    de ofrecerse para altas/ediciones nuevas.
  - `CatalogService.list_categories` dejó de filtrar por `active = 1`:
    devuelve todas — la pantalla de administración necesita ver (y poder
    reactivar) las inactivas. Que el alta/edición de producto sólo ofrezca
    las activas pasó a ser un filtro del frontend, no del backend.
  - Frontend: `ConfigCategorias.tsx`, sección nueva en Configuración
    (`Configuracion.tsx`, junto a Unidades de medida), mismo patrón que
    `ConfigUnidades.tsx` con edición agregada (nombre + interruptor
    Activa/Inactiva, estilo `ItemEditDialog` de `Productos.tsx`).
  - `Productos.tsx`: columna **Categoría** (nombre, o «—» sin categoría),
    ordenable. El select de categoría del alta/edición de producto ahora
    sólo ofrece las **activas** — salvo que se esté editando un producto
    cuya categoría quedó inactiva, que se sigue mostrando (si no, el select
    la pierde y la edición rompe lo que ya tenía cargado). Si todavía no hay
    ninguna categoría cargada, el select muestra un enlace a
    Configuración › Categorías.
- **Fix: el alta de un producto valida lo mismo que la edición.** Cierra el
  hueco que había quedado documentado como pendiente en la entrada de abajo
  («editar producto»): `POST /catalog/items` no validaba nada — con una
  categoría inexistente reventaba la FK de Postgres y salía un 500 sin
  traducir, y aceptaba nombre vacío y precio/costo negativos. Ahora:
  - `CatalogService._validar_item` (`app/services/catalog.py`) es el único
    lugar donde viven las tres reglas (nombre no vacío tras `strip()`,
    categoría existente, precio/costo ≥ 0); `create_item` y `update_item`
    lo llaman los dos. Antes la edición las tenía repartidas entre un
    `KeyError` propio (categoría) y `Field` de Pydantic en `ItemUpdate`
    (nombre/precio/costo) — dos formatos de error para el mismo 422. La
    excepción nueva es `ItemInvalido`, que los dos endpoints de
    `app/routers/catalog.py` traducen a 422 con el mismo `detail`. La
    unidad sigue igual que antes (`KeyError` en `_get_unit`, ya compartida).
  - Por eso se sacó el `Field(min_length=1, ge=0)` de `ItemUpdate`: con él
    ahí, mutar `_validar_item` para no chequear el precio no alcanzaba para
    poner en rojo la edición (Pydantic lo seguía frenando antes de llegar
    al servicio) — la regla no estaba realmente compartida, sólo duplicada.
  - Frontend: no hizo falta tocar nada — `ItemCreateDialog` ya mostraba el
    `detail` del 422 con el mismo `describeError` que `ItemEditDialog`.
- **Se puede editar un producto ya cargado.** La pantalla Productos tenía
  alta y un detalle de códigos/variantes, pero ningún camino para corregir
  el nombre, el precio o la categoría de un producto existente. Ahora:
  - `PUT /catalog/items/{item_id}` (`app/routers/catalog.py`), gateado igual
    que el alta (`dependencies=staff_or_admin` en `app/main.py`). Reemplaza
    el item entero (mismo criterio que el alta): nombre, unidad, categoría,
    descripción, activo/vendible/comprable y precio/costo.
  - 🔴 **Cambiarle la unidad a un producto que ya tiene movimientos
    (stock, venta o compra) da 409** — cambiarla ahí le cambiaría el
    significado a todo lo que esos movimientos ya registraron con la unidad
    vieja. El resto de los campos se edita siempre; sólo la unidad queda
    bloqueada. `CatalogService.update_item`/`has_movements` en
    `app/services/catalog.py`.
  - De paso, la edición valida lo que el alta no valida y comparte servicio
    con ella: categoría inexistente (422, la FK de Postgres la revienta con
    un 500 sin esto) y nombre vacío/precio-costo negativos (422, vía
    `Field` en el modelo del router). **El alta tiene el mismo hueco** en
    los tres casos — queda pendiente, no se tocó para no ampliar esta
    entrega.
  - Botón «Editar» (ícono lápiz) por fila en Productos, junto al de
    códigos/variantes. Abre `ItemEditDialog`, que precarga los mismos
    campos que el alta más un switch «Activo» — comparten el formulario
    (`ItemFormFields`) para no duplicar el JSX. Los precios se validan como
    número no negativo con coma o punto decimal (mismo criterio que
    `parseMonto` de `Pos.tsx`); el alta no valida esto hoy, y no se lo tocó.
- **Chore: el pin de libracore pasa a v1.106.1.** Trae el motor de restore único
  (bases temporales, migraciones contra ellas e intercambio por nombre) y el
  backup que ya no sale vacío en silencio (v1.106.0), con sus correcciones: los
  pools descartan las conexiones viejas después del intercambio, una base sin
  variable de entorno frena el restore antes de tocar nada, y los errores de
  migración traen la excepción (v1.106.1). Sin migraciones.
- **Fix: los montos del cobro se leen como los escribe un cajero.** «Monto» y
  «Recibe» usaban `Number(x) || 0`: «3.000» valía 3 pesos y «3000,00» valía 0,
  y el cobro quedaba en «Falta cubrir» sin explicación. Ahora siguen la misma
  regla que el efectivo del turno («1.500» es mil quinientos, con coma
  decimal). Un valor ilegible se marca en el campo y no deja cobrar.
- **Fix: la cantidad de una línea del carrito ya no queda en 0 en silencio.**
  En «Cantidad» (F6) se aceptaba cualquier texto, y con «a3» la línea viajaba
  al registrar la venta con `qty: 0`. Ahora la cantidad se valida (coma o
  punto decimal, mayor a 0): con un valor inválido se ve el error y «Aceptar»
  queda deshabilitado. `0 * código` en el campo de escaneo también se rechaza.
- **Fix: tres defectos del POS encontrados en una prueba en pantalla
  (2026-09-17).**
  - El cierre de turno guardaba **$0 declarado en silencio** con un texto
    inválido en «Efectivo contado» (p. ej. «a500»): `Number(x) || 0` tapaba
    el `NaN`. Ahora se valida con `parseMonto` (acepta coma o punto decimal,
    `500`/`500.5`/`500,50`/`1.500,50`; nunca negativo) — con un monto
    inválido el campo muestra el error y el botón queda deshabilitado, sin
    mandar el POST. Mismo fix en «Efectivo inicial en caja» al abrir el
    turno, que es dinero declarado por el mismo motivo.
  - El encabezado del POS mostraba el prefijo duplicado («Sucursal Sucursal
    Centro · Caja Caja 1») cuando el nombre de la sucursal/caja ya lo traía;
    ahora sólo se antepone si hace falta. La pantalla se identifica además
    como «POS (Caja)» en ese mismo renglón, sin agregar un bloque nuevo.
  - `CierreDiario.tsx` mostraba una diferencia negativa como «$-500,00» en
    vez de «-$500,00» (el `$` antepuesto a mano en el JSX queda pegado al
    número, no al signo). Nuevo helper único `pesos()` en `src/lib/dinero.ts`
    para todo monto que pueda ser negativo — también usado en
    `CuentasCorrientes.tsx` (reemplaza su `conSigno` local, duplicado) y en
    `Reportes.tsx` (saldo del período / saldo total de caja).
- **Las fechas de los listados de Ventas se ven dd-mm-aaaa** y no en el ISO
  crudo de la API (`2026-09-17`). Hallazgo de la prueba en pantalla de cajas
  en dev. El arreglo es del kit (libra-ui v0.73.1) y alcanza a las columnas
  Fecha de sus pantallas.
- **«Catálogo» pasa a llamarse «Productos», y «Unidades» se muda a
  Configuración.** La pestaña «Unidades» que tenía esa pantalla ahora es una
  sección propia de Configuración («Unidades de medida») — el alta de un
  producto las sigue necesitando, así que Productos las sigue cargando, sólo
  que ya no las muestra. `/catalogo` redirige a `/productos` (mismo patrón que
  las redirecciones de Configuración). Los endpoints `/catalog/*` no cambian.
  Como Configuración es sólo de admin, la pantalla de unidades deja de verse
  para el cajero (staff).
- **La pantalla de venta del mostrador pasa a llamarse «POS (Caja)»** en el
  menú lateral. La ruta (`/pos`) y la pantalla en sí no cambian.
- **Compras al 100% del ancho, con la recepción de mercadería DENTRO de la
  orden.** El listado de órdenes de compra dejó la grilla al 50% con el
  detalle desplegado al costado: ahora es una tabla completa, igual que el
  resto de las pantallas, con «Nueva compra» arriba a la derecha y el detalle
  en su propia ruta (`/compras/:id`). El panel suelto de recepciones se retira
  — «Recibir mercadería» pasa a ser una acción de la orden, con el depósito de
  destino, un remito opcional y la cantidad/costo de cada línea precargados y
  editables (topeados contra lo pendiente). Una recepción que quedó en
  borrador por cualquier motivo sigue viéndose y confirmable desde
  «Recepciones de esta orden», dentro del mismo detalle. Las recepciones
  viejas que no estaban atadas a una orden ya no tienen pantalla; el stock que
  movieron no cambia.
- **El ticket de una venta que no está confirmada avisa en un modal.** En
  Ventas, la impresora de un borrador descartado abría una pestaña con el JSON
  del 409. Ahora aparece «Solo se imprime el ticket de una venta confirmada.»
  (libra-ui v0.73.0). La regla sigue siendo la del backend y no cambia.
- **La venta y la devolución salen del depósito de la sucursal de la caja del turno**,
  validado en el backend (422) con el gancho `validar_deposito` de libracommerce
  v0.17.0. Hasta ahora lo garantizaba sólo el POS. Pin de libracommerce a v0.17.0.
- **Fix: el backup salía sin ninguna base contra PostgreSQL.** La `Instancia`
  del backup pasaba `db_path`/`libracore_db_path` (URLs) por `bases=`, que es
  para rutas de archivo — `_copiar_base` las salteaba en silencio y el ZIP
  descargable traía los logos y ninguna base. Ahora usa `postgres_url`/
  `postgres_extra` de `libracore.respaldo`, con la base de LibraCore sumada
  aparte sólo cuando es distinta de la del dominio.
- **Varias cajas por sucursal, turno por cajero y por caja, y cierre diario**
  (ver DECISIONS.md ADR-026). Hasta ahora había una sola caja para toda la
  instancia y el turno era compartido (`get_turno_activo_any`): con dos
  locales vendiendo a la vez eso mezclaba la plata de los dos cajeros en el
  mismo arqueo. Ahora cada sucursal tiene sus propias cajas (con su propio
  punto de venta de ARCA), el turno es del usuario y de la caja donde abrió,
  y una caja no admite dos turnos abiertos a la vez. Pantallas nuevas «Cajas»
  (admin) y «Cierre diario» (admin y cajero, con ticket de 80 mm); el POS fija
  la sucursal a la de la caja del turno mientras hay uno abierto. El arranque
  reasigna las cajas huérfanas y le crea su primera caja a toda sucursal que
  no tenga (incluida una nueva, al darla de alta) — idempotente, no rompe
  instancias existentes con turnos abiertos sin caja. Pin de `libracore`
  actualizado a v1.104.0.
- **La pantalla dice de qué ambiente es el token de MercadoPago**: `Ambiente de
  prueba`, `Ambiente de producción` o `Ambiente sin verificar`, con la fecha en
  que se determinó. 🔴 MercadoPago **no tiene homologación como ARCA** — no hay
  host de sandbox, es el mismo `api.mercadopago.com` y lo que define el ambiente
  es el token. Sin el cartel las dos fallas son mudas: un token de producción en
  una instancia `dev` **cobra plata de verdad** y uno de prueba en la instancia
  de un comercio **no cobra nada**, y las dos se ven igual — el QR de caja se
  genera y la orden se crea. Mirar el prefijo no alcanza, porque un *usuario de
  prueba* de MercadoPago entrega credenciales `APP_USR-` igual que las reales:
  lo único que lo delata es el `nickname` de `/users/me`, así que quien clasifica
  es **Probar conexión**, que ahora recarga la sección. La clasificación lleva la
  huella del token, así que si la credencial cambia por cualquier vía se descarta
  sola. Pines: `libracore` v1.65.0 y `libra-ui` v0.54.0.
- **La grafía de MercadoPago, normalizada** (ver ADR-024): este POS escribía
  el medio como `mercado_pago` y el resto de la familia usa `mercadopago`. Era
  la última divergencia del vocabulario, y no se podía cambiar el selector sin
  migrar antes las filas ya escritas: cada reporte habría partido ese medio en
  dos líneas para la misma cosa. Las tres listas del frontend pasan a la grafía
  canónica y la base se normaliza sola en cada arranque, incluida una restaurada
  desde un backup viejo. **El recibo ya emitido de una cobranza por MercadoPago
  deja de imprimir el slug crudo** —`mercado_pago`, con guion bajo, en la
  columna «Medio»— y pasa a imprimir la etiqueta. 5 tests nuevos de backend y 5
  de guarda en el frontend.

- **Cobro con QR de MercadoPago y factura automática** (ver ADR-023): en el
  diálogo de cobro, con Mercado Pago cubriendo el total, aparece «Cobrar con
  QR»: pone el monto en el QR impreso del mostrador, espera a que
  MercadoPago avise que se acreditó y cierra la venta sola — con la factura
  emitida, si la instancia tiene la automática prendida. El QR es el cartel
  fijo de la caja y no cambia nunca; lo que cambia es cuánto cobra.

  **A diferencia de Contalibra, primero se cobra y después se confirma la
  venta**, así que no queda ninguna venta registrada como cobrada que nadie
  pagó. Cancelar el cobro baja el monto del cartel, para que el próximo que
  escanee no pague la venta anterior. Sección nueva **Mercado Pago** en
  Configuración (Access Token, User ID, POS ID y el toggle de la
  automática). Pide `libracore` **v1.40.0 o más**, que es donde se arregló la
  URL del QR: con la anterior el cobro daba 404 contra una cuenta real. 21
  tests nuevos de backend y 6 de frontend.

- **Anulación y devolución** (ver ADR-022): anular una venta repone el
  stock y saca de la caja lo cobrado (y si estaba fiada, le baja la deuda al
  cliente); devolver reintegra sólo algunos productos, por el medio que se
  elija — no tiene por qué ser el mismo por el que entró. Pantalla nueva de
  **Ventas** con el historial: antes no había forma de ver una venta ya
  cobrada, así que deshacer la de ayer era imposible. 15 tests nuevos, más
  14 en `libracommerce` v0.4.0 y 12 en `libracore` v0.30.1.

- **Ticket impreso** (ver ADR-021): después de cobrar, F8 (o el botón)
  abre el PDF del ticket térmico y dispara la impresión. El generador es de
  `libracore` v0.29.0 — extraído de Contalibra, donde ya existía y estaba
  duplicado en Restolibra. Pantalla nueva de configuración del ticket
  (ancho de rollo 58/80 mm, cuerpo de letra, logo, pie, línea de corte) con
  vista previa, para no gastar rollo probando. 15 tests nuevos.

- **Cuenta corriente / fiado** (ver ADR-020): se puede vender a cuenta
  corriente desde el POS eligiendo el cliente (F7). Lo fiado **no entra al
  arqueo del turno** — no es plata que entró; el movimiento de caja aparece
  recién cuando el cliente viene a pagar. Pantalla nueva de Cuentas
  corrientes con quién debe, el detalle de cada cuenta y el registro de
  cobranzas. Endpoint nuevo `PATCH /sales/{id}` para asignar el cliente a
  una venta ya empezada, porque en el mostrador eso se sabe al cobrar. 17
  tests nuevos; el cálculo del saldo es de `libracore` v0.28.0, ahora
  compartido con Contalibra y Restolibra.

- **Balanza de mostrador** (ver ADR-019): el POS lee las etiquetas que
  imprime la balanza y toma de ahí el peso, en vez de agregar una unidad.
  Soporta los dos modos de configuración del equipo (peso embebido o
  importe ya calculado), con el formato declarado por el comercio en
  Configuración → Balanza, que incluye un probador para escanear una
  etiqueta real y ver qué entendió el sistema antes de vender con eso.
  Tipo de código nuevo `scale` en el catálogo. 16 tests nuevos, más los
  del parser en `libracommerce` v0.3.0.

- **`DOCS_AUTH_SECRET` expuesto en `docker-compose.yml`**: conecta el
  endpoint `POST /auth/verify` (ver abajo) con el valor real cargado en
  `.env`, necesario para que `/docs/` de `ventalibra_web` autentique
  contra esta instancia. Sin cambios de código.

- **Endpoint `POST /auth/verify`** (ver ADR-018): chequeo de credenciales
  sin sesión, protegido por `X-Internal-Auth`/`DOCS_AUTH_SECRET`, para que
  el login de `/docs/` de `ventalibra_web` valide contra la instancia real
  del cliente. 5 tests nuevos.
- Scaffold inicial (Fase 1): auth por sesión, catálogo (categorías,
  unidades, items), ubicaciones, movimientos de stock manuales y flujo de
  venta POS (crear → agregar líneas → confirmar → descuenta stock real),
  compuesto sobre `libracommerce` v0.1.1 y `libracore` v0.17.1.
- CI en verde: secret `LIBRA_PAT` propio (fine-grained, alcance
  `libracommerce`+`libracore`, solo lectura).
- Fase 2 (compras): proveedores (`Party`), órdenes de compra y recepciones
  (`PurchaseOrder`/`PurchaseReceipt`), confirmar recepción genera stock +
  actualiza costo + sincroniza la orden vinculada, delegando en
  `libracommerce.usecases.purchasing.confirm_purchase_receipt`. `SaleService.confirm`
  (Fase 1) refactorizado para delegar igual en `confirm_sale`, cerrando la
  duplicación con LibraCommerce. Pin de `libracommerce` a v0.1.2.
- Investigado un `401 not authenticated` intermitente en la suite (~15-30%
  de las corridas): **no es un bug de código**, es el reloj de este WSL2
  saltando ~15s de forma recurrente (confirmado con un script de
  diagnóstico), rompiendo la verificación de expiración de `itsdangerous`.
  Sin cambios de código — ver DECISIONS.md ADR-006 para el diagnóstico
  completo y los intentos descartados (locks, thread-limiter, `async def`).
- Fase 3 (caja y facturación ARCA): segunda base SQLite dedicada a
  `libracore.db` (`app/services/billing.py`, mismo patrón que
  medlibra/gestiolibra). Clientes (`app/services/customers.py`) con
  extensión opcional `party_billing` (cuit/condición de IVA). Facturación
  **opcional por venta** (`invoice: bool` en `POST /sales/{id}/confirm`,
  tipo A/B según condición de IVA, "Consumidor Final" sin cliente). Caja
  **siempre** al confirmar una venta cobrada (`medio_pago` ahora
  requerido), factures o no — a diferencia de MedLibra/Gestiolibra, que
  solo tocan caja si hay factura. Config ARCA vía `GET`/`PUT /config/arca`.
  8 tests nuevos (39 en total) + smoke end-to-end real. Ver DECISIONS.md
  ADR-007.
- **Renombrado TiendaLibra → VentaLibra** (2026-07-25): `tiendalibra.com.ar`
  no estaba disponible para registrar; se registró `ventalibra.com.ar` en
  su lugar. Repo de GitHub, directorio local, paquete Python, título de la
  app, cookie de sesión (`tl_session` → `vl_session`), env vars
  (`TIENDALIBRA_*` → `VENTALIBRA_*`), nombres de archivo de base SQLite y
  toda la documentación del producto actualizados para mantener la
  convención de la familia (nombre de producto = dominio). Ver
  DECISIONS.md ADR-008.
- Fase 5 — planes y gating por módulo: tres planes (Básico $20k/Estándar
  $35k/Premium $55k), módulo `facturacion` gateado desde Estándar,
  catálogo/stock/venta sin gating. `confirm_sale` corta con 403 antes de
  tocar nada si se pide factura sin el módulo habilitado. 6 tests nuevos
  (45 en total). Ver DECISIONS.md ADR-009.
- Fase 5 — infraestructura de deploy: `Dockerfile`/`docker-compose.yml`/
  scripts de onboarding (`nuevo_cliente.py`/`panel_admin.py`/`npm_api.py`/
  `npm_setup.py`), deploy keys SSH nuevas (`libracommerce` solo lectura,
  `ventalibra` propia). Primer contenedor real (`ventalibra-dev`, puerto
  `8081`) construido y verificado en el VPS. Ver DECISIONS.md ADR-010.
- Fase 5 — dominio y SSL: corregida la delegación DNS de
  `ventalibra.com.ar` (estaba mal configurada del lado del proveedor).
  `dev.ventalibra.com.ar` provisionado en NPM con SSL, apuntando al
  contenedor `ventalibra-dev` — verificado real por HTTPS. Ver
  DECISIONS.md ADR-010.
- Fase 5 — primer cliente real: `prueba` onboardeado vía
  `scripts/nuevo_cliente.py` (plan Premium, puerto 8082,
  `prueba.ventalibra.com.ar` con SSL, login real verificado). Bug real
  encontrado y corregido en el camino, no específico de este repo:
  `build_image()` de `libracore.provisioning` no pasa `--ssh`, así que
  hacía falta construir `ventalibra:latest` aparte del `-dev` (que
  `docker compose` nombra distinto) — mismo patrón ya presente sin
  documentar en Gestiolibra/MedLibra. Ver DECISIONS.md ADR-011.
- Fase 4 — extensiones de catálogo completa: códigos de barra, listas de
  precio y variantes de talle/color construidas en LibraCommerce (pin
  actualizado a `v0.1.3`) y conectadas a VentaLibra. `GET /catalog/items/
  scan` resuelve un item por código (POS), nuevo router `/pricing`
  (listas de precio, precios por item, resolución efectiva), `variant_id`
  opcional en ventas y stock (`SaleService.add_item` valida que la
  variante pertenezca al item y resuelve precio antes de caer al
  `default_sale_price`; stock trackeado independiente por variante). 17
  tests nuevos (62 en total) + smoke end-to-end real contra `uvicorn`.
  Ver DECISIONS.md ADR-012.
- Corrección de documentación: "captura de plan en el onboarding" no era
  un pendiente real — `scripts/nuevo_cliente.py` siempre lo preguntó y
  aplicó (default `basico`). Sin cambios de código. Ver DECISIONS.md
  ADR-013.
- Frontend (MVP): SPA React 19+TypeScript+Vite+Tailwind v4+shadcn/ui
  (mismo stack final que Gestiolibra). Login, POS de venta (buscar por
  nombre o escanear código de barras, elegir variante, agregar/confirmar
  con sucursal/medio de pago/factura opcional), catálogo (alta de
  unidades/items/códigos de barra/variantes). `app/asgi.py` sirve el
  build de producción (mismo patrón que Gestiolibra). Verificado real de
  punta a punta contra un build de producción servido por `uvicorn`
  (login → catálogo → escaneo → venta con variante → confirmación →
  stock de esa variante actualizado). Ver DECISIONS.md ADR-014.
- Frontend — resto del back office: sucursales, proveedores, clientes
  (alta+listado), compras (órdenes de compra y recepciones con
  confirmación), usuarios (CRUD, admin-only), config ARCA (admin-only).
  Pin de `libracommerce` actualizado a `v0.1.4` (`list_purchase_orders`/
  `list_purchase_receipts`, endpoints de listado que no existían).
  Bug real corregido: `SupplierService`/`CustomerService.list_all()`
  mezclaban clientes y proveedores en la misma lista — tabla
  `party_roles` nueva (propia de este repo, mismo patrón que
  `party_billing`). Verificado real de punta a punta contra un build de
  producción, incluido un bug propio de UI corregido en el camino
  (gating del formulario de líneas de una orden usaba
  `is_fully_received()`, que da vacuamente `true` sin líneas). 66/66
  tests. Ver DECISIONS.md ADR-015.
- Reportes de ventas, caja y stock (admin-only): ventas confirmadas por
  rango de fechas con total, desglose por día y top-10 de items más
  vendidos; resumen de caja (ingresos/egresos/saldo) vía
  `libracore.db.caja`; stock actual por item con flag de stock bajo/cero.
  Sin tabla ni estado propio — lectura de agregación pura sobre datos ya
  generados, mismo patrón que el dashboard de Gestiolibra/MedLibra.
  Verificado real de punta a punta contra un build de producción. 74/74
  tests. Ver DECISIONS.md ADR-016. **Cierra Fase 5.**
- Incidente: `dev.ventalibra.com.ar` quedó caído porque el contenedor
  del VPS corría código viejo (sin la ruta catch-all del SPA); al
  redeployar con el código actual, crasheó por un gap de fondo:
  `init_schema()` (LibraCommerce) usa `CREATE TABLE IF NOT EXISTS`, que
  es un no-op sobre tablas ya persistidas y nunca agrega columnas
  nuevas (`variant_id` de Fase 4) a una base real ya existente. Fix:
  mecanismo real de migraciones numeradas e idempotentes
  (`libracommerce/db/migrations.py`, trackeadas en `schema_migrations`),
  8 tests nuevos, LibraCommerce `v0.1.5`. Verificado no solo
  sintéticamente sino contra la base real y persistida del cliente
  `prueba` (backup previo, rebuild de `ventalibra:latest`, reinicio del
  contenedor): migración aplicada sin errores ni pérdida de datos. Ver
  DECISIONS.md ADR-017.
