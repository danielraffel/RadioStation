#!/usr/bin/env python3
"""Utility script for RadioStation project."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DEFAULT_MODEL_URL = (
    "https://huggingface.co/kennethdang/clap-mini/resolve/main/dummy.pt?download=1"
)


def run(cmd):
    """Run a shell command and stream output."""
    print("$", " ".join(cmd))
    subprocess.check_call(cmd)


def ensure_uv():
    """Ensure uv is installed."""
    if shutil.which("uv") is None:
        print("uv not found; installing...")
        run([sys.executable, "-m", "pip", "install", "uv"])
    else:
        print("uv already installed.")


def install_requirements():
    req = BASE_DIR / "requirements.txt"
    # ensure a uv virtual environment exists
    venv_dir = BASE_DIR / ".venv"
    if not venv_dir.exists():
        run(["uv", "venv", str(venv_dir)])
    if req.exists():
        run(["uv", "pip", "install", "-r", str(req)])
    else:
        print("No requirements.txt found; skipping dependency install.")


def download_model(url: str):
    from urllib.request import urlopen

    models_dir = BASE_DIR / "models"
    models_dir.mkdir(exist_ok=True)
    target = models_dir / Path(url.split("?")[0]).name
    if target.exists():
        print(f"Model already exists at {target}")
        return
    print(f"Downloading model from {url} ...")
    with urlopen(url) as r, open(target, "wb") as f:
        while True:
            chunk = r.read(8192)
            if not chunk:
                break
            f.write(chunk)
    print(f"Model downloaded to {target}")


def setup(args):
    """Setup project: ensure uv, install deps, download model, create dirs."""
    ensure_uv()
    install_requirements()
    download_model(args.model_url)
    for path in ["wavs/raw", "wavs/processed/candidates", "wavs/themed"]:
        (BASE_DIR / path).mkdir(parents=True, exist_ok=True)
    print("Setup complete.")


def start(args):
    """Start the FastAPI server in background."""
    pid_file = BASE_DIR / ".server_pid"
    if pid_file.exists():
        print("Server appears to be running (pid file exists).")
        return
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "app.web:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    print("Starting server...")
    proc = subprocess.Popen(cmd)
    pid_file.write_text(str(proc.pid))
    print(f"Server started with PID {proc.pid}")


def stop(args):
    """Stop the background server."""
    pid_file = BASE_DIR / ".server_pid"
    if not pid_file.exists():
        print("No PID file found; server may not be running.")
        return
    pid = int(pid_file.read_text())
    print(f"Stopping server {pid} ...")
    try:
        os.kill(pid, 15)
    except OSError as exc:
        print(f"Error stopping server: {exc}")
    else:
        print("Server stopped.")
    pid_file.unlink(missing_ok=True)


def demo(args):
    """Generate a demo WAV file and move it through directories."""
    import wave
    import math
    import struct

    sr = 44100
    freq = 440.0
    duration = 1.0
    samples = [
        int(32767 * 0.5 * math.sin(2 * math.pi * freq * t / sr))
        for t in range(int(sr * duration))
    ]

    raw_path = BASE_DIR / "wavs/raw/demo.wav"
    processed_path = BASE_DIR / "wavs/processed/candidates/demo.wav"
    themed_dir = BASE_DIR / "wavs/themed/demo"
    themed_path = themed_dir / "demo.wav"
    themed_dir.mkdir(parents=True, exist_ok=True)

    with wave.open(str(raw_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    print(f"Created {raw_path}")

    shutil.copy(raw_path, processed_path)
    print(f"Copied to {processed_path}")

    shutil.move(str(processed_path), str(themed_path))
    print(f"Moved to {themed_path}")


def run_pipeline_cmd(args):
    """Run the sample generation pipeline."""
    from app.pipeline import run_pipeline

    result = run_pipeline()
    print("Pipeline result:")
    print(result)


def main():
    parser = argparse.ArgumentParser(description="Radio Station management script")
    sub = parser.add_subparsers(dest="cmd")

    p_setup = sub.add_parser("setup", help="Install deps and download model")
    p_setup.add_argument("--model-url", default=DEFAULT_MODEL_URL)
    p_setup.set_defaults(func=setup)

    p_start = sub.add_parser("start", help="Start web server")
    p_start.add_argument("--port", type=int, default=8000)
    p_start.set_defaults(func=start)

    p_stop = sub.add_parser("stop", help="Stop web server")
    p_stop.set_defaults(func=stop)

    p_demo = sub.add_parser("demo", help="Generate wav and move files")
    p_demo.set_defaults(func=demo)

    p_run = sub.add_parser("run", help="Run sample pipeline")
    p_run.set_defaults(func=run_pipeline_cmd)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
