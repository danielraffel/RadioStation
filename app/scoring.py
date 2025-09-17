"""CLAP scoring integration (optional).

This module attempts to load the LAION-CLAP model and expose a helper to score
an audio file against a list of text prompts, returning the best-matching theme.

If the `laion_clap` package or model checkpoint is unavailable, scoring can be
disabled by default. Enable with `SCORING_ENABLED=1` and ensure a .pt checkpoint
is present under `models/` or specify `CLAP_MODEL_PATH`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

_model = None
_loaded_path: Optional[Path] = None


def is_enabled() -> bool:
    return os.environ.get("SCORING_ENABLED", "0") in ("1", "true", "True")


def _find_checkpoint() -> Optional[Path]:
    explicit = os.environ.get("CLAP_MODEL_PATH")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    if MODELS_DIR.exists():
        for p in MODELS_DIR.glob("*.pt"):
            return p
    return None


def _ensure_model():
    global _model, _loaded_path
    if _model is not None:
        return
    try:
        from laion_clap import CLAP_Module  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"laion_clap not available: {exc}")
    ckpt = _find_checkpoint()
    if not ckpt:
        raise RuntimeError("No CLAP checkpoint found under models/ or CLAP_MODEL_PATH.")
    
    # For music_speech_audioset_epoch_15_esc_89.98.pt, use HTSAT-base without fusion
    # as specified in the CLAP documentation
    try:
        m = CLAP_Module(enable_fusion=False, amodel='HTSAT-base')
        m.load_ckpt(str(ckpt))
        print(f"CLAP model loaded successfully from {ckpt}")
    except Exception as e:
        # Fallback to default configuration
        try:
            m = CLAP_Module(enable_fusion=False)
            m.load_ckpt(str(ckpt))
            print(f"CLAP model loaded with default config from {ckpt}")
        except Exception as fallback_err:
            raise RuntimeError(f"Failed to load CLAP model {ckpt}. Error: {e}. Fallback error: {fallback_err}")
    
    _model = m
    _loaded_path = ckpt


def best_theme_for_wav(wav_path: Path, prompts: list, themes: List[str]) -> Optional[tuple[str, float]]:
    """Return (best_theme, similarity) using cosine similarity between audio and text embeddings.

    `prompts` is a list of dicts with `name` and `prompt`. We match `themes`
    against prompt names (case-insensitive) and score using those texts.
    """
    if not is_enabled():
        return None
    _ensure_model()
    assert _model is not None
    # Map names to prompts
    name_to_prompt = {p["name"].lower(): p["prompt"] for p in prompts}
    texts: List[str] = []
    theme_names: List[str] = []
    for t in themes:
        key = t.lower()
        if key in name_to_prompt:
            texts.append(name_to_prompt[key])
            theme_names.append(t)
    if not texts:
        return None
    # Compute embeddings
    audio_emb = _model.get_audio_embedding_from_filelist(x=[str(wav_path)], use_tensor=True)
    text_emb = _model.get_text_embedding(texts, use_tensor=True)
    # Normalize and cosine similarity
    import torch

    a = torch.nn.functional.normalize(audio_emb, dim=-1)  # (1, d)
    t = torch.nn.functional.normalize(text_emb, dim=-1)   # (N, d)
    sims = (a @ t.T).squeeze(0)  # (N,)
    best_idx = int(torch.argmax(sims).item())
    best_score = float(sims[best_idx].item())
    return theme_names[best_idx], best_score
