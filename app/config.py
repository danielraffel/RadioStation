import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'
PROMPTS_PATH = Path(__file__).resolve().parent / 'prompts.json'

DEFAULT_ENV = {
    'CLIP_SECONDS': '2',
    'SAMPLES_PER_BANK': '24',
    'NUM_BANKS': '16',
    'MAX_RETRIES_PER_THEME': '0',  # 0 means run until complete
    'THEME1': 'Soft',
    'THEME2': 'Loud',
    'THEME3': 'Bumpy',
    'THEME4': 'Smooth',
    'THEME5': 'Harsh',
    'THEME6': 'Warm',
    'THEME7': 'Bright',
    'THEME8': 'Dark',
    'THEME9': 'Metallic',
    'THEME10': 'Woody',
    'THEME11': 'Airy',
    'THEME12': 'Noisy',
    'THEME13': 'Percussive',
    'THEME14': 'Sustained',
    'THEME15': 'Glitchy',
    'THEME16': 'Eerie',
}

DEFAULT_PROMPTS = [
    {"name": "Soft", "prompt": "Quiet, gentle, low-intensity sound like a whisper or fabric brushing. Smooth, not harsh or piercing."},
    {"name": "Loud", "prompt": "Booming, powerful, high-volume sound that dominates space. Strong transients and presence."},
    {"name": "Bumpy", "prompt": "Uneven, jolting, irregular percussive texture like a train on rough tracks; not smooth."},
    {"name": "Smooth", "prompt": "Continuous, flowing, connected sound without rough edges. Even dynamics and rounded timbre."},
    {"name": "Harsh", "prompt": "Rough, grating, distorted or metallic noise; aggressive highs. Unpleasant or biting character."},
    {"name": "Warm", "prompt": "Full, rounded low-mids, gentle highs; cozy and intimate. Not thin or brittle."},
    {"name": "Bright", "prompt": "Emphasized highs and detail; crisp and shiny. Not dark or muffled."},
    {"name": "Dark", "prompt": "Subdued highs, weight in lows/low-mids; shadowy or muted. Not bright or sparkly."},
    {"name": "Metallic", "prompt": "Ringing, resonant metal tones; clangs, scrapes, chimes. Distinct overtones and sheen."},
    {"name": "Woody", "prompt": "Organic, resonant wood timbre like knocks, taps, or acoustic bodies. Warm transients."},
    {"name": "Airy", "prompt": "Breath, wind, or subtle high-frequency shimmer. Light, spacious, and diffuse."},
    {"name": "Noisy", "prompt": "Broadband or narrow-band noise textures (hiss, static). Texture over pitch."},
    {"name": "Percussive", "prompt": "Short, transient-rich hits or sequences; clear onsets. Minimal sustain."},
    {"name": "Sustained", "prompt": "Long, held tones or pads with steady energy. Minimal transient emphasis."},
    {"name": "Glitchy", "prompt": "Digital artifacts, stutters, buffer errors, granular pops. Non-linear rhythm."},
    {"name": "Eerie", "prompt": "Unsettling, mysterious ambience; dissonant or hollow. Suggests tension or space."},
]


def load_env() -> None:
    """Load .env into os.environ with defaults."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())
    for key, value in DEFAULT_ENV.items():
        os.environ.setdefault(key, value)


def save_env(new_values: dict) -> None:
    """Persist config values to .env and os.environ."""
    data = {**DEFAULT_ENV}
    data.update({k: str(v) for k, v in os.environ.items() if k in DEFAULT_ENV})
    data.update({k: str(v) for k, v in new_values.items() if k in DEFAULT_ENV})
    lines = [f"{k}={data[k]}\n" for k in DEFAULT_ENV]
    ENV_PATH.write_text(''.join(lines))
    for k in DEFAULT_ENV:
        os.environ[k] = data[k]


def load_prompts() -> list:
    """Load prompts from disk or defaults."""
    if PROMPTS_PATH.exists():
        return json.loads(PROMPTS_PATH.read_text())
    return DEFAULT_PROMPTS


def save_prompts(prompts: list) -> None:
    PROMPTS_PATH.write_text(json.dumps(prompts, indent=2))


def get_config() -> dict:
    load_env()
    config = {k: os.environ[k] for k in DEFAULT_ENV}
    config['themes'] = [os.environ[f'THEME{i}'] for i in range(1, 17)]
    config['prompts'] = load_prompts()
    return config

