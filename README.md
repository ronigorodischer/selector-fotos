# Selector local de fotos

Primera aplicación funcional para revisar fotos sin subirlas a internet. El motor es Python y la ventana se abre en tu navegador. No necesita servicios de IA de pago ni un servidor remoto.

El botón **Mover seleccionadas** organiza los originales marcados **Se queda** en la subcarpeta `Seleccionadas` del proyecto. Muestra el lote antes de moverlo, conserva las subcarpetas y las parejas RAW + JPG, y omite las fotos que ya están allí. No sobrescribe archivos. Las tomas conservan su identidad, estrellas, ajustes y grupos en el catálogo; el movimiento de archivos no se revierte con Ctrl+Z.

## Instalar en otro PC (Windows)

1. Instala **Python 3.11 de 64 bits** desde [python.org](https://www.python.org/downloads/). Activa **Add Python to PATH**. También se admiten Python 3.12 y 3.13.
2. Inicia sesión en GitHub con la cuenta que tenga acceso al [repositorio privado](https://github.com/ronigorodischer/selector-fotos). Puedes clonarlo con Git o descargar **Code → Download ZIP** y descomprimirlo.

   ```powershell
   git clone https://github.com/ronigorodischer/selector-fotos.git
   cd selector-fotos
   ```

3. Haz doble clic en **Instalar.cmd**. La primera vez necesita internet para descargar las dependencias en `.venv/`. No requiere OpenCV preinstalado ni acceso de administrador.
4. Abre **Iniciar.cmd** o **Abrir Selector.vbs**. En la app, pulsa la tarjeta del proyecto y pega la ruta de las fotos de ese PC. Después pulsa **Analizar sesión**.

La primera apertura muestra un proyecto vacío llamado `inicio`. No presupone rutas del equipo original. Las fotos deben estar disponibles localmente; Git no las descarga.

## macOS y Linux

Con Python 3.11–3.13 de 64 bits y Git instalados:

```bash
git clone https://github.com/ronigorodischer/selector-fotos.git
cd selector-fotos
bash Instalar.sh
bash Iniciar.sh
```

Si `python3` apunta a otra versión, instala explícitamente con `python3.11 setup_selector.py`. Después el lanzador usa el Python de `.venv/`. Los scripts y dependencias contemplan estas plataformas; la verificación manual se realizó en Windows x64, pendiente una prueba en un Mac real.

## Abrir y actualizar

Haz doble clic en **Abrir Selector.vbs**. Si Windows bloquea los scripts VBS, utiliza **Iniciar.cmd**. La dirección local es `http://127.0.0.1:8765/`. La app recuerda la última carpeta de este dispositivo. No se expone a otros equipos de la red.

Se guardan las decisiones y la caché en `data/`, dentro de esta carpeta. Conserva esa carpeta para recuperar tu trabajo. Cerrar la pestaña no detiene el servidor: utiliza el botón de encendido al pie de la barra lateral para cerrarlo. Volver a abrir el acceso reutiliza el servidor existente.

Para actualizar una copia clonada, cierra el servidor y ejecuta `git pull --ff-only`. Después vuelve a ejecutar **Instalar.cmd** o `bash Instalar.sh` y abre la app. Git excluye `data/`, `.venv/`, `.deps/`, fotos locales y credenciales; no borres esos datos al actualizar. No coloques fotos dentro de los directorios de código del repositorio.

**Usar otro dispositivo no sincroniza las selecciones automáticamente.** El catálogo guarda rutas absolutas: copiar `data/` a otro sistema o a otra ruta no migra las referencias. Para empezar una sesión allí, copia tus fotos por separado y analiza su carpeta en la nueva instalación. Exporta CSV/JSON en el equipo original como respaldo de decisiones; todavía no existe importación/revinculación automática de catálogos. Conserva el equipo original hasta terminar cualquier migración de trabajo.

## Revisar

- **Vista auto** cambia la distribución según la orientación visible, teniendo en cuenta giros y recortes. En vertical, los controles y las miniaturas pasan al lateral para aprovechar la altura; en horizontal, la tira queda abajo. Puedes elegir **Vertical** u **Horizontal** manualmente. Al comparar varias fotos, el modo automático elige la distribución que les da más espacio.
- `P`: se queda; `X`: se va; `U`: pendiente. El avance automático se puede desactivar a la derecha.
- `← / →`: foto anterior/siguiente; al llegar al extremo de un grupo, continúa en el grupo vecino respetando los filtros. `↑ / ↓`: grupo anterior/siguiente que tenga fotos visibles con los filtros actuales; abre su primera foto visible. `R` y `Shift+R`: girar. `0–5`: estrellas. `Ctrl/Cmd+Z`: deshacer un cambio.
- Casillas sobre miniaturas: seleccionar tomas para comparar. Comparar muestra hasta cuatro. A 100 %, el desplazamiento se sincroniza.
- Ruedita sobre la foto: arriba acerca y abajo aleja, manteniendo el punto bajo el cursor. El zoom va desde encajar en el visor hasta 400 % del tamaño original. Al acercar, arrastra la imagen para desplazarte; **Ajustar** vuelve a encajarla y **100 %** muestra los píxeles del original. Fuera del visor, la ruedita sigue desplazando los paneles normalmente.
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

`requirements.txt` fija las versiones verificadas de NumPy, OpenCV headless, Pillow, rawpy, ExifRead y Send2Trash. La instalación usa un entorno aislado y comprueba una inferencia real del modelo YuNet incluido. [OpenCV headless](https://pypi.org/project/opencv-python-headless/) evita dependencias gráficas innecesarias; [rawpy](https://pypi.org/project/rawpy/) proporciona las bibliotecas RAW para las plataformas compatibles.

Diagnóstico sin conexión y pruebas después de instalar:

```powershell
.venv\Scripts\python.exe setup_selector.py --check
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

En macOS/Linux sustituye `.venv\Scripts\python.exe` por `.venv/bin/python`. Las pruebas crean fotografías de muestra dentro de `data/` y no operan sobre tu sesión. La prueba de papelera utiliza solo un archivo descartable generado.

Modelo de rostros YuNet de OpenCV Zoo: archivo `face_detection_yunet_2026may.onnx`, SHA-256 `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0`. Licencia MIT en `models/YUNET_LICENSE.txt`; fuente: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet.

`validate_session.py` usa una copia aislada del proyecto dentro de `data/`, aplica ajustes de prueba allí y exporta toda la sesión a 1600 px. Verifica JPG, perfil ICC, ZIP y hashes de los originales. No cambia decisiones ni ajustes del proyecto real. Puede tardar varios minutos y conserva la salida para revisarla.

Al migrar desde el piloto 01 se crea `project.before-editing.sqlite` antes de añadir los campos nuevos. Las decisiones se conservan.
