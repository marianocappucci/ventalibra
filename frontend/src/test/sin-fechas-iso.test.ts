// Guard: ninguna pantalla imprime una fecha en ISO.
//
// 🔴 Busca la **propiedad final** —"ningun campo de fecha llega al texto
// renderizado sin pasar por el helper"— y no el patron viejo. Es la leccion de
// las dos normalizaciones anteriores: un `sed` que reemplaza parte del patron
// deja el grep de control ciego, y buscar `toLocaleDateString` no encuentra las
// fechas armadas con slicing.
//
// Lee el FUENTE en vez de renderizar: son ~40 pantallas, muchas detras de una
// sesion y de datos que habria que sembrar. El precio es que no ve una fuga que
// pase por una variable intermedia; a cambio cubre todas las pantallas, no las
// tres que tienen test de render.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const RAIZ = new URL('..', import.meta.url).pathname

/** Un campo cuyo valor es una fecha ISO segun el contrato de la API. */
const CAMPO = String.raw`(?:fecha|fecha_[a-z_]+|date|[a-z_]+_at|starts_at|ends_at|` +
  String.raw`valid_until|vencimiento|periodo|periodo_desde|periodo_hasta|apertura|cierre|mtime|ts)`

/** Los formateadores del producto. Un uso envuelto en uno de ellos ya paso por
 *  el helper: el formato lo decide `lib/fechas.ts`, no la vista. */
const HELPERS = String.raw`(?:fecha|fechaHora|hora|horaConSegundos|aFechaLocal|horaDe|sinSegundos|formatDate)`

const INTERPOLADO = new RegExp(String.raw`\{\s*[A-Za-z_][\w.]*\.${CAMPO}\s*(?:\?\?[^}]*|\|\|[^}]*)?\}`)
// 🔴 El `(?:\?\?\s*''\s*)?` no es adorno: sin el, este regex no ve
// `(v.confirmed_at ?? '').slice(0, 10)` — que es EXACTAMENTE la forma que tenia
// una de las fugas. Lo agarro el control positivo de mas abajo; sin ese control
// el guard habria dado verde con un detector ciego.
const RECORTADO = new RegExp(String.raw`\.${CAMPO}[\w.]*\s*(?:\?\?\s*''\s*)?\)?\s*\.(?:slice|substring)\(0,\s*(?:10|16|19)\)`)
const USA_HELPER = new RegExp(String.raw`\b${HELPERS}\s*\(`)

/** Lo que la regla excluye a proposito: los `<input type="date">` hablan el
 *  formato del navegador, y las `key` y los parametros de API no se ven. */
const EXCLUIDO = [
  /type="date"/, /type="datetime-local"/, /\bkey=\{/, /^\s*(?:\/\/|\/\*|\*)/,
  /\bz\.(?:string|date|coerce)/, /\baria-label=|\btitle=/, /\bapi\.(?:get|post|put|del|patch)\(/,
]

export function fugasEn(texto: string): number[] {
  const fugas: number[] = []
  texto.split('\n').forEach((linea, i) => {
    if (EXCLUIDO.some((r) => r.test(linea))) return
    const recortado = RECORTADO.test(linea)
    if (!INTERPOLADO.test(linea) && !recortado) return
    if (USA_HELPER.test(linea) && !recortado) return
    // Una prop (`algo={x.fecha}`) no es texto renderizado.
    if (!recortado && /[A-Za-z_-]+=\{[^{}]*\}\s*$/.test(linea.trim())) return
    fugas.push(i + 1)
  })
  return fugas
}

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return archivos(p)
    return /\.tsx?$/.test(n) && !/\.test\./.test(n) ? [p] : []
  })
}

describe('ninguna fecha visible queda en ISO', () => {
  it('el detector encuentra una fuga cuando la hay', () => {
    // 🔴 Control POSITIVO, y no es ceremonia: sin el, un detector roto —un
    // regex que no matchea nada— daria exactamente el mismo verde que un
    // codigo limpio. El cero de abajo solo significa algo si este test pasa.
    expect(fugasEn('<td>{f.fecha}</td>')).toEqual([1])
    expect(fugasEn('<span>{o.created_at}</span>')).toEqual([1])
    expect(fugasEn("{(v.confirmed_at ?? '').slice(0, 10)}")).toEqual([1])
  })

  it('el detector NO marca lo que la regla excluye', () => {
    expect(fugasEn('<Input type="date" value={borrador.fecha} />')).toEqual([])
    expect(fugasEn('<Fragment key={g.fecha}>')).toEqual([])
    expect(fugasEn('<td>{fecha(f.fecha)}</td>')).toEqual([])
    expect(fugasEn('<td>{fechaHora(t.apertura)}</td>')).toEqual([])
  })

  it('no queda ninguna en pages/ ni components/', () => {
    const sitios: string[] = []
    for (const dir of ['pages', 'components']) {
      let lista: string[]
      try {
        lista = archivos(join(RAIZ, dir))
      } catch {
        continue
      }
      for (const f of lista) {
        for (const linea of fugasEn(readFileSync(f, 'utf8'))) {
          sitios.push(`${f.replace(RAIZ, '')}:${linea}`)
        }
      }
    }
    expect(sitios).toEqual([])
  })
})
