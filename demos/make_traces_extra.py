from __future__ import annotations

import io
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE / "ai-traces"

DEMO.mkdir(exist_ok=True)


def make_epub() -> None:
    buffer = io.BytesIO()
    body = (
        "<html><body><p>Welcome. Note that this chapter was drafted for you.\u200b"
        "</p></body></html>"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("content.opf", "<package/>")
        z.writestr("cap1.xhtml", body)
    (DEMO / "libro.epub").write_bytes(buffer.getvalue())


def make_docx() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "docProps/core.xml",
            '<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties">'
            "<dc:creator>GPT-4o</dc:creator><cp:lastModifiedBy>claude</cp:lastModifiedBy>"
            "</cp:coreProperties>",
        )
        z.writestr("word/document.xml", "<w:document/>")
    (DEMO / "propuesta.docx").write_bytes(buffer.getvalue())


def make_pdf() -> None:
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"4 0 obj<</Author (ChatGPT) /Creator (claude) /Producer (gemini)>>endobj\n"
        b"trailer<</Root 1 0 R/Info 4 0 R>>\n"
        b"%%EOF\n"
    )
    (DEMO / "doc.pdf").write_bytes(body)


make_epub()
make_docx()
make_pdf()
print("ok")