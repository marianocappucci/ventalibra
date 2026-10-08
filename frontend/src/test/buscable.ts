// Helpers para probar un `SelectBuscable` (libra-ui v0.129.0, ADR-039): la lista existe en el DOM sólo mientras está abierta, así que un test que
// antes miraba las `<option>` de un `<select>` (o el texto de un `SelectTrigger`) pasa por acá. Mismos nombres y comportamiento que
// `elegirEnBuscable` y `opcionesDe` de `test/helpers-pantallas.tsx` del kit.
import { screen, within } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

type Usuario = ReturnType<typeof userEvent.setup>

/** Elige una opción: se abre el campo con un click y se hace click en la opción por su etiqueta. */
export async function elegirEnBuscable(user: Usuario, combobox: HTMLElement, texto: string | RegExp) {
  await user.click(combobox)
  await user.click(await screen.findByRole('option', { name: texto }))
}

/** Las etiquetas de las opciones de un `SelectBuscable`: se abre, se lee y se cierra con Escape. */
export async function opcionesDe(user: Usuario, combobox: HTMLElement): Promise<string[]> {
  await user.click(combobox)
  const lista = await screen.findByRole('listbox')
  const textos = within(lista).queryAllByRole('option').map((o) => o.textContent ?? '')
  await user.keyboard('{Escape}')
  return textos
}
