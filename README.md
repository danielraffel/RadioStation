# RadioStation

Simple prototype described by Spec.md: downloads audio, processes into WAVs and hosts a FastAPI web interface. 

## Setup

```bash
python manage.py setup
```
This checks for [uv](https://github.com/astral-sh/uv), installs it if missing, installs Python requirements and downloads the CLAP model into `models/`.

Copy `.env.example` to `.env` and provide a comma-separated list of `THEMES` to
classify audio samples.

Running setup also creates `wavs/raw`, `wavs/processed/candidates`, and
`wavs/themed` directories to hold incoming and sorted clips.

## Start the web server

```bash
python manage.py start
```
Visit [http://127.0.0.1:8000](http://127.0.0.1:8000).

The root page serves a very small HTML front end from `app/static/index.html`.

## Stop the web server

```bash
python manage.py stop
```

## Demo: generate WAV and move files

```bash
python manage.py demo
```
Creates a demo WAV and moves it through `wavs/raw` → `wavs/processed/candidates` → `wavs/themed/demo/`.

## Fetch themed samples

```bash
python manage.py samples --count 3 --length 2 --max-tries 10
```

Downloads three sample clips (default), trims or loops each to two seconds and
scores them against the `THEMES` using a simulated CLAP scorer. Clips scoring
above `--threshold` (0.5 by default) are copied into `wavs/themed/<theme>/`; if a
clip fails to match, it is moved to `wavs/processed/candidates` and another
download attempt is made until `--max-tries` is reached. Adjust `--length` to
change clip duration or `--count` to collect more samples.

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

See `Spec.md` for the full vision.
