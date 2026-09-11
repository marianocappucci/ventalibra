// El espaciado entre el label y su control, en un solo valor.
//
// **Este test lee el FUENTE, no el DOM**, y es a propósito. Lo que hay que
// impedir no es que una pantalla se rompa —ninguna se rompe con 6 px en vez de
// 8— sino que las pantallas **vuelvan a divergir**. Eso no se ve en ningún
// render: se ve comparando archivos, y sólo si alguien se acuerda de comparar.
//
// De dónde salió: el humano reportó (2026-08-14) que en los formularios "los
// labels y los cuadros de inputs casi se solapan", y que el del **login** era el
// correcto. Medido: el login usa `gap-2` (8 px) y el resto de las pantallas
// usaba `gap-1.5` (6 px). Se convergió al 8 px del login en `libra-ui`,
// Contalibra y Restolibra — la regla de siempre: se normaliza hacia la
// convención que alguien ya cumple, no hacia una nueva.
//
// 🔴 **Este producto llegó casi un mes tarde, y por la misma razón que
// Contalibra había llegado una semana tarde: no tenía el guard.** Lo encontró el
// chequeo de VentaLibra contra Contalibra y Restolibra del 2026-09-11: 40
// contenedores `grid gap-1.5` en diez pantallas, contra ninguno en los otros
// dos. Es el mismo archivo que tienen ellos, para que la próxima vez lo diga el
// producto y no la comparación con el vecino.
//
// ⚠️ **No se puede resolver con una regla CSS global.** Un `margin-bottom` sobre
// `[data-slot="label"]` tocaría también al login, que ya está en 8 px y pasaría
// a 10. El único lugar donde vive el espaciado es la clase del contenedor.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Desde el root donde corre vitest (`frontend/`). **No** desde
// `import.meta.url`: en este setup no es una URL `file:` y `fileURLToPath`
// revienta, con lo que el archivo entero queda sin correr — que se lee como
// "1 suite failed" y no como "el guard no midió nada".
const SRC = join(process.cwd(), 'src')

// El patrón NO es el literal `grid gap-1.5`. Una comparación de texto contiguo
// tiene un punto ciego: no ve `grid gap-1.5 flex-1`, que acá existía en cinco
// lugares. Se pregunta por `grid` y `gap-1.5` **en el mismo className**, con
// bordes de palabra para que `gap-15` o `gap-1` no se cuelen.
const CAMPO_APRETADO = /className="[^"]*\bgrid\b[^"]*\bgap-1\.5\b/

// Y el mismo patrón para la convención buena, que es lo que mide el control
// positivo del final.
const CAMPO_BIEN = /className="[^"]*\bgrid\b[^"]*\bgap-2\b/

// 🔴 **Se saltea `src/test`, y no es cosmético.** En este producto los tests
// viven ADENTRO de `src`, y este archivo tiene `grid gap-1.5` escrito como dato
// —es el control que prueba que el patrón matchea—. Sin saltearlo, el guard se
// encuentra a sí mismo y queda rojo para siempre.
const EXCLUIDO = join(SRC, 'test')

function fuentes(dir: string): string[] {
  if (dir === EXCLUIDO) return []
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? fuentes(p) : (/\.tsx?$/.test(n) ? [p] : [])
  })
}

const ARCHIVOS = fuentes(SRC)

describe('el espaciado de los campos no vuelve a divergir', () => {
  it('encuentra los fuentes', () => {
    // Sin esto, una ruta mal armada haría pasar al test de abajo con cero
    // archivos leídos — verde por no haber mirado nada.
    expect(ARCHIVOS.length).toBeGreaterThan(30)
  })

  it('🔴 ningún contenedor de campo usa `gap-1.5`', () => {
    const culpables: string[] = []
    for (const p of ARCHIVOS) {
      readFileSync(p, 'utf8').split('\n').forEach((linea, i) => {
        if (CAMPO_APRETADO.test(linea)) {
          culpables.push(`${p.slice(SRC.length + 1)}:${i + 1}`)
        }
      })
    }
    // El mensaje va en el `expect` y no en un comentario: cuando esto se ponga
    // rojo, lo que se lee es esta línea, no el archivo.
    expect(culpables, 'los campos van con `grid gap-2` (8 px, el del login): '
      + '`gap-1.5` deja el label pegado al input').toEqual([])
  })

  it('y los dos patrones matchean de verdad lo que dicen matchear', () => {
    // El control de los casos de arriba y de abajo. Sin esto, un regex que no
    // matchea nada daría la lista vacía y el guard pasaría con el defecto
    // entero presente — que es el modo favorito de fallar de un test que busca
    // ausencias.
    expect(CAMPO_APRETADO.test('<div className="grid gap-1.5">')).toBe(true)
    expect(CAMPO_APRETADO.test('<div className="grid gap-1.5 flex-1">')).toBe(true)
    expect(CAMPO_APRETADO.test('<div className="grid flex-1 gap-1.5">')).toBe(true)
    expect(CAMPO_BIEN.test('<div className="grid gap-2">')).toBe(true)
    // Y que no se lleve puesto el aire entre un icono y su texto, que es `flex`
    // y sigue legítimamente en 6 px (acá: los chips del POS y las pestañas).
    expect(CAMPO_APRETADO.test('<span className="flex items-center gap-1.5">')).toBe(false)
    expect(CAMPO_APRETADO.test('<div className="flex flex-wrap gap-1.5">')).toBe(false)
    // Y que `gap-15` o `gap-1` no se cuelen por un borde de palabra flojo.
    expect(CAMPO_APRETADO.test('<div className="grid gap-1">')).toBe(false)
    expect(CAMPO_APRETADO.test('<div className="grid gap-15">')).toBe(false)
    expect(CAMPO_BIEN.test('<div className="grid gap-20">')).toBe(false)
  })

  it('y la convención SÍ está presente, no es que no haya campos', () => {
    // El otro control, y el que más falta hace: "cero culpables" también es lo
    // que devolvería un producto sin un solo contenedor de campo, o un
    // `fuentes()` que no leyó nada. Si esto bajara a cero habría que mirar el
    // guard, no festejar.
    //
    // 🔸 La referencia de los 8 px es el **login**, pero acá no se puede afirmar
    // sobre ella: este producto no tiene un Login propio, lo arma `libra-ui`.
    // Esa referencia la sostiene el guard del motor.
    const conLaConvencion = ARCHIVOS.filter((p) => CAMPO_BIEN.test(readFileSync(p, 'utf8')))
    // Diez pantallas al 2026-09-11; el piso sólo distingue "hay" de "no hay".
    expect(conLaConvencion.length).toBeGreaterThan(5)
  })
})
