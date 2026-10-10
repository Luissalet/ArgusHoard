# Argus's Hoard

Una **memoria de pantalla** privada y alojada en tu propio ordenador con
Windows: cada pocos segundos Argus captura la pantalla, anota la ventana activa,
descarta las capturas que no han cambiado, pasa OCR a las nuevas y te ofrece una
línea de tiempo, búsqueda de texto completo y tiempo por aplicación. Todo se
guarda en local y se expone a un asistente («Faustus») a través de MCP. Es una
versión transparente y en manos del usuario de la idea de «recordar lo que has
visto»: puedes ver exactamente qué se guarda, pausarlo, excluir aplicaciones,
borrar tramos y limitar el disco que ocupa.

Nada sale del ordenador. No hay nube, ni telemetría, ni más conexiones que
`127.0.0.1`.

## Qué se captura (sed sinceros con vosotros mismos)

Mientras el estado sea **mirando**, cada `interval_s` segundos (5 por defecto):

1. Se lee la ventana activa (título, nombre del proceso, monitor).
2. Si coincide una **exclusión** (nombre de proceso o expresión regular sobre el
   título), no se captura ni se lee nada; solo se cuenta un momento «oculto» en
   ese día.
3. Si no, se captura la pantalla: con `capture_scope: active` (por defecto)
   solo el monitor donde está la ventana activa (el principal si no se sabe);
   con `all`, todos los monitores. Una captura que parece igual a la
   anterior del mismo monitor (misma ventana y menos de `dedupe_threshold`
   celdas cambiadas en una cuadrícula gris de 384×216) **no se guarda**: se
   alarga la hora `until` de la anterior. Así se calculan las duraciones.
4. Las capturas nuevas se guardan en WebP (ancho máximo 1280) más una miniatura
   de 320 px en `data/frames/AAAA/MM/DD/<id>.webp` y entran en la cola de OCR.
   El OCR nunca bloquea la captura; la cola se ve en el estado.
5. El texto y los bloques (cajas, confianza) van a SQLite con un índice FTS5
   (BM25 sobre texto, título de ventana y aplicación).

No se captura nada en **pausa**, en **modo privado**, con la captura
**desactivada** ni cuando coincide una exclusión. Nunca se tocan teclas, audio,
portapapeles ni tráfico de red.

## Controles de privacidad

- **Pausar / reanudar** desde el aviso superior, la API o la herramienta
  `screen_pause`.
- **Modo privado**: un interruptor grande en *Ajustes* (sin atajo de teclado).
  No se captura nada hasta que lo apagues; sobrevive a los reinicios.
- **Exclusiones**: por nombre de proceso (`keepass*`, `banco-app`) o por
  expresión regular sobre el título (`incógnito|private browsing`). Puedes
  comprobar cualquier aplicación o título en Ajustes («¿esta ventana se
  excluiría?»).
- **Retención**: las capturas con más de `retention_days` días (30 por
  defecto) se borran, imágenes y texto, al arrancar y cada 10 minutos.
- **Límite de disco**: si la carpeta de capturas supera `storage_cap_mb` se
  borran primero las más antiguas.
- **Fijar una captura**: en su detalle, «☆ Fijar» la conserva frente a la
  limpieza por antigüedad o espacio. Puedes desfijarla. Un borrado explícito
  del tramo sí la elimina.
- **Borrar un tramo**: `DELETE /api/frames?from&to`, «Borrar este día» en la
  línea de tiempo o la herramienta `screen_delete_range`. Es definitivo.

## Requisitos

- Windows 10/11 (captura y ventana activa). El resto de la cadena también
  funciona en Linux/macOS con el backend falso, para pruebas y demostraciones.
- Python 3.11 o superior (3.13 funciona). Node 22 solo para construir la
  interfaz.
- Basta con la CPU. Con `ocr_backend: auto` el motor es `winocr`
  (Windows.Media.Ocr, unos 150 ms por pantalla 1080p, necesita
  `requirements-windows.txt`) cuando está disponible. Después comparte el OCR
  de Kafka a través del hub de Hoard Link antes de probar `rapidocr` (ONNX en
  CPU) y `tesseract` locales. Evita cargar otro modelo OCR cuando Kafka responde;
  Windows conserva su lectura local rápida. Un motor elegido expresamente
  sigue teniendo prioridad. `family` también se selecciona con `PUT /api/settings`;
  las pantallas solo viajan a ese servicio local, como un PNG temporal que se
  borra enseguida.
  En automático, si el servicio deja de estar disponible puede usar una alternativa
  local y volver a probar Kafka en las siguientes capturas. Un error de autorización
  o de herramienta no cambia de motor silenciosamente.

