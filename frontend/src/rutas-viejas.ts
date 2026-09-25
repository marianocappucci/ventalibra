/** Las tres pantallas de configuración que fueron ítems del menú lateral.
 *
 *  Eran `/config-arca`, `/config-balanza` y `/config-ticket`. Al unificarse en
 *  una sola pantalla (2026-08-05) quedaron como redirecciones y no se borraron:
 *  pueden estar en un favorito o en un mensaje, y un 404 en Configuración
 *  parece que se rompió el sistema.
 *
 *  🔴 **Viven acá y no adentro de `App.tsx` porque el test las duplicaba.**
 *  `src/test/configuracion.test.tsx` armaba su propio `<Routes>` con estas tres
 *  líneas escritas de nuevo, así que medía su propia copia: cuando el destino
 *  de ARCA cambió —dejó de ser una pestaña de primer nivel y pasó a ser una
 *  sub-sección de "Integraciones"— el test siguió pasando sobre la ruta vieja
 *  mientras la app redirigía a otro lado. Con una sola definición eso no puede
 *  volver a pasar.
 *
 *  ⚠️ El destino de ARCA lleva **las dos** claves del query. Con sólo
 *  `?seccion=arca` la redirección no falla: aterriza en Empresa, que es peor
 *  que un error porque no se nota.
 */
export const REDIRECCIONES_DE_CONFIGURACION: Record<string, string> = {
  '/config-arca': '/configuracion?seccion=integraciones&integracion=arca',
  '/config-balanza': '/configuracion?seccion=balanza',
  '/config-ticket': '/configuracion?seccion=ticket',
}

/** El ítem del menú lateral "Catálogo" pasó a llamarse "Productos"
 *  (2026-09-17, pedido del humano) y su ruta de `/catalogo` a `/productos`.
 *  Misma razón que la tabla de arriba para no borrarla: puede estar en un
 *  favorito o en un mensaje, y un 404 en Productos parece que se rompió el
 *  sistema. Mismo motivo para vivir en este archivo y no en `App.tsx`: que un
 *  test no pueda medir su propia copia de la redirección en vez de la que usa
 *  la app -- ver el docstring de arriba. */
export const REDIRECCIONES_DE_CATALOGO: Record<string, string> = {
  '/catalogo': '/productos',
}

/** Link legado de la pantalla de cuenta corriente del kit (ADR-027).
 *
 *  `libra-ui/comercio/CuentaCorriente` linkea `/cuenta-corriente/:id` (Ver
 *  cuenta) y su detalle vuelve a `/cuenta-corriente` (Volver). La "Ficha
 *  cliente" `/clientes/:id` ya tiene pantalla propia, no redirección.
 *  Sin esta entrada, "Volver" caería al catch-all del POS.
 */
export const REDIRECCIONES_DEL_KIT: Record<string, string> = {
  '/cuenta-corriente': '/cuentas-corrientes',
}
