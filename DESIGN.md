---
name: Argus's Hoard
description: Una memoria de pantalla privada que muestra con claridad qué recuerda, cuándo mira y cómo olvidar.
colors:
  accent: "#4a3f8f"
  accent-hover: "#3a3172"
  ink: "#2a2740"
  muted: "#6b6880"
  paper: "#fbfafd"
  white: "#ffffff"
  line: "#e5e2ef"
  soft: "#efedf6"
  sidebar: "#f3f1f9"
  nav-active: "#e3dff3"
  nav-active-ink: "#3a3072"
  nav-hover: "#eae7f4"
  field-line: "#d8d3e8"
  field-ink: "#2f2a4f"
  placeholder: "#857f9c"
  supporting-ink: "#666280"
  focus: "#6b5fc0"
  button-line: "#dcd8e8"
  panel: "#f5f3fa"
  watch-bg: "#e6e2f5"
  watch-ink: "#3a3072"
  pause-bg: "#f7ecd6"
  pause-ink: "#7a5a17"
  private-bg: "#2a2740"
  private-ink: "#f3f1f9"
  off-bg: "#ecebf0"
  off-ink: "#5c5970"
  ok-bg: "#e4efe6"
  ok-ink: "#2f5f3a"
  danger-bg: "#fbeceb"
  danger-ink: "#8a3a2c"
  danger-line: "#e8c8c2"
  bar-bg: "#e7e4f1"
  highlight: "#f6e9a8"
typography:
  headline:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: 1.65
  button:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: "18px"
  label:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  code:
    fontFamily: "Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  badge: "5px"
  field: "6px"
  control: "7px"
  panel: "8px"
  dialog: "12px"
spacing:
  control-gap: "8px"
  action-gap: "10px"
  field-margin: "20px"
  page-gutter: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "8px 15px"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "8px 15px"
  button-danger:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "8px 15px"
  field:
    backgroundColor: "{colors.white}"
    textColor: "{colors.field-ink}"
    rounded: "{rounded.field}"
    padding: "8px 11px"
    width: "100%"
  nav-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-active-ink}"
    rounded: "{rounded.control}"
    padding: "10px 13px"
  banner-watching:
    backgroundColor: "{colors.watch-bg}"
    textColor: "{colors.watch-ink}"
    rounded: "{rounded.panel}"
    padding: "10px 16px"
  banner-private:
    backgroundColor: "{colors.private-bg}"
    textColor: "{colors.private-ink}"
    rounded: "{rounded.panel}"
    padding: "10px 16px"
  inline-panel:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.panel}"
    padding: "20px"
---

# Design System: Argus's Hoard

## Overview

**Creative North Star: "Memoria a la vista"**

Argus recuerda lo que hubo en pantalla, y la interfaz existe para que esa
memoria sea legible y controlable. Un papel frío con un acento índigo profundo
sostiene tres ideas: qué había (miniaturas y texto reconocido), cuándo (línea de
tiempo con duraciones) y si Argus está mirando ahora mismo (el aviso de estado
en todas las páginas). Nada decora: cada color señala un estado o una acción.

**Key Characteristics:**

- Papel frío y líneas discretas; el índigo marca acciones y el estado «mirando».
- El estado de grabación es siempre visible y escrito: mirando, en pausa,
  privado, desactivada.
- Las capturas son tarjetas planas con miniatura, hora y duración; el detalle
  superpone el texto OCR como texto seleccionable.
- Los controles de privacidad (modo privado, pausa, exclusiones, borrado) son
  grandes, explícitos y sin confirmaciones ocultas.

## Colors

El índigo organiza las acciones; los neutros de papel y lavanda sostienen la
lectura de listas largas de capturas.

### Primary

- **Índigo:** `accent` identifica botones principales, enlaces, el día
  seleccionado y las barras de actividad; `accent-hover` lo oscurece.
- **Lavanda de selección:** `nav-active`/`nav-active-ink` marcan la sección
  activa; `soft` responde a controles secundarios y filas al pasar el puntero.

### Estados de grabación

- **Mirando:** `watch-bg`/`watch-ink`, con un punto que late lentamente.
- **En pausa:** `pause-bg`/`pause-ink`, ocre cálido.
- **Modo privado:** `private-bg`/`private-ink`, tinta oscura invertida: es el
  único bloque oscuro de la interfaz, para que no pase desapercibido.
- **Desactivada:** `off-bg`/`off-ink`, gris neutro.

### Neutral

- **Papel:** `paper` es la superficie principal; `white` corresponde a campos,
  tarjetas y controles secundarios; `sidebar` separa el índice.
