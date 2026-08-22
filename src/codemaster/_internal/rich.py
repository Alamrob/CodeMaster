"""Optional rich metadata parsing for images.

Wraps ``piexif`` (EXIF) and ``c2pa-python`` (C2PA) so the structural scanners
in :mod:`codemaster.handlers.image_meta` degrade gracefully when either
library is missing. Every parse is best-effort and never raises.
"""

from __future__ import annotations

import io
import json
from typing import Any

from codemaster import catalog
from codemaster.handlers import _deps

_SOFT_BINDINGS = (
    ("com.adobe.trustmark", "Adobe TrustMark"),
    ("com.adobe.icn", "Adobe (content fingerprint)"),
    ("com.digimarc", "Digimarc"),
    ("com.imatag.lamark", "Imatag (Lamark)"),
    ("ai.steg", "Steg.AI"),
    ("com.microsoft.invismark", "Microsoft InvisMark"),
    ("com.microsoft.wavmark", "Microsoft WavMark"),
    ("com.verimatrix", "Verimatrix"),
    ("com.nagra.nexguard", "NAGRA NexGuard"),
    ("com.aiwatermark", "AIWatermark (Meta PixelSeal)"),
    ("ai.trufo", "Trufo"),
    ("app.overlai", "Overlai"),
    ("es.lumatrace", "LumaTrace"),
)


def exif_pairs(payload: bytes) -> list[tuple[str, str]]:
    """Decode a raw EXIF/TIFF payload into printable ``(tag, value)`` pairs.

    ``payload`` is the raw TIFF structure: a JPEG APP1-EXIF segment payload
    after the ``Exif\\x00\\x00`` prefix, or a PNG ``eXIf`` chunk body. Returns
    an empty list when the payload is not valid EXIF or piexif is absent.
    """
    if not _deps.piexif_ok():
        return []
    piexif = _deps.load("piexif")
    try:
        parsed = piexif.load(payload, key_is_name=True)
    except Exception:
        return []
    pairs: list[tuple[str, str]] = []
    for ifd, tags in parsed.items():
        if ifd == "thumbnail" or not isinstance(tags, dict):
            continue
        for name, value in tags.items():
            text = _as_text(value)
            if text:
                pairs.append((f"{ifd}.{name}", text))
    return pairs


def c2pa_info(data: bytes) -> dict[str, Any] | None:
    """Return structured C2PA provenance claims parsed by the official reader.

    Returns ``None`` when the reader is unavailable, no valid manifest is
    embedded, or parsing fails; callers then fall back to structural byte
    scans. On success returns a dict with any of ``generator``, ``issuer``,
    ``state``, ``actions`` and ``ai``/``enhanced`` flags.
    """
    if not _deps.c2pa_ok():
        return None
    c2pa = _deps.load("c2pa")
    try:
        reader = c2pa.Reader.try_create(io.BytesIO(data))
    except Exception:
        return None
    if reader is None:
        return None
    try:
        store = json.loads(reader.json())
    except Exception:
        return None
    finally:
        reader.close()
    return _store_claims(store)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, tuple):
        parts = [_as_text(part) for part in value]
        return ", ".join(part for part in parts if part)
    return ""


def _store_claims(store: dict[str, Any]) -> dict[str, Any] | None:
    manifest = _active_manifest(store)
    if not manifest:
        return None
    info: dict[str, Any] = {}
    generator = manifest.get("claim_generator")
    if isinstance(generator, str) and generator.isprintable() and generator:
        info["generator"] = generator
    else:
        candidates = manifest.get("claim_generator_info")
        if (
            isinstance(candidates, list)
            and candidates
            and isinstance(candidates[0], dict)
        ):
            name = candidates[0].get("name")
            if isinstance(name, str) and name.isprintable() and name:
                info["generator"] = name
    signature = manifest.get("signature_info")
    if isinstance(signature, dict):
        for key in ("issuer", "common_name"):
            value = signature.get(key)
            if isinstance(value, str) and value:
                info["issuer"] = value
                break
    state = store.get("validation_state")
    if isinstance(state, str) and state:
        info["state"] = state
    actions, ai, enhanced = _action_claims(manifest)
    if actions:
        info["actions"] = actions
    manifest_bytes = json.dumps(store, ensure_ascii=False).encode()
    _provenance_scan(manifest_bytes, info)
    if ai or info.get("ai"):
        info["ai"] = True
    if enhanced or info.get("enhanced"):
        info["enhanced"] = True
    if not any(
        key in info for key in ("generator", "issuer", "actions", "vendor", "state")
    ):
        return None
    return info


def _active_manifest(store: dict[str, Any]) -> dict[str, Any]:
    manifests = store.get("manifests")
    if not isinstance(manifests, dict):
        return {}
    active = manifests.get(store.get("active_manifest"))
    return active if isinstance(active, dict) else {}


def _action_claims(manifest: dict[str, Any]) -> tuple[list[str], bool, bool]:
    actions: list[str] = []
    ai = False
    enhanced = False
    assertions = manifest.get("assertions")
    if not isinstance(assertions, list):
        return actions, ai, enhanced
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        label = assertion.get("label")
        data = assertion.get("data")
        if (
            not isinstance(label, str)
            or not label.startswith("c2pa.actions")
            or not isinstance(data, dict)
        ):
            continue
        for action in _as_actions(data):
            if action:
                actions.append(action)
            if action == "AI-generated":
                ai = True
            elif action == "AI-enhanced":
                enhanced = True
    return list(dict.fromkeys(actions)), ai, enhanced


def _as_actions(data: dict[str, Any]) -> list[str]:
    raw = data.get("actions")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        action = entry.get("action")
        if not isinstance(action, str):
            continue
        label = action.removeprefix("c2pa.")
        source = entry.get("digitalSourceType")
        if isinstance(source, str) and "trainedAlgorithmicMedia" in source:
            label = "AI-generated" if "composite" not in source else "AI-enhanced"
        names.append(label)
    return names


def _provenance_scan(payload: bytes, info: dict[str, Any]) -> None:
    """Derive provenance verdicts by scanning the serialized manifest store."""
    lowered = payload.lower()
    if b"trainedalgorithmicmedia" in lowered:
        if b"compositewithtrainedalgorithmicmedia" in lowered:
            info["enhanced"] = True
        else:
            info["ai"] = True
    if b"watermark" in lowered:
        info["watermarked"] = True
    text = lowered.decode("utf-8", errors="replace")
    for token, org in catalog.REGISTRY.vendors.items():
        if token in text:
            info["vendor"] = org
            break
    model = catalog.REGISTRY.resolve_agent(text)
    if model is not None:
        info["model"] = model
    if b"synthid" in lowered and (info.get("ai") or info.get("enhanced")):
        info["synthid"] = info.get("vendor", "Google")
    soft = [label for token, label in _SOFT_BINDINGS if token.encode() in lowered]
    if soft:
        info["soft_bindings"] = soft
