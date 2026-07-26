# Changelog — VentaLibra

Cambios funcionales y releases publicados. Para tareas internas usar
`TASKS.md` y para operaciones del wiki usar `log.md` (repo de wiki).

## [Unreleased]

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