## Instalación y arranque (Windows)

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\pip install -r requirements-windows.txt   :: opcional: winocr, pywin32
npm install
npm run build                                         :: construye la interfaz en argus\static
venv\Scripts\python scripts\selftest.py               :: una captura real + OCR: imprime texto y tiempos
venv\Scripts\python scripts\launch.py                 :: arranca la app y abre el navegador
```

`python -m argus` arranca el servidor en `http://127.0.0.1:5183` (variables
`ARGUS_PORT`/`PORT`; `PORT_STRICT=1` lo fija, si no se usa el siguiente puerto
libre). Los datos viven en `ARGUS_DATA_DIR` o `<repo>/data` (ignorado por git).

Otras variables: `ARGUS_CAPTURE=auto|mss|fake|none`,
`ARGUS_WINDOW=auto|windows|fake|none`, `ARGUS_AUTOSTART=0` (no arrancar el hilo
de captura), `ARGUS_VISUAL=auto|fake|none`, `ARGUS_VISUAL_THREADS`,
`ARGUS_VISUAL_DUTY` (ver Búsqueda visual).

### Acceso desde el móvil (a través de un túnel)

El servidor escucha en 127.0.0.1 y solo responde a peticiones cuyo `Host` sea `localhost`, `127.0.0.1` o `[::1]`. Para entrar desde el móvil a través de un túnel que ponga la aplicación delante (una red privada, un proxy inverso), indicad los nombres de host adicionales en `ARGUS_ALLOWED_HOSTS`, separados por comas, exactos o `*.sufijo`: `ARGUS_ALLOWED_HOSTS=mi-pc.example,*.ts.net`. Las mayúsculas no importan y una entrada sin puerto vale para cualquiera (escribid `mi-pc.example:8443` para fijar uno); el `Origin` de las llamadas a la API también tiene que corresponder a uno de esos hosts (con cualquier esquema o puerto). Las peticiones *fetch* desde otras webs se siguen rechazando; abrir la aplicación desde otra página (un enlace, un bookmarklet, el menú de compartir) es una navegación normal y funciona.

Una vez abierta a través del túnel, el navegador ofrece instalarla (PWA).

### Piezas comunes

La parte de servidor viene de la biblioteca compartida Hoard Link, copiada en `argus/hoard_link/` (no se edita aquí): guarda de host y origen, manejo de errores, `/api/health`, manifiesto PWA con service worker y SPA, archivos de puerto y de token (el token tiene al menos 32 caracteres), lectura de configuración, el envoltorio de SQLite, el enrutador del catálogo de herramientas y el puente MCP. La búsqueda usa sus reglas de palabras y BM25 (`hoard_link.docs.textsearch`: acentos plegados, palabras de relleno fuera de las consultas de varias palabras, las cortas exactas y las largas como prefijo) y el detector de cambios su hash perceptual (`hoard_link.docs.imaging`). `ARGUS_LOG` ya no se lee: el servidor registra a nivel INFO en la consola y en `data/logs/argus-hoard.log` (rotativo).

Desarrollo: `python scripts/dev.py` lanza uvicorn con `--reload` y el servidor
de Vite (que redirige `/api`).

## Búsqueda visual

Además del texto OCR, Argus puede buscar las capturas por su aspecto
(`gráfica azul`, `blue bar chart`, `código en fondo oscuro`) y encontrar las
pantallas que se parecen a una que ya tenéis. Es opcional y local.

- **Modelo**: CLIP ViT-B/32 multilingüe, 512 dimensiones. La torre de texto es la
  exportación multilingüe de DistilBERT (ONNX int8, unos 135 MB) y la de imagen es
  el modelo de visión ONNX con pesos fp16 (unos 176 MB). En total unos 314 MB de
  descarga (unos 300 MiB en disco) en `data/models/clip-b32-multilingual/`. **No**
  se descarga solo: pulsad *Descargar modelo* en Ajustes o llamad a
  `POST /api/visual/download`. Si cambia el identificador del modelo, se vuelve a
  descargar y a indexar.
