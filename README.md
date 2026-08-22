# codemaster

Plataforma de saneamiento de huellas AI para **cualquier tipo de contenido**: adjunta archivos o directorios y elimina comentarios, docstrings, firmas de modelos generativos, glifos invisibles (esteganografia Unicode), metadatos de proveniencia (EXIF/XMP/IPTC/C2PA), marcas visibles en imagenes, metadatos de autor en documentos y huellas forenses en binarios.

Nucleo sin dependencias externas; extras ligeros opcionales para pixels y metadatos ricos.

## Instalacion

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Extras disponibles: `images` (PIL/piexif), `pixels` (PIL/numpy/opencv), `c2pa` (lector C2PA oficial). Sin ellos, los modulos se degradan via `is_available()`.

## Uso

```
codemaster scan [RUTA...]                 inventario de hallazgos por tipo
codemaster scan --json .                  salida estructurada (score por archivo)
codemaster identify [RUTA...]             clasifica el contenido y lista senales
codemaster identify --json .              clasificacion estructurada
codemaster check [RUTA...]                puerta CI: salida 1 ante hallazgos firmes
codemaster check --strict .               falla tambien con avisos
codemaster report [RUTA...] --format md   exporta reporte (md|html|json|human)
codemaster report . --format html -o rep  escribe reporte en archivo
codemaster config --show                  muestra config persistente
codemaster config --workers 8 --glyphs    actualiza config
codemaster scrub [RUTA...]                ensayo: muestra el plan sin escribir
codemaster scrub --apply --backup .       aplica, reservando copia .bak
codemaster scrub --apply --fix-unicode .  incluye limpieza de glifos invisibles
codemaster scrub --apply --keep-meta .    aplica sin tocar metadatos
```

`scan` y `check` son de solo lectura. `scrub` nunca modifica sin `--apply` explicito.

En `--json` y en la salida humana de `identify`, cada archivo incluye `score`:
agregado en `[0, 1]` ponderando cada hallazgo por gravedad (los senales peligrosos
dominan), util para filtrar en CI.

## Plataforma

Ademas de la CLI, el proyecto ofrece dos interfaces y servicios integrados:

| Interfaz | Comando | Descripcion |
| --- | --- | --- |
| Escritorio | `codemaster-gui` | ventana tkinter: elegir ruta, analizar, seleccionar que limpiar (todo por defecto), confirmar y aplicar con respaldo |
| Web | `codemaster-web` | dashboard en `http://127.0.0.1:8765` con gatos animados (three.js), progreso en vivo, limpieza, reportes e historial |

El servidor web expone una API REST local (sin dependencias externas):

- `GET /api/scan?path=...&stream=0` — analisis paralelo (SSE si se omite `stream`)
- `GET /api/report?path=...&format=md|html|json`
- `GET /api/history` — historial de limpiezas aplicadas
- `GET /api/config` / `POST /api/config` — configuracion persistente
- `POST /api/clean` — limpiar una lista de rutas con respaldo

El escaneo usa `ThreadPoolExecutor` (trabajadores configurables via `config --workers`)
con escrituras atomicas (tmp + rename) y rollback ante error; cada limpieza aplicada
se registra en `~/.codemaster/history.jsonl` y la config en `~/.codemaster.json`
(override con las variables de entorno `CODEMASTER_HOME` y `CODEMASTER_CONFIG`).

## Proveniencia C2PA

Cuando el lector C2PA (extra `c2pa`) esta disponible, `identify` y `scan` exponen el
estado de validacion de cada manifiesto en el slip `c2pa` como `state: valid` /
`state: invalid` / `state: unknown`, ademas del generador detectado. Los manifiestos
que solo contienen estado (sin generador conocido) no fuerzan `ai: true`.

## Catalogo de huellas

El catalogo vive en `src/codemaster/signatures.toml` y se edita sin tocar codigo:

- `[[models]]`: modelos de IA con su grupo (`llm`, `image`, `video`, `audio`, `code`)
  y patrones de coincidencia (case-insensitive).
- `[phrases]`: frases tipicas por categoria (`authorship`, `narration`, `fragment`).
- `[agents]`: mapeo de cadenas C2PA (`claim_generator` / `softwareAgent`) a un
  modelo canonico.
