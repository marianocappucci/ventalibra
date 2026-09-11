// 🔴 **Ninguna pantalla declara la lista de medios de pago.**
//
// Hasta el 2026-09-11 este producto tenía tres copias del vocabulario del motor
// —`MEDIOS_PAGO` en `Pos.tsx`, `MEDIOS_DEVOLUCION` en `Ventas.tsx` y otra
// `MEDIOS_PAGO` en `CuentasCorrientes.tsx`— y el backend no validaba el medio.
// O sea que el selector era lo único que decía qué se podía cobrar, y las tres
// escondían medios que la familia ofrece (Cuenta DNI, otras billeteras, cheque).
//
// Es el mismo guard que Contalibra y Restolibra tienen desde el 2026-08-24. Lo
// encontró el chequeo de VentaLibra contra esos dos. Una copia en el frontend
// siempre termina divergiendo, porque nada la compara con la del backend: acá
// no hay lista, se pide (`lib/medios-pago.ts`).
//
// Se lee el fuente y no el DOM a propósito: montar cada pantalla para buscar un
// `<option>` sería mucho más frágil que buscar el literal.
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = resolve(__dirname, '..')

/** 🔴 Saca los comentarios antes de buscar.
 *
 *  Sin esto el guard se dispara con **la nota que explica por qué la copia se
 *  fue**. Un guard que empuja a borrar el porqué está mal escrito. */
function sinComentarios(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
}

function fuentes(): { nombre: string; texto: string }[] {
  const archivos: { nombre: string; texto: string }[] = []
  const recorrer = (dir: string) => {
    for (const entrada of readdirSync(dir, { withFileTypes: true })) {
      const ruta = resolve(dir, entrada.name)
      if (entrada.isDirectory()) {
        if (entrada.name === 'test' || entrada.name === 'components') continue
        recorrer(ruta)
      } else if (/\.tsx?$/.test(entrada.name)) {
        archivos.push({
          nombre: ruta.replace(src + '/', ''),
          texto: sinComentarios(readFileSync(ruta, 'utf8')),
        })
      }
    }
  }
  recorrer(src)
  return archivos
}

/** Los medios que sólo pueden venir de una lista declarada a mano. Se busca el
 *  literal entre comillas: un `'efectivo'` suelto en un `.tsx` es un valor por
 *  defecto o una comparación, pero **tres o más juntos** son una lista. */
const CLAVES = ['efectivo', 'transferencia', 'mercadopago', 'cuenta_dni', 'billetera', 'cheque']

function clavesPresentes(texto: string): string[] {
  return CLAVES.filter((c) => texto.includes(`'${c}'`) || texto.includes(`${c}:`))
}

describe('el vocabulario de medios de pago no vuelve al frontend', () => {
  it('🔴 ninguna pantalla declara tres o más medios juntos', () => {
    const sospechosos = fuentes()
      .map(({ nombre, texto }) => ({ nombre, presentes: clavesPresentes(texto) }))
      .filter(({ presentes }) => presentes.length >= 3)
      .map(({ nombre, presentes }) => `${nombre} (${presentes.join(', ')})`)

    expect(sospechosos).toEqual([])
  })

  it('🔴 `MEDIOS_PAGO_LABELS` no vuelve, ni siquiera re-exportada', () => {
    const conLaCopia = fuentes()
      .filter(({ texto }) => texto.includes('MEDIOS_PAGO_LABELS'))
      .map(({ nombre }) => nombre)
    expect(conLaCopia).toEqual([])
  })

  it('el control — el guard sabe leer los fuentes de verdad', () => {
    // Sin esto, un `readdirSync` sobre la carpeta equivocada daría cero archivos
    // y los dos tests de arriba pasarían con la copia adentro: "un cero
    // esperado necesita un positivo".
    const archivos = fuentes()
    expect(archivos.length).toBeGreaterThan(20)
    expect(archivos.some(({ nombre }) => nombre === 'lib/medios-pago.ts')).toBe(true)
    const shim = archivos.find(({ nombre }) => nombre === 'lib/medios-pago.ts')!
    expect(shim.texto).toContain('medios-pago')
    // Y las tres pantallas que tenían la lista siguen estando entre los leídos.
    for (const pantalla of ['pages/Pos.tsx', 'pages/Ventas.tsx', 'pages/CuentasCorrientes.tsx']) {
      expect(archivos.some(({ nombre }) => nombre === pantalla), pantalla).toBe(true)
    }
  })

  it('el control — la lista que había en el POS la habría agarrado', () => {
    // La de devolución tenía cuatro medios y la del POS seis; con tres claves
    // ya se dispara. Si alguien afloja el umbral o las claves, esto se pone rojo.
    const laDelPos = `const MEDIOS_PAGO = [
      { value: 'efectivo', label: 'Efectivo' },
      { value: 'transferencia', label: 'Transferencia' },
      { value: MERCADO_PAGO, label: 'Mercado Pago' },
    ]
    const MERCADO_PAGO = 'mercadopago'`
    expect(clavesPresentes(sinComentarios(laDelPos)).length).toBeGreaterThanOrEqual(3)
  })

  it('el control — sacar comentarios no tapa una lista de verdad', () => {
    const conLista = "const MEDIOS = { efectivo: 'x', transferencia: 'y', cheque: 'z' }"
    expect(sinComentarios(`// un comentario\n${conLista}`)).toContain('efectivo')
    expect(sinComentarios('// MEDIOS_PAGO_LABELS en una nota')).not.toContain('MEDIOS_PAGO_LABELS')
    expect(sinComentarios('/* bloque */ const x = 1')).toContain('const x = 1')
  })
})
