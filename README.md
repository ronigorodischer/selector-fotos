# Selector local · piloto Halloween

Primera aplicación funcional para revisar fotos sin subirlas a internet. El motor es Python y la ventana se abre en tu navegador. No necesita servicios de IA de pago ni un servidor remoto.

## Abrir en este equipo

Haz doble clic en **Abrir Selector.vbs**. Si Windows bloquea los scripts VBS, utiliza **Iniciar.cmd**. La dirección local es `http://127.0.0.1:8765/`. La app recuerda la última carpeta y Halloween ya estará analizado.

Se guardan las decisiones y la caché en `data/`, dentro de esta carpeta. Conserva esa carpeta para recuperar tu trabajo. Cerrar la pestaña no detiene el servidor: utiliza el botón de encendido al pie de la barra lateral para cerrarlo. Volver a abrir el acceso reutiliza el servidor existente.

## Revisar

- `P`: se queda; `X`: se va; `U`: pendiente. El avance automático se puede desactivar a la derecha.
- Flechas: foto anterior/siguiente. `R` y `Shift+R`: girar. `0–5`: estrellas. `Ctrl/Cmd+Z`: deshacer un cambio.
- Casillas sobre miniaturas: seleccionar tomas para comparar. Comparar muestra hasta cuatro. A 100 %, el desplazamiento se sincroniza.
- Puedes unir las tomas seleccionadas, separarlas y cambiar la tolerancia de los grupos. Los grupos corregidos manualmente se mantienen al reagrupar.
- Una pareja ARW/JPG se muestra como una toma si coincide carpeta, nombre base, fecha de captura EXIF y modelo de cámara. Los archivos que no se pueden verificar se mantienen separados.
- **Reencuadre y color** (`C`) abre el recorte libre o 3:2, 4:5, 1:1 y 9:16, cambio horizontal/vertical, giro y enderezado de hasta 15°. Arrastra las esquinas o usa los porcentajes. El enderezado recorta los bordes para evitar esquinas negras.
- Hay looks cálido, frío y blanco y negro, intensidad y comparación sin LUT. Puedes importar `.cube` 3D SDR de 2–65 puntos, dominio y salidas 0–1, creados para entrada/salida sRGB. No se convierten LUTs Log/HLG. Los JPG sin perfil se tratan como sRGB; los perfiles ICC compatibles se convierten a sRGB.
- **Aplicar color a seleccionadas** copia solo LUT e intensidad, conserva los recortes y giros, y se deshace como un cambio. **Ver original** alterna con la fotografía sin ajustes.
- **Exportar selección** crea JPG nuevos de la foto actual, la selección, las conservadas o toda la sesión, a resolución del recorte o con lado mayor de hasta 3000/1600 px. Se ejecuta en segundo plano y genera un ZIP con JPG sRGB y `ajustes.json`. No amplía imágenes ni sobrescribe originales. Descarga el ZIP al terminar; también queda en `data/<proyecto>/exports/`.
- Exportar CSV/JSON sigue disponible e incluye decisiones y ajustes. Estos manifiestos no renderizan imágenes ni modifican catálogos de Lightroom.
- La cruz marca una toma. **Enviar rechazadas a la papelera** prepara una lista con las rechazadas de todo el proyecto y requiere otra confirmación. En RAW/JPG vinculados se incluyen ambos archivos. No hay eliminación permanente como alternativa ni vaciado de papelera.
- Después de un envío, la recuperación se realiza desde la papelera del sistema. Si falla parte del lote, se muestra qué archivos se enviaron; no se promete atomicidad entre RAW y JPG.

## Qué está listo y qué falta

Este piloto incluye lectura de JPG y ARW, grupos por similitud y tiempo, hashes de duplicados exactos, detalle relativo, rostros ampliados, comparación, rotación, decisiones persistentes y exportación de manifiestos. Los originales no se reescriben.

La agrupación y la puntuación son **experimentales**. La cifra compara el detalle dentro de un grupo y no es una nota artística ni una certeza sobre el enfoque del sujeto. Cuando un disfraz cubre el rostro, se usa como orientación el detalle de la zona central. No se evalúan ojos abiertos/cerrados ni composición estética. Halloween contiene únicamente JPG: falta validar un ARW real de tu cámara. El piloto 02 ya incluye recorte, enderezado, LUTs y exportación JPG. El enfoque se analiza sobre la foto original, sin cambiar por los ajustes.

La aplicación funciona sin conexión después de la instalación. Omite archivos de OneDrive marcados como solo disponibles en la nube para evitar descargarlos. El código es portable, pero todavía no se ha probado en macOS ni se ha generado un instalador independiente de Python. El contenedor Electron y esas funciones continúan en el plan original.

## Comandos de desarrollo

```text
python app.py --source "ruta de la sesión" --analyze --audit
python app.py --source "ruta de la sesión" --open
python -m unittest discover -s tests -v
python validate_session.py "ruta de la sesión"
```

Bibliotecas externas: NumPy, OpenCV y Pillow ya instaladas; rawpy, ExifRead y Send2Trash en `.deps/`. Requisitos en `requirements.txt`. Para usarlo en otro equipo hay que instalar esas bibliotecas con una versión de OpenCV compatible con el modelo YuNet empaquetado, o sustituir el detector por el modelo correspondiente a esa versión. El piloto actual se verificó con OpenCV 5.0.0, Python 3.11.9 y Windows.

Modelo de rostros YuNet de OpenCV Zoo: archivo `face_detection_yunet_2026may.onnx`, SHA-256 `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0`. Licencia MIT en `models/YUNET_LICENSE.txt`; fuente: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet.

`validate_session.py` usa una copia aislada del proyecto dentro de `data/`, aplica ajustes de prueba allí y exporta toda la sesión a 1600 px. Verifica JPG, perfil ICC, ZIP y hashes de los originales. No cambia decisiones ni ajustes del proyecto real. Puede tardar varios minutos y conserva la salida para revisarla.

Al migrar desde el piloto 01 se crea `project.before-editing.sqlite` antes de añadir los campos nuevos. Las decisiones se conservan.