- `[vendors]`: tokens que implican una organizacion (OpenAI, Anthropic, Google...).

Incluye 80+ modelos: chat/LLM (chatgpt, claude, gemini, deepseek, qwen, grok...),
imagen (dall-e, midjourney, stable-diffusion, flux, firefly, ideogram, seedream...),
video (sora, veo, runway, pika, luma, kling...), audio (elevenlabs, suno, udio,
whisper...) y codigo (copilot, codex, cursor, v0, bolt.new...).

Lista el catalogo con `codemaster catalog [--group llm|image|video|audio|code]`.
Al resolver proveniencia C2PA, el manifiesto se mapea al modelo y vendor conocidos
via `[agents]`/`[vendors]`.

## Tipos de contenido

| Tipo | Deteccion | Saneado |
| --- | --- | --- |
| Texto/codigo | suffijo o ratio imprimible | comentarios, docstrings, firmas, glifos |
| HTML | doctype/markup | comentarios, meta generator/author, glifos |
| EPUB | PK zip con `mimetype` + `.opf` | glifos invisibles en XHTML (audit de narracion/firmas) |
| DOCX/XLSX/PPTX | PK zip con word/document.xml, xl/workbook.xml, ppt/presentation.xml | autor en core.xml, glifos en document.xml |
| PDF | cabecera `%PDF-` | valores /Author /Creator /Producer /Title |
| JPEG | SOI FFD8 | segmentos APP1-EXIF, APP1-XMP, APP13-IPTC, COM (sin recomprimir) |
| PNG | firma 8-byte | chunks tEXt/iTXt/zTXt AI, eXIf, jumbf |
| GIF | cabecera `GIF87a`/`GIF89a` | extensiones Comment (0xFE) y XMP (0xFF) |
| TIFF | `II*\x00`/`MM\x00*` | tags software/artist/xmp/ExifIFD en IFD |
| HEIC/AVIF | ISO BMFF `ftyp` heic/avif | cajas `meta`/XMP/C2PA (zeroing ISO BMFF) |
| Imagen (pixels) | marcas visibles reales de IA | localize -> fill (inpaint cv2) |
| Binarios | bytes nulos | solo reporte forense (no reescribibles) |

## Marcas visibles reales

Con el extra `pixels` instalado, el handler de pixels detecta y elimina marcas visibles
de generadores de IA por el patron **localize -> fill**: localiza la marca por
correlacion de silueta (NCC, CPU) y rellena su area con inpainting cv2.

Registradas: `gemini` (sparkle de 4 puntas, abajo-derecha), `doubao`, `jimeng`, `qwen`,
`kling`, `yuanbao` (texto CJK, abajo-derecha), `samsung` (abajo-izquierda),
`runninghub` (arriba-izquierda), `baidu` y `liblib` (abajo-centro). Sin opencv, se
degradan a la heuristica generica de esquina (reporte/relleno grueso).

Las marcas de texto viven como **plugins** en `src/codemaster/marks.toml` + un
archivo alpha en `src/codemaster/assets/`. Para registrar una marca nueva:

1. Coloca su silueta alpha (fondo negro, glifo blanco) en `assets/<marca>_alpha.png`
2. Anade una entrada `[[marks]]` en `marks.toml` con `key`, `asset`, `corner`,
   fracciones de tamano/margen, umbral NCC y `detect_frontend`
   (`tophat`/`binary`/`contrast`/`gray`).

El motor `visible.py` no se toca: carga el catalogo via `codemaster.marks.REGISTRY`.

Los activos alpha de deteccion se portan desde `remove-ai-watermarks` (Apache 2.0,
ver `src/codemaster/assets/README.md`); el motor aqui es un reimplementacion ligera
sin torch/onnx.

## Verificacion local

```
tools\sweep.ps1
```

Ejecuta formato, lint, tipos, pruebas y la autoevaluacion del propio arbol (excluye `tests`, los catalogos de reglas `signatures.py`/`registry.py`/`visible.py`, los activos de calibracion `assets` y la referencia vendored `remove-ai-watermarks-main`).
