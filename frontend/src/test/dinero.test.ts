// `pesos()`: el signo va ANTES del `$`, nunca pegado al número. Encontrado
// en `CierreDiario.tsx` (2026-09-17, prueba en pantalla del humano): con una
// diferencia negativa, `$` + `money(v)` a mano daba "$-500,00" en vez de
// "-$500,00".
import { describe, expect, it } from 'vitest'

import { money, pesos } from '../lib/dinero'

describe('pesos()', () => {
  it('un negativo lleva el signo antes del $', () => {
    expect(pesos(-500)).toBe('-$500,00')
  })

  it('un positivo no lleva signo', () => {
    expect(pesos(1500.5)).toBe('$1.500,50')
  })

  it('cero no lleva signo', () => {
    expect(pesos(0)).toBe('$0,00')
  })

  it('acepta el valor como string, igual que money()', () => {
    expect(pesos('-500')).toBe('-$500,00')
  })
})

describe('money()', () => {
  it('formatea con separador de miles y dos decimales, sin signo aparte', () => {
    expect(money(1500.5)).toBe('1.500,50')
  })
})
