Product Spec: CLAP-Themed Sample Curator (Local, macOS, UV)

Summary

A local macOS app that bulk-downloads audio from YouTube (via yt-dlp), generates standardized WAV samples, embeds them with CLAP, and auto-sorts into 16 themed folders with 24 samples per folder (total 384).
Runs locally with UV environment management.
Provides a simple web UI to view and override config (from .env) and launch the pipeline with real-time progress and logs.

⸻

Goals & Non-Goals

Goals
	•	One-click local pipeline: download → preprocess → embed → classify → curate → export.
	•	Expose all core settings in a web UI (pre-filled from .env, override per-run).
	•	Output exactly 16 folders × 24 samples of 16-bit / 44.1 kHz / stereo WAV, sorted by theme.
	•	Prefer quality: discard files that don’t fit target themes or fail quality gates.
	•	Minimal setup using UV; no cloud services.

Non-Goals
	•	No user authentication or multi-user support.
	•	No persistent database (CSV/JSON metadata is sufficient).
	•	No external hosting; strictly local.

⸻

Users & Primary Use Cases
	•	Producer / Sound Designer: quickly create curated, themed mini-libraries.
	•	Researcher / Tinkerer: experiment with CLAP-based zero-shot audio labeling.

⸻

High-Level Flow
	1.	Configure (via .env + Web UI overrides)
	2.	Collect (wide net using yt-dlp with random or seeded search phrases)
	3.	Preprocess (normalize format, length, fades, loudness/rms gates)
	4.	Embed (CLAP audio embeddings; optional text/title fusion)
	5.	Classify (cosine similarity against 16 theme prompts)
	6.	Curate (top-N per theme; deduplicate; enforce quality)
	7.	Export (16 folders × 24 samples, 16/44.1 stereo WAV)
	8.	Report (CSV/JSON manifests + web UI summaries)

⸻

Architecture

Components
	•	Web Server: FastAPI (or Flask) with:
	•	Config endpoint (load .env, return JSON)
	•	“Generate” job endpoint (start pipeline)
	•	Status/logs endpoints (progress polling)
	•	Static front end (simple HTML/JS)
	•	Worker: Python pipeline (single process with internal queue; optional thread for UI-safe progress updates).
	•	CLAP: LAION-AI/CLAP checkpoint for “speech, music and general audio”.
	•	Audio Tooling: yt-dlp, ffmpeg, pydub/torchaudio.

Directory Layout

project/
  app/                     # web + pipeline code
  models/                  # CLAP .pt checkpoint
  wavs/
    raw/                   # raw downloads from yt-dlp (wav)
    processed/
      candidates/          # normalized candidate clips pre-classification
    themed/
      <theme_1>/           # final curated exports (24 files each)
      ...
      <theme_16>/
  manifests/
    runs/<timestamp>/
      classification.csv
      rejected.csv
      run_config.json
  .env
  pyproject.toml
  README.md


⸻

Setup & Installation (UV)
	•	Requirements: macOS, Python 3.10+, ffmpeg in PATH, Git.
	•	Environment:
	•	uv venv
	•	uv pip install -r requirements.txt (or uv pip install . if pyproject.toml used)
	•	Assets:
	•	Clone LAION-AI/CLAP locally (to vendor processing utils if needed).
	•	Download model:
lukewys/laion_clap/.../music_speech_audioset_epoch_15_esc_89.98.pt → models/clap_music_speech_audioset_epoch_15_esc_89.98.pt
	•	Run:
	•	uv run python -m app.web → opens local web UI at http://127.0.0.1:PORT

Note: Installer step will verify ffmpeg, CLAP checkpoint path, and GPU availability (optional).

⸻

Configuration

.env (baseline)

# YouTube & Collection
BATCHES=8
SEARCH_TERMS_FILE=words.txt
TERMS_PER_QUERY=2
DOWNLOADS_PER_TERM=8
MAX_VIDEO_DURATION_SEC=600
CLIP_STRATEGY=center            # center|random|fixed_offsets
CLIP_MS=2000
MIN_AUDIO_MS=500
DELETE_NONCONFORMING=true

# Audio Output
TARGET_SR=44100
TARGET_BIT_DEPTH=16
TARGET_CHANNELS=2
NORMALIZE=true
FADE_MS=500
LOUDNESS_GATE_DBFS=-40

# CLAP / Classification
CLAP_CHECKPOINT=models/clap_music_speech_audioset_epoch_15_esc_89.98.pt
FUSE_TITLE_WEIGHT=0.2           # 0.0 disables title-text fusion
SIM_THRESHOLD=0.35
MULTILABEL=false                 # single best match fills target counts
THEMES_FILE=themes.yaml          # 16 prompts with rich descriptions
TARGET_THEMES=16
SAMPLES_PER_THEME=24
OVERSAMPLE_FACTOR=5              # download N× more than needed

