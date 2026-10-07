# Tasks — VentaLibra

Trabajo concreto y vigente. Al completar o descartar una tarea, actualizarla;
no usar este archivo como historial (para eso está `CHANGELOG.md`).

## En curso

- [ ] Pedido al kit (`libra-ui`): el aviso ámbar permanente de `comercio/Vencimientos` («Hasta que las ventas descuenten por lote, el saldo de cada lote puede ser
  MAYOR al real…», `AvisoSaldoSobreestimado`, 4 lugares: la pantalla y los tres diálogos) sigue fijo en v0.92.0 y ya no es cierto para lo vendido, devuelto, ajustado o
  transferido con `libracommerce` v0.30.0 (ADR-053). Pedir que sea condicional (por ejemplo, sólo si el reporte trae `resumen.saldos_con_salidas_sin_lote > 0`, que es
  exactamente el caso de un «sin lote» negativo heredado) o que tenga una prop para apagarlo. La prop `puedeMermar` que se había pedido ya no hace falta (la baja está habilitada).
- [ ] POS: probar el diálogo «¿Vender igual?» y los avisos de la venta cobrada en un navegador real (se probaron con vitest y `fetch` simulado, ADR-053); decidir si el aviso
  por vencer se ofrece también en Ventas/VentaDetalle (hoy `GET /api/ventas/{id}` trae `avisos` y la pantalla del kit no los muestra) — pedido al kit si se quiere.
- [ ] Vencimientos: los productos con un saldo «sin lote» negativo heredado (ventas anteriores a A-4) no dejan dar de baja sus lotes hasta conciliar con el conteo físico (un
  ajuste que lleve ese bucket a cero): avisar a los comercios que ya marcaron productos con ADR-052 (ADR-053).

- [ ] Ajuste de stock con lote por API (`OpcionesStock.con_lotes`, hoy APAGADA, ADR-053): el kit v0.92.0 no lo usa. Si hace falta, antes de prenderla agregar una guarda
  por cuerpo que exija `vencimientos.mover` cuando el pedido trae `lot_code` o `expires_at` (con sólo `stock.ajustar`, que tiene el staff heredado, se alterarían lotes por la ruta alternativa) y su test en `tests/test_roles_matriz.py`.

## Completadas

- [x] Scaffold Fase 1: persistencia (`app/db.py`), auth
  (`app/auth.py`/`security.py`/`services/users.py`), catálogo
  (`app/services/catalog.py`), stock, ventas POS (`app/services/sales.py`),
  routers, tests, CI — responsable: LLM.
- [x] Fase 2: compras (proveedores, orden/recepción, orquestación de stock
  vía `libracommerce.usecases.purchasing.confirm_purchase_receipt`) — pin
  de `libracommerce` a v0.1.2, secuencias propias (`app/db.py`), 10 tests
  nuevos (30 en total) + smoke end-to-end — responsable: LLM.
- [x] Fase 3: caja/facturación vía LibraCore (`app/services/billing.py`,
  segunda base SQLite dedicada, clientes con extensión `party_billing`,
  facturación opcional por venta, caja siempre al confirmar) — 8 tests
  nuevos (39 en total) + smoke end-to-end — responsable: LLM.
- [x] Fase 5 (código): planes y gating por módulo (`plans.py`, tabla
  `modulos`, `ModuleRepository`, `require_module()`) — 6 tests nuevos
  (45 en total) — responsable: LLM.
- [x] Fase 5 (infraestructura): `Dockerfile`/`docker-compose.yml`/scripts
  de onboarding, deploy keys SSH (`libracommerce`/`ventalibra`),
  contenedor `ventalibra-dev` verificado en el VPS (puerto 8081) —
  responsable: LLM.
- [x] Fase 5 (dominio/SSL): DNS de `ventalibra.com.ar` corregido por el
  usuario; NPM+SSL provisionado para `dev.ventalibra.com.ar`
  (`forward_host=ventalibra-dev:8000`), verificado real por HTTPS —
  responsable: LLM (provisioning) + usuario (fix de DNS).
