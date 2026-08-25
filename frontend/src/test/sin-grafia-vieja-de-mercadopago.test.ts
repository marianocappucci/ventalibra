// Guard: ninguna pantalla vuelve a escribir `mercado_pago`.
//
// Este POS fue el último lugar de la familia con una grafía propia para
// MercadoPago: `mercado_pago` con guion bajo, contra el `mercadopago` pegado
// que usan los otros diez repos. Estaba declarada en TRES listas distintas
// —`Pos.tsx`, `CuentasCorrientes.tsx`, `Ventas.tsx`— y esa multiplicidad es
// justamente lo que la mantuvo viva: normalizar una y olvidar las otras deja
// el defecto igual, con dos pantallas escribiendo cada grafía.
//
// 🔴 **Y no es cosmético.** Cada fila escrita con la grafía vieja es una fila
// que los reportes agrupan aparte: el mismo medio sale en dos líneas del
// cierre de caja, con la plata bien contada y el reparto mal. Volver a
// introducirla obliga a otra migración de datos, que es lo que costó sacarla
// (ver `app/normalizacion_medios.py`).
//
// Lee el FUENTE y no renderiza, mismo criterio que `sin-hoy-en-utc.test.ts`:
// son decenas de pantallas, muchas detrás de una sesión y de datos que habría
// que sembrar. El precio es que no ve una grafía armada por concatenación; a
// cambio cubre todas las pantallas, no las pocas que tienen test de render.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { cwd } from 'node:process'

import { describe, expect, it } from 'vitest'

const RAIZ = cwd()
const DIRECTORIOS = [join(RAIZ, 'src')]
/** Si el barrido ve menos que esto, la ruta está mal y el cero no vale. */
const MINIMO_DE_ARCHIVOS = 20

/** 🔴 **Vacía a propósito, y esa es la afirmación.** Ningún módulo de este
 *  producto escribe la grafía vieja. Si algún día hiciera falta una exención,
 *  se agrega acá con su razón — no se afloja el patrón. */
const EXENTAS: string[] = []

/** Este mismo archivo.
 *
 *  🔴 No es una exención: es el instrumento. El guard **tiene** que escribir la
 *  grafía vieja para poder probar que la detecta —los controles positivos de
 *  más abajo—, y sin este salteo se marcaría a sí mismo. Va aparte de
 *  `EXENTAS` justamente para que esa lista siga pudiendo afirmar que ningún
 *  módulo del producto está exento. */
const ESTE_GUARD = 'src/test/sin-grafia-vieja-de-mercadopago.test.ts'

/** La grafía vieja como VALOR, no como palabra suelta.
 *
 *  Busca el identificador completo entre delimitadores, para no marcar
 *  `mercadopago` (la buena) ni una palabra más larga que la contenga. El
 *  `medio_pago` de los payloads —una CLAVE, no un valor— no matchea: son
 *  cadenas distintas. */
const GRAFIA_VIEJA = /\bmercado_pago\b/

export function usosEn(texto: string): number[] {
  const usos: number[] = []
  texto.split('\n').forEach((linea, i) => {
    // Un comentario que EXPLICA la grafía vieja no es un uso: la nota de
    // `Pos.tsx` la nombra para contar de dónde viene. Sin esta línea el guard
    // se marcaría a sí mismo y a cada comentario que documenta la migración.
    if (/^\s*(?:\/\/|\/\*|\*)/.test(linea)) return
    if (GRAFIA_VIEJA.test(linea)) usos.push(i + 1)
  })
  return usos
}

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return archivos(p)
    return /\.tsx?$/.test(n) ? [p] : []
  })
}

describe('la grafía vieja de MercadoPago no vuelve', () => {
  it('el detector encuentra la grafía vieja cuando está', () => {
    // 🔴 Control POSITIVO. Sin él, un regex roto da exactamente el mismo verde
    // que un código limpio: el cero de más abajo sólo significa algo si esto
    // pasa.
    expect(usosEn("  { value: 'mercado_pago', label: 'Mercado Pago' },")).toEqual([1])
    expect(usosEn('  const MERCADO_PAGO = "mercado_pago"')).toEqual([1])
    expect(usosEn('  if (medio === `mercado_pago`) return true')).toEqual([1])
  })

  it('el detector NO marca lo que la regla permite', () => {
    // La grafía canónica, que es la que ahora escribe todo el producto.
    expect(usosEn("  { value: 'mercadopago', label: 'Mercado Pago' },")).toEqual([])
    // La CLAVE `medio_pago` de los payloads: es el nombre del campo, no el
    // valor, y no tiene nada que ver con esta migración.
    expect(usosEn("  await api.post(url, { medio_pago: 'efectivo' })")).toEqual([])
    // Y un comentario que explica la grafía vieja no es un uso.
    expect(usosEn("  // hasta esta version se escribia 'mercado_pago'")).toEqual([])
    expect(usosEn('   * `mercado_pago` era la grafía de este POS.')).toEqual([])
  })

  it('la lista de exentas está vacía en este producto', () => {
    // 🔴 Un `for` sobre una lista vacía es un test que no puede fallar. Éste
    // sí: afirma que NADA está exento, que es la propiedad que se sostiene.
    expect(EXENTAS).toEqual([])
  })

  it('las exenciones son rutas vivas, no comodines olvidados', () => {
    for (const ruta of EXENTAS) {
      expect(existsSync(join(RAIZ, ruta))).toBe(true)
    }
    // Y la del propio guard también: si este archivo se renombra sin tocar la
    // constante, el salteo deja de aplicar donde debe y empieza a aplicar en
    // ningún lado — el test se pondría rojo sobre sí mismo, que es ruidoso
    // pero al menos visible. Este assert lo dice antes y más claro.
    expect(existsSync(join(RAIZ, ESTE_GUARD))).toBe(true)
  })

  it('no queda ningún uso en el código, tests incluidos', () => {
    // 🔴 Los archivos de test **no** se saltean, a diferencia del guard de
    // fechas. Un test que sigue mandando la grafía vieja es un test que
    // ejercita un camino que ya no existe, y encima la mantiene viva como
    // ejemplo a copiar.
    const sitios: string[] = []
    let revisados = 0
    for (const dir of DIRECTORIOS) {
      for (const f of archivos(dir)) {
        const ruta = relative(RAIZ, f).split('\\').join('/')
        if (ruta === ESTE_GUARD) continue
        if (EXENTAS.includes(ruta)) continue
        revisados += 1
        for (const linea of usosEn(readFileSync(f, 'utf8'))) {
          sitios.push(`${ruta}:${linea}`)
        }
      }
    }
    // Sin este assert, una ruta mal armada haría que el barrido no encontrara
    // ningún archivo y la lista vacía de abajo daría verde.
    expect(revisados).toBeGreaterThan(MINIMO_DE_ARCHIVOS)
    expect(sitios).toEqual([])
  })
})
