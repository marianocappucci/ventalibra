// El helper de fechas: el unico lugar del frontend donde se decide como se ve
// una fecha.
//
// 🔴 Los asserts miden la **propiedad final** ("ninguna salida visible trae una
// barra ni queda en ISO"), no el patron que se venia usando. Buscar `%d/%m` o
// `toLocaleDateString` no encuentra las fechas armadas a mano con slicing, que
// es como estaban la mitad de las que este cambio cerro.
import { describe, expect, it } from 'vitest'

import { fecha, fechaHora, hora, horaConSegundos } from '../lib/fechas'

describe('fecha()', () => {
  it('da vuelta un ISO pelado', () => {
    expect(fecha('2026-08-22')).toBe('22-08-2026')
  })

  it('no confunde el dia con el mes', () => {
    // 🔴 El control que separa `dd-mm-aaaa` de `mm-dd-aaaa`. Con una fecha como
    // `2026-01-01` las dos lecturas dan el mismo texto y el test pasaria igual
    // con el formato invertido.
    expect(fecha('2026-03-11')).toBe('11-03-2026')
  })

  it('NO corre el dia para atras', () => {
    // 🔴 El defecto que este helper existe para no repetir:
    // `new Date('2026-08-22')` es medianoche UTC, que en Argentina son las
    // 21:00 del 21. Formatear eso convirtiendo de zona muestra el dia anterior
    // SIEMPRE, no solo de noche.
    expect(fecha('2026-08-22')).not.toBe('21-08-2026')
    expect(fecha('2026-01-01')).toBe('01-01-2026')
  })

  it('de un timestamp naive se queda con la fecha, sin moverla', () => {
    // El backend guarda hora de Argentina sin offset. Pasarla por `Date` la
    // interpretaria como hora del navegador y la volveria a correr.
    expect(fecha('2026-08-22 23:30:00')).toBe('22-08-2026')
    expect(fecha('2026-08-22T00:15:00')).toBe('22-08-2026')
  })

  it('un ISO CON zona si se convierte a hora de Argentina', () => {
    // 🔴 La otra mitad de la regla: con offset explicito el valor SI es un
    // instante. `2026-08-23T01:00:00Z` son las 22:00 del 22 en Argentina.
    // Reordenarle el texto mostraria el 23.
    expect(fecha('2026-08-23T01:00:00Z')).toBe('22-08-2026')
    expect(fecha('2026-08-22T22:00:00-03:00')).toBe('22-08-2026')
  })

  it('ninguna salida trae barra ni queda en ISO', () => {
    const entradas = [
      '2026-08-22', '2026-08-22 14:30:00', '2026-08-22T14:30:00',
      '2026-08-23T01:00:00Z', '2026-12-31T23:59:59-03:00',
    ]
    for (const entrada of entradas) {
      const salida = fecha(entrada)
      expect(salida).not.toContain('/')
      expect(salida).not.toMatch(/^\d{4}-\d{2}-\d{2}/)
    }
  })

  it('lo que no es una fecha vuelve como vino', () => {
    // Recortar a ciegas arma una fecha con pedazos de otra cosa. Mostrar lo que
    // vino deja ver que el dato es el raro.
    expect(fecha('2026-W34')).toBe('2026-W34')
    expect(fecha('2026-08')).toBe('2026-08')
    expect(fecha('')).toBe('')
    expect(fecha(null)).toBe('')
    expect(fecha(undefined)).toBe('')
  })
})

describe('fechaHora()', () => {
  it('da `dd-mm-aaaa HH:MM` en reloj de 24 h', () => {
    expect(fechaHora('2026-08-22 14:30:00')).toBe('22-08-2026 14:30')
    expect(fechaHora('2026-08-22 00:05:00')).toBe('22-08-2026 00:05')
  })

  it('no usa reloj de 12 h', () => {
    const salida = fechaHora('2026-08-22 18:45:00')
    expect(salida).toBe('22-08-2026 18:45')
    expect(salida).not.toMatch(/a\.?\s?m\.?|p\.?\s?m\.?/i)
  })

  it('un valor sin hora sale solo como fecha', () => {
    expect(fechaHora('2026-08-22')).toBe('22-08-2026')
  })

  it('convierte cuando el valor trae zona', () => {
    expect(fechaHora('2026-08-23T01:00:00Z')).toBe('22-08-2026 22:00')
  })
})

describe('hora() y horaConSegundos()', () => {
  it('devuelven la hora del timestamp naive sin moverla', () => {
    expect(hora('2026-08-22 14:30:00')).toBe('14:30')
    expect(horaConSegundos('2026-08-22 14:30:07')).toBe('14:30:07')
  })

  it('un valor sin hora no inventa una', () => {
    expect(hora('2026-08-22')).toBe('')
    expect(horaConSegundos('2026-08-22')).toBe('')
    expect(horaConSegundos('')).toBe('')
  })
})