- **Tinta:** `ink` sostiene títulos y contenido; `supporting-ink` corresponde a
  ayudas, horas y metadatos.
- **Líneas:** `line` separa regiones; `field-line` y `button-line` bordean
  controles.

`highlight` marca las coincidencias de búsqueda (`<mark>`); `danger-*` se
reserva para borrar y para errores del sistema.

**The Estado escrito Rule.** Cada estado se comunica con texto; el color solo
lo refuerza.

## Typography

**Body Font:** Segoe UI con system-ui y sans-serif de respaldo. Georgia solo en
el monograma «A». Consolas para patrones de exclusión y texto OCR en bloque.

- **Headline:** título de página (30px; 26px en móvil).
- **Title:** título de sección o de captura (17px; 15px en el detalle).
- **Body:** 14px; descripciones y ayudas a 12–13px.
- **Label:** etiquetas de formulario y cabeceras de tabla (12px, seminegrita).
- Horas, duraciones y contadores usan cifras tabulares (`.num`).

## Layout

Escritorio: índice fijo de 224px y contenido flexible con mínimo cero; margen
de página de 40px. La línea de tiempo usa una cuadrícula de tarjetas (2 a 5
columnas según ancho) precedida por el deslizador del día. El detalle es un
diálogo nativo de hasta 1200px con imagen a la izquierda y panel de texto de
320px a la derecha.

- Hasta 768px el índice pasa a barra superior con navegación horizontal
  desplazable; los formularios y el detalle pasan a una columna; el panel de
  texto OCR queda bajo la imagen.
- Sin desplazamiento horizontal de página en ningún ancho.

## Elevation & Depth

Plana por defecto. La única sombra es la del diálogo de detalle y la del aviso
flotante. Sin cristal ni desenfoques.

## Shapes

Radios discretos: campos 6px, controles 7px, paneles y tarjetas 8px, diálogo
12px. Los interruptores son píldoras; el de modo privado es grande y se
oscurece al activarse. Las cajas OCR se dibujan con contorno discontinuo solo al
pedirlo («Ver cajas»).

## Components

### Banner de estado

Presente bajo la barra superior en todas las páginas. Texto del estado, detalle
(intervalo, motor OCR, cola) y la acción contraria (Pausar, Reanudar, Salir del
modo privado). `role="status"`, `aria-live="polite"`.

### Tarjeta de captura

Miniatura 16:9, hora seminegrita y duración alineada a la derecha, título de
ventana, aplicación y dos líneas de extracto. La tarjeta seleccionada por el
deslizador lleva borde índigo.

### Visor de captura

Diálogo nativo con cabecera (título, aplicación, hora, duración, monitor),
anterior/siguiente (también flechas del teclado) y cerrar. Sobre la imagen se
superponen los bloques OCR como texto transparente y seleccionable, escalado con
`ResizeObserver`. El panel lateral muestra el texto completo con «Copiar».

### Buttons

Primario índigo con tinta blanca, secundario blanco con borde, destructivo rojo
suave. Altura mínima 38px (30px en `btn-sm`). Estado deshabilitado a 0,45 de
opacidad. Foco visible con contorno de 2px en `focus`.

### Inputs / Fields

Etiqueta encima, ayuda debajo. Los campos numéricos de Ajustes guardan al
perder el foco o con Intro; los interruptores y selectores guardan al instante.
No hay botón «Guardar».

### Navigation

Icono de línea y texto; la sección activa combina peso, color y fondo con
`aria-current`. En móvil, desplazamiento horizontal sin truncar nombres.

### Exclusiones

Lista de filas sobre `soft` con etiqueta de tipo, patrón en monoespaciada,
interruptor y «Quitar». La caja «¿esta ventana se excluiría?» responde con
frase completa y la regla que aplica.

## Do's and Don'ts

### Do:

- **Do** mantener el aviso de estado en todas las páginas y con el texto exacto.
- **Do** usar el bloque oscuro únicamente para el modo privado.
- **Do** mostrar duraciones y contadores reales; los vacíos indican la causa
  (sin capturas, en pausa, día sin datos).
- **Do** conservar el texto OCR como texto seleccionable sobre la imagen.

### Don't:

- **Don't** añadir confirmaciones modales a acciones reversibles ni ocultar las
  irreversibles (borrar pide confirmación nativa y dice «no se puede deshacer»).
- **Don't** convertir la línea de tiempo en tarjetas elevadas con sombra.
- **Don't** usar rojo para estados que no sean borrado o error.
- **Don't** mostrar datos de ejemplo ficticios en la interfaz real.
