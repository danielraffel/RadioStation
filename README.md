# RadioStation

Simple prototype described by Spec.md: downloads audio, processes into WAVs and hosts a FastAPI web interface. 

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

See `Spec.md` for the full vision.
