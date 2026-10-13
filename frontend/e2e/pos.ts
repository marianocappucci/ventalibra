import { expect, type Page } from '@playwright/test'

// Lo que se hace con el POS en más de un spec, por la pantalla y como lo hace el cajero.

export const CAMPO_DE_CODIGO = 'Código o nombre del producto'

/** Escanea (o escribe) un código o un nombre y Enter; espera a que la línea esté en el ticket. Con `N * nombre` van N unidades. */
export async function agregarAlTicket(page: Page, texto: string, linea: string | RegExp): Promise<void> {
  const campo = page.getByLabel(CAMPO_DE_CODIGO)
  await campo.fill(texto)
  await campo.press('Enter')
  await expect(page.getByRole('row', { name: linea })).toBeVisible()
}

/** El botón grande de «Cobrar» (F2) y su diálogo: devuelve el botón de confirmar, para que el spec decida cuándo apretarlo. */
export async function abrirCobro(page: Page, total: string) {
  await page.getByRole('button', { name: /^Cobrar/ }).click()
  const dialogo = page.getByRole('dialog')
  await expect(dialogo.getByRole('heading', { name: `Cobrar ${total}` })).toBeVisible()
  return dialogo.getByRole('button', { name: 'Cobrar', exact: true })
}