- **Sin dependencias nuevas**: usa `onnxruntime`, `numpy`, `Pillow` y `httpx`, que
  Argus ya tiene. El tokenizador WordPiece y la capa de proyección están en
  `argus/visual_model.py`.
- **Solo CPU**. El motor fija `CUDA_VISIBLE_DEVICES=-1` antes de cargar
  onnxruntime y pide el proveedor de CPU, con un hilo (`ARGUS_VISUAL_THREADS`).
  Nunca toca una GPU.
- **Solo las capturas que Argus guarda**, nunca la pantalla en directo. Un hilo en
  segundo plano con la prioridad más baja del sistema toma las capturas más
  recientes que faltan en lotes de 4, descansa tanto como trabajó
  (`ARGUS_VISUAL_DUTY=0.5`) y cede mientras la cola de OCR tenga trabajo. Se puede
  interrumpir y seguir (pregunta a la base de datos qué capturas no tienen vector
  del modelo actual) y descarga el modelo de memoria tras 10 minutos sin uso
  (unos 650 MB residentes en todo el proceso mientras está cargado). Una captura ilegible se salta, no se
  reintenta en bucle.
- **Almacenamiento**: tabla `frame_vectors` en la base de datos de Argus, 512
  valores float16 (1 KB) por captura, con el identificador del modelo. Borrar una
  captura (una a una, por tramo, por retención o por el límite de disco) borra su
  vector en la misma transacción. Los vectores de un modelo anterior se sustituyen
  y nunca se mezclan en una búsqueda.
- **Búsqueda**: `mode=text|visual|both` (por defecto `both`). El modo visual
  convierte la consulta con la torre de texto y puntúa cada vector por coseno (por
  fuerza bruta sobre una matriz float16 en memoria). El modo `both` fusiona ese
  orden con el del OCR por fusión de rangos recíprocos (k=60); un momento hallado
  por las dos vías lleva `via: ["text","visual"]`, `visual_score` y un `score`
  fusionado. Un umbral de relevancia deja fuera el ruido visual de la fusión
  (absoluto 0,20, a menos de 0,05 del mejor y, desde 50 capturas indexadas, media
  más 2 desviaciones típicas). Sin un índice utilizable, `both` responde solo con
  texto y lo dice; `visual` responde 409.
- **Buscar parecidas**: `GET /api/frames/{id}/similar`, el botón *Ver pantallas
  parecidas* en Buscar y *Buscar parecidas* en el visor. Si la captura aún no está
  indexada, la procesa en el momento, y deja fuera su propio momento.
- **Ajuste**: `visual_search` (activado por defecto; solo hace algo si el modelo
  está presente). `GET /api/visual` devuelve el estado: indexadas/total, modelo,
  tamaño en disco, ms por captura y progreso de la descarga.
- **Variables**: `ARGUS_VISUAL=auto|fake|none` (`fake` es un incrustador de
  colores determinista para las pruebas), `ARGUS_VISUAL_THREADS`,
  `ARGUS_VISUAL_DUTY`.

Medido en este PC con el modelo real, un hilo de CPU y capturas de 1280x720: unos
100 ms por captura al indexar (de 91 a 123 ms, igual en lotes de 4), 6 ms para
convertir una consulta, de 8 a 13 ms en una búsqueda HTTP completa y cerca de 1 ms
para puntuar 10 vectores. La fuerza bruta es lineal; un índice de
100.000 capturas es un producto de matrices de 512 columnas, que debería quedar en
decenas de milisegundos, sin medir aquí.

