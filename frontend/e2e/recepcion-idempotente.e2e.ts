import { expect, test } from 'libra-ui/e2e'
import { crearOrdenDeCompra, crearProducto, recepcionesDe, stockDe } from './datos'

// «Recibir mercadería» es idempotente (ADR-045): manda la recepción entera con su `clave_operacion` y un reintento con la misma
// clave no vuelve a mover stock. Lo difícil de probar sin navegador es el caso que la justifica: la respuesta se pierde DESPUÉS
// de que el servidor escribió. Acá el servidor recibe y registra el pedido de verdad (`route.fetch()`), y al navegador se le
// corta la conexión (`route.abort()`): la pantalla no sabe si se registró y ofrece reenviar el intento con la misma clave.
// Lo único que cuenta al final está en la API: UNA recepción y el stock entró UNA vez.
test.use({ rol: 'encargado' })

test('si se corta la respuesta de «Recibir», reenviar el intento no duplica la recepción ni el stock', async ({ page, api, apiDe }) => {
  const admin = await apiDe('admin')
  const producto = await crearProducto(admin, { precio: 900, stock: 0 })
  const orden = await crearOrdenDeCompra(admin, producto, { cantidad: 10, costo: 450 })

  // Sólo el PRIMER pedido se corta; el reenvío pasa tal cual.
  let cortados = 0
  await page.route('**/api/purchase-receipts/recibir', async (route) => {
    if (cortados > 0) return route.continue()
    cortados++
    await route.fetch() // el servidor recibe y registra
    await route.abort('connectionreset') // pero la respuesta no llega
  })

  await page.goto(`/compras/${orden.id}`)
  await page.getByRole('button', { name: 'Recibir mercadería' }).click()
  const dialogo = page.getByRole('dialog')
  await expect(dialogo.getByRole('heading', { name: `Recibir mercadería — Orden ${orden.numero}` })).toBeVisible()
  await expect(dialogo.getByLabel(`Cantidad a recibir de ${producto.nombre}`)).toHaveValue('10')
  await dialogo.getByRole('button', { name: 'Recibir', exact: true }).click()

  // La pantalla no sabe qué pasó: no da la recepción por hecha y deja reenviar el MISMO intento.
  await expect(dialogo.getByText(/No se sabe si se llegó a registrar/)).toBeVisible()
  await expect(dialogo.getByText(/Hay un intento anterior de recibir esta orden sin confirmar/)).toBeVisible()
  expect(cortados).toBe(1)
  // El servidor, en cambio, sí la registró: ahí está el riesgo que cubre la clave.
  expect(await recepcionesDe(api, orden.id)).toHaveLength(1)
  expect(await stockDe(admin, producto)).toBe(10)

  await dialogo.getByRole('button', { name: 'Reenviar el intento anterior' }).click()

  // El motor contesta `repetida: true` y la pantalla lo dice.
  await expect(page.getByText('Esa recepción ya estaba registrada (era un reintento): no se cargó dos veces.')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // Una sola recepción, un solo ingreso de stock.
  expect(await recepcionesDe(api, orden.id)).toHaveLength(1)
  expect(await stockDe(admin, producto)).toBe(10)
})
