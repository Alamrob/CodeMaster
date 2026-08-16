from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from codemaster import signatures
from codemaster._internal import rich
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_AI_KEYWORDS = (
    b"Software",
    b"Artist",
    b"Comment",
    b"DigitalSourceType",
    b"generator",
    b"c2pa",
    b"ContentCredentials",
    b"synthid",
)
_PNG_TEXT_KEYS = frozenset(
    {
        "Software",
        "Artist",
        "Author",
        "Comment",
        "Description",
        "Copyright",
        "Generator",
        "c2pa",
        "AI",
    }
)
_JPEG_LABELS = (
    (b"Exif\x00\x00", "exif"),
    (b"http://ns.adobe.com/xap/1.0/\x00", "xmp"),
    (b"Photoshop 3.0\x00", "iptc"),
)
_TRAIL_MARKERS = (b"c2pa", b"jumbf", b"ContentCredentials", b"synthid")
_C2PA_MARKERS = (b"jumb", b"jumd", b"c2pa", b"ContentCredentials", b"synthid")
_PNG_CRITICAL = frozenset({"IHDR", "PLTE", "IDAT", "IEND"})
_RIFF_IMAGE = frozenset({b"VP8 ", b"VP8L", b"ALPH", b"ANMF"})
_AI_TOOL_TERMS = (
    "adobe firefly",
    "firefly",
    "dall-e",
    "dalle",
    "midjourney",
    "stable diffusion",
    "dreamstudio",
    "leonardo ai",
    "ideogram",
    "imagen",
    "sora",
    "flux",
    "chatgpt image",
    "gpt-4o",
    "microsoft designer",
    "meta ai",
    "doubao",
    "jimeng",
    "kling",
    "qwen-image",
    "recraft",
    "seedream",
    "runway",
    "luma",
    "pixverse",
    "hailuo",
    "krea",
    "hunyuan",
    "yuanbao",
    "veo",
    "gemini image",
)
_TIFF_TYPE_SIZES = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    6: 1,
    7: 1,
    8: 2,
    9: 4,
    10: 8,
    11: 4,
    12: 8,
}
_TIFF_TEXT_TAGS = {
    270: "imagedescription",
    271: "make",
    272: "model",
    305: "software",
    315: "artist",
    33432: "copyright",
}
_ISOBMFF_BRANDS = frozenset(
    {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"heim",
        b"heis",
        b"hevm",
        b"hevs",
        b"mif1",
        b"msf1",
        b"avif",
        b"avis",
    }
)
_XMP_BMFF_MARKERS = (
    b"http://ns.adobe.com/xap/1.0/",
    b"<x:xmpmeta",
    b"xpacket",
    b"<xmpmeta",
)
_BMFF_XMP_UUID = bytes.fromhex("be7acfcb97a942e89c71999491e3afac")


@dataclass
class _Segment:
    start: int
    marker: int
    payload: bytes


class _ImageMetaHandler:
    name = "meta"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "image"

    def audit(self, blob: Blob) -> list[Slip]:
        data = blob.data
        if data.startswith(b"\xff\xd8\xff"):
            return _jpeg_audit(data)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return _png_audit(data)
        if _is_webp(data):
            return _riff_audit(data)
        if _is_gif(data):
            return _gif_audit(data)
        if _is_tiff(data):
            return _tiff_audit(data)
        if _is_bmff(data):
            return _bmff_audit(data)
        return _generic_audit(data)

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        if not edits.meta:
            return blob.data, []
        data = blob.data
        if data.startswith(b"\xff\xd8\xff"):
            return _jpeg_wash(data)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return _png_wash(data)
        if _is_webp(data):
            return _riff_wash(data)
        if _is_gif(data):
            return _gif_wash(data)
        if _is_tiff(data):
            return _tiff_wash(data)
        if _is_bmff(data):
            return _bmff_wash(data)
        return data, []


HANDLER: Handler = _ImageMetaHandler()


