# Plan de aplicación personal para seleccionar fotografías

## Objetivo y decisiones acordadas

Crear una aplicación de escritorio para revisar sesiones de personas y eventos más rápido. Cámara inicial: Sony ZV-E10, archivos ARW y JPG. Uso personal, procesamiento local, con posibilidad de incorporar servicios en la nube en el futuro. Primera entrega centrada en selección; después vendrán recorte y LUTs. Las fotos rechazadas se enviarán a la papelera del sistema únicamente tras una confirmación expresa dentro de la aplicación.

El éxito consiste en reducir el tiempo de revisión sin perder tomas valiosas ni confundir archivos asociados con fotografías repetidas. La aplicación recomienda; el fotógrafo conserva el control de cada decisión.

Defaults para los datos todavía no especificados: probar 1.000 y 10.000 tomas; interfaz en español; Windows x64 como primer equipo de prueba y macOS Apple Silicon como segundo destino. La compatibilidad con Mac Intel queda para una entrega posterior. No se presupone GPU dedicada ni un editor concreto. No se implementará sincronización de proyectos entre equipos en la primera versión.

## 1. Experiencia y primera versión

### Importación y organización

- Abrir una carpeta de sesión e incluir sus subcarpetas. Registrar las rutas originales; no copiar toda la sesión ni modificar sus imágenes al importar.
- Una toma puede tener varios archivos: por ejemplo, `DSC01234.ARW` y `DSC01234.JPG`. Mostrarlos como una sola tarjeta con indicador RAW + JPG y permitir elegir qué representación se visualiza.
- Emparejar solamente archivos en la misma carpeta, con el mismo nombre base y metadatos de captura compatibles. Si falta evidencia o hay conflicto, dejarlos separados y permitir vincularlos manualmente. No emparejar por nombre entre carpetas distintas.
- Diferenciar tres conceptos: archivos idénticos, tomas visualmente casi iguales y una escena con variaciones. Una pareja RAW + JPG representa una toma, no dos fotos sobrantes.
- Ordenar escenas por fecha de captura y tomas por tiempo de captura de forma predeterminada. Ofrecer orden por recomendación sin cambiar el orden mientras se está revisando.
- Permitir dividir y unir grupos manualmente, bloquear esas correcciones y ajustar la sensibilidad del agrupamiento.
- Cargar miniaturas y primeras vistas de forma progresiva, mientras continúa el análisis. Mostrar el estado de procesamiento, permitir pausarlo y reanudarlo.

### Pantalla de selección

- Centro: fotografía grande. Abajo: tira de tomas del grupo. Lateral: grupos, filtros, progreso de selección y panel de rostros ampliados.
- Comparación de dos a cuatro tomas, con zoom al 100 % y desplazamiento sincronizado. En tamaños diferentes, sincronizar la región relativa sin presentar escalado interpolado como detalle real.
- Estados explícitos: **Pendiente**, **Se queda**, **Se va**. Todas las tomas empiezan pendientes. Las recomendaciones del análisis no cambian estos estados.
- Atajos: `P` conservar, `X` rechazar, `U` pendiente; flechas para navegar; `1–5` para estrellas; `0` para quitar estrellas; `R` girar 90° a la derecha y `Shift+R` a la izquierda; `Ctrl/Cmd+Z` para deshacer decisiones y ajustes.
- El botón de cruz marca «Se va». Un botón separado «Enviar rechazadas a la papelera» inicia la revisión y confirmación del lote. No asociar una tecla de navegación a la operación de papelera.
- Filtros por estado, estrellas, advertencia de enfoque y grupos con pendientes. Permitir conservar varias tomas de un grupo y conservar una foto aunque reciba una mala recomendación.
- Guardar automáticamente decisiones, estrellas, agrupaciones y rotación; recuperar el proyecto y la posición de revisión al abrirlo otra vez.
- Rotación de visualización no destructiva desde la primera entrega. Se combina con la orientación EXIF y se guarda en el proyecto; no se reescribe el ARW ni el JPG original.

### Salida inicial

