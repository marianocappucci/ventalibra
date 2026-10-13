import type { Locator, Page } from '@playwright/test'
import { expect, test } from 'libra-ui/e2e'
import { abrirTurno, cerrarTurno, crearPerecedero, crearProducto, enDias, quitarMinimo, unico, venderPorApi } from './datos'

// La reposición sugerida con filas (ADR-051): el motor cruza lo que se vende, lo que hay y el mínimo, y la pantalla dice cuánto pedir. La
// demo no tiene productos con qué sugerir, así que cada corrida siembra los suyos y calcula A MANO lo que tiene que salir (la fórmula es
// `necesidad = vendido × (cobertura + plazo) / días de muestra` y `sugerido = ceil(necesidad − stock)`, con el mínimo de piso):
//   - un producto que se vendió y se está quedando sin stock: sugiere por rotación;
//   - uno por debajo de su mínimo, sin ventas: sugiere lo que falta para llegar al mínimo;
//   - uno con stock de sobra: NO aparece (sí al apagar «Sólo lo que hay que pedir»);
//   - un perecedero cuya góndola «llena» es de lotes vencidos: lo vencido no cuenta como stock y el producto se pide; el mismo stock en un
//     lote vigente no se pide.
// Todos los productos tienen nombre único: la instancia acumula los de otras corridas y se busca cada fila por el suyo.
test.use({ rol: 'deposito' })

/** La celda de una fila bajo la columna que empieza con `columna`: la posición la dice el encabezado, que cambia según las columnas opcionales.
 *  Se usa con la tabla ya dibujada (con la fila a la vista): mientras recarga, la pantalla no tiene encabezados. */
async function celda(page: Page, fila: Locator, columna: string): Promise<Locator> {
  const encabezados = await page.getByRole('columnheader').allTextContents()
  const posicion = encabezados.findIndex((e) => e.trim().startsWith(columna))
  expect(posicion, `no hay columna «${columna}» entre ${encabezados.join(' | ')}`).toBeGreaterThanOrEqual(0)
  return fila.getByRole('cell').nth(posicion)
}