def _line_index(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def _jpeg_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    segments = _jpeg_segments(data)
    for segment in segments:
        label = None
        for header, name in _JPEG_LABELS:
            if segment.payload.startswith(header):
                label = name
                break
        if label is None and segment.marker == 0xFE:
            label = "comment"
        if (
            label is None
            and 0xE0 <= segment.marker <= 0xEF
            and _looks_like_c2pa(segment.payload)
        ):
            label = "c2pa"
        if label is None:
            continue
        strong = label == "c2pa" or any(
            keyword in segment.payload for keyword in _AI_KEYWORDS
        )
        slips.append(
            Slip(
                1,
                segment.start + 1,
                label,
                _segment_name(segment, label),
                Grade.DANGER if strong else Grade.SIGNAL,
            )
        )
        if label == "exif":
            slips.extend(_exif_value_slips(segment.payload[6:], segment.start))
    slips.extend(_trail_scan(data))
    slips.extend(_c2pa_slips(data))
    return slips


def _exif_value_slips(payload: bytes, offset: int) -> list[Slip]:
    slips: list[Slip] = []
    for tag, value in rich.exif_pairs(payload):
        if not _hits_ai_tool(value):
            continue
        slips.append(
            Slip(
                1,
                offset + 1,
                "exif",
                f"{tag} = {value}"[:48],
                Grade.DANGER,
            )
        )
    return slips


def _c2pa_slips(data: bytes) -> list[Slip]:
    info = rich.c2pa_info(data)
    if info is None:
        return []
    slips: list[Slip] = []
    generator = info.get("generator")
    if isinstance(generator, str):
        rank = Grade.DANGER if _hits_ai_tool(generator) else Grade.SIGNAL
        slips.append(Slip(1, 1, "c2pa", f"generator: {generator}"[:48], rank))
    vendor = info.get("vendor")
    if isinstance(vendor, str):
        slips.append(Slip(1, 1, "c2pa", f"vendor: {vendor}"[:48], Grade.SIGNAL))
    if info.get("ai") or info.get("enhanced"):
        kind = "AI-enhanced" if info.get("enhanced") else "AI-generated"
        slips.append(Slip(1, 1, "c2pa", f"source: {kind}", Grade.DANGER))
    if info.get("watermarked"):
        slips.append(Slip(1, 1, "c2pa", "watermarked (declared)", Grade.DANGER))
    if info.get("synthid"):
        vendor = info.get("synthid")
        label = f"synthid watermark present ({vendor})"
        slips.append(Slip(1, 1, "c2pa", label[:48], Grade.DANGER))
    for label in info.get("soft_bindings", []):
        slips.append(Slip(1, 1, "c2pa", f"soft-binding: {label}"[:48], Grade.DANGER))
    issuer = info.get("issuer")
    if isinstance(issuer, str):
        slips.append(Slip(1, 1, "c2pa", f"issuer: {issuer}"[:48], Grade.SIGNAL))
    state = info.get("state")
    if isinstance(state, str):
        slips.append(Slip(1, 1, "c2pa", f"state: {state}"[:48], Grade.SIGNAL))
    return slips


def _hits_ai_tool(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in _AI_TOOL_TERMS)


def _looks_like_c2pa(payload: bytes) -> bool:
    return any(marker in payload for marker in _C2PA_MARKERS)


def _jpeg_segments(data: bytes) -> list[_Segment]:
    segments: list[_Segment] = []
    index = 2
    while index + 3 < len(data):
        if data[index] != 0xFF:
            break
        marker = data[index + 1]
        if marker in (0xD8, 0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
            index += 2
            continue
        if marker in (0xD9, 0xDA):
            break
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if length < 2:
            break
        payload_end = index + 4 + length - 2
        if payload_end > len(data):
            break
        segments.append(_Segment(index, marker, data[index + 4 : payload_end]))
        index = payload_end
    return segments


def _segment_name(segment: _Segment, label: str) -> str:
    return f"APPx{label} len={len(segment.payload)}"


def _jpeg_wash(data: bytes) -> tuple[bytes, list[str]]:
    segments = _jpeg_segments(data)
    keep: list[_Segment] = []
    dropped = 0
    for segment in segments:
        drop = segment.marker == 0xFE
        if not drop:
            for header, _ in _JPEG_LABELS:
                if segment.payload.startswith(header):
                    drop = True
                    break
        if not drop and 0xE0 <= segment.marker <= 0xEF:
            drop = _looks_like_c2pa(segment.payload)
        if drop:
            dropped += 1
            continue
        keep.append(segment)
    if dropped == 0:
        return data, []
    out = bytearray(b"\xff\xd8")
    for segment in keep:
        out.append(0xFF)
        out.append(segment.marker)
        out += struct.pack(">H", len(segment.payload) + 2)
        out += segment.payload
    scan_start = (
        segments[-1].start + 2 + 2 + len(segments[-1].payload) if segments else 0
    )
    tail = data[scan_start:]
    if not tail.startswith(b"\xff\xda"):
        return data, []
    out += tail
    return bytes(out), ["meta"]


def _png_chunks(data: bytes) -> list[tuple[int, str, bytes]]:
    chunks: list[tuple[int, str, bytes]] = []
    index = 8
    while index + 8 <= len(data):
        length = struct.unpack(">I", data[index : index + 4])[0]
        ctype = data[index + 4 : index + 8].decode("latin-1")
        body_start = index + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            break
        chunks.append((index, ctype, data[body_start:body_end]))
        index = body_end + 4
        if ctype == "IEND":
            break
    return chunks


def _png_text_key(body: bytes) -> str:
    return body.split(b"\x00", 1)[0].decode("latin-1")


def _png_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for index, ctype, body in _png_chunks(data):
        if ctype == "eXIf":
            slips.append(Slip(1, index + 1, "exif", "png eXIf chunk", Grade.SIGNAL))
            slips.extend(_exif_value_slips(body, index))
        elif ctype in ("tEXt", "iTXt", "zTXt"):
            key = _png_text_key(body)
            if key in _PNG_TEXT_KEYS or key.lower() in _PNG_TEXT_KEYS:
                slips.append(Slip(1, index + 1, "pngtext", f"{key}", Grade.DANGER))
        elif ctype in ("jumb", "caBX", "jumbf"):
            slips.append(Slip(1, index + 1, "c2pa", f"png {ctype} chunk", Grade.DANGER))
    slips.extend(_trail_scan(data))
    slips.extend(_c2pa_slips(data))
    return slips


def _png_wash(data: bytes) -> tuple[bytes, list[str]]:
    chunks = _png_chunks(data)
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    dropped = False
    for _, ctype, body in chunks:
        drop = ctype in ("eXIf", "jumbf", "jumb", "caBX")
        if not drop and ctype in ("tEXt", "iTXt", "zTXt"):
            drop = (
                _png_text_key(body) in _PNG_TEXT_KEYS
                or _png_text_key(body).lower() in _PNG_TEXT_KEYS
            )
        if not drop and ctype not in _PNG_CRITICAL:
            drop = _looks_like_c2pa(body)
        if drop:
            dropped = True
            continue
        _write_chunk(out, ctype, body)
    if not dropped:
        return data, []
    if b"IEND" not in bytes(out[-8:]):
        _write_chunk(out, "IEND", b"")
    return bytes(out), ["meta"]


def _write_chunk(out: bytearray, ctype: str, body: bytes) -> None:
    out += struct.pack(">I", len(body))
    name = ctype.encode("latin-1")
    out += name + body
    out += struct.pack(">I", zlib.crc32(name + body) & 0xFFFFFFFF)


def _is_webp(data: bytes) -> bool:
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def _riff_chunks(data: bytes) -> list[tuple[int, bytes, bytes]]:
    chunks: list[tuple[int, bytes, bytes]] = []
    index = 12
    while index + 8 <= len(data):
        fourcc = data[index : index + 4]
        length = struct.unpack("<I", data[index + 4 : index + 8])[0]
        body_start = index + 8
        body_end = body_start + length
        padded = length % 2
        if body_end + padded > len(data):
            break
        chunks.append((index, fourcc, data[body_start:body_end]))
        index = body_end + padded
    return chunks


def _riff_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for index, fourcc, payload in _riff_chunks(data):
        name = fourcc.decode("latin-1")
        is_c2pa = fourcc == b"C2PA" or (
            fourcc not in _RIFF_IMAGE and _looks_like_c2pa(payload)
        )
        if is_c2pa:
            slips.append(Slip(1, index + 1, "c2pa", f"webp {name} chunk", Grade.DANGER))
        elif name in ("EXIF", "XMP "):
            slips.append(Slip(1, index + 1, "meta", f"webp {name} chunk", Grade.SIGNAL))
    slips.extend(_trail_scan(data))
    slips.extend(_c2pa_slips(data))
    return slips


def _riff_wash(data: bytes) -> tuple[bytes, list[str]]:
    chunks = _riff_chunks(data)
    if not chunks:
        return data, []
    body = bytearray()
    dropped = 0
    for _, fourcc, payload in chunks:
        drop = fourcc == b"C2PA" or (
            fourcc not in _RIFF_IMAGE and _looks_like_c2pa(payload)
        )
        if not drop and fourcc in (b"EXIF", b"XMP "):
            drop = True
        if drop:
            dropped += 1
            continue
        body += fourcc + struct.pack("<I", len(payload)) + payload
        if len(payload) % 2:
            body += b"\x00"
    if dropped == 0:
        return data, []
    out = bytearray(b"RIFF")
    out += struct.pack("<I", len(body) + 4)
    out += b"WEBP" + bytes(body)
    return bytes(out), ["meta"]


def _generic_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    slips.extend(_trail_scan(data))
    for marker in (
        b"http://ns.adobe.com/xap/1.0/",
        b"Exif\x00\x00",
        b"Photoshop 3.0\x00",
    ):
        index = data.find(marker)
        if index != -1:
            slips.append(
                Slip(
                    1,
                    index + 1,
                    "meta",
                    marker.decode(errors="replace")[:20],
                    Grade.SIGNAL,
                )
            )
    slips.extend(signatures.match(_extract_ascii(data)))
    return slips


def _extract_ascii(data: bytes) -> str:
    runs: list[str] = []
    current: list[bytes] = []
    for byte in data:
        if byte in (9, 10, 13) or 32 <= byte <= 126:
            current.append(bytes((byte,)))
        else:
            if len(current) >= 5:
                runs.append(b"".join(current).decode("latin-1"))
            current = []
    if len(current) >= 5:
        runs.append(b"".join(current).decode("latin-1"))
    return "\n".join(runs)


def _trail_scan(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for marker in _TRAIL_MARKERS:
        index = data.find(marker)
        if index != -1:
            slips.append(
                Slip(
                    1,
                    _line_index(data, index),
                    "c2pa",
                    marker.decode(errors="replace"),
                    Grade.DANGER,
                )
            )
    return slips


def _is_gif(data: bytes) -> bool:
    return data.startswith(b"GIF87a") or data.startswith(b"GIF89a")


def _gif_blocks(data: bytes) -> list[tuple[int, int, int, bytes]]:
    """Return ``(offset, end, label, payload)`` for GIF comment/XMP extensions."""
    if not _is_gif(data) or len(data) < 14:
        return []
    index = 13
    packed = data[10]
    if packed & 0x80:
        index += 3 * (1 << ((packed & 0x07) + 1))
    blocks: list[tuple[int, int, int, bytes]] = []
    while index < len(data):
        marker = data[index]
        if marker == 0x3B:
            break
        if marker == 0x2C:
            if index + 9 >= len(data):
                break
            ipacked = data[index + 9]
            index += 10
            if ipacked & 0x80:
                index += 3 * (1 << ((ipacked & 0x07) + 1))
            if index >= len(data):
                break
            index += 1
            while index < len(data) and data[index] != 0:
                index += data[index] + 1
            index += 1
            continue
        if marker == 0x21 and index + 1 < len(data):
            label = data[index + 1]
            offset = index
            cursor = index + 2
            payload = bytearray()
            while cursor < len(data) and data[cursor] != 0:
                block_len = data[cursor]
                payload += data[cursor + 1 : cursor + 1 + block_len]
                cursor += 1 + block_len
            index = cursor + 1
            if label == 0xFE or (label == 0xFF and payload[:11] == b"XMP DataXMP"):
                blocks.append((offset, index, label, bytes(payload)))
            continue
        break
    return blocks


def _gif_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for offset, _, label, payload in _gif_blocks(data):
        name = "xmp" if label == 0xFF else "comment"
        grade = Grade.DANGER if _looks_like_c2pa(payload) else Grade.SIGNAL
        slips.append(Slip(1, offset + 1, name, f"gif {name} extension", grade))
    slips.extend(_trail_scan(data))
    return slips


def _gif_wash(data: bytes) -> tuple[bytes, list[str]]:
    drops = _gif_blocks(data)
    if not drops:
        return data, []
    out = bytearray()
    cursor = 0
    for start, end, _, _ in drops:
        out += data[cursor:start]
        cursor = end
    out += data[cursor:]
    return bytes(out), ["meta"]


def _is_tiff(data: bytes) -> bool:
    return data.startswith(b"II*\x00") or data.startswith(b"MM\x00*")


@dataclass(frozen=True)
class _TiffTag:
    number: int
    field_type: int
    count: int
    offset: int
    value: bytes
    region: tuple[int, int]


def _tiff_tags(data: bytes) -> list[_TiffTag]:
    """Walk TIFF IFDs (incl. ExifIFD/GPS) returning tag/raw-value entries.

    The returned ``offset`` is the file position of the tag's 4-byte entry,
    and ``value`` is the decoded field (inline or pointed-to). ``region`` is
    the byte range holding the value in the file. Best-effort.
    """
    if not _is_tiff(data) or len(data) < 8:
        return []
    little = data.startswith(b"II")
    fmt = "<" if little else ">"
    if struct.unpack(fmt + "H", data[2:4])[0] != 42:
        return []
    tags: list[_TiffTag] = []
    seen: set[int] = set()
    queue = [struct.unpack(fmt + "I", data[4:8])[0]]
    while queue:
        offset = queue.pop()
        if offset < 8 or offset + 2 > len(data) or offset in seen:
            continue
        seen.add(offset)
        count = struct.unpack(fmt + "H", data[offset : offset + 2])[0]
        cursor = offset + 2
        for _ in range(count):
            if cursor + 12 > len(data):
                break
            number, field_type, item = struct.unpack(
                fmt + "HHI", data[cursor : cursor + 8]
            )
            entry = cursor + 8
            size = _TIFF_TYPE_SIZES.get(field_type, 0) * item
            if size <= 4:
                value = data[entry : entry + 4][:size]
                region = (entry, entry + size)
            else:
                target = struct.unpack(fmt + "I", data[entry : entry + 4])[0]
                value = data[target : target + size]
                region = (target, target + size)
            tags.append(_TiffTag(number, field_type, item, cursor, value, region))
            if number == 34665 and field_type == 4 and item == 1:
                queue.append(struct.unpack(fmt + "I", data[entry : entry + 4])[0])
            if number == 34853 and field_type == 4 and item == 1:
                queue.append(struct.unpack(fmt + "I", data[entry : entry + 4])[0])
            cursor += 12
        if cursor + 4 <= len(data):
            nxt = struct.unpack(fmt + "I", data[cursor : cursor + 4])[0]
            if nxt:
                queue.append(nxt)
    return tags


def _tiff_text(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()


def _is_bmff(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _ISOBMFF_BRANDS


@dataclass(frozen=True)
class _Box:
    btype: bytes
    start: int
    end: int
    header: int


def _bmff_boxes(data: bytes, limit: int = 0, start: int = 0) -> list[_Box]:
    """Walk ISO BMFF boxes at one level, returning header+payload spans."""
    boxes: list[_Box] = []
    cursor = start
    if limit <= 0:
        limit = len(data)
    while cursor + 8 <= limit:
        size = struct.unpack(">I", data[cursor : cursor + 4])[0]
        btype = data[cursor + 4 : cursor + 8]
        header = 8
        if size == 1:
            if cursor + 16 > limit:
                break
            size = struct.unpack(">Q", data[cursor + 8 : cursor + 16])[0]
            header = 16
        elif size == 0:
            size = limit - cursor
        if size < header or cursor + size > limit:
            break
        boxes.append(_Box(btype, cursor, cursor + size, header))
        cursor += size
    return boxes


def _bmff_scan(data: bytes) -> list[tuple[bytes, int, int]]:
    """Return ``(btype, start, end)`` of metadata boxes in the meta atom.

    ISO BMFF meta boxes come right after a top-level ``meta`` FullBox header
    (4 extra bytes). We look for XMP/EXIF/C2PA storages there and at top level.
    """
    found: list[tuple[bytes, int, int]] = []
    for box in _bmff_boxes(data):
        if box.btype == b"meta":
            start = box.start + box.header + 4
            for child in _bmff_boxes(data, limit=box.end, start=start):
                if _bmff_meta_storage(
                    child.btype, data[child.start + child.header : child.end]
                ):
                    found.append((child.btype, child.start + child.header, child.end))
        elif _bmff_meta_storage(box.btype, data[box.start + box.header : box.end]):
            found.append((box.btype, box.start + box.header, box.end))
    return found


def _bmff_meta_storage(btype: bytes, payload: bytes) -> bool:
    if btype == b"uuid":
        return payload.startswith(_BMFF_XMP_UUID) or any(
            marker in payload for marker in _C2PA_MARKERS
        )
    if (
        btype == b"Exif"
        or payload.startswith(b"II*\x00")
        or payload.startswith(b"MM\x00*")
    ):
        return True
    return any(marker in payload for marker in _XMP_BMFF_MARKERS) or _looks_like_c2pa(
        payload
    )


def _bmff_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for btype, start, _end in _bmff_scan(data):
        payload = data[start : start + 16]
        label = btype.decode("latin-1", errors="replace")
        if btype == b"uuid":
            if payload.startswith(_BMFF_XMP_UUID):
                kind, rank = "xmp", Grade.SIGNAL
            elif _looks_like_c2pa(data[start : start + 64]):
                kind, rank = "c2pa", Grade.DANGER
            else:
                kind, rank = "c2pa", Grade.DANGER
        elif btype == b"Exif":
            kind, rank = "exif", Grade.DANGER
        else:
            kind, rank = "xmp", Grade.SIGNAL
        slips.append(Slip(1, start + 1, kind, f"bmff {label} box", rank))
    slips.extend(_trail_scan(data))
    slips.extend(_c2pa_slips(data))
    return slips


def _bmff_wash(data: bytes) -> tuple[bytes, list[str]]:
    found = _bmff_scan(data)
    if not found:
        return data, []
    out = bytearray(data)
    for _btype, start, end in found:
        width = end - start
        if 0 < width <= len(out) - start:
            out[start:end] = b"\x00" * width
    return bytes(out), ["meta"]


def _tiff_audit(data: bytes) -> list[Slip]:
    slips: list[Slip] = []
    for tag in _tiff_tags(data):
        name = _TIFF_TEXT_TAGS.get(tag.number)
        if tag.field_type == 2 and tag.count and name:
            text = _tiff_text(tag.value)
            if not text:
                continue
            strong = _hits_ai_tool(text) or any(
                keyword in tag.value for keyword in _AI_KEYWORDS
            )
            slips.append(
                Slip(
                    1,
                    tag.offset + 1,
                    "exif",
                    f"tiff {name}: {text}"[:48],
                    Grade.DANGER if strong else Grade.SIGNAL,
                )
            )
        elif tag.number == 700:
            is_xmp = b"xmp" in tag.value.lower() or tag.value.startswith(b"<x:")
            if is_xmp:
                rank = Grade.DANGER if _looks_like_c2pa(tag.value) else Grade.SIGNAL
                slips.append(Slip(1, tag.offset + 1, "xmp", "tiff xmp tag", rank))
        elif _looks_like_c2pa(tag.value):
            slips.append(
                Slip(
                    1,
                    tag.offset + 1,
                    "c2pa",
                    f"tiff tag {tag.number}",
                    Grade.DANGER,
                )
            )
    slips.extend(_trail_scan(data))
    slips.extend(_c2pa_slips(data))
    return slips


def _tiff_wash(data: bytes) -> tuple[bytes, list[str]]:
    drops: dict[int, int] = {}
    for tag in _tiff_tags(data):
        if tag.number == 700 or _looks_like_c2pa(tag.value):
            drops[tag.offset] = 12
            left, right = tag.region
            drops[left] = right - left
            continue
        name = _TIFF_TEXT_TAGS.get(tag.number)
        if (
            tag.field_type == 2
            and tag.count
            and name
            and _hits_ai_tool(_tiff_text(tag.value))
        ):
            drops[tag.offset] = 12
            left, right = tag.region
            drops[left] = right - left
    if not drops:
        return data, []
    out = bytearray(data)
    for offset, width in drops.items():
        if offset + width <= len(out):
            out[offset : offset + width] = b"\x00" * width
    return bytes(out), ["meta"]
