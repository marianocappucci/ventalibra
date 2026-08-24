/**
 * El **unico** lugar donde se formatea una fecha en el frontend.
 *
 * La regla del ecosistema (2026-08-12, `wiki/concepts/estandares-desarrollo.md`):
 * la API habla ISO 8601 en las dos direcciones y `dd-mm-aaaa` es **solo**
 * presentacion. La base sigue guardando ISO, los parametros de fecha en URLs
 * siguen en ISO y los `<input type="date">` no se tocan.
 *
 * El producto no tenia ninguno: las dos fechas que mostraba --el extracto de
 * cuenta corriente y la columna Fecha de Ventas-- salian crudas de la API, una
 * tal cual y la otra recortada a mano con `(v.confirmed_at ?? '').slice(0, 10)`.
 * Ese recorte es la razon por la que ningun grep de `%d/%m` ni de
 * `toLocaleDateString` las encontraba.
 */

export const TZ = 'America/Argentina/Buenos_Aires'

/** Un `aaaa-mm-dd` pelado, tal como lo serializa una columna `date`. */
const SOLO_FECHA = /^(\d{4})-(\d{2})-(\d{2})$/

/** `aaaa-mm-dd HH:MM[:SS]` — lo que el backend guarda, sin zona.
 *
 * Acepta tanto el espacio como la `T`: la misma columna sale con espacio por
 * SQLite y con `T` por PostgreSQL. */
const FECHA_HORA = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/

/**
 * Un ISO que trae zona explicita (`Z` o `-03:00`).
 *
 * 🔴 Ese SI es un instante y hay que convertirlo, no reordenarle el texto.
 * La distincion importa desde que el sidecar de PostgreSQL pasa a UTC-3: un
 * `timestamptz` se serializa en la zona de la SESION, asi que la misma columna
 * puede salir `...Z` o `...-03:00` segun donde corra. Reordenar el texto de un
 * `2026-08-22T01:00:00Z` mostraria el 22, cuando en Argentina son las 22:00 del
 * 21. Con offset se convierte; sin offset (naive, ya en hora de Argentina) se
 * reordena.
 */
const CON_ZONA = /(?:Z|[+-]\d{2}:?\d{2})$/

type Valor = string | Date | null | undefined

/**
 * `dd-mm-aaaa`. Acepta un ISO (con hora o sin ella) o un `Date`.
 *
 * 🔴 **Un `aaaa-mm-dd` no es un instante: es un dia del calendario.**
 * `new Date('2026-08-22')` es medianoche UTC, que en Argentina son las 21:00
 * del 21 — convertirlo de zona lo corre un dia para atras SIEMPRE, no solo de
 * noche. Y los timestamps del backend son naive en hora de Argentina: pasarlos
 * por `Date` los interpreta como hora del navegador y los vuelve a mover.
 * Por eso los dos casos se resuelven reordenando el TEXTO, sin construir un
 * `Date`: no hay zona de la que convertir, asi que no hay nada que corromper.
 *
 * Lo que no matchea ninguna de las dos formas se devuelve tal cual, no
 * recortado a ciegas: mejor mostrar lo que vino que una cadena armada con
 * pedazos de otra cosa.
 */
export function fecha(valor: Valor): string {
  if (!valor) return ''
  if (typeof valor === 'string') {
    const solo = SOLO_FECHA.exec(valor)
    if (solo) return `${solo[3]}-${solo[2]}-${solo[1]}`
    if (CON_ZONA.test(valor)) return deDate(new Date(valor), false)
    const conHora = FECHA_HORA.exec(valor)
    if (conHora) return `${conHora[3]}-${conHora[2]}-${conHora[1]}`
    return valor
  }
  return deDate(valor, false)
}

/** `dd-mm-aaaa HH:MM`, reloj de 24 h. Un valor sin hora sale solo como fecha. */
export function fechaHora(valor: Valor): string {
  if (!valor) return ''
  if (typeof valor === 'string') {
    if (CON_ZONA.test(valor)) return deDate(new Date(valor), true)
    const conHora = FECHA_HORA.exec(valor)
    if (conHora) return `${conHora[3]}-${conHora[2]}-${conHora[1]} ${conHora[4]}:${conHora[5]}`
    return fecha(valor)
  }
  return deDate(valor, true)
}

/** Solo `HH:MM`. Vacio si el valor no trae hora. */
export function hora(valor: Valor): string {
  if (!valor) return ''
  if (typeof valor === 'string') {
    if (CON_ZONA.test(valor)) return deDate(new Date(valor), true).slice(11)
    const conHora = FECHA_HORA.exec(valor)
    return conHora ? `${conHora[4]}:${conHora[5]}` : ''
  }
  return deDate(valor, true).slice(11)
}

/** `HH:MM:SS`. La columna Hora del log de actividad muestra los segundos: dos
 *  movimientos del mismo minuto se distinguen por ahi. */
export function horaConSegundos(valor: Valor): string {
  if (typeof valor !== 'string' || !valor) return ''
  const conHora = FECHA_HORA.exec(valor)
  if (!conHora) return ''
  return conHora[6] ? `${conHora[4]}:${conHora[5]}:${conHora[6]}` : `${conHora[4]}:${conHora[5]}`
}

/**
 * Un `Date` → `dd-mm-aaaa[ HH:MM]` en hora de Argentina.
 *
 * 🔴 Se arma con `formatToParts` y no con el `format()` de `es-AR` directo: ese
 * devuelve `22/08/2026`, **con barras**, y la convencion del ecosistema es con
 * guiones. Leyendo el codigo, `es-AR` + `2-digit` parece que ya diera el
 * formato pedido.
 */
function deDate(d: Date, conHora: boolean): string {
  if (Number.isNaN(d.getTime())) return ''
  const partes = new Intl.DateTimeFormat('es-AR', {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    ...(conHora ? { hour: '2-digit' as const, minute: '2-digit' as const, hour12: false } : {}),
  }).formatToParts(d)
  const p = (tipo: Intl.DateTimeFormatPartTypes) =>
    partes.find((x) => x.type === tipo)?.value ?? ''
  const dia = `${p('day')}-${p('month')}-${p('year')}`
  return conHora ? `${dia} ${p('hour')}:${p('minute')}` : dia
}