test('la reposición sugiere lo que corresponde, no lo que sobra, y lo vencido no cuenta como stock', async ({ page, apiDe }) => {
  const admin = await apiDe('admin')
  const cajero = await apiDe('cajero')

  // Rotación: 10 en stock, se venden 7 y quedan 3.
  const yerba = await crearProducto(admin, { nombre: unico('Yerba e2e'), precio: 4_800, stock: 10 })
  // Bajo el mínimo: 2 en stock, mínimo de 20 y ninguna venta.
  const fideos = await crearProducto(admin, { nombre: unico('Fideos e2e'), precio: 1_450, stock: 2, stockMinimo: 20 })
  // Stock de sobra: 100 en stock, mínimo de 5.
  const arroz = await crearProducto(admin, { nombre: unico('Arroz e2e'), precio: 1_100, stock: 100, stockMinimo: 5 })
  // Perecedero con 23 en stock, 20 de ellos de un lote vencido hace 5 días: sirven 3, y el mínimo es 10.
  const yogurVencido = await crearPerecedero(admin, {
    lotes: [{ lote: unico('LV'), vence: enDias(-5), cantidad: 20 }, { lote: unico('LB'), vence: enDias(30), cantidad: 3 }], stockMinimo: 10,
  })
  // El control: las mismas 23 unidades y el mismo mínimo, pero todo en un lote vigente. Alcanza.
  const yogurVigente = await crearPerecedero(admin, { lotes: [{ lote: unico('LB'), vence: enDias(30), cantidad: 23 }], stockMinimo: 10 })

  await abrirTurno(cajero, admin)
  try {
    await venderPorApi(cajero, yerba, 7)
  } finally {
    await cerrarTurno(cajero)
  }

  try {
    await page.goto('/reposicion')
    const fila = (producto: { nombre: string }) => page.getByRole('row', { name: new RegExp(producto.nombre) })
    // «Sugerido» es la penúltima columna (la última es «Motivo»): se cuenta desde el final y no depende de las columnas opcionales, y mientras la
    // tabla se recarga con otros parámetros el locator espera solo.
    const sugerido = (producto: { nombre: string }) => fila(producto).getByRole('cell').nth(-2)

    // Con los parámetros de siempre (30 días de rotación, 15 de cobertura, 3 de plazo): el horizonte es de 18 días y el producto nuevo tiene menos de
    // una semana de muestra, que se divide por 7. Yerba: 7 × 18 / 7 = 18 de necesidad − 3 de stock = 15.
    await expect(fila(yerba)).toBeVisible()
    await expect(sugerido(yerba)).toHaveText(/^15\s*UN$/)
    await expect(fila(yerba)).toContainText('Por rotación')
    await expect(await celda(page, fila(yerba), 'Vendido en la ventana')).toHaveText('7')
    await expect(await celda(page, fila(yerba), 'Stock')).toHaveText('3')
    // Fideos: no se vendió nada, pero 2 de 20 de mínimo: faltan 18.
    await expect(sugerido(fideos)).toHaveText(/^18\s*UN$/)
    await expect(fila(fideos)).toContainText('Bajo el mínimo')
    // Yogur con lo vencido: el stock real es 23 y se ve, pero 20 no se pueden ofrecer; quedan 3 de 10 de mínimo: faltan 7.
    await expect(await celda(page, fila(yogurVencido), 'Stock')).toContainText('23')
    await expect(await celda(page, fila(yogurVencido), 'Stock')).toContainText('incl. 20 vencido')
    await expect(sugerido(yogurVencido)).toHaveText(/^7\s*UN$/)
    await expect(fila(yogurVencido)).toContainText('Bajo el mínimo')
    // Lo que no hay que pedir no está: ni el arroz, ni las mismas 23 unidades en un lote vigente.
    await expect(fila(arroz)).toHaveCount(0)
    await expect(fila(yogurVigente)).toHaveCount(0)

    // Un plazo de entrega más largo (10 días) agranda el horizonte a 25: yerba pasa a 7 × 25 / 7 − 3 = 22. Los que van por mínimo no cambian.
    await page.getByLabel('Plazo de entrega (días)').fill('10')
    await expect(sugerido(yerba)).toHaveText(/^22\s*UN$/)
    await expect(sugerido(fideos)).toHaveText(/^18\s*UN$/)
    await expect(sugerido(yogurVencido)).toHaveText(/^7\s*UN$/)

    // El CSV baja con los mismos parámetros que la pantalla: trae la fila de la yerba con 22 en «sugerido» y no trae el arroz.
    const csv = await (await page.request.get((await page.getByRole('link', { name: 'CSV' }).getAttribute('href'))!)).text()
    const [cabecera, ...lineas] = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/)
    const lineaDeYerba = lineas.find((l) => l.includes(yerba.nombre))
    expect(lineaDeYerba, 'la yerba no está en el CSV').toBeTruthy()
    expect(lineaDeYerba!.split(',')[cabecera.split(',').indexOf('sugerido')]).toBe('22')
    expect(csv).not.toContain(arroz.nombre)

    // Sin «Sólo lo que hay que pedir» aparecen los que no hacen falta, con sugerido 0.
    await page.getByLabel('Sólo lo que hay que pedir').uncheck()
    await expect(fila(arroz)).toBeVisible()
    await expect(sugerido(arroz)).toHaveText(/^0\s*UN$/)
    await expect(sugerido(yogurVigente)).toHaveText(/^0\s*UN$/)
    await expect(await celda(page, fila(yogurVigente), 'Stock')).not.toContainText('vencido')
  } finally {
    // Los que quedaron bajo su mínimo salen del reporte de stock bajo, que comparte `/reportes` con el spec de desbordes.
    await quitarMinimo(admin, fideos)
    await quitarMinimo(admin, yogurVencido)
  }
})
