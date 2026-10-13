---
name: "Argus's Hoard — capturas importadas"
description: "Importación, búsqueda y lectura de capturas guardadas."
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
  text-dim: "#9c9ba6"
  warning-bg: "rgba(212,168,67,.14)"
  warning-ink: "#e0bb62"
  danger-bg: "rgba(196,70,58,.16)"
  danger-ink: "#ee8b80"
  highlight: "rgba(212,168,67,.35)"
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
  small: "6px"
  control: "8px"
  panel: "10px"
  dialog: "12px"
spacing:
  control-gap: "8px"
  control-padding: "8px 15px"
  field-padding: "8px 11px"
  panel-padding: "20px"
  page-mobile: "16px"
  page-desktop: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "{spacing.control-padding}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "{spacing.control-padding}"
  button-danger:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "{spacing.control-padding}"
  field:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "{spacing.field-padding}"
    width: "100%"
  nav-active:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 13px"
  chip-warning:
    backgroundColor: "{colors.warning-bg}"
    textColor: "{colors.warning-ink}"
    rounded: "{rounded.small}"
    padding: "2px 6px"
  frame-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "8px"
  ocr-header:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    padding: "8px 16px"
  provenance:
    textColor: "{colors.text-muted}"
    typography: "{typography.help}"
---

# Design System: Argus's Hoard — capturas importadas

## Overview

**Creative North Star: "Memoria a la vista"**

La interfaz existente usa superficies oscuras violetas, títulos serif y controles sans. Las imágenes y el texto reconocido llevan el contenido; el acento señala acciones y selección. Esta nota describe ese código y su entrega aprobada, sin proponer una identidad nueva.

**Key Characteristics:**

- Original reconocible y OCR seleccionable.
- Procedencia y base de fecha explícitas.
- Estado de captura visible en todas las páginas.
- Controles del detalle que se ajustan al ancho disponible.

**Superficie y modo:** Operate; `#/importar`, resultados de `#/buscar` y visor de captura. El éxito consiste en importar imágenes existentes, leer su OCR y recuperarlas mediante búsqueda sin atribuirles actividad observada.

**Origen fechado:** 13-10-2026; tarea Ágora #445, entrega R2 aprobada; fuente `7383d70148f2e79acbe2bd0ab531feb892ed11f6` en `D:/LocalAI/candidates/argus-import445-referencias-20261013`, sobre `bd01717522049fa1aa4565335276b143dec94a93` y `20997d42831e8d3346145c1f4d419e382b6685a9`. Tokens: `client/src/hoard-theme.css`, bloque `html[data-hoard-app="argus"]`; reglas finales: `client/src/index.css`. Componentes: `App.jsx`, `pages/Importar.jsx`, `pages/Buscar.jsx`, `components/FrameViewer.jsx` y `components/ui.jsx`.

**Persistencia:** documento de superficie para integración documental posterior, con sidecar schemaVersion 2. El `DESIGN.md` raíz antiguo describe un tema claro y `PRODUCT.md` falta; esa deuda previa se registra, sin sobrescribir ninguno. Las rampas del sidecar son muestras sintetizadas para el panel, no nuevos tokens del producto.

## Colors

### Primary

El violeta claro (`accent`) identifica Elegir imágenes, Buscar y selección; `accent-strong` refuerza el hover. Los botones principales usan tinta oscura (`accent-ink`), tal como el tema de Argus.

### Neutral

El fondo profundo sostiene la página, la superficie separa navegación y tarjetas, y el tono elevado señala hover y selección. Los campos usan el tono hundido. Texto principal, ayudas y metadatos mantienen tres niveles; las líneas separan regiones sin añadir sombra a las tarjetas.

Los estados OCR pendientes usan ocre; errores y borrado conservan el rojo del producto. Las coincidencias de búsqueda se resaltan con `highlight`.

**The Estado escrito Rule.** Cada estado se comunica con texto; el color solo lo refuerza.

## Typography

Los títulos de página y marca conservan la familia serif compartida. El cuerpo, formularios y OCR del visor usan la familia sans compartida; el bloque OCR declara `fontFamily: inherit`, aunque se presenta dentro de `pre`. No afirmar que ese texto usa monoespaciada.

Título de página (30px, peso 700); marca (15px, peso 700); cuerpo (14px, interlineado 1,65); botones (13px, peso 600); etiquetas y ayudas (12px). Horas y contadores usan cifras tabulares. La nota registra stacks CSS, sin certificar qué fallback resolvió cada equipo.

## Layout

Desde 768px la navegación ocupa una columna de 220px, con fila de marca de 64px. El contenido tiene mínimo cero y margen lateral de 40px. En móvil el margen es 16px y la navegación se desplaza horizontalmente; las secciones existentes siguen disponibles.

Importación: selector de imágenes, formulario de rutas con ayuda, resultado y biblioteca. El formulario tiene ancho máximo 48rem; la biblioteca pasa por 1/2/3/4 columnas en los cortes base/640/1024/1280px. Las miniaturas importadas conservan su proporción mediante `object-contain`; no imponerles la miniatura 16:9 recortada que usa la búsqueda.

