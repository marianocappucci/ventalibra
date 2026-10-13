import { expect, test } from 'libra-ui/e2e'
import { abrirTurno, cerrarTurno, crearProducto, venderPorApi, ventasVisibles } from './datos'

// Decisión del humano (2026-10-07, ADR-068): el cajero y el vendedor sólo ven las ventas de los turnos de caja que abrieron ELLOS,
// abiertos o cerrados. Sin la capacidad `ventas.todas` (que sólo tiene el encargado, y el admin por construcción), una venta
// ajena es 404, igual que una que no existe. El backend lo prueba con la API; esto prueba lo que ve la persona: su
// listado no trae la venta de otro, y el link directo a esa venta no la muestra.
test.use({ rol: 'cajero' })

test('el cajero sólo ve las ventas de sus turnos, también las de uno ya cerrado, y no las de otro', async ({ page, api, apiDe }) => {
  const admin = await apiDe('admin')
  const encargado = await apiDe('encargado')
  const producto = await crearProducto(admin, { precio: 1_000 })

  try {
    // La caja es una sola y un turno es por usuario: primero vende el encargado y la libera.
    await abrirTurno(encargado, admin)
    const ajena = await venderPorApi(encargado, producto, 1)
    await cerrarTurno(encargado)

    // El cajero hace dos turnos seguidos, una venta en cada uno.
    await abrirTurno(api, admin)
    const primera = await venderPorApi(api, producto, 2)
    await cerrarTurno(api)
    await abrirTurno(api, admin)
    const segunda = await venderPorApi(api, producto, 3)

    // Control por la API: el admin ve las tres; el cajero, sólo las suyas.
    const delAdmin = (await ventasVisibles(admin)).map((v) => v.numero)
    expect(delAdmin).toEqual(expect.arrayContaining([ajena.numero, primera.numero, segunda.numero]))
    const delCajero = (await ventasVisibles(api)).map((v) => v.numero)
    expect(delCajero).toEqual(expect.arrayContaining([primera.numero, segunda.numero]))
    expect(delCajero).not.toContain(ajena.numero)

    // Lo que ve en pantalla.
    await page.goto('/ventas')
    await expect(page.getByText(segunda.numero, { exact: true })).toBeVisible()
    await expect(page.getByText(primera.numero, { exact: true })).toBeVisible()
    await expect(page.getByText(ajena.numero, { exact: true })).toHaveCount(0)

    // Y la venta de otro, por el link directo, no existe para él.
    await page.goto(`/ventas/${ajena.id}`)
    await expect(page.getByText('Venta no encontrada')).toBeVisible()
    await expect(page.getByText(ajena.numero)).toHaveCount(0)
    // La suya sí abre.
    await page.goto(`/ventas/${segunda.id}`)
    await expect(page.getByText(segunda.numero).first()).toBeVisible()
  } finally {
    await cerrarTurno(api)
    await cerrarTurno(encargado)
  }
})
