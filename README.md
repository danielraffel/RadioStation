# RadioStation

RadioStation is a small prototype that automatically builds themed audio sample banks from YouTube. When you run the pipeline it:

* searches YouTube for audio matching up to **16** user-defined themes
* downloads each result and trims it into short **2-second** WAV clips
* uses the [CLAP](https://github.com/laion-ai/CLAP) model to score each clip and sort it into the most relevant theme

Running `python manage.py run` fills **16 folders** in `wavs/themed/`. Each folder corresponds to a theme and contains **24 samples**, giving you **384 clips** ready for use.

## How it works

1. The `run` command pulls audio from YouTube using [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).
2. Each download is trimmed to two seconds with [`ffmpeg`](https://ffmpeg.org/) and converted to WAV.
3. The CLAP model ranks the clip against your theme prompts.
4. The clip is stored in `wavs/themed/<THEME>/` until every theme folder holds 24 samples.

## Setup

```bash
python manage.py setup
```
This checks for [uv](https://github.com/astral-sh/uv), installs it if missing, installs Python requirements and downloads the CLAP model into `models/`.  The audio pipeline relies on [yt-dlp](https://github.com/yt-dlp/yt-dlp), [pydub](https://github.com/jiaaro/pydub) and a system `ffmpeg` binary for trimming and format conversion.

## Start the web server

```bash
python manage.py start
```
Visit [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Stop the web server

```bash
python manage.py stop
```

## Run the sample pipeline

```bash
python manage.py run
```

The pipeline keeps downloading and classifying audio until all banks reach the
target sample count. If a download fails to map to a theme after CLAP scoring,
it retries. By default it will keep trying until every bank is full. Set
`MAX_RETRIES_PER_THEME` in the `.env` file (or via the web page) to limit how
many unmatched downloads are attempted before giving up.

## Demo: generate WAV and move files

```bash
python manage.py demo
```
Creates a demo WAV and moves it through `wavs/raw` → `wavs/processed/candidates` → `wavs/themed/demo/`.

## Customize model

Pass `--model-url` to `setup` to download a different model.

```bash
python manage.py setup --model-url https://example.com/model.pt
```

## Project layout

```
app/                FastAPI app and static front end
manage.py           utility script
models/             downloaded model checkpoints
wavs/               audio folders
```

## Configuration (.env and Web UI)

Runtime settings live in the `.env` file and are exposed on the web page at
`/`. Important keys:

| variable | default | description |
| --- | --- | --- |
| `CLIP_SECONDS` | `2` | length of each generated clip |
| `SAMPLES_PER_BANK` | `24` | number of samples to collect for each theme |
| `NUM_BANKS` | `16` | how many themed banks are used |
| `MAX_RETRIES_PER_THEME` | `0` | unmatched downloads to attempt before stopping (`0` = run until complete) |
| `THEME1`..`THEME16` | *(varies)* | search terms used for YouTube downloads and themed folders |

The web UI lets you edit these values, the 16 theme search terms, and the theme prompts. Saving the form writes updates back to `.env` and `app/prompts.json` so future runs use them.

See `Spec.md` for the full vision.
