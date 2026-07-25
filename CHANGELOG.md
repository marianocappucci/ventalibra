# Changelog — TiendaLibra

Cambios funcionales y releases publicados. Para tareas internas usar
`TASKS.md` y para operaciones del wiki usar `log.md` (repo de wiki).

## [Unreleased]

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