El diálogo mide como máximo 1200px, limitado por `calc(100vw - 24px)` y `calc(100dvh - 24px)`. En escritorio separa imagen y panel OCR de 320px; en móvil apila ambos. Cabecera, acciones y barra OCR permiten varias filas. R2 limita la decoración de marca a `aside.app-sidebar`: un `aside` del visor no recibe el fondo ni tamaño del emblema de navegación.

## Elevation & Depth

Superficies planas y bordes. Diálogo y aviso flotante conservan la sombra compartida; el diálogo oscurece el fondo. La selección de una tarjeta usa borde y contorno violeta. No añadir profundidad a la biblioteca.

Transiciones de controles (0,16s); el aviso de captura activa conserva el pulso existente (2,4s). La regla global de movimiento reducido elimina animaciones y transiciones. Esto describe el código; no certifica una prueba manual de ese ajuste.

## Shapes

Esquinas de control (8px), tarjetas/paneles (10px), chips (6px) y diálogo (12px). Contornos OCR visibles solo al pedir «Ver cajas» o al pasar el puntero; el texto transparente permanece seleccionable sobre la imagen.

## Components

### Importación y campos

«Elegir imágenes» admite PNG, JPEG, WebP y BMP mediante selector nativo múltiple. Las rutas se introducen una por línea; «Incluir subcarpetas» es opcional. «Importar rutas» se deshabilita con entrada vacía o durante el trabajo. El resultado distingue importadas, duplicadas, cola OCR y errores por fuente; un fallo parcial no borra los éxitos. El OCR continúa en segundo plano y «Actualizar» recarga el listado; «Cargar más» conserva lo ya cargado. No se entrega vigilancia continua de carpetas.

### Biblioteca y procedencia

Cada tarjeta abre el visor y muestra nombre, fecha, estado OCR y extracto o causa del vacío. Las importadas se fijan al entrar; «Fijar/Fijada» sigue permitiendo cambiarlo. La fuente y su SHA identifican duplicados y conservan los originales; bytes nuevos producen otra versión. La fecha por defecto es la modificación del archivo; MCP puede proporcionar otra. El visor distingue «fecha del archivo» y «fecha indicada».

**The Procedencia Rule.** Una imagen importada se etiqueta «Archivo importado» y nunca se presenta como tiempo observado en pantalla.

### Búsqueda y visor OCR

Los resultados conservan filtros, agrupación y modos de texto/aspecto existentes; una importada participa en búsqueda y lectura, con procedencia. Actividad, sesiones, recientes y timeline observado permanecen separados de las importaciones. El detalle conserva original completo, OCR, contador de bloques, Copiar, Ver/Ocultar cajas, Fijar, Anterior, Siguiente, Buscar parecidas y Cerrar, según disponibilidad. Buscar parecidas sigue ligado a la búsqueda visual activa; esta entrega no certifica su calidad con un modelo.

Botones con altura mínima 38px, o 30px en variante pequeña; deshabilitados a 0,45 de opacidad. El código incluye foco visible de 2px para controles y borde de foco para campos. Se mantienen etiquetas, nombres accesibles y `aria-pressed` para fijación. Teclado completo y contraste no se han probado en este pase documental.

### Evidencia y alcance

Entrega del autor: 144 pruebas aprobadas y 1 omitida en suite, 25 del área, 13 de contexto JS y build; MCP nativo de 14 herramientas, con `screen_import` y `screen_import_list`, lectura/búsqueda WinOCR CPU real, SHA conservadas, procedencia y actividad cero. Evidencia: `D:/LocalAI/research-inbox/referencias-20261013/argus-qa/mcp-frozen.log` y `mcp-receipt.json`.

Revisión independiente: 24 casos propios imports/search/API sobre R1 con backend idéntico en R2, y dictamen R2 `ship`. El revisor leyó el recibo MCP del autor; no ejecutó un segundo MCP independiente. Documentos: `D:/LocalAI/research-inbox/referencias-review445-20261013/FINISH-R2.md`, `REVIEW-R2.md` y `FUNCTIONAL-R1.md`.

Capturas existentes vistas en este pase: `desktop-library.png`, `mobile-library.png`, `desktop-ocr-r2.png`, `mobile-ocr-r2.png`, `desktop-search-r2.png`, bajo `D:/LocalAI/research-inbox/referencias-20261013/argus-qa/screens/`. Biblioteca sigue válida porque R2 no cambia el importador; OCR R2 muestra título/contador y controles visibles. El autor además midió en 390px un diálogo con ancho cliente y scroll iguales (346px), y comprobó Cerrar. Esta documentación no inicia navegador, servidor, modelo ni render.

## Do's and Don'ts

### Do:

- **Do** conservar el aviso de estado y todas las funciones anteriores.
- **Do** mostrar origen, base de fecha y estado OCR con texto.
- **Do** conservar originales y OCR seleccionable.
- **Do** limitar las reglas de marca a la navegación y permitir ajuste de acciones y OCR.

### Don't:

- **Don't** atribuir duración observada a un archivo importado.
- **Don't** convertir la importación puntual en una promesa de vigilancia de carpetas.
- **Don't** recuperar los tokens claros antiguos como autoridad de esta superficie.
- **Don't** presentar pruebas del autor como una ejecución MCP independiente del revisor.