- Exportar un manifiesto JSON y CSV con rutas, representación RAW/JPG, estado, estrellas y rotación.
- Permitir copiar los archivos de las tomas conservadas a una carpeta de salida, preservando la estructura relativa y sin sobrescribir archivos existentes.
- Una copia de originales no incorpora visualmente la rotación guardada en el proyecto. La exportación renderizada con ajustes pertenece a la segunda entrega.
- Posponer la integración específica con Lightroom o Capture One hasta conocer el editor utilizado. La primera versión no modifica catálogos ni XMP existentes.

## 2. Análisis fotográfico y herramientas

### Tecnología propuesta

| Componente | Elección | Propósito |
|---|---|---|
| Aplicación | Electron + React + TypeScript | Interfaz y acceso de escritorio en Windows y Mac |
| Motor de imágenes | Python 3.11, en proceso separado | Ejecutar análisis sin bloquear la interfaz |
| Lectura de RAW | rawpy / LibRaw | Extraer previsualizaciones y revelar ARW cuando haga falta |
| Metadatos | ExifTool empaquetado | Fecha, cámara, exposición y orientación |
| Procesamiento | OpenCV, NumPy y Pillow | Similitud, nitidez, normalización y caché |
| Rostros y ojos | MediaPipe Face Landmarker | Localizar rostros y producir señales orientativas de parpadeo |
| Persistencia | SQLite | Proyectos, archivos, grupos, decisiones y trabajos |
| Empaquetado | electron-builder y PyInstaller | Incluir el motor para no exigir Python al usuario |

Las versiones de las dependencias se fijarán en la primera prueba técnica. Se conservarán los avisos de licencia y las licencias de los modelos empaquetados. No se entrenará un modelo propio para el primer lanzamiento.

### Detección de tomas similares

1. Leer orientación y metadatos y crear una representación de análisis consistente por toma.
2. Encontrar copias exactas de archivos mediante tamaño y SHA-256 calculado en segundo plano. No asumir igualdad por nombre ni eliminar copias automáticamente.
3. Para tomas casi iguales, utilizar pHash como filtro rápido y verificación visual con descriptores locales y similitud estructural cuando el alineamiento sea fiable. Buscar candidatos por cercanía temporal y también por cercanía de hash en el proyecto, sin comparar todos los pares de imágenes a resolución completa.
4. Para escenas, combinar cercanía temporal, similitud visual y distribución de rostros. La semejanza del fondo por sí sola no basta para afirmar que dos tomas son intercambiables.
5. Limitar la distancia visual respecto de la toma representativa del grupo para evitar que una cadena de pequeñas semejanzas termine juntando escenas distintas. Respetar siempre las divisiones y uniones manuales.

Los umbrales se calibrarán con sesiones etiquetadas y se guardarán con versión. El primer lanzamiento usará estas señales ligeras; incorporar embeddings DINOv2 Small será una mejora posterior si la evaluación muestra errores de similitud que lo justifiquen. No es un requisito inicial ni supone llamar a un modelo de lenguaje por fotografía.

### Enfoque, ojos y recomendación

- Medir detalle en varias escalas mediante gradientes y Laplaciano, atendiendo al ruido, al tamaño de la región y a la exposición. No usar únicamente la varianza de Laplaciano de toda la imagen como veredicto de enfoque.
- En retratos, priorizar regiones de rostro y ojos frente al fondo. Permitir elegir el rostro principal y marcar varios rostros importantes en fotos de grupo.
- Si no hay rostro fiable, permitir seleccionar la región del sujeto manualmente. Mostrar «No evaluable» cuando la imagen o la región no aporten información suficiente.
- Usar MediaPipe como fuente de señales de párpados, no como certeza sobre intención o calidad. Rostros pequeños, perfiles, gafas y oclusiones pueden producir una valoración incierta.
- Presentar una puntuación de nitidez relativa dentro del grupo y advertencias separadas sobre ojos y exposición. La puntuación no equivale a probabilidad ni a una nota artística universal.
- Recomendar candidatas dentro del grupo con explicaciones como «más detalle en el rostro principal» o «posibles ojos cerrados». Con evidencia débil, mostrar un empate o pedir revisión visual.
- Comparar señales sobre versiones de análisis equivalentes. Una miniatura pequeña no permite afirmar nitidez fina; generar una vista de mayor resolución cuando sea necesario y distinguir resultados provisionales de confirmados.
- Exposición y recorte de altas luces se valoran sobre la representación analizada; no presentarlos como medición de recuperabilidad del sensor RAW.

