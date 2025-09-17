# RadioStation

RadioStation helps you create custom audio sample banks for music production by harvesting and organizing clips from YouTube. Define your own search terms and themes to build personalized sound libraries tailored to your creative needs.

The pipeline automatically:

* searches YouTube using your custom search terms for each theme (supports 1-16 themes)
* downloads audio efficiently (only segments from long videos to save bandwidth)
* processes each download into multiple short clips (duration configurable, default 2 seconds)
* optionally uses the [CLAP](https://github.com/laion-ai/CLAP) model to score clips and assign them to the best-matching theme

The system is fully customizable:
- **Number of themes**: Use 1-16 themes (NUM_BANKS, default 16, max 16)
- **Samples per theme**: Set how many samples to collect per theme (SAMPLES_PER_BANK, default 24)
- **Clip duration**: Adjust the length of each clip (CLIP_SECONDS, default 2 seconds)
- **Search terms**: Define custom YouTube searches for each theme
- **CLAP prompts**: Optionally provide text prompts for AI-powered audio matching

Running `python3 manage.py run` fills your theme folders in `wavs/sessions/{session_id}/themes/`, creating a organized sample library ready for your DAW or sampler.

## How it works

1. The pipeline searches YouTube for audio matching your themes using [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).
2. Smart download mode optimizes bandwidth - for long videos, only downloads a small segment from the center.
3. Each video download can be processed into one or multiple clips (default: 1 clip of 2 seconds per video, re-configurable via `SLICES_PER_VIDEO` for number of clips and `CLIP_SECONDS` for duration).
4. Processed clips are temporarily stored in `wavs/processed/candidates/` for evaluation.
5. Optional: The CLAP model scores each candidate clip against all theme prompts to find the best match (disabled by default with `SCORING_ENABLED=0`).
6. Clips are moved from candidates to `wavs/sessions/{session_id}/themes/<THEME>/` and renamed sequentially.
7. The pipeline continues until each theme folder reaches the target sample count.

## Quick Start

```bash
git clone https://github.com/danielraffel/RadioStation.git
cd RadioStation
cp .env.example .env
python3 manage.py setup
```

This will:

- create your configuration file from the example template
- create a local virtual environment in `.venv` using `uv`
- install Python dependencies
- download the CLAP model into `models/` (see Model Auth below)
- start the server and open the UI: http://127.0.0.1:8000

From the web page you can edit settings and click “Run pipeline” to kick it off. A status panel shows whether it’s running and the last result/error. Use the “Stop” button to cancel a running job.

By default, the pipeline fills each theme bank up to `SAMPLES_PER_BANK` (24) using up to `SEARCH_RESULTS_PER_THEME` results per iteration.

## Setup

```bash
python3 manage.py setup
```
This checks for [uv](https://github.com/astral-sh/uv), installs it if missing, installs Python requirements and downloads the CLAP model into `models/`.  The audio pipeline relies on [yt-dlp](https://github.com/yt-dlp/yt-dlp), [pydub](https://github.com/jiaaro/pydub) and a system `ffmpeg` binary for trimming and format conversion.

If your model is hosted on Hugging Face and requires authentication or gated access, set one of these environment variables so the downloader can add the proper Authorization header:

- `HF_TOKEN`
- `HUGGINGFACE_HUB_TOKEN`
- `HUGGINGFACEHUB_API_TOKEN`
- `HUGGINGFACE_TOKEN`

Example:

```bash
export HF_TOKEN=hf_xxx_your_token
python3 manage.py setup
```

To skip model downloading entirely (e.g., using a local checkpoint later), run either:

```bash
python3 manage.py setup --skip-model
# or
python3 manage.py setup --model-url skip
```

### Start the web server

```bash
python3 manage.py start
```
Visit [http://127.0.0.1:8000](http://127.0.0.1:8000). The page includes:
- a form to edit config and prompts
- a “Run pipeline” button, a Stop button, and a status panel

### Stop the web server

```bash
python3 manage.py stop
```

## Run the sample pipeline (CLI)

Use the same environment that `setup` created. EITHER run via `uv`:

```bash
uv run python3 manage.py run
```

Or activate the virtual environment first:

```bash
source .venv/bin/activate
python3 manage.py run
```

The pipeline keeps downloading and classifying audio until all banks reach the
target sample count. If a download fails to map to a theme after CLAP scoring,
it retries. By default it will keep trying until every bank is full. Set
`MAX_RETRIES_PER_THEME` in the `.env` file (or via the web page) to limit how
many unmatched downloads are attempted before giving up.

## Run the pipeline (Web)

- Start the server (`python3 manage.py start`) and open http://127.0.0.1:8000
- Click “Run pipeline”; use “Refresh status” to view progress/errors. Click “Stop” to cancel.

## Demo: generate WAV and move files

```bash
python3 manage.py demo
```
Creates a demo WAV and moves it through `wavs/raw` → `wavs/processed/candidates` → `wavs/themed/demo/`.

## Model auth and customization

Pass `--model-url` to `setup` to download a different model.

```bash
python3 manage.py setup --model-url https://example.com/model.pt
```

For private Hugging Face repos, ensure you export a token (see above). If you encounter HTTP 401/403 during download, the setup will continue but the model file will not be present until you provide access or use a public URL.

You can also skip model downloading if you want to provide a local checkpoint later:

```bash
python3 manage.py setup --skip-model
# or
python3 manage.py setup --model-url skip
```

## Project Layout

```
app/                FastAPI app and static front end
manage.py           utility script
models/             downloaded model checkpoints
wavs/               audio folders (see below for structure)
```

## Audio Folder Structure

The `wavs/` directory contains all audio processing stages:

### During Processing (Temporary)
```
wavs/
├── raw/                     # Initial downloads from YouTube (temporary)
├── processed/
│   └── candidates/          # Processed clips awaiting organization
└── sessions/
    └── {session_id}/        # Session-specific output
```

### Final Output Structure

**WITH CLAP Scoring Enabled:**
```
wavs/sessions/{session_id}/
└── themes/
    ├── Soft/
    │   ├── Soft_001.wav     # Clips scored and assigned to best-matching theme
    │   ├── Soft_002.wav     # May include clips from ANY theme's searches
    │   └── ...
    ├── Loud/
    ├── Bumpy/
    └── ... (16 themes total)
```
Files are scored across ALL themes and moved to the best-matching theme folder. A clip searched under "Soft" might score higher for "Dark" and be placed there instead.

**WITHOUT CLAP Scoring:**
```
wavs/sessions/{session_id}/
└── themes/
    ├── Soft/
    │   ├── Soft_001.wav     # Clips from Soft theme searches only
    │   ├── Soft_002.wav     # No cross-theme scoring
    │   └── ...
    ├── Loud/
    ├── Bumpy/
    └── ... (16 themes total)
```
Files are moved to their search theme folder without scoring. Clips searched under "Soft" always go to the Soft folder.

**Note:** The `raw/` and `processed/candidates/` folders are temporary working directories. All final outputs are organized in `wavs/sessions/{session_id}/themes/` regardless of CLAP being enabled.

## Configuration (.env and Web UI)

Runtime settings live in the `.env` file and are exposed on the web page at
`/`. Important keys:

| variable | default | description |
| --- | --- | --- |
| `CLIP_SECONDS` | `2` | length of each generated clip |
| `SAMPLES_PER_BANK` | `24` | number of samples to collect for each theme |
| `NUM_BANKS` | `16` | how many themed banks are used |
| `MAX_RETRIES_PER_THEME` | `0` | unmatched downloads to attempt before stopping (`0` = run until complete) |
| `SEARCH_RESULTS_PER_THEME` | `32` | how many search results to process per iteration |
| `DOWNLOAD_WORKERS` | `4` | concurrent downloads per theme batch (max: 10) |
| `SLICES_PER_VIDEO` | `1` | number of clips to extract from each video (creates _s1, _s2, etc.) |
| `SLICE_STRIDE_SECONDS` | `1` | step between slices (seconds) |
| `DOWNLOAD_CHUNK_SECONDS` | `10` | segment size in seconds; also the threshold for smart mode |
| `AUDIO_QUALITY` | `best` | audio quality: `best` or `worst` |
| `DOWNLOAD_METHOD` | `smart` | download method: `smart`, `segment`, or `aria2c` |
| `ARIA2C_ENABLED` | `1` | use `aria2c` as external downloader for speed |
| `ARIA2C_CONN_PER_SERVER` | `4` | aria2c `-x` connections per server (max: 16, conservative default) |
| `ARIA2C_SPLIT` | `4` | aria2c `-s` split count (max: 16, conservative default) |
| `ARIA2C_CHUNK_SIZE` | `10M` | aria2c chunk size `-k` (larger = fewer requests) |
| `SCORING_ENABLED` | `0` | disable CLAP scoring and routing |
| `CLAP_MODEL_PATH` | `''` | override path to CLAP checkpoint (otherwise auto-detected under `models/`) |
| `THEME1`..`THEME16` | *(varies)* | search terms used for YouTube downloads and themed folders |

The web UI lets you edit these values, the 16 theme search terms, and the theme prompts. Saving the form writes updates back to `.env` and `app/themes.json` so future runs use them.

### How Downloads Work

#### Smart Mode (default - recommended)
Automatically chooses the most efficient download method based on video length:

- **For long videos** (longer than segment size): Uses **ffmpeg** to download ONLY a segment from the center
  - Example: 2-hour podcast → downloads only 10 seconds from the middle
  - Saves bandwidth and time by avoiding unnecessary downloads
  - aria2c is NOT used (it can't do partial downloads)

- **For short videos** (equal or shorter than segment size): Downloads the entire video
  - Example: 8-second clip → downloads all 8 seconds
  - May use **aria2c** if enabled for faster download speeds
  - Then trims to final clip length

The segment size (default 10 seconds) acts as the threshold. Videos longer than this use segments, shorter ones download fully.

#### Segment Mode (force ffmpeg)
- Always uses **ffmpeg** to download segments from video centers
- Downloads exactly the "segment size" amount regardless of video length
- Most efficient for consistently long videos
- aria2c is never used in this mode

#### Full Download Mode (force aria2c)
- Always uses **aria2c** accelerator for maximum speed
- Downloads entire video files, then trims to clip length
- Fast but inefficient - a 2-hour video means downloading 2 hours of content!
- Only recommended for short videos where speed is critical

#### Key Points
- **ffmpeg**: Can download specific segments (efficient for long videos)
- **aria2c**: Fast parallel downloader but must download entire files
- Smart mode prevents downloading gigabytes when you only need seconds
- Segment size must be ≥ clip duration (automatically enforced)

#### Real-World Example
With default settings (2-second clips, 10-second segments):
```
Video Length    Smart Mode Action                   Data Downloaded
5 seconds   →   Full download (may use aria2c)  →  5 seconds
10 seconds  →   Full download (may use aria2c)  →  10 seconds
30 seconds  →   ffmpeg segment from center      →  10 seconds only
2 hours     →   ffmpeg segment from center      →  10 seconds only!
```
Without smart segments, that 2-hour video would download 7,200 seconds of data!

### Audio Quality

- **Best**: Higher quality audio using `bestaudio` format (~0.06 MB per 5 seconds)
- **Worst**: Smaller file sizes using `worstaudio` format (~0.03 MB per 5 seconds)

### Multiple Slices Per Video

When `SLICES_PER_VIDEO` is greater than 1, the system extracts multiple segments from the same video. This creates temporary files with suffixes like `_s1`, `_s2`, etc. in the candidates folder. This is intentional and helps generate variety from longer videos. The URL deduplication prevents downloading the same video multiple times, but allows extracting multiple unique segments.

These slice indicators are only used during processing. Final files in theme folders are numbered sequentially (e.g., `Soft_001.wav`, `Soft_002.wav`).

See `Spec.md` for the full vision.

## Prerequisites

- Python 3.12+
- `ffmpeg` installed and on your `PATH`. Example (macOS): `brew install ffmpeg`
- Optional: [`aria2`](https://aria2.github.io/) for faster downloads. Example (macOS): `brew install aria2`
- Optional (for CLAP scoring): install PyTorch + laion-clap. Example:

```bash
# macOS/CPU quick start (adjust for your platform/GPU)
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
uv pip install laion-clap
export SCORING_ENABLED=1
# ensure a .pt checkpoint exists in models/ or set CLAP_MODEL_PATH
```

## Troubleshooting

- ModuleNotFoundError (e.g., `yt_dlp`): run the CLI via `uv` (`uv run python3 manage.py run`) or activate `.venv` first. Running `python3 manage.py run` with the system Python can't see the project's venv packages.
- HTTP 401/403 on model download: export a Hugging Face token, or use a public URL, or skip model download during setup.
- ffmpeg not found: install via your package manager and ensure it's on `PATH`.
- CLAP not used: enable `SCORING_ENABLED=1` and install PyTorch + `laion-clap`; also ensure the checkpoint file exists in `models/`.

## FAQ

### Why does RadioStation use ffmpeg instead of aria2c for downloading segments?

While **aria2c** is excellent for parallel downloads and can significantly speed up full file downloads, it has a critical limitation: **it cannot download specific time segments from videos**. When you need just 10 seconds from a 2-hour video:

- **ffmpeg**: Downloads ONLY the 10-second segment you need (efficient!)
- **aria2c**: Must download the entire 2-hour file first, then extract the segment (inefficient!)

For a typical 2-hour podcast:
- With ffmpeg segments: ~2MB downloaded
- With aria2c full download: ~200MB downloaded (100x more!)

**Note**: ffmpeg downloads segments sequentially (not parallelized), but the bandwidth savings far outweigh the speed benefits of parallel downloading when working with long videos.

### How do I avoid YouTube rate limiting or account issues?

**Important**: Avoid using yt-dlp without authentication as it may trigger rate limits. If you need to authenticate:

1. **Use a non-critical Google account** - There's always a risk of the account being rate-limited or banned
2. **Never use your primary account** for automated downloading

### How do I authenticate yt-dlp with YouTube?

YouTube requires cookies for authentication since yt-dlp cannot handle Google's OAuth flow. See the [official yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) for details.

#### Method 1: Export cookies from your browser (Recommended)

1. Install a cookies exporter extension:
   - Chrome: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. Log into YouTube in your browser

3. Export cookies to a file (e.g., `cookies.txt`)

4. Use with RadioStation:
   ```bash
   export YTDLP_COOKIES_PATH=/path/to/cookies.txt
   python3 manage.py run
   ```

#### Method 2: Use cookies directly from browser

yt-dlp can read cookies directly from your browser:

```bash
# For Chrome
yt-dlp --cookies-from-browser chrome "URL"

# For Firefox
yt-dlp --cookies-from-browser firefox "URL"

# With specific profile
yt-dlp --cookies-from-browser "chrome:Profile 1" "URL"
```

To use with RadioStation, you'll need to modify the downloader settings in `app/downloader.py` to include the cookies parameter.

**⚠️ Security Note**: Never share your cookies file as it contains your session authentication. Add `*.txt` and specifically `cookies.txt` to your `.gitignore`.

### Why are my web UI settings not taking effect?

If you have environment variables exported in your shell (e.g., `export SLICES_PER_VIDEO=5`), they override the web UI settings. To fix:

```bash
# Check for RadioStation variables in your shell
env | grep -E "CLIP_|SAMPLES_|SLICES_|DOWNLOAD_"

# Unset any conflicting variables
unset SLICES_PER_VIDEO
```

The web UI updates the `.env` file, but shell exports take precedence. Best practice: Don't export RadioStation variables in your shell.

## License

This project is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0).
See the [LICENSE](LICENSE.txt) file for details.
