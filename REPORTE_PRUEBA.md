# Prueba completa · Halloween

- Origen: `C:\Users\ronig\OneDrive\Escritorio\halloween`.
- Sesión: **266 JPG**, 1,56 GB aproximadamente. No contiene ARW.
- Primera pasada: **83.23 segundos**, con dos trabajos de análisis simultáneos.
- Resultado actual: **197 grupos**, **61 fotos con rostros detectados**, **0 errores de análisis**.
- Auditoría posterior a las pruebas de interfaz: **266/266 originales conservan tamaño, fecha de modificación y SHA-256**.
- Entrega: **266 pendientes, 0 conservadas y 0 rechazadas**, sin estrellas ni rotaciones de prueba.
- Caché: **61,4 MiB** aproximadamente. Descargas de bibliotecas y modelo: **1,3 MB** aproximadamente, más metadatos de instalación.

## Verificaciones

**10 pruebas automáticas aprobadas**: análisis y detalle relativo; persistencia y deshacer; agrupación manual; confirmación obsoleta; original modificado; fallo parcial de una pareja RAW/JPG; error de papelera sin eliminación alternativa; operación correcta; autenticación, origen y recorrido HTTP; papelera real usando un archivo de texto desechable generado por la prueba.

**Probado en navegador**: carga de la sesión, conservar y deshacer, rotación y restauración, estrellas persistentes tras recargar, comparación de dos fotos, zoom original 4000 × 6000, búsqueda global, ampliaciones de rostros y listado/cancelación del envío a papelera. No se confirmó ningún envío de fotografías de Halloween. Todas las marcas de prueba quedaron deshechas.

## Límites

El número de grupos no mide precisión. Falta comparar agrupaciones y recomendaciones con tu criterio y medir el tiempo de selección humana. La puntuación es relativa al detalle dentro de un grupo, no una nota artística ni una certeza sobre el enfoque del sujeto.

El lector RAW está instalado, pero falta validar un ARW real de tu cámara. El piloto funciona en Windows mediante un servidor limitado a 127.0.0.1 y un navegador. No se han probado Mac ni instaladores independientes. No se evalúan ojos cerrados ni se han implementado recorte/LUTs. La exportación actual es CSV/JSON y no renderiza imágenes ni modifica catálogos de Lightroom.

Los detalles están en `data/04ccea8999f9dbcc/report.json`, `source_manifest.json`, `integrity.json` y `project.sqlite`.
