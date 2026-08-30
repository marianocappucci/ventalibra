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