# Export
THEMED_DIR=wavs/themed
RAW_DIR=wavs/raw
CANDIDATE_DIR=wavs/processed/candidates

# Runtime
WORKERS=4
LOG_LEVEL=INFO

Web UI Override Rules
	•	On page load, fetch current .env values → populate form fields.
	•	User edits do not mutate .env by default; they apply to the current run.
	•	“Save as default” button optionally writes back to .env.

⸻

Web UI

Page: Generate Themed Library

Sections
	1.	Run Profile
	•	Batches, Oversample Factor, Samples per Theme, Themes File, toggle Delete Nonconforming.
	2.	Collection
	•	Search Terms File, Terms per Query, Downloads per Term, Max Video Duration.
	3.	Preprocessing
	•	Clip Strategy (center|random|fixed_offsets), Clip ms, Min Audio ms, Normalize, Fade ms, Loudness Gate dBFS, Target SR/BitDepth/Channels.
	4.	Classification
	•	CLAP Checkpoint path (file picker), Fuse Title Weight, Similarity Threshold, Multilabel toggle.
	•	Themes Preview (read-only list of 16 prompts with inline edit per-run).
	5.	Export
	•	Themed Output Dir, toggle Symlink vs Copy (default: copy).
	6.	Controls
	•	Generate (starts job), Stop, Save as Default.
	7.	Progress & Logs
	•	Overall progress bar + per-phase bars:
	•	Downloading, Preprocessing, Embedding, Classifying, Curating, Exporting
	•	Counters: downloaded, candidates, embedded, accepted per theme, rejected.
	•	Live log tail (last 200 lines), downloadable full log.
	8.	Results
	•	Run summary (per-theme counts, average similarity, rejected count)
	•	Buttons: Open output folder, Download manifests, View classification table.

⸻

Pipeline Details

1) Collection (YouTube)
	•	Form randomized search phrases from SEARCH_TERMS_FILE (sample TERMS_PER_QUERY words).
	•	yt-dlp search: per phrase, fetch DOWNLOADS_PER_TERM videos (use ytsearch).
	•	Enforce MAX_VIDEO_DURATION_SEC.
	•	Download best audio, convert to WAV via ffmpeg postprocessor, place in wavs/raw/.
	•	Save metadata sidecar (.json) with id, title, duration, channel, url.

Progress
	•	Show counts: phrases queued, videos selected, downloads complete, failures.

2) Preprocessing
	•	Load WAV, downmix/upmix to stereo, resample to 44.1 kHz, 16-bit.
	•	Derive clip per CLIP_STRATEGY (default: center window).
	•	Apply fade in/out FADE_MS, normalize if enabled.
	•	Reject if:
	•	duration < MIN_AUDIO_MS
	•	loudness below LOUDNESS_GATE_DBFS
	•	peak clipping detected (optional gate)
	•	Write candidate clips to processed/candidates/.

Progress
	•	Candidate count; rejected reasons (too short, too quiet, decode error).

3) Embedding (CLAP)
	•	Load CLAP checkpoint once.
	•	Batch-embed audio (configurable WORKERS).
	•	Optional title fusion:
	•	Embed title text (if available)
	•	fused = normalize( (1 - FUSE_TITLE_WEIGHT) * audio_emb + FUSE_TITLE_WEIGHT * title_emb )

Progress
	•	Batches completed / total; GPU used (yes/no).

4) Classification
	•	Load 16 theme prompts (rich text) from themes.yaml; embed once.
	•	Compute cosine similarity between each candidate and each theme.
	•	If MULTILABEL=false: assign the single best theme.
	•	If MULTILABEL=true: assign all with similarity ≥ SIM_THRESHOLD (useful for exploration).
	•	Write manifests/runs/<ts>/classification.csv:

filename,theme_top1,score_top1,<theme1_score>,...,<theme16_score>,title,duration_ms,reject_reason



Progress
	•	Classified count; similarity score histogram (inline sparkline).

5) Curation
	•	For each theme:
	•	Sort by similarity desc.
	•	Deduplicate by audio hash (min distance gating to avoid near-duplicates).
	•	Select top 24.
	•	If fewer than 24:
	•	Mark deficiency; optionally auto-continue collection until filled (configurable; default off).
	•	All non-selected candidates are marked rejected if DELETE_NONCONFORMING=true.

Progress
	•	Per-theme selected vs target (e.g., 18/24), with a green check on completion.

6) Export
	•	Copy (or symlink) selected files to wavs/themed/<theme>/.
	•	Ensure final format 16-bit, 44.1 kHz, stereo; re-encode if needed as last step.
	•	Generate export manifest (export_summary.json) with paths and scores.

⸻

Default 16 Themes (editable)

