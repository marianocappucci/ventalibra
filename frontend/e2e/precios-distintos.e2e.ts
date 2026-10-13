import { esperarApi, expect, test } from 'libra-ui/e2e'
import { abrirTurno, cambiarPrecio, cerrarTurno, crearProducto, pesos, stockDe, ventasVisibles } from './datos'
import { abrirCobro, agregarAlTicket } from './pos'

// ADR-079: el servidor valida el precio de cada línea al registrar la venta. Si el POS mandó uno que ya no es el vigente (el
// precio cambió con la pantalla abierta), `POST /api/ventas` contesta 409 `precios_distintos` y NO escribe nada. El
// cajero tiene que verlo: el cobro se cierra SIN cobrar, el ticket toma los precios nuevos y un aviso dice cuántos
// productos cambiaron. No se cobra solo: el total cambió y lo tiene que ver. Recién el segundo intento cobra, a los precios nuevos.
test.use({ rol: 'cajero' })

test('si cambian los precios con la venta armada, el cobro avisa, no cobra, y el segundo intento cobra bien', async ({ page, api, apiDe }) => {
  const admin = await apiDe('admin')
  let yerba = await crearProducto(admin, { precio: 4_800 })
  let fideos = await crearProducto(admin, { precio: 1_450 })
  const turno = await abrirTurno(api, admin)

  try {
    await page.goto('/pos')
    await agregarAlTicket(page, yerba.nombre, new RegExp(yerba.nombre))
    await agregarAlTicket(page, `2 * ${fideos.nombre}`, new RegExp(fideos.nombre))
    await expect(page.getByText(pesos(4_800 + 2 * 1_450), { exact: true })).toBeVisible()

    // Mientras el cajero tiene la venta armada, otra persona (el admin, por la API) cambia los dos precios.
    yerba = await cambiarPrecio(admin, yerba, 5_200)
    fideos = await cambiarPrecio(admin, fideos, 1_600)

    // Primer intento: el servidor rechaza, el POS no cobra.
    const confirmar = await abrirCobro(page, pesos(4_800 + 2 * 1_450))
    const rechazada = esperarApi(page, '/api/ventas', { metodo: 'POST', estado: 409 })
    await confirmar.click()
    const cuerpo = (await (await rechazada).json()) as { detail: { codigo: string; precios: unknown[] } }
    expect(cuerpo.detail.codigo).toBe('precios_distintos')
    expect(cuerpo.detail.precios).toHaveLength(2)

    await expect(page.getByRole('alert').filter({ hasText: 'Cambiaron los precios de 2 productos' })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByText(/cobrada/)).toHaveCount(0)
    // El ticket quedó con los precios vigentes y el total nuevo.
    const total = 5_200 + 2 * 1_600
    await expect(page.getByRole('row', { name: new RegExp(yerba.nombre) })).toContainText(pesos(5_200))
    await expect(page.getByRole('row', { name: new RegExp(fideos.nombre) })).toContainText(pesos(1_600))
    await expect(page.getByText(pesos(total), { exact: true })).toBeVisible()
    // Y no se escribió nada: ni venta ni stock.
    expect(await ventasVisibles(api, turno)).toHaveLength(0)
    expect(await stockDe(admin, yerba)).toBe(100)
    expect(await stockDe(admin, fideos)).toBe(100)

    // Segundo intento: cobra, a los precios nuevos.
    const segundo = await abrirCobro(page, pesos(total))
    const venta = esperarApi(page, '/api/ventas', { metodo: 'POST', estado: 200 })
    await segundo.click()
    expect(((await (await venta).json()) as { total: number }).total).toBe(total)
    await expect(page.getByText(/^Venta POS-\d+ cobrada$/)).toBeVisible()

    const ventas = await ventasVisibles(api, turno)
    expect(ventas).toHaveLength(1)
    expect(ventas[0].items.map((i) => [i.producto_id, i.precio])).toEqual(
      expect.arrayContaining([[yerba.id, 5_200], [fideos.id, 1_600]]),
    )
    expect(await stockDe(admin, yerba)).toBe(99)
    expect(await stockDe(admin, fideos)).toBe(98)
  } finally {
    await cerrarTurno(api)
  }
})
