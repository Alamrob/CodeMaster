from __future__ import annotations

from codemaster.handlers import (
    forensics,
    html,
    image_meta,
    image_pixels,
    office,
    pdf,
    text,
)
from codemaster.handlers.base import Blob, Handler


def chain(blob: Blob) -> list[Handler]:
    kind = blob.kind
    if kind == "image":
        handlers: list[Handler] = [image_meta.HANDLER]
        if image_pixels.HANDLER.probe(blob):
            handlers.append(image_pixels.HANDLER)
        return handlers
    if kind == "pdf":
        return [pdf.HANDLER]
    if kind in ("docx", "xlsx", "pptx"):
        return [office.HANDLER]
    if kind == "html":
        return [html.HANDLER]
    if kind == "binary":
        return [forensics.HANDLER]
    if kind in ("text", "code"):
        return [text.HANDLER]
    return []
