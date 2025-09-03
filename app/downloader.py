"""Download and process audio clips from YouTube using yt-dlp and pydub.

Two modes:
- download_candidates_for_term(): produce processed candidate clips in
  `wavs/processed/candidates/` for later scoring/assignment.
- download_and_process(): legacy helper that downloads one and drops into a
  themed folder directly (kept for compatibility).
"""

from pathlib import Path
import glob
import os
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from yt_dlp import YoutubeDL
from pydub import AudioSegment, effects

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "wavs" / "raw"
PROCESSED_DIR = BASE_DIR / "wavs" / "processed" / "candidates"
THEMED_DIR = BASE_DIR / "wavs" / "themed"


def _ydl_opts(term: str, max_results: int = 1, clip_ms: int | None = None, logger=None) -> dict:
    # Optional aria2c acceleration
    use_aria = os.environ.get("ARIA2C_ENABLED", "1") not in ("0", "false", "False")
    aria_args = []
    if use_aria:
        conn = os.environ.get("ARIA2C_CONN_PER_SERVER", "16")
        split = os.environ.get("ARIA2C_SPLIT", "16")
        chunk = os.environ.get("ARIA2C_CHUNK_SIZE", "1M")
        aria_args = [
            "-x", str(conn),
            "-s", str(split),
            "-k", str(chunk),
        ]

    # Prefer smaller audio when possible to reduce raw size
    ytdlp_format = os.environ.get("YTDLP_FORMAT", "bestaudio[filesize<10M]/bestaudio/best")

    opts = {
        "format": ytdlp_format,
        "noplaylist": True,
        "quiet": True,
        "paths": {"home": str(RAW_DIR)},
        "outtmpl": {"default": f"{term}_%(id)s.%(ext)s"},
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }

    if use_aria:
        opts["external_downloader"] = "aria2c"
        if aria_args:
            opts["external_downloader_args"] = aria_args

    # Limit downloads to just the first clip duration when supported
    use_sections = os.environ.get("YTDLP_USE_SECTIONS", "1") not in ("0","false","False")
    if use_sections and clip_ms is not None and clip_ms > 0:
        sec = max(1, int(round(clip_ms/1000)))
        # Format as 0-SS for yt-dlp --download-sections
        opts["download_sections"] = [f"*0-{sec}"]
        # Also speed up fragmented downloads
        try:
            opts["concurrent_fragment_downloads"] = int(os.environ.get("CONCURRENT_FRAGMENT_DOWNLOADS", "4"))
        except Exception:
            pass
    if logger is not None:
        opts["logger"] = logger

    # Use ytsearchN to fetch multiple results when requested
    opts["_search_count"] = int(max_results)
    return opts


def _process_to_candidate(path: Path, clip_ms: int) -> Path | None:
    sound = AudioSegment.from_file(path, "wav")
    if len(sound) < clip_ms:
        path.unlink(missing_ok=True)
        return None
    clip = sound[:clip_ms]
    fade = clip_ms // 4
    clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / path.name
    clip.export(out_path, format="wav")
    path.unlink(missing_ok=True)
    return out_path


def _process_to_candidate_slices(path: Path, clip_ms: int, slices_per_video: int, slice_stride_ms: int) -> List[Path]:
    """Produce up to N slices per video, sequentially with given stride."""
    sound = AudioSegment.from_file(path, "wav")
    out: List[Path] = []
    if len(sound) < clip_ms:
        path.unlink(missing_ok=True)
        return out
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    taken = 0
    start = 0
    while taken < slices_per_video and start + clip_ms <= len(sound):
        clip = sound[start:start+clip_ms]
        fade = clip_ms // 4
        clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
        suffix = f"_s{taken+1}"
        out_path = PROCESSED_DIR / f"{path.stem}{suffix}{path.suffix}"
        clip.export(out_path, format="wav")
        out.append(out_path)
        taken += 1
        start += max(slice_stride_ms, 1)
    path.unlink(missing_ok=True)
    return out


def _extract_search(term: str, max_results: int, logger=None) -> List[Tuple[str, str]]:
    """Return list of (video_id, url) for search results."""
    ydl = YoutubeDL(_ydl_opts(term, max_results=max_results, logger=logger))
    info = ydl.extract_info(f"ytsearch{int(max_results)}:{term}", download=False)
    entries = info.get("entries") or []
    results: List[Tuple[str, str]] = []
    for e in entries:
        vid = e.get("id")
        url = e.get("webpage_url") or e.get("url")
        if vid and url:
            results.append((vid, url))
    return results


def _download_one(url: str, term: str, vid: str, clip_ms: int, logger=None) -> Path | None:
    """Download a single url and return expected wav path if present."""
    ydl = YoutubeDL(_ydl_opts(term, max_results=1, clip_ms=clip_ms, logger=logger))
    try:
        ydl.download([url])
    except Exception:
        return None
    p = RAW_DIR / f"{term}_{vid}.wav"
    return p if p.exists() else None


def download_candidates_for_term(
    term: str,
    clip_ms: int = 2000,
    max_results: int = 1,
    download_workers: int = 1,
    slices_per_video: int = 1,
    slice_stride_ms: int = None,
    log_cb=None,
) -> List[Path]:
    """Download up to max_results items in parallel and return candidate slice paths."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if slice_stride_ms is None:
        slice_stride_ms = clip_ms
    # optional yt-dlp logger that forwards to pipeline logs
    logger = None
    if log_cb is not None:
        class YDLLogger:
            def debug(self, msg):
                try:
                    txt = str(msg)
                except Exception:
                    txt = "(debug msg)"
                if not txt.startswith('[debug] '):
                    log_cb(txt)
            def info(self, msg):
                log_cb(str(msg))
            def warning(self, msg):
                log_cb("WARN: " + str(msg))
            def error(self, msg):
                log_cb("ERROR: " + str(msg))
        logger = YDLLogger()
    items = _extract_search(term, max_results, logger=logger)
    candidates: List[Path] = []
    if not items:
        return candidates
    workers = max(1, int(download_workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_download_one, url, term, vid, clip_ms, logger=logger) for (vid, url) in items]
        for fut in as_completed(futs):
            wav_path = fut.result()
            if wav_path and wav_path.exists():
                slices = _process_to_candidate_slices(wav_path, clip_ms, int(slices_per_video), int(slice_stride_ms))
                candidates.extend(slices)
    return candidates


def _process_file_legacy(path: Path, theme: str, clip_ms: int) -> None:
    sound = AudioSegment.from_file(path, "wav")
    if len(sound) < clip_ms:
        path.unlink(missing_ok=True)
        return
    clip = sound[:clip_ms]
    fade = clip_ms // 4
    clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
    out_dir = THEMED_DIR / theme
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / path.name
    clip.export(out_path, format="wav")
    path.unlink(missing_ok=True)


def download_and_process(term: str, theme: str, clip_ms: int = 2000) -> None:
    """Legacy: download one clip and store under the given theme folder."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ydl = YoutubeDL(_ydl_opts(term, max_results=1))
    ydl.download([f"ytsearch1:{term}"])
    for filepath in glob.glob(str(RAW_DIR / f"{term}_*.wav")):
        _process_file_legacy(Path(filepath), theme, clip_ms)
