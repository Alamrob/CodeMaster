from __future__ import annotations

from codemaster import catalog
from codemaster.report import Grade
from codemaster.signatures import match


def test_catalog_has_groups() -> None:
    assert {"llm", "image", "video", "audio", "code"} <= set(catalog.REGISTRY.groups)


def test_catalog_many_models() -> None:
    assert len(catalog.REGISTRY.models) >= 60
    names = {m.name for m in catalog.REGISTRY.models}
    assert {"chatgpt", "claude", "gemini", "midjourney", "sora", "suno"} <= names


def test_catalog_phrases_loaded() -> None:
    assert "authorship" in catalog.REGISTRY.phrases
    assert "narration" in catalog.REGISTRY.phrases
    assert "fragment" in catalog.REGISTRY.phrases


def test_resolve_agent_maps_generator() -> None:
    assert catalog.REGISTRY.resolve_agent("Image Generator - gpt-4o") == "gpt-4o"
    assert catalog.REGISTRY.resolve_agent("com.adobe.firefly") == "firefly"
    assert catalog.REGISTRY.resolve_agent("unrelated tool") is None


def test_vendors_present() -> None:
    assert len(catalog.REGISTRY.vendors) >= 10


def test_llm_models_match() -> None:
    slips = match("uses claude for the summary")
    assert any(s.kind == "model" and s.rank is Grade.SIGNAL for s in slips)


def test_video_model_matches() -> None:
    slips = match("prompt for sora video generation")
    assert any(s.kind == "model" for s in slips)


def test_audio_model_matches() -> None:
    slips = match("voice cloned with elevenlabs")
    assert any(s.kind == "model" for s in slips)


def test_code_model_matches() -> None:
    slips = match("refactor using github copilot")
    assert any(s.kind == "model" for s in slips)


def test_image_model_matches() -> None:
    slips = match("image made with stable diffusion")
    assert any(s.kind == "model" for s in slips)


def test_clean_text_still_silent() -> None:
    assert match("def compute():\n    return 1\n") == []


def test_model_named_similar_word_not_flagged() -> None:
    # "ollama" should not match a bare "llama" boundary pattern
    slips = match("run model via ollama server")
    assert not any(s.kind == "model" for s in slips)
