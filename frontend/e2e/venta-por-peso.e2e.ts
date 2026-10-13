import { esperarApi, expect, test } from 'libra-ui/e2e'
import {
  abrirTurno, asegurarBalanza, cerrarTurno, crearPesable, crearProducto, etiquetaDeBalanza, pesos, stockDe, ventasVisibles,
} from './datos'
import { abrirCobro, agregarAlTicket } from './pos'

// Una venta completa en el POS, de punta a punta: el cajero escanea la etiqueta de la balanza (un artículo por peso) y
// agrega un artículo por unidad, cobra en efectivo y la instancia lo registra. Lo que ningún unitario ve: que el
// ticket, el diálogo de cobro y la API digan lo mismo.
//
// ADR-079: la línea que sale de una etiqueta de balanza no cambia de cantidad. El servidor valida el peso contra la
// etiqueta cruda, así que otra cantidad no se cobraría: el POS lo dice y la deja como estaba.
test.use({ rol: 'cajero' })

test('el cajero vende un artículo por peso y uno por unidad, y se cobra el total', async ({ page, api, apiDe }) => {
  const admin = await apiDe('admin')
  await asegurarBalanza(admin)
  const queso = await crearPesable(admin, { precioKg: 12_000 })
  const yerba = await crearProducto(admin, { precio: 4_800 })
  const turno = await abrirTurno(api, admin)

  try {
    await page.goto('/pos')

    // 0,350 kg de queso a $12.000 el kilo = $4.200, tal como los lee el cajero en la etiqueta.
    await agregarAlTicket(page, etiquetaDeBalanza(queso.plu, 0.35), new RegExp(queso.nombre))
    const lineaDeQueso = page.getByRole('row', { name: new RegExp(queso.nombre) })
    await expect(lineaDeQueso).toContainText('0,350')
    await expect(lineaDeQueso).toContainText(pesos(12_000))
    await expect(lineaDeQueso).toContainText(pesos(4_200))

    // La línea de balanza no cambia de cantidad.
    await lineaDeQueso.click()
    await page.getByRole('button', { name: /Cantidad/ }).click()
    await expect(page.getByText('La cantidad de un producto de balanza la fija su etiqueta')).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(lineaDeQueso).toContainText('0,350')

    // Un artículo por unidad sí: «2 * nombre» entran dos.
    await agregarAlTicket(page, `2 * ${yerba.nombre}`, new RegExp(yerba.nombre))
    await expect(page.getByRole('row', { name: new RegExp(yerba.nombre) })).toContainText(pesos(9_600))

    const total = 4_200 + 2 * 4_800
    await expect(page.getByText(pesos(total), { exact: true })).toBeVisible()

    const confirmar = await abrirCobro(page, pesos(total))
    const venta = esperarApi(page, '/api/ventas', { metodo: 'POST' })
    await confirmar.click()
    const respuesta = await venta
    expect(respuesta.status()).toBe(200)
    const cobrada = (await respuesta.json()) as { total: number }
    expect(cobrada.total).toBe(total)

    await expect(page.getByText(/^Venta POS-\d+ cobrada$/)).toBeVisible()
    await expect(page.getByText(pesos(total), { exact: true })).toBeVisible()

    // Y lo que quedó en la instancia: una sola venta de este turno, con el peso exacto y el stock descontado.
    const ventas = await ventasVisibles(api, turno)
    expect(ventas).toHaveLength(1)
    expect(ventas[0].estado).toBe('cobrada')
    expect(ventas[0].items.find((i) => i.producto_id === queso.id)?.qty).toBe(0.35)
    expect(await stockDe(admin, queso)).toBeCloseTo(20 - 0.35, 3)
    expect(await stockDe(admin, yerba)).toBe(98)
  } finally {
    await cerrarTurno(api)
  }
})
