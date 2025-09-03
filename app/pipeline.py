"""Pipeline to fill themed banks with scored clips."""

import os
from pathlib import Path
from typing import List

from .config import load_env, load_prompts
from .downloader import download_candidates_for_term
from . import scoring

BASE_DIR = Path(__file__).resolve().parent.parent
THEMED_DIR = BASE_DIR / "wavs" / "themed"
PROCESSED_DIR = BASE_DIR / "wavs" / "processed" / "candidates"


def _count_in_bank(theme: str) -> int:
    d = THEMED_DIR / theme
    if not d.exists():
        return 0
    return len([p for p in d.glob("*.wav")])


def _move_to_theme(path: Path, theme: str) -> Path:
    out_dir = THEMED_DIR / theme
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / path.name
    # ensure no overwrite
    i = 1
    while out_path.exists():
        out_path = out_dir / f"{path.stem}_{i}{path.suffix}"
        i += 1
    path.replace(out_path)
    return out_path


def _assign_with_scoring(wav_path: Path, themes: List[str], prompts: list, min_sim: float) -> tuple[str | None, float | None]:
    """Return (best_theme, score) using CLAP scoring; None if below threshold.

    Falls back to the first provided theme if scoring is disabled.
    """
    if scoring.is_enabled():
        try:
            res = scoring.best_theme_for_wav(wav_path, prompts, themes)
            if res:
                name, score = res
                if score is not None and score < min_sim:
                    return None, score
                return name, score
        except Exception as _exc:  # noqa: BLE001
            # fall back to original theme if scoring fails
            return themes[0], None
    # fallback: keep by search term – caller passes the intended target theme name
    return themes[0], None


def run_pipeline(stop_cb=None, progress_cb=None, log_cb=None):
    """Download, score, and organize clips until banks are filled.

    stop_cb: optional callable returning True when a stop has been requested.
    progress_cb: optional callable receiving a dict of live progress.
    """
    load_env()
    prompts = load_prompts()
    clip_ms = int(os.environ['CLIP_SECONDS']) * 1000
    samples_per_bank = int(os.environ['SAMPLES_PER_BANK'])
    max_retries = int(os.environ.get('MAX_RETRIES_PER_THEME', '0'))
    search_batch = int(os.environ.get('SEARCH_RESULTS_PER_THEME', '32'))
    download_workers = int(os.environ.get('DOWNLOAD_WORKERS', '4'))
    slices_per_video = int(os.environ.get('SLICES_PER_VIDEO', '1'))
    slice_stride_ms = int(float(os.environ.get('SLICE_STRIDE_SECONDS', os.environ['CLIP_SECONDS'])) * 1000)
    min_sim = float(os.environ.get('SCORING_MIN_SIMILARITY', '0.0'))

    themes = [os.environ[f'THEME{i}'] for i in range(1, 17)]

    results = {t: _count_in_bank(t) for t in themes}
    retries = {t: 0 for t in themes}

    def emit_progress(current_theme=None, note: str | None = None):
        if not progress_cb:
            return
        banks_completed = sum(1 for t in themes if results[t] >= samples_per_bank)
        overall_filled = sum(results.values())
        overall_target = samples_per_bank * len(themes)
        percent = int(100 * overall_filled / overall_target) if overall_target else 100
        payload = {
            'themes': themes,
            'filled': dict(results),
            'retries': dict(retries),
            'target_per_bank': samples_per_bank,
            'banks_completed': banks_completed,
            'total_banks': len(themes),
            'overall_filled': overall_filled,
            'overall_target': overall_target,
            'percent': percent,
            'current_theme': current_theme,
        }
        if note:
            payload['note'] = note
        progress_cb(payload)

    for idx, term in enumerate(themes):
        emit_progress(current_theme=term, note=f"Processing {term}")
        if stop_cb and stop_cb():
            break
        target_theme = term
        while results[target_theme] < samples_per_bank:
            if stop_cb and stop_cb():
                break
            if max_retries and retries[target_theme] >= max_retries:
                break
            # download candidates for this term
            candidates = download_candidates_for_term(
                term,
                clip_ms=clip_ms,
                max_results=search_batch,
                download_workers=download_workers,
                slices_per_video=slices_per_video,
                slice_stride_ms=slice_stride_ms,
                log_cb=log_cb,
            )
            if not candidates:
                # nothing new came in; stop to avoid tight loop
                if log_cb:
                    log_cb(f"No new candidates for {term}")
                break
            for cand in candidates:
                if stop_cb and stop_cb():
                    break
                # best_theme uses scoring if enabled; otherwise assigns to target_theme
                best_theme, score = _assign_with_scoring(cand, [target_theme] + [t for t in themes if t != target_theme], prompts, min_sim)
                if best_theme is None:
                    # below threshold, treat as unmatched and discard
                    cand.unlink(missing_ok=True)
                    retries[target_theme] += 1
                    if log_cb:
                        log_cb(f"Discarded {cand.name} (score {score:.3f} < {min_sim:.3f})")
                    continue
                _move_to_theme(cand, best_theme)
                if log_cb:
                    log_cb(f"Assigned {cand.name} -> {best_theme} (score {score if score is not None else 'n/a'})")
                if best_theme == target_theme:
                    results[target_theme] += 1
                else:
                    retries[target_theme] += 1
                if results[target_theme] >= samples_per_bank:
                    break
                emit_progress(current_theme=term)

    final = {
        'themes': themes,
        'clip_ms': clip_ms,
        'prompts': prompts,
        'filled': results,
        'retries': retries,
        'scoring_enabled': scoring.is_enabled(),
    }
    emit_progress(current_theme=None)
    return final


if __name__ == '__main__':
    result = run_pipeline()
    print(result)
