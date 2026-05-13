# Labelbox Labeling Guide — Tree Images from Drone
# Guía de etiquetado en Labelbox — Imágenes de árboles desde drones

> [Español](#español) | [English](#english)

---

## Referencia rápida

| | |
|---|---|
| Herramienta | Cuadro delimitador |
| Tamaño mínimo | 500 × 500 px |
| Especies por cuadro | 1 |
| Opciones de órgano | Flor, Fruto |
| Overlay de tamaño y especie | `.` (tecla punto) |
| Duplicar cuadro | `Ctrl+D` |
| Ver todos los atajos | Ícono de teclado (barra superior) |

## Quick Reference

| | |
|---|---|
| Tool | Bounding box |
| Minimum box size | 500 × 500 px |
| Species per box | 1 |
| Organ options | Flower, Fruit |
| Size & species overlay | `.` (period key) |
| Duplicate box | `Ctrl+D` |
| See all shortcuts | Keyboard icon (top bar) |

---

# English

## Table of Contents

- [Getting Started & Drawing Bounding Boxes](#getting-started--drawing-bounding-boxes)
- [Attachments](#attachments)
- [Minimum Box Size (500 × 500 px)](#minimum-box-size-500--500-px)
- [Classifying the Taxon](#classifying-the-taxon)
- [Annotating Organs (Flower / Fruit)](#annotating-organs-flower--fruit)
- [One Species per Box](#one-species-per-box)
- [Excluding the Background](#excluding-the-background)
- [Issues](#issues)
- [Skipping Images](#skipping-images)
- [Keyboard Shortcuts](#keyboard-shortcuts)

---

## Getting Started & Drawing Bounding Boxes

Click **Start Labeling** to enter the annotation queue. Images appear one at a time — for each image you must either annotate it or skip it.

The left panel shows the **Planta** tool (bounding box). At the top right: **SKIP** and **SUBMIT** (greyed out until at least one box is drawn).

> 📷 **Image needed:** Screenshot of the initial Labelbox view — Planta tool on the left, empty canvas, SKIP and greyed-out SUBMIT at top right.

**How to draw a box:**

1. Select the **Planta** tool in the left panel (selected by default).
2. Click and drag on the image to draw a rectangle around the plant.
3. Release the mouse — the left panel switches to show the classification fields:
   - **Taxón** — which plant species, genus, or family
   - **Órgano** — whether flowers or fruits are visible
4. Fill in the classification fields (see [Classifying the Taxon](#classifying-the-taxon) and [Annotating Organs](#annotating-organs-flower--fruit) below).
5. Draw additional boxes if needed, then click **SUBMIT** (top right) to confirm and move to the next image.

> 📷 **Image needed:** Screenshot after drawing a box — left panel shows Taxón (Select one) and Órgano (Select all that apply) fields, SUBMIT button active at top right.

**How to adjust an existing box:** Click it to select it. Drag corners or edges to resize; drag the whole box to reposition it.

---

## Attachments

The **paperclip icon** in the top-left toolbar opens the Attachments panel. It provides context for the current image and contains two items:

- **wide (Image)** — a wide-angle aerial photo showing the broader area around the close-up image. Use it to understand the spatial context of the canopy patch you are annotating.
- **map (Html)** — an interactive map of the site. When a Digital Terrain Model (DTM) is available, it shows ground elevation and estimated tree height. Otherwise it shows the Digital Surface Model (DSM) of the area (canopy surface elevation).

> 📷 **Image needed:** Screenshot of the Attachments panel open, showing the wide image and the interactive DTM map.

---

## Minimum Box Size (500 × 500 px)

**Draw boxes no smaller than 500 × 500 pixels.** Smaller boxes are not useful for model training.

- If a plant is too small to fill a 500 × 500 px box, skip it.
- If a mixed area contains multiple species but none can be isolated in 500 × 500 px, annotate only the dominant species.

**How to check the size and species of a box:**

Press the `.` (period) key on your keyboard, or enable **Overlay object titles** in the display settings. This shows the assigned taxon name and the pixel dimensions of each box directly on the image.

> 📷 **Image needed:** Screenshot with the overlay enabled, showing taxon name and box dimensions displayed on each box.

---

## Classifying the Taxon

After drawing a box, assign a **Taxón** if you can identify the plant. This is a single-choice (radio) field — pick the best match:

- **Species** (preferred): e.g., `Alseis blackiana-ALSBL`
- **Genus**: e.g., `Alseis` — use if you cannot identify to species
- **Family**: e.g., `Rubiaceae` — use if you cannot identify to genus

If you cannot identify the plant at all, leave the Taxón field empty.

**How to search:** Start typing the species name or code in the Taxón field. The list filters as you type. Species labels may include shortcodes appended after the name (e.g., `Alseis blackiana-ALSBL`).

**Hierarchy of precision:** Always aim for the most precise level you can confidently assign. An uncertain species identification is worse than a confident genus or family.

> 📷 **Image needed:** Screenshot of the classification panel showing the Taxón radio list with a search being typed and a species being selected.

---

## Annotating Organs (Flower / Fruit)

If flowers and/or fruits are visible in the box, check the corresponding option(s) in the **Órgano** field. This is a checklist — you can select one, both, or neither:

- **Flor** — flowers are visible
- **Fruto** — fruits are visible

Leave the Órgano field empty if no reproductive organs are visible.

> 📷 **Image needed:** Screenshot showing the Órgano checklist with "Flor" checked on an image where flowers are visible.

---

## One Species per Box

**Each bounding box must contain exactly one taxon.**

- If an image shows two different species, draw **two separate boxes**, one per species.
- If two species overlap and cannot be cleanly separated, draw the box around the dominant or most clearly visible one.
- There is no maximum number of boxes per image.

> 📷 **Image needed:** Example image with two separate boxes on two different species.

---

## Excluding the Background

**Boxes should cover the plant, not the background.**

- Do not draw one large box that covers everything in the image if it would include soil, sky, or unrelated vegetation.
- If the canopy has visible gaps (e.g., bare soil or sky visible through the crown), draw separate boxes around each canopy patch rather than one box over the entire image.

> 📷 **Image needed:** Side-by-side comparison — left: incorrect single box covering the whole image including background; right: correct multiple boxes covering only the plant crowns.

**Exception:** If a species covers the entire image with no significant background, a single box covering the full image is fine.

---

## Issues

If you notice something worth flagging on a specific spot in the image — a species not found in the list, a damaged area, or anything requiring attention — you can place a pin using the **Issues tool** (flag icon in the top-left toolbar).

**How to create an issue:**

1. Click the **flag icon** in the top-left toolbar to activate the Issues tool.
2. Click on the relevant spot in the image to place a pin.
3. In the Issues panel that opens on the right, select a **Category** from the dropdown. Use one of the existing categories:
   - **Características (hojas, flores, frutos) ausentes** — the species cannot be identified with the available information
   - **De apariencia botánica** — something has the shape or appearance of a plant but cannot be confirmed due to lack of taxonomic information
   - **Especie desconocida** — the species is impossible to identify even to family level
   - **Especie no encontrado en la lista** — the species is recognizable but missing from the taxon list
   - **Foto dañada** — the image is damaged, making identification impossible
   - **Otro asunto** — no plants visible, presence of animals, or any other issue
4. Add a comment describing the issue.

**Do not add new categories.** If none of the existing ones fit, use *Otro asunto* and explain in the comment.

**Do not use Issues to skip an image.** If the whole image cannot be annotated, use the **SKIP** button instead.

> 📷 **Image needed:** Screenshot of the Issues panel open with the category dropdown visible.

---

## Skipping Images

Some images may be too blurry, too dark, too empty, or otherwise impossible to annotate. You can skip them.

**How to skip:**

1. Click **SKIP** at the top right. A dialog will appear: *"Are you sure you want to erase this label and mark it as skipped?"*
2. Select a **reason** from the dropdown:
   - **mala calidad de la foto** — image is too blurry, dark, or low quality
   - **demasiadas especies entrelazadas** — too many intertwined species to separate
   - **características (hojas, flores, frutos) ausentes** — no identifiable features visible
   - **especies desconocidas** — species cannot be identified at all
3. Fill in the **description** field — a single `.` (period) is sufficient since the reason is already captured.
4. Click **OK** to confirm.

> 📷 **Image needed:** Screenshot of the skip dialog with the reason dropdown open, showing the four options.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `.` (period) | Toggle overlay showing taxon name and box dimensions |
| `Ctrl+D` | Duplicate the selected box (copies taxon and organ) |
| `Esc` | Cancel the current action / deselect |

**Ctrl+D is especially useful** when the same species appears many times in an image: draw and classify the first box, then press `Ctrl+D` to duplicate it and reposition the copy. The taxon and organ are preserved.

**To see all available shortcuts:** Click the **keyboard icon** in the top bar (to the left of the settings icon). Additional shortcuts appear as a tooltip on the three-dot menu of each tool.

> 📷 **Image needed:** Screenshot showing the keyboard shortcut panel that opens when clicking the keyboard icon.

---

---

# Español

## Índice

- [Primeros pasos y cómo dibujar cuadros](#primeros-pasos-y-cómo-dibujar-cuadros)
- [Archivos adjuntos](#archivos-adjuntos)
- [Tamaño mínimo del cuadro (500 × 500 px)](#tamaño-mínimo-del-cuadro-500--500-px)
- [Clasificar el taxón](#clasificar-el-taxón)
- [Anotar órganos (Flor / Fruto)](#anotar-órganos-flor--fruto)
- [Una especie por cuadro](#una-especie-por-cuadro)
- [Excluir el fondo](#excluir-el-fondo)
- [Issues (incidencias)](#issues-incidencias)
- [Omitir imágenes](#omitir-imágenes)
- [Atajos de teclado](#atajos-de-teclado)

---

## Primeros pasos y cómo dibujar cuadros

Haz clic en **Start Labeling** para entrar a la cola de anotación. Las imágenes aparecen de una en una — por cada imagen debes anotarla u omitirla.

El panel izquierdo muestra la herramienta **Planta** (cuadro delimitador). En la parte superior derecha: **SKIP** y **SUBMIT** (inactivo hasta que se dibuje al menos un cuadro).

> 📷 **Imagen necesaria:** Captura de pantalla de la vista inicial de Labelbox — herramienta Planta a la izquierda, lienzo vacío, botones SKIP y SUBMIT (inactivo) en la parte superior derecha.

**Cómo dibujar un cuadro:**

1. Selecciona la herramienta **Planta** en el panel izquierdo (está seleccionada por defecto).
2. Haz clic y arrastra sobre la imagen para dibujar un rectángulo alrededor de la planta.
3. Suelta el ratón — el panel izquierdo muestra los campos de clasificación:
   - **Taxón** — la especie, género o familia de la planta
   - **Órgano** — si hay flores o frutos visibles
4. Rellena los campos de clasificación (ver [Clasificar el taxón](#clasificar-el-taxón) y [Anotar órganos](#anotar-órganos-flor--fruto) más abajo).
5. Dibuja cuadros adicionales si es necesario, luego haz clic en **SUBMIT** (parte superior derecha) para confirmar y pasar a la siguiente imagen.

> 📷 **Imagen necesaria:** Captura de pantalla después de dibujar un cuadro — panel izquierdo con los campos Taxón y Órgano, botón SUBMIT activo en la parte superior derecha.

**Cómo ajustar un cuadro existente:** Haz clic sobre él para seleccionarlo. Arrastra las esquinas o los bordes para redimensionarlo; arrastra el cuadro completo para reposicionarlo.

---

## Archivos adjuntos

El **ícono del clip** en la barra de herramientas superior izquierda abre el panel de archivos adjuntos. Proporciona contexto para la imagen actual y contiene dos elementos:

- **wide (Image)** — una fotografía aérea de ángulo amplio que muestra la zona alrededor de la imagen de primer plano. Úsala para entender el contexto espacial del parche de dosel que estás anotando.
- **map (Html)** — un mapa interactivo del sitio. Cuando se dispone de un Modelo Digital del Terreno (DTM), muestra la elevación del suelo y la altura estimada de los árboles. En caso contrario, muestra el Modelo Digital de Superficie (DSM) de la zona (elevación de la superficie del dosel).

> 📷 **Imagen necesaria:** Captura de pantalla del panel de archivos adjuntos abierto, mostrando la imagen amplia y el mapa interactivo del DTM.

---

## Tamaño mínimo del cuadro (500 × 500 px)

**Dibuja cuadros de al menos 500 × 500 píxeles.** Los cuadros más pequeños no son útiles para el entrenamiento del modelo.

- Si una planta es demasiado pequeña para llenar un cuadro de 500 × 500 px, omítela.
- Si una zona mixta contiene varias especies pero ninguna puede aislarse en 500 × 500 px, anota solo la especie dominante.

**Cómo verificar el tamaño y la especie de un cuadro:**

Presiona la tecla `.` (punto) en el teclado, o activa **Overlay object titles** en la configuración de visualización. Esto muestra el nombre del taxón asignado y las dimensiones en píxeles de cada cuadro directamente sobre la imagen.

> 📷 **Imagen necesaria:** Captura de pantalla con el overlay activado, mostrando el nombre del taxón y las dimensiones de cada cuadro sobre la imagen.

---

## Clasificar el taxón

Después de dibujar un cuadro, asigna un **Taxón** si puedes identificar la planta. Este es un campo de selección única (radio) — elige la mejor opción:

- **Especie** (preferida): p. ej., `Alseis blackiana-ALSBL`
- **Género**: p. ej., `Alseis` — usa esto si no puedes identificar a nivel de especie
- **Familia**: p. ej., `Rubiaceae` — usa esto si no puedes identificar a nivel de género

Si no puedes identificar la planta, deja el campo Taxón vacío.

**Cómo buscar:** Empieza a escribir el nombre de la especie o el código en el campo Taxón. La lista se filtra mientras escribes. Las etiquetas de las especies pueden incluir códigos cortos añadidos después del nombre (p. ej., `Alseis blackiana-ALSBL`).

**Jerarquía de precisión:** Siempre apunta al nivel más preciso que puedas asignar con confianza. Una identificación de especie incierta es peor que un género o familia con confianza.

> 📷 **Imagen necesaria:** Captura de pantalla del panel de clasificación mostrando la lista de radio Taxón con una búsqueda escrita y una especie siendo seleccionada.

---

## Anotar órganos (Flor / Fruto)

Si hay flores y/o frutos visibles en el cuadro, marca la(s) opción(es) correspondiente(s) en el campo **Órgano**. Es una lista de verificación — puedes seleccionar una, ambas o ninguna:

- **Flor** — hay flores visibles
- **Fruto** — hay frutos visibles

Deja el campo Órgano vacío si no hay órganos reproductivos visibles.

> 📷 **Imagen necesaria:** Captura de pantalla que muestre el checklist de Órgano con "Flor" marcado en una imagen donde hay flores visibles.

---

## Una especie por cuadro

**Cada cuadro delimitador debe contener exactamente un taxón.**

- Si una imagen muestra dos especies diferentes, dibuja **dos cuadros separados**, uno por especie.
- Si dos especies se superponen y no pueden separarse limpiamente, dibuja el cuadro alrededor de la dominante o la más claramente visible.
- No hay un número máximo de cuadros por imagen.

> 📷 **Imagen necesaria:** Imagen de ejemplo con dos cuadros separados sobre dos especies diferentes.

---

## Excluir el fondo

**Los cuadros deben cubrir la planta, no el fondo.**

- No dibujes un cuadro grande que cubra todo en la imagen si incluye suelo, cielo u otra vegetación no relacionada.
- Si el dosel tiene huecos visibles (p. ej., suelo desnudo o cielo visible a través de la copa), dibuja cuadros separados alrededor de cada parche de dosel en lugar de un solo cuadro sobre toda la imagen.

> 📷 **Imagen necesaria:** Comparación lado a lado — izquierda: cuadro único incorrecto que cubre toda la imagen incluyendo el fondo; derecha: múltiples cuadros correctos que cubren solo las copas de las plantas.

**Excepción:** Si una especie cubre toda la imagen sin fondo significativo, un solo cuadro que cubra la imagen completa es correcto.

---

## Issues (incidencias)

Si detectas algo que merece ser señalado en un punto concreto de la imagen — una especie no encontrada en la lista, una zona dañada u otra situación que requiera atención — puedes colocar un pin usando la herramienta de **Issues** (ícono de bandera en la barra de herramientas superior izquierda).

**Cómo crear un issue:**

1. Haz clic en el **ícono de bandera** en la barra superior izquierda para activar la herramienta de Issues.
2. Haz clic en el punto de la imagen que quieras señalar.
3. En el panel de Issues que se abre a la derecha, selecciona una **Categoría** del menú desplegable. Usa una de las categorías existentes:
   - **Características (hojas, flores, frutos) ausentes** — no es posible identificar la especie con la información disponible
   - **De apariencia botánica** — algo tiene la forma o el aspecto de una planta, pero no se puede afirmar con certeza por falta de información taxonómica
   - **Especie desconocida** — especie imposible de identificar ni siquiera a nivel de familia
   - **Especie no encontrado en la lista** — la especie es reconocible pero falta en la lista de taxones
   - **Foto dañada** — la imagen está dañada e impide la identificación
   - **Otro asunto** — sin plantas, presencia de animales u otro asunto
4. Añade un comentario describiendo el issue.

**No añadas categorías nuevas.** Si ninguna encaja, usa *Otro asunto* y explícalo en el comentario.

**No uses Issues para omitir una imagen.** Si la imagen completa no puede anotarse, usa el botón **SKIP** en su lugar.

> 📷 **Imagen necesaria:** Captura de pantalla del panel de Issues abierto con el menú desplegable de categorías visible.

---

## Omitir imágenes

Algunas imágenes pueden estar demasiado borrosas, demasiado oscuras, vacías o ser imposibles de anotar. Puedes omitirlas.

**Cómo omitir:**

1. Haz clic en **SKIP** en la parte superior derecha. Aparecerá un diálogo: *"Are you sure you want to erase this label and mark it as skipped?"*
2. Selecciona un **motivo** en el menú desplegable:
   - **mala calidad de la foto** — imagen borrosa, oscura o de mala calidad
   - **demasiadas especies entrelazadas** — demasiadas especies mezcladas para poder separarlas
   - **características (hojas, flores, frutos) ausentes** — no hay características identificables visibles
   - **especies desconocidas** — no es posible identificar ninguna especie
3. Rellena el campo de **descripción** — basta con escribir un `.` (punto), ya que el motivo queda registrado en la categoría.
4. Haz clic en **OK** para confirmar.

> 📷 **Imagen necesaria:** Captura de pantalla del diálogo de omisión con el menú desplegable abierto mostrando los cuatro motivos disponibles.

---

## Atajos de teclado

| Atajo | Acción |
|---|---|
| `.` (punto) | Activar/desactivar el overlay con el nombre del taxón y las dimensiones del cuadro |
| `Ctrl+D` | Duplicar el cuadro seleccionado (copia taxón y órgano) |
| `Esc` | Cancelar la acción actual / deseleccionar |

**`Ctrl+D` es especialmente útil** cuando la misma especie aparece varias veces en una imagen: dibuja y clasifica el primer cuadro, luego presiona `Ctrl+D` para duplicarlo y reposiciona la copia. El taxón y el órgano se conservan.

**Para ver todos los atajos disponibles:** Haz clic en el **ícono del teclado** en la barra superior (a la izquierda del ícono de configuración). También se muestran atajos adicionales en el menú de tres puntos de cada herramienta.

> 📷 **Imagen necesaria:** Captura de pantalla que muestre el panel de atajos de teclado que se abre al hacer clic en el ícono del teclado.
