# Assets

Los activos alpha de detección (`*_alpha.png`, `gemini_bg_*.png`) se portan desde
`remove-ai-watermarks` (Apache License 2.0), cuya implementación original es:

- <https://github.com/nathanielknight/remove-ai-watermarks> (repo vendored local en
  `remove-ai-watermarks-main/`)

El motor ligero `codemaster.handlers.visible` los usa para localizar (correlación NCC)
y eliminar marcas visibles de IA (localize -> fill, relleno por inpaint cv2) siguiendo
el patrón de la referencia sin copiar su maquinaria pesada (sin torch/onnx).
