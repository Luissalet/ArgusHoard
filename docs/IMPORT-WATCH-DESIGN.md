---
name: "Argus's Hoard — carpetas automáticas"
description: "Referencia del bloque de observación de carpetas en Importar capturas."
colors:
  accent: "#8f84f4"
  accent-strong: "#b1a9f7"
  accent-ink: "#13131b"
  deep: "#14141d"
  sunken: "#100f17"
  surface: "#1b1a25"
  elevated: "#252431"
  border: "#353444"
  border-hover: "#58566c"
  text: "#e2e1ec"
  text-muted: "#b5b4be"
  danger-ink: "#ee8b80"
typography:
  headline:
    fontFamily: "'Cinzel', 'Iowan Old Style', Charter, Georgia, 'Liberation Serif', 'Noto Serif', 'Times New Roman', serif"
    fontSize: "30px"
    fontWeight: 700
    letterSpacing: "-0.015em"
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "14px"
    lineHeight: 1.65
  button:
    fontSize: "13px"
    fontWeight: 600
    lineHeight: "18px"
  label:
    fontSize: "12px"
    fontWeight: 600
  help:
    fontSize: "12px"
rounded:
  control: "8px"
  card: "10px"
spacing:
  control-gap: "8px"
  section-gap: "12px"
  section-margin: "24px"
  button-padding: "8px 15px"
  field-padding: "8px 11px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "{spacing.button-padding}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "{spacing.button-padding}"
  folder-field:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "{spacing.field-padding}"
    width: "100%"
  status:
    textColor: "{colors.text-muted}"
    typography: "{typography.help}"
  capture-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "8px"
  nav-active:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 13px"
---

# Design System: Argus — carpetas automáticas

## Overview

**Creative North Star: «Memoria a la vista», identidad existente.** Modo **Operate**: guardar carpetas de capturas y consultar su incorporación a la biblioteca existente. El bloque amplía Importar capturas y conserva la navegación, el aviso general de estado, la importación puntual, la biblioteca y el visor OCR.

Referencia acotada a `client/src/pages/Importar.jsx`, `index.css` y el selector Argus de `hoard-theme.css`, fuente **d6262016147ee57356a30ac9847366206e784e8e**, entrega **481, revisión 1**, leída antes de documentar. El `DESIGN.md` raíz todavía describe el anterior tema claro; `docs/SCREEN_IMPORT-DESIGN.md` ya registra el tema oscuro real. Se conserva ambos archivos y se documenta esta ampliación por separado: esta nota no sustituye la identidad de otras páginas ni afirma que la entrega esté integrada o activa en Main.

Las capturas del autor, vistas en este pase documental, muestran escritorio y móvil con una carpeta guardada, recursión activada y biblioteca existente. Evidencia: `D:/LocalAI/research-inbox/referencias-ampliacion-20261013/screens/argus-watch-desktop.png` y `argus-watch-mobile.png`. No se abrió navegador, servidor o modelo para redactar esta referencia.

## Colors

### Primary

El violeta claro del tema Argus identifica la selección y los controles principales anteriores. «Guardar carpetas» y «Comprobar ahora» reutilizan los botones secundarios existentes; la nueva sección no añade un color de observación distinto.

### Neutral

El fondo profundo sostiene la página; los campos utilizan la superficie hundida, y los botones y tarjetas la superficie normal. El elevado señala hover y navegación activa. Ayudas y estado usan texto secundario. Los errores se presentan con el tratamiento previo y texto explícito.

**The Estado escrito Rule.** Carpetas guardadas, modo privado, última comprobación, espera y errores se describen con texto; el color no representa por sí solo el estado.

## Typography

La marca y el título principal conservan la serif de la familia; formulario, ayuda y estado utilizan su sans compartida. Los tokens recogen las declaraciones CSS, sin certificar qué fuente o fallback resolvió un equipo. El encabezado «Carpetas automáticas» es texto de sección seminegrita; no introduce otra escala ni estilo de marca.

Ayuda y estado permanecen en el nivel de metadatos. Las rutas usan el campo de texto existente, sin imponer una fuente monoespaciada. La fecha visible de «Última comprobación» corresponde a la observación del servicio; no reemplaza la fecha del archivo de cada captura.

## Layout

La secuencia es importación puntual, ayuda/resultado, carpetas automáticas y biblioteca. La nueva sección comparte el ancho máximo de 48rem con el formulario anterior: título, explicación, campo de dos filas, recursión, acciones y estado. Los espacios de sección y entre controles proceden de las utilidades actuales.

Desde 768px el shell conserva columna lateral de 220px, marca de 64px y margen de contenido de 40px. Por debajo, la navegación pasa a barra horizontal desplazable y el contenido usa margen de 16px. La sección permanece en una columna; las dos acciones permiten ajuste en varias filas. Las rutas y mensajes largos pueden partirse. La biblioteca conserva su cuadrícula de 1/2/3/4 columnas en base/640/1024/1280px y sus miniaturas completas con `object-contain`.

La captura móvil muestra texto y rutas ajustados, checkbox y ambas acciones accesibles visualmente. No se infiere de la imagen una certificación universal de ausencia de overflow, teclado o lector de pantalla.

## Elevation & Depth