El encuadre tendrá asistencia en la segunda entrega: guías, horizonte y posibles cortes de rostro cerca de los bordes. No se prometerá una clasificación objetiva de la composición ni se utilizará para rechazar automáticamente fotografías.

## 3. Datos, rendimiento y papelera

### Organización interna e interfaces

- Guardar proyecto y caché en una ubicación local elegida por el usuario. La caché es regenerable; las decisiones se guardan en SQLite y se incluyen en la copia de seguridad del proyecto.
- Identificadores estables para proyecto, toma, archivo y grupo. Separar estado humano, resultados del análisis y ajustes no destructivos. Cada resultado registra versión del algoritmo y representación analizada.
- Un único servicio Python administra las escrituras de SQLite. Electron se comunica con él por mensajes JSON de línea mediante stdin/stdout; los logs van por stderr. Cada petición lleva identificador y cada trabajo produce eventos de progreso y resultado.
- Comandos mínimos: abrir/importar proyecto, listar grupos por páginas, obtener vista previa, analizar, cancelar, cambiar estado, puntuar, girar, dividir/unir grupo, exportar y preparar/registrar operaciones de papelera.
- El proceso principal de Electron gestiona diálogos y `shell.trashItem`. La interfaz recibe únicamente operaciones autorizadas y archivos del proyecto; se mantiene aislada del acceso directo al sistema.
- Interfaz interna `AnalysisProvider`: recibe referencias a vistas de análisis y devuelve señales, confianza y versión. Implementar solo el proveedor local. Un futuro proveedor de nube será optativo, con consentimiento y estimación de costo antes de enviar imágenes.
- No subir fotos ni metadatos, ni incluir telemetría remota, en la primera versión.

### Rendimiento

- Preferir JPG asociado o previsualización ARW incrustada para comenzar a revisar. Identificar la representación en pantalla. Revelar el RAW cuando no exista una vista utilizable o se necesite comprobar detalle real.
- Priorizar la toma abierta y sus vecinas. Dos trabajos pesados simultáneos como valor inicial, con límites de memoria y sin cargar una sesión completa en RAM.
- Lista virtualizada, miniaturas en disco, caché en memoria acotada y lectura paginada. Evitar recalcular análisis válido al reabrir una sesión.
- Invalidar caché si cambia el archivo de origen; no perder decisiones humanas por cambiar de algoritmo. Si cambia un original, pedir revisarlo antes de cualquier operación de papelera.
- Si un disco se desconecta o un archivo falla, conservar decisiones y continuar con los demás. Permitir volver a localizar la carpeta y verificar sus archivos.
- Un solo proceso de aplicación puede modificar cada proyecto a la vez. Guardar y restaurar una copia previa antes de migraciones del esquema de datos.

### Envío a la papelera

1. Preparar una lista inmutable de archivos de las tomas marcadas «Se va». Mostrar número de tomas, número de ARW/JPG, tamaño y rutas; el alcance será todo el proyecto y se indicará expresamente, aunque haya filtros activos.
2. RAW y JPG vinculados se incluyen juntos. La revisión permite quitar una toma completa del lote. Desvincular los archivos antes si se quiere conservar uno de ellos.
3. Después de la confirmación, volver a verificar estado, identidad y ubicación de cada archivo. Excluir enlaces simbólicos y rutas que salgan de las carpetas de origen autorizadas.
4. Registrar cada operación antes de llamar a la papelera y guardar su resultado individual. No afirmar que un lote RAW + JPG es atómico: si falla un archivo, mostrar qué parte se movió y cuál sigue en origen.
5. Si la papelera no está disponible, detener esa operación y mostrar el error. Nunca sustituirla por eliminación permanente. No mover automáticamente XMP existentes ni archivos ajenos a la toma.
6. Tras un cierre inesperado, reconciliar el registro con el estado de los archivos sin repetir operaciones de resultado incierto. Un archivo ausente no prueba por sí solo que esté en la papelera.

