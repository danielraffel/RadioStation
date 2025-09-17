import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'
PROMPTS_PATH = Path(__file__).resolve().parent / 'prompts.json'
THEMES_PATH = Path(__file__).resolve().parent / 'themes.json'

DEFAULT_ENV = {
    'CLIP_SECONDS': '2',
    'SAMPLES_PER_BANK': '24',
    'NUM_BANKS': '16',
    'MAX_RETRIES_PER_THEME': '0',  # 0 means run until complete
    'SEARCH_RESULTS_PER_THEME': '32',
    'DOWNLOAD_WORKERS': '4',
    'SLICES_PER_VIDEO': '1',
    'SLICE_STRIDE_SECONDS': '2',
    'DOWNLOAD_CHUNK_SECONDS': '10',
    # Downloader acceleration (aria2c via yt-dlp)
    # Conservative settings to avoid YouTube rate limiting
    'ARIA2C_ENABLED': '1',
    'ARIA2C_CONN_PER_SERVER': '4',  # Reduced from 16
    'ARIA2C_SPLIT': '4',  # Reduced from 16  
    'ARIA2C_CHUNK_SIZE': '10M',  # Increased from 1M
    # yt-dlp controls
    'YTDLP_USE_SECTIONS': '1',
    'YTDLP_FORMAT': 'bestaudio[filesize<10M]/bestaudio/best',
    'AUDIO_QUALITY': 'best',  # 'best' or 'worst' - controls audio quality for downloads
    'DOWNLOAD_METHOD': 'smart',  # 'smart', 'segment', or 'aria2c'
    'CONCURRENT_FRAGMENT_DOWNLOADS': '4',
    # Scoring (CLAP)
    'SCORING_ENABLED': '1',
    # Optional explicit model path for CLAP
    'CLAP_MODEL_PATH': '',
    'SCORING_MIN_SIMILARITY': '0.0',
    # Session management
    'SESSION_ID': '',
    # OpenAI integration
    'OPENAI_API_KEY': '',
    'USE_OPENAI_EXPANSION': '0',
    # Words list mode
    'USE_WORDS_LIST': '0',
    'WORDS_MODE': 'one_per_theme',
    'THEME_WORDS_OPT_OUT': '',
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
    """Load .env into os.environ with defaults.
    
    For OPENAI_API_KEY, checks in order:
    1. Already in os.environ (from shell export)
    2. .env file
    3. Default (empty string)
    """
    # First, preserve any existing OPENAI_API_KEY from shell environment
    existing_openai_key = os.environ.get('OPENAI_API_KEY')
    
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # For OPENAI_API_KEY, only set if not already in environment
            if key == 'OPENAI_API_KEY' and existing_openai_key:
                continue
            
            os.environ.setdefault(key, value)
    
    for key, value in DEFAULT_ENV.items():
        # Special handling for OPENAI_API_KEY - preserve shell environment
        if key == 'OPENAI_API_KEY' and existing_openai_key:
            continue
        os.environ.setdefault(key, value)


def save_env(new_values: dict) -> None:
    """Persist config values to .env and os.environ.
    
    Special handling for OPENAI_API_KEY:
    - If empty string provided, removes from .env (will use shell export)
    - If non-empty provided, saves to .env
    """
    data = {**DEFAULT_ENV}
    data.update({k: str(v) for k, v in os.environ.items() if k in DEFAULT_ENV})
    data.update({k: str(v) for k, v in new_values.items() if k in DEFAULT_ENV})
    
    # Build lines, skipping OPENAI_API_KEY if it's empty (to use shell export)
    lines = []
    for k in DEFAULT_ENV:
        if k == 'OPENAI_API_KEY' and not data[k].strip():
            continue  # Skip writing empty API key to .env
        lines.append(f"{k}={data[k]}\n")
    
    ENV_PATH.write_text(''.join(lines))
    
    # Update os.environ, but preserve shell OPENAI_API_KEY if .env value is empty
    for k in DEFAULT_ENV:
        if k == 'OPENAI_API_KEY' and not data[k].strip():
            # Don't override shell export with empty value
            continue
        os.environ[k] = data[k]


def load_prompts() -> list:
    """Load prompts from disk or defaults."""
    if PROMPTS_PATH.exists():
        return json.loads(PROMPTS_PATH.read_text())
    return DEFAULT_PROMPTS


def save_prompts(prompts: list) -> None:
    PROMPTS_PATH.write_text(json.dumps(prompts, indent=2))


def load_themes() -> list:
    """Load themes from themes.json with backward compatibility."""
    if THEMES_PATH.exists():
        themes = json.loads(THEMES_PATH.read_text())
        # Ensure we have exactly 16 themes
        while len(themes) < 16:
            themes.append({
                "name": f"Theme{len(themes)+1}",
                "search": f"Theme{len(themes)+1}",
                "prompt": "Generic sound"
            })
        return themes[:16]
    
    # Backward compatibility: create from env variables and prompts
    themes = []
    prompts_dict = {p['name']: p['prompt'] for p in load_prompts()}
    
    for i in range(1, 17):
        theme_name = os.environ.get(f'THEME{i}', f'Theme{i}')
        themes.append({
            "name": theme_name,
            "search": theme_name,  # Initially use name as search term
            "prompt": prompts_dict.get(theme_name, "Generic sound")
        })
    
    return themes


def save_themes(themes: list) -> None:
    """Save themes to themes.json."""
    THEMES_PATH.write_text(json.dumps(themes, indent=2))
    # Also update env variables for backward compatibility
    for i, theme in enumerate(themes[:16], 1):
        os.environ[f'THEME{i}'] = theme['name']


def get_config() -> dict:
    load_env()
    config = {k: os.environ[k] for k in DEFAULT_ENV}
    
    # Load themes with new structure
    theme_objects = load_themes()
    config['themes'] = theme_objects
    config['theme_names'] = [t['name'] for t in theme_objects]  # For backward compatibility
    
    # Keep prompts for backward compatibility but sync with themes
    config['prompts'] = [{'name': t['name'], 'prompt': t['prompt']} for t in theme_objects]
    
    return config