Provide descriptive prompts (2 sentences each) in themes.yaml:
	1.	Soft — Quiet, gentle, low-intensity sound like a whisper or fabric brushing. Smooth, not harsh or piercing.
	2.	Loud — Booming, powerful, high-volume sound that dominates space. Strong transients and presence.
	3.	Bumpy — Uneven, jolting, irregular percussive texture like a train on rough tracks; not smooth. Skips or stutters are characteristic.
	4.	Smooth — Continuous, flowing, connected sound without rough edges. Even dynamics and rounded timbre.
	5.	Harsh — Rough, grating, distorted or metallic noise; aggressive highs. Unpleasant or biting character.
	6.	Warm — Full, rounded low-mids, gentle highs; cozy and intimate. Not thin or brittle.
	7.	Bright — Emphasized highs and detail; crisp and shiny. Not dark or muffled.
	8.	Dark — Subdued highs, weight in lows/low-mids; shadowy or muted. Not bright or sparkly.
	9.	Metallic — Ringing, resonant metal tones; clangs, scrapes, chimes. Distinct overtones and sheen.
	10.	Woody — Organic, resonant wood timbre like knocks, taps, or acoustic bodies. Warm transients.
	11.	Airy — Breath, wind, or subtle high-frequency shimmer. Light, spacious, and diffuse.
	12.	Noisy — Broadband or narrow-band noise textures (hiss, static). Texture over pitch.
	13.	Percussive — Short, transient-rich hits or sequences; clear onsets. Minimal sustain.
	14.	Sustained — Long, held tones or pads with steady energy. Minimal transient emphasis.
	15.	Glitchy — Digital artifacts, stutters, buffer errors, granular pops. Non-linear rhythm.
	16.	Eerie — Unsettling, mysterious ambience; dissonant or hollow. Suggests tension or space.

⸻

Quality Gates & Policies
	•	Silence/Noise Checks: RMS and peak analysis to reject near-silence and severe clipping.
	•	Length Consistency: re-trim to CLIP_MS if drift occurs.
	•	Duplicate Control: perceptual hash or spectral centroid variance to prevent near-duplicates per theme.
	•	Title Stoplist (optional): ignore spammy keywords (“compilation”, “hour”, “asmr”) when using title fusion.

⸻

Progress, Status & Logs
	•	Overall bar + phase bars with counts.
	•	Live log tail with filters: ALL | WARN | ERROR.
	•	Final Run Summary card:
	•	Per-theme counts (selected/24), average similarity, #rejected, #duplicates removed.
	•	Links: open output directory, download manifests/logs.

⸻

Error Handling
	•	Hard failures (missing model, no ffmpeg): show blocking banner with remediation hint.
	•	Soft failures (some downloads fail): continue run; surface counts and reasons.
	•	Insufficient samples: show per-theme deficit; offer “Continue collecting” action.

⸻

Manifests & Reproducibility
	•	run_config.json: effective parameters (after UI overrides).
	•	classification.csv: per-file scores + assignment.
	•	rejected.csv: filename + reason (quality gate, low score, duplicate).
	•	export_summary.json: final selections with scores and target paths.

⸻

Performance & Concurrency
	•	Embed in batches (vectorized) with WORKERS control.
	•	Disk I/O bounded; avoid re-encoding if already compliant.
	•	GPU optional; fall back to CPU with reduced batch size.

⸻

Security & Privacy
	•	Local only; no external API calls beyond YouTube/HF asset fetch.
	•	No PII stored. Titles saved in manifests for transparency.

⸻

Acceptance Criteria
	1.	Setup with UV completes; model checkpoint validated on first run.
	2.	Web UI lists .env values; edits override per-run; optional “Save as default” writes back.
	3.	One run produces 16 themed folders with 24 samples each in 16/44.1 stereo WAV.
	4.	classification.csv includes similarity scores for all themes per file.
	5.	Deletion of nonconforming candidates respects DELETE_NONCONFORMING.
	6.	Progress bars and logs update live across all phases.
	7.	Re-running with same config yields consistent results (modulo random seeds, if set).

⸻

Open Questions (to decide during implementation)
	•	Should we expose a strictness slider that maps to SIM_THRESHOLD and quality gates?
	•	Default clip length: keep 2000 ms or expose range 1000–4000 ms?
	•	Continue collecting: automatic until each theme reaches 24, or manual confirm?

⸻

Implementation Notes (AI Integrator)
	•	Reuse existing downloader/processor; insert:
	•	Metadata sidecar write (id/title/duration).
	•	Candidate directory stage before classification.
	•	CLAP embedding + classification stage.
	•	Curation stage enforcing per-theme quotas and dedupe.
	•	Provide a lightweight job manager (single active job; cancelable).
	•	Ensure idempotence: skip already-embedded files by hash cache.
	•	Keep all thresholds and prompts config-first (read from .env / themes.yaml).