El bloque nuevo permanece plano sobre el fondo de página. Campo, botones y tarjetas se distinguen por superficies y bordes; no se añaden paneles, sombras ni animaciones. Las transiciones existentes de controles duran 0,16s; la regla global de movimiento reducido las elimina. Las sombras previas del diálogo y aviso flotante no pertenecen a este bloque.

## Shapes

Campo y botones conservan radios de control; las tarjetas mantienen el radio mayor. Los checkboxes son controles nativos: el bloque no define `accent-color` propio y su aspecto depende del navegador. No se sustituyen por interruptores decorativos.

## Components

### Campo de carpetas y recursión

«Carpetas de capturas, una por línea» es una etiqueta envolvente de textarea de dos filas, sin corrector ortográfico. «Observar también subcarpetas» es un checkbox nativo independiente de «Incluir subcarpetas» de la importación puntual. El servicio normaliza y persiste las carpetas; su configuración inicial vacía conserva el comportamiento anterior.

`load()` hidrata el borrador una sola vez mediante `watchHydrated`. «Actualizar» y el refresco del copilot consultan configuración/estado y biblioteca sin reescribir el texto o la recursión que la persona está editando. El contexto del copilot distingue carpetas guardadas y borrador. La persistencia del borrador durante esta instancia de página no equivale a persistencia de texto sin guardar tras recargarla.

### Guardar y comprobar

«Guardar carpetas» persiste las rutas y la recursión del borrador. Guardar una lista vacía detiene la observación y conserva las capturas previas. «Comprobar ahora» pide un escaneo de la configuración **ya guardada**, no guarda implícitamente el borrador. Ambos controles se deshabilitan durante una operación; comprobar también requiere carpetas guardadas, y guardar requiere estado cargado.

El foco genérico de controles usa contorno de 2px con separación de 3px. Los campos terminan usando borde violeta al enfocar y `outline: none`; no atribuirles el contorno del botón. El código aporta etiquetas y `aria-labelledby` a la sección, `role="status"` al estado y `role="alert"` al error. Este pase documental no ejecuta una auditoría de teclado o contraste.

### Estado de observación

Se muestran número de carpetas guardadas o configuración vacía, modo privado cuando procede, instante de última comprobación, importadas de esa comprobación, esperando estabilidad y errores por fuente. Los contadores de la última comprobación no son el total histórico de biblioteca ni la cantidad de texto OCR ya disponible. La interfaz obtiene estos datos al cargar, guardar, comprobar o actualizar: el hilo del servicio observa en segundo plano, pero esta página no añade un sondeo continuo de estado.

La cadencia del servicio es de cinco segundos y también admite comprobación manual. «Permanece igual en dos comprobaciones» significa **misma fecha de modificación en nanosegundos y mismo tamaño** en dos observaciones del archivo; no es una prueba de escritura atómica ni un mínimo garantizado de diez segundos. Tampoco detecta bytes cambiados conservando exactamente tamaño y mtime. Tras la importación se comprueba de nuevo la firma para no marcar como resuelta una versión que haya cambiado entretanto.

El modo privado evita nuevas observaciones/importaciones al comprobarlo y se vuelve a consultar entre archivos. No se promete cancelación atómica de una importación ya iniciada. Pausar o desactivar la grabación de pantalla no detiene por sí solo las carpetas guardadas; son estados distintos. Errores o desapariciones no borran capturas anteriores. El mismo importador conserva los originales y evita duplicados por fuente/SHA; el OCR sigue en segundo plano. La observación de carpetas no es grabación de pantalla ni aporta tiempo de actividad observada.

### Biblioteca y evidencia

Las nuevas capturas aparecen en la misma biblioteca y visor, con procedencia, fecha de archivo, estado OCR y extracto. Las funciones anteriores, incluida la importación manual, siguen visibles. El servicio también se expone por API/MCP ordinarios propios: no depende de un ejecutable o servidor del proyecto de referencia.

El autor aporta suite de **150 pruebas aprobadas y una omitida**, MCP de **16 herramientas** y OCR WinOCR CPU real en QA aislada; las pruebas y sus resultados pertenecen al autor, no a este documentador. Recibos: `D:/LocalAI/research-inbox/referencias-ampliacion-20261013/SUBMISSION-ARGUS-WATCH-R1.md`, `argus-watch-suite-count.log` y `argus-watch-qa/mcp-receipt.json`. La revisión funcional y el dictamen de acabado corresponden a los revisores independientes de 481. Esta referencia no emite un voto de aprobación del código, no certifica modelos ni afirma activación en producción.

## Do's and Don'ts

### Do:

- **Do** conservar el diseño oscuro y los controles de importación y biblioteca existentes.
- **Do** distinguir el borrador, la configuración guardada y la última observación.
- **Do** mantener errores y estado escritos, rutas ajustables y acciones que pueden envolver.
- **Do** conservar historial, originales y procedencia al detener o cambiar carpetas.

### Don't:

- **Don't** atribuir tiempo observado en pantalla a archivos importados.
- **Don't** presentar tamaño/mtime estable como garantía de escritura atómica o plazo exacto.
- **Don't** recuperar los tokens claros del `DESIGN.md` raíz como autoridad de esta sección.
- **Don't** afirmar sondeo continuo del estado de la página, cancelación instantánea o activación en Main sin prueba.
- **Don't** confundir lectura de recibos del autor con ejecución independiente de tests, MCP o navegador.
