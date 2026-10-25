# Piloto 02 · Reencuadre, LUTs y exportación

## Entregado

- Recorte libre, 3:2, 4:5, 1:1 y 9:16, arrastre de esquinas y campos de porcentaje.
- Cambio de proporción horizontal/vertical, giro y enderezado de hasta 15°, con recorte automático de bordes negros.
- Looks locales cálido, frío y blanco y negro; intensidad y antes/después.
- Importación de LUTs `.cube` 3D SDR para entrada/salida sRGB; validación de tamaño, dominio, datos y canales. Ejemplo propio en `examples/Identidad_sRGB.cube`.
- Color en lote sin sustituir los recortes/giros de otras tomas; deshacer del lote como una operación.
- Exportación en segundo plano a JPG sRGB y ZIP con manifiesto. Se renderiza desde el original a resolución completa antes de limitar el lado mayor. Los originales no se reescriben.
- Copia de seguridad de la base de datos antes de migrar el piloto anterior.

## Prueba completa con Halloween

**266/266 JPG validados, 0 errores**. Se aplicaron recorte central del 80 %, enderezado de 1,5° y LUT cálido al 65 % en una copia aislada de la base de datos; no son decisiones de selección ni una propuesta de edición artística para toda la sesión.

Tiempo: **384.79 segundos** (aproximadamente 6 minutos y 25 segundos), lado mayor 1600 px, calidad 95, un trabajo de exportación a la vez. Cada JPG se abrió y comprobó su tamaño y perfil ICC; el ZIP pasó la comprobación de integridad. Tamaño del ZIP: **123.5 MiB**.

[Copia de prueba de los 266 JPG](<D:/sELECDE FOTOS/data/validacion-edicion-31a4c798/04ccea8999f9dbcc/exports/393416aba16e7d180b78891b70d891ee/seleccion-editada.zip>).

[Registro de validación](<D:/sELECDE FOTOS/data/validacion-edicion-31a4c798/validacion.json>).

La auditoría final confirma **266/266 originales intactos por tamaño, fecha y SHA-256**. Proyecto real al entregar: 266 pendientes, 0 conservadas, 0 rechazadas y 0 tomas con ajustes de prueba guardados.

## Verificación de software y navegador

**25 pruebas automáticas aprobadas**. Incluyen LUT identidad, orden RGB y mezcla, entradas incompletas/Log/HDR no admitidas, coordenadas inválidas, giro del área recortada, enderezado sin bordes negros, persistencia, deshacer, color en lote, migración con copia de seguridad, exportación a resolución correcta tras usar una previsualización, perfil ICC, ZIP y revisión obsoleta del editor. También siguen pasando las pruebas anteriores de decisiones, análisis y papelera.

En navegador se comprobó arrastrar una esquina, recorte 4:5, LUT cálido, enderezado, guardado, alternancia con original, exportación/descarga de una foto y apertura del ZIP descargado. Se importó el LUT identidad de ejemplo desde el selector de archivos. Los ajustes guardados durante la prueba se deshicieron.

La exportación individual descargada contiene un JPG de **3987 × 4985 px** con perfil ICC y su manifiesto, sin errores de ZIP. Las pruebas visuales se hicieron en Windows; macOS y RAW real siguen pendientes. Ojos cerrados y evaluación estética no están implementados.

No se descargaron bibliotecas ni modelos adicionales para esta etapa; el procesamiento de fotografías no hace llamadas a servicios de IA.