- [x] Fase 5 (primer cliente real): `prueba` onboardeado vía
  `scripts/nuevo_cliente.py` (plan Premium, puerto 8082,
  `prueba.ventalibra.com.ar` con SSL). Bug real encontrado y corregido en
  el camino (`build_image()` sin `--ssh`, latente también en
  Gestiolibra/MedLibra) — ver DECISIONS.md ADR-011 — responsable: LLM.
- [x] Fase 4: códigos de barra/listas de precio/variantes construidas en
  LibraCommerce (pin `v0.1.3`) y conectadas a VentaLibra (`/catalog/
  items/scan`, `/pricing`, `variant_id` en ventas y stock) — 17 tests
  nuevos (62 en total), verificado real contra `uvicorn` — ver
  DECISIONS.md ADR-012 — responsable: LLM.
- [x] Corrección: "captura de plan en el onboarding" no era un pendiente
  real — `crear_cliente()`/`main()` ya lo hacían. Ver DECISIONS.md
  ADR-013 — responsable: LLM.
- [x] Frontend (MVP): React/Vite/Tailwind/shadcn-ui — login, POS de
  venta (buscar/escanear/variantes/confirmar), catálogo (unidades,
  items, códigos, variantes). Verificado real de punta a punta contra
  un build de producción. Ver DECISIONS.md ADR-014 — responsable: LLM.
- [x] Frontend: resto del back office (sucursales, proveedores,
  clientes, compras, usuarios, config ARCA). Bug real corregido en el
  camino (`party_roles`, mezcla de clientes/proveedores). Pin de
  `libracommerce` a `v0.1.4`. Verificado real de punta a punta,
  66/66 tests. Ver DECISIONS.md ADR-015 — responsable: LLM.
- [x] Reportes de ventas, caja y stock (admin-only, sin tabla propia).
  Verificado real de punta a punta, 74/74 tests. Ver DECISIONS.md
  ADR-016 — responsable: LLM. **Cierra Fase 5.**
- [x] Incidente: `dev.ventalibra.com.ar` caído (código viejo deployado) +
  gap de fondo (`init_schema()` no migra bases persistidas). Mecanismo
  real de migraciones en LibraCommerce (`v0.1.5`, 8 tests nuevos),
  verificado contra la base real del cliente `prueba` sin pérdida de
  datos. Ver DECISIONS.md ADR-017 — responsable: LLM.
- [x] Roles de usuario (admin, encargado, vendedor, cajero, depósito + `staff` heredado): matriz única en `app/permisos.py`,
  guardas por capacidad en todos los routers, `capacidades` en `/auth/me`, menú y rutas de la SPA por rol, tests de la tabla
  rol × endpoint; el depósito no recibe compras y el cajero fía pero no ve cuenta corriente; el costo sólo para `costos.ver` (filtro de respuesta por prefijo, `app/costos.py`) y el ticket de un turno sólo para
  quien lo abrió o ve los de todos. Ver DECISIONS.md ADR-049 — responsable: LLM.

## Próximas

- [ ] Roles: que el kit (`libra-ui`) sepa que el costo puede faltar y que hay roles de sólo lectura. El costo ya no viaja a quien no
  tiene `costos.ver` (`app/costos.py`), pero Productos muestra `$ NaN` en «Precio costo» (pide una prop para ocultar la columna, y lo mismo el costo y el
  subtotal del detalle de una orden de compra), más una prop `soloLectura` por pantalla (ADR-049). Recibir compras es del encargado
  (el depósito no: decisión del humano, 2026-09-29).
- [ ] Roles: migrar los usuarios `staff` existentes a un rol concreto (hoy siguen con los permisos de siempre) y, cuando no quede
  ninguno, retirar el rol y `catalogo.configurar`.

## Bloqueadas

- [ ] Ninguna por ahora.

- [x] **Roles: que el cajero vea sólo su turno — las ventas** (2026-10-07, ADR-068): el cajero y el vendedor ven, anulan, devuelven, facturan y reimprimen sólo las ventas de sus turnos (libracommerce ADR-038).
- [ ] **Roles: una vista de cliente reducida para el POS** (sin facturas, presupuestos ni remitos): la ficha de un cliente le sigue mostrando esos documentos al cajero (ADR-049, ADR-068).