Deshacer decisiones funciona antes del envío. Después, la recuperación corresponde a la papelera de Windows o macOS; no se promete una restauración automática desde la aplicación. La aplicación nunca vaciará la papelera.

## 4. Etapas y pruebas que haremos juntos

| Etapa | Entregable | Criterio para avanzar |
|---|---|---|
| 0. Prueba técnica | Leer pares ARW/JPG, orientación, vistas y rostros de una muestra | Los archivos reales de la ZV-E10 abren y el análisis corre localmente |
| 1. Selección manual | Ventana de escritorio, parejas, grupos manuales, estados, comparación, rotación y guardado | Completar una revisión y recuperarla al reiniciar |
| 2. Selección asistida | Grupos automáticos, enfoque, ojos y recomendaciones explicadas | Superar la evaluación de precisión y rapidez |
| 3. Primera versión usable | Papelera, exportación, manejo de fallos e instalador Windows | Pasar pruebas con copias de una sesión completa |
| 4. Portabilidad | Motor e instalador macOS Apple Silicon | Repetir el recorrido completo en un Mac real |
| 5. Reencuadre y color | Recorte, enderezado, LUTs y exportación renderizada | Las vistas y los archivos exportados coinciden |

Las etapas 0–3 forman el primer piloto de selección. El código se organiza desde el inicio para ambos sistemas. Compilar y probar Mac requiere un Mac o un ejecutor macOS; no se considerará verificado desde Windows. Firma y notarización para distribución pública quedan fuera del piloto personal.

### Evaluación conjunta

- Empezar con copias de 200–500 tomas reales que incluyan ráfagas, parejas RAW/JPG, fotos verticales, desenfoque, movimiento intencional, bokeh, ruido, grupos y ojos cerrados.
- Tú identificas grupos y candidatas preferidas. Separar una sesión para calibración y otra para evaluación; si al principio solo hay una, dividir por secuencias completas y considerar las métricas preliminares.
- Objetivos iniciales de calidad: al menos 95 % de precisión en agrupación de casi duplicadas y 80 % de recuperación sobre pares etiquetados; incluir una candidata que conservarías entre las tres primeras en al menos 90 % de grupos evaluables. Medir por separado escenas, casi duplicadas y advertencias de enfoque.
- Incluir positivos difíciles y negativos con mismo fondo y diferentes personas. No mejorar la precisión dejando casi todo sin agrupar; registrar siempre cobertura y recuperación.
- Comparar tiempo, errores y fotografías conservadas en dos conjuntos comparables, alternando revisión manual y asistida para reducir el efecto de memoria. Meta: reducir al menos 30 % el tiempo sin perder ninguna toma imprescindible que hayas señalado.
- Después probar 1.000 y 10.000 tomas. Objetivos provisionales en SSD local: primera vista utilizable en 5 segundos y cambio entre vistas precargadas con latencia p95 inferior a 150 ms. Registrar equipo, tamaño de sesión, RAM máxima y duración del análisis; no prometer esos tiempos en cualquier notebook.
- Probar papelera con archivos temporales: cancelar confirmación, pareja parcialmente fallida, archivo bloqueado, disco desconectado, falta de permisos, cambio de estado durante preparación y cierre entre operación y registro. Verificar los archivos presentes en la papelera de cada sistema.
- Verificar reinicio durante análisis, archivos corruptos, EXIF ausente, nombres repetidos entre carpetas, orientación EXIF reflejada y rotaciones sucesivas. Comprobar que una nueva ejecución del análisis no cambia decisiones ni grupos corregidos.
- Probar exportación sin sobrescrituras y comparar hashes de originales antes y después de la revisión. Las pruebas destructivas se hacen con copias, nunca con la única copia de una sesión.