Límites, sin adornos. Con diez capturas sintéticas (gráfica, tarta, factura,
código, hoja de cálculo, terminal, etc.) y quince consultas en inglés y español,
la pantalla correcta salió primera en 13 de 15. CLIP B/32 a 224 px ve la
composición, el color y el tipo de documento, no el texto pequeño: un terminal
oscuro y código oscuro se confunden con facilidad, y una hoja de cálculo descrita
en español quedó tercera (en inglés, `spreadsheet grid`, primera). Las
puntuaciones están comprimidas (0,22 a 0,24 para pantallas sin relación, 0,25 a
0,30 para un acierto): fijaos en el orden, no en el número. Las palabras exactas
que hay en pantalla siguen siendo cosa de la búsqueda OCR; por eso `both` es el
modo por defecto. La imagen se ajusta con bandas (lado largo a 224 px, relleno
gris), que ordenó mejor que deformarla o recortar el centro, y el modelo de
visión con pesos fp16 ordena igual que el fichero fp32 de 335 MB, mientras que
uno int8 reduce el tamaño a la mitad y ordena claramente peor.

## La interfaz

- **Línea de tiempo**: selector de día; el día se agrupa en *sesiones* (una
  misma aplicación y ventana vistas de forma continua: franja horaria, duración,
  número de pantallas, miniaturas); una sesión se despliega con sus capturas y un
  deslizador; una captura se abre en grande con el texto OCR superpuesto y
  seleccionable, anterior/siguiente (flechas del teclado).
- **Buscar**: texto + cómo buscar (texto y aspecto, solo texto, solo aspecto) + rango de fechas + aplicación, con *Ver pantallas parecidas* en cada momento; una fila por momento (las
  pantallas repetidas de una ventana se agrupan, con tira de miniaturas), horas
  como «hoy 17:32–17:41» / «ayer 09:10».
- **Actividad**: tiempo por aplicación (barras), títulos de ventana más
  frecuentes, tabla por día.
- **Ajustes**: modo privado, búsqueda visual (interruptor, descarga del modelo, progreso del índice), captura activada, intervalo, sensibilidad al
  cambio, monitores, motor OCR (con la disponibilidad de cada uno), ancho de
  imagen, retención, límite de disco, exclusiones (añadir, quitar, activar y
  caja de prueba) y una tarjeta de estado (cola, disco, última captura,
  backends, errores).

Un aviso en todas las páginas indica **Argus está mirando / en pausa / modo
privado / captura desactivada**.

## API

Todas las rutas escuchan solo en `127.0.0.1` y rechazan otros hosts u orígenes.

| Ruta | Para qué |
| --- | --- |
| `GET /api/health` | `{service, version, dataDirConfigured}` (sin autenticación) |
| `GET /api/status` | estado, cola, última captura, disco, retención, backends, `capture_scope`, monitores, `idle_since`/`idle_s` (la pantalla activa no cambia desde entonces) |
| `GET/PUT /api/settings` | ajustes (PUT acepta un objeto parcial) |
| `POST /api/pause`, `POST /api/resume`, `POST /api/private` | controles de grabación (`private` alterna; con `{private: bool}` fija) |
| `GET/POST /api/exclusions`, `PATCH/DELETE /api/exclusions/{id}`, `POST /api/exclusions/test` | exclusiones |
| `GET /api/timeline?from&to&app&q&title&limit&cursor&order` | capturas con duración y extracto, paginación por cursor |
| `GET /api/sessions?day` (o `from&to`) `&app` | capturas consecutivas de una misma aplicación y ventana agrupadas en sesiones (inicio, fin, duración, número, miniaturas) |
| `GET /api/frames/{id}` · `/image` · `/thumb` | texto completo + bloques + anterior/siguiente; ficheros WebP |
| `PATCH /api/frames/{id}/pin` | fijar o desfijar con `{ "pinned": true/false }` |
| `GET /api/search?q&from&to&app&limit&mode` | candidatos FTS5 reordenados con BM25 (título 3 / aplicación 2 / texto 1, IDF suavizado para que `rank` sea siempre un negativo real), `snippet()` con marcas `[ ]`; las pantallas casi idénticas de una misma ventana en 10 minutos se agrupan en un *momento* (`first_at`, `last_at`, `count`, `frame_ids`, la mejor primero); `limit` cuenta momentos; `mode=text\|visual\|both` (por defecto `both`) añade el orden visual fusionado por RRF (`via`, `visual_score`, `score`), `both` vuelve al texto si no hay índice utilizable y `visual` responde 409 |
| `GET /api/frames/{id}/similar?limit&from&to&app&same_moment` | momentos que se parecen a esta captura (se procesa en el momento); 409 si la búsqueda visual no está disponible |
| `GET /api/visual`, `POST /api/visual/download`, `POST /api/visual/reindex` | estado de la búsqueda visual (indexadas/total, modelo, tamaño, ms por captura, progreso de descarga), descarga explícita del modelo, vaciar y rehacer el índice |
| `GET /api/apps?from&to` | tiempo por aplicación y títulos más frecuentes |
| `GET /api/days` | días con datos (capturas, momentos ocultos, segundos) |
| `DELETE /api/frames?from&to` | borrar un tramo (definitivo) |
| `GET /api/agent/tools`, `POST /api/agent/call` | catálogo de herramientas y puente MCP (token Bearer) |

