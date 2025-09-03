"""Download and process audio clips from YouTube using yt-dlp and pydub."""

from pathlib import Path
import glob

from yt_dlp import YoutubeDL
from pydub import AudioSegment, effects

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "wavs" / "raw"
THEMED_DIR = BASE_DIR / "wavs" / "themed"


def _ydl_opts(term: str) -> dict:
    return {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "paths": {"home": str(RAW_DIR)},
        "outtmpl": {"default": f"{term}_%(id)s.%(ext)s"},
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }


def _process_file(path: Path, theme: str, clip_ms: int) -> None:
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
    """Download one clip for search term and store processed clip under theme folder."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ydl = YoutubeDL(_ydl_opts(term))
    ydl.download([f"ytsearch1:{term}"])
    for filepath in glob.glob(str(RAW_DIR / f"{term}_*.wav")):
        _process_file(Path(filepath), theme, clip_ms)
