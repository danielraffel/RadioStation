# RadioStation

Simple prototype described by Spec.md: downloads audio, processes into WAVs and hosts a FastAPI web interface.

The pipeline curates **24 samples per bank** across **16 themed banks** for a
total of 384 clips. Each clip is **2 seconds** long by default.

## Setup

```bash
python manage.py setup
```
This checks for [uv](https://github.com/astral-sh/uv), installs it if missing, installs Python requirements and downloads the CLAP model into `models/`.

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

The web UI lets you edit these values and the theme prompts. Saving the form
writes updates back to `.env` and `app/prompts.json` so future runs use them.

See `Spec.md` for the full vision.