`from`/`to` aceptan fechas ISO, `AAAA-MM-DD` (día completo) y expresiones:
`hoy`, `ayer`, `anteayer`, `esta mañana`, `esta tarde`, `anoche`,
`hace 2 horas`, `hace 15 minutos`, `últimos 30 minutos`, `esta semana`,
`la semana pasada`, `ayer a las 9`, y sus equivalentes en inglés.

## Herramientas MCP

El puente (`mcp_server.py`) obtiene la lista de herramientas de la app en
marcha y reenvía cada llamada a `POST /api/agent/call` con el token de
`data/mcp-token`; nunca abre la base de datos.

| Herramienta | Qué hace |
| --- | --- |
| `screen_status` | estado de la grabación, cola, última captura, disco, retención |
| `screen_search` | búsqueda de texto completo con fragmentos, y `mode` text, visual o both para encontrar pantallas por su aspecto; cada resultado es un momento (`first_at`, `last_at`, `count`, `frame_ids`, `via`) |
| `screen_similar` | momentos que se parecen a una captura dada |
| `screen_timeline` | qué había en pantalla y cuándo, con duraciones |
| `screen_frame_text` | texto OCR completo de una captura (bloques opcionales) |
| `screen_pin_frame` | fijar o desfijar una captura para conservarla durante la limpieza automática |
| `screen_recent` | el texto de los últimos N minutos, sin repeticiones, lo más reciente primero |
| `screen_activity` | tiempo por aplicación, ventanas principales, sesiones más largas y una línea de resumen |
| `screen_days` | días con datos |
| `screen_pause` / `screen_resume` | solo cuando el usuario lo pide |
| `screen_delete_range` | borrado definitivo de un tramo (destructiva) |

Conectadlo desde Faustus con `faustus-plugin.json`, o a mano:
`{PYTHON} mcp_server.py` con `ARGUS_URL=http://127.0.0.1:5183` y
`ARGUS_TOKEN_FILE=<repo>/data/mcp-token`.

## Pruebas

```bat
venv\Scripts\python -m pytest -q
```

Cubren la detección de cambios, las exclusiones, el intérprete de expresiones
de tiempo, OCR real sobre imágenes generadas, almacenamiento/FTS/fragmentos,
duraciones de la línea de tiempo, retención y límite de disco, la API con
`TestClient` y el backend falso, la autenticación del puente y una prueba de
extremo a extremo que arranca `python -m argus` en un subproceso y lista las
herramientas a través del puente MCP por stdio.

`tests/test_visual.py` cubre la búsqueda visual con un incrustador falso
determinista (fusión, indexado reanudable, borrado, cambio de modo, cambio de
modelo, la descarga contra un servidor HTTP local, la API y las herramientas del
agente). Una prueba usa el modelo real y está marcada `slow`: se omite si el
modelo no está descargado; apuntad `ARGUS_TEST_MODEL_DATA` a un directorio de
datos que lo tenga.

## Verificación en el ordenador real

`scripts/selftest.py` hace una captura real, lee la ventana activa, ejecuta el
motor OCR e imprime el texto y los tiempos, sin arrancar la app. Podéis pasarle
un motor (`rapidocr`, `winocr`, `tesseract`) para forzarlo, o `--fake` para usar
imágenes generadas. Es lo primero que conviene ejecutar en Windows: los
backends exclusivos de Windows (captura con `mss`, ventana activa con `ctypes`,
`winocr`) no se pueden probar en una máquina Linux sin pantalla.

## Licencia

MIT — ved `LICENSE`.
