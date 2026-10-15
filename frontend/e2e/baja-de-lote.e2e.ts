import { esperarApi, expect, test } from 'libra-ui/e2e'
import { crearPerecedero, depositoPredeterminado, enDias, saldosPorLote, stockDe, unico } from './datos'

// La baja de un lote (merma) desde `/vencimientos` (ADR-052 y A-4, ADR-053). Lo que importa y ningún unitario ve: que la pantalla
// dé de baja EL lote que se tocó, por la cantidad que se escribió, y no otro; que el stock del producto baje exactamente eso y que
// la API lo cuente igual que la pantalla. La baja la hace quien mueve la mercadería (`vencimientos.mover`: el depósito y el
// encargado); el mostrador no puede, y eso lo corta el servidor, no la pantalla.
// Ancho de escritorio amplio: desde libra-ui v0.152.1 (ADR-065) la lista de lotes pasa a tarjetas cuando la tabla no entra (con el menú abierto
// eso pasa hasta ~1366 px) y este spec lee las FILAS de la tabla. Las tarjetas las prueba el kit.
test.use({ rol: 'deposito', viewport: { width: 1600, height: 900 } })

test('el depósito da de baja una parte de un lote vencido: baja ese lote y el stock, y el otro lote no se toca', async ({ page, apiDe }) => {
  const admin = await apiDe('admin')
  const vencido = unico('LV')
  const vigente = unico('LB')
  // Un lote vencido hace 5 días (8 unidades) y otro que vence en 10 (5): los dos entran en los 15 días de aviso de la pantalla.
  const producto = await crearPerecedero(admin, {
    lotes: [{ lote: vencido, vence: enDias(-5), cantidad: 8 }, { lote: vigente, vence: enDias(10), cantidad: 5 }],
  })
  expect(await saldosPorLote(admin, producto)).toEqual({ [vencido]: 8, [vigente]: 5 })
  expect(await stockDe(admin, producto)).toBe(13)

  await page.goto('/vencimientos')
  const filaVencida = page.getByRole('row', { name: new RegExp(`${producto.nombre}.*${vencido}`) })
  await expect(filaVencida).toContainText('Vencido')
  await expect(filaVencida).toContainText('8 UN')
  const filaVigente = page.getByRole('row', { name: new RegExp(`${producto.nombre}.*${vigente}`) })
  await expect(filaVigente).toContainText('5 UN')

  await page.getByRole('button', { name: `Dar de baja (merma) ${producto.nombre}, lote ${vencido}` }).click()
  const dialogo = page.getByRole('dialog')
  await expect(dialogo.getByRole('heading', { name: 'Dar de baja (merma)' })).toBeVisible()
  await expect(dialogo).toContainText(`lote ${vencido}`)
  // La cantidad arranca en todo el saldo; se da de baja sólo una parte.
  await expect(dialogo.getByLabel('Cantidad a dar de baja')).toHaveValue('8')
  await dialogo.getByLabel('Cantidad a dar de baja').fill('3')
  const merma = esperarApi(page, '/api/vencimientos/merma', { metodo: 'POST', estado: 200 })
  await dialogo.getByRole('button', { name: 'Confirmar' }).click()

  const respuesta = (await (await merma).json()) as { cantidad: number; saldo_restante: number; lote: string; repetida: boolean }
  expect(respuesta).toMatchObject({ lote: vencido, cantidad: 3, saldo_restante: 5, repetida: false })

  // La pantalla lo dice, cierra el diálogo y recarga: el lote que se tocó quedó en 5 y el otro sigue en 5.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('status').filter({ hasText: `Se dieron de baja 3 UN de ${producto.nombre}, lote ${vencido}. Saldo del lote: 5 UN.` })).toBeVisible()
  await expect(filaVencida).toContainText('5 UN')
  await expect(filaVencida).not.toContainText('8 UN')
  await expect(filaVigente).toContainText('5 UN')

  // Lo que quedó en la instancia: el lote tocado bajó 3, el otro no se movió y el stock del producto bajó exactamente 3.
  expect(await saldosPorLote(admin, producto)).toEqual({ [vencido]: 5, [vigente]: 5 })
  expect(await stockDe(admin, producto)).toBe(10)
})

test('el cajero no puede dar de baja un lote: el servidor rechaza con 403 y no se toca nada', async ({ apiDe }) => {
  const admin = await apiDe('admin')
  const cajero = await apiDe('cajero')
  const lote = unico('LV')
  const producto = await crearPerecedero(admin, { lotes: [{ lote, vence: enDias(-1), cantidad: 4 }] })

  const intento = await cajero.post('/api/vencimientos/merma', {
    data: { producto_id: producto.id, deposito_id: await depositoPredeterminado(admin), lote, vence: enDias(-1), cantidad: 4, clave_operacion: unico('clave') },
  })
  expect(intento.status()).toBe(403)
  expect(await saldosPorLote(admin, producto)).toEqual({ [lote]: 4 })
  expect(await stockDe(admin, producto)).toBe(4)
})