Las métricas anteriores son objetivos de aceptación propuestos; todavía no son resultados medidos. Si una señal no alcanza su objetivo, permanecerá como aviso experimental y no se usará para clasificar candidatas.

## 5. Segunda entrega: reencuadre y LUTs

- Recorte libre y proporciones 3:2, 4:5, 1:1 y 9:16, reversibles; alternar orientación horizontal/vertical del recorte sin girar artificialmente al sujeto.
- Enderezado y rotación de 90° como operaciones distintas. Guardar coordenadas normalizadas y una secuencia de transformaciones definida para que zoom, recorte y exportación coincidan.
- Aplicar ajustes a una toma o a una selección explícita, con vista previa y deshacer. No copiar ciegamente el mismo rectángulo entre imágenes con orientaciones distintas.
- Importar LUTs 3D `.cube` concebidos para entrada y salida sRGB, con intensidad y comparación antes/después. No aceptar automáticamente LUTs Log/HLG como si fueran compatibles con un JPG de cámara.
- Usar una conversión de color consistente en vista y exportación. Un LUT no equivale a un preset de revelado RAW ni recupera información perdida en una previsualización.
- Exportar JPG sRGB con recorte, rotación y look aplicados, preservando originales. La integración por XMP se diseñará y verificará contra el editor que realmente utilices; no se promete trasladar un LUT arbitrario como preset editable.

## Modelo de desarrollo y consumo

Recomendación principal: **GPT-6.1 Sol con razonamiento medio** para construir la base, conectar el análisis, revisar el manejo de archivos y resolver fallos entre sistemas. Usar **GPT-6 Luna con esfuerzo bajo o medio** para tareas acotadas, textos, estilos y arreglos pequeños a partir de este plan. Reservar aumentos de razonamiento para problemas concretos; Astra no es necesario como modelo habitual.

Mantener entregas pequeñas y verificables, con una tarea y criterio de aceptación por cambio. El motor fotográfico usa bibliotecas y modelos locales: no consume créditos de OpenAI por cada foto. Las descargas iniciales de dependencias/modelos requieren conexión; el trabajo posterior debe funcionar sin conexión.

No se estima un total de créditos todavía: depende de iteraciones, errores y del alcance que se añada. La tarifa publicada distingue tokens de entrada, caché y salida; una diferencia por token no garantiza la misma diferencia en costo por tarea terminada.

## Referencias verificadas el 25 de octubre de 2026

- [Sony ZV-E10: especificaciones y formato ARW](https://helpguide.sony.net/ilc/2070/v1/en/contents/TP1000201578.html).
- [LibRaw: cámaras compatibles](https://www.libraw.org/supported-cameras). La compatibilidad debe comprobarse también en la compilación de rawpy empaquetada.
- [rawpy: extracción de previsualizaciones y revelado](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html).
- [MediaPipe Face Landmarker para Python](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python). Su documentación acredita salidas faciales; su eficacia para selección fotográfica debe evaluarse con nuestras imágenes.
- [Electron: operaciones con la papelera](https://www.electronjs.org/docs/latest/api/shell).
- [electron-builder: compilaciones para distintos sistemas](https://www.electron.build/docs/features/multi-platform-build/).
- [Narrative: recorrido de selección](https://help.narrative.so/en/articles/11069214-narrative-quickstart-tutorial) y [recorte](https://help.narrative.so/en/articles/7337379-crop-and-level-your-images-in-narrative), como referencia funcional.
- [OpenAI: selección de modelos](https://learn.chatgpt.com/docs/model-selection) y [precios y créditos](https://learn.chatgpt.com/docs/pricing).

Estado actualizado: piloto local de selección implementado y probado con 266 JPG de Halloween; recorte, enderezado, LUTs sRGB y exportación JPG/ZIP implementados en el piloto 02. Ver REPORTE_PRUEBA.md y REPORTE_EDICION.md. Pendientes: validación humana de calidad y ahorro de tiempo, RAW real, macOS/instaladores, ojos cerrados e integración con el editor utilizado.
