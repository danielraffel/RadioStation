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
    "https://huggingface.co/lukewys/laion_clap/resolve/main/music_speech_audioset_epoch_15_esc_89.98.pt"
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
    """Download model file with optional Hugging Face auth.

    - Supports env tokens: HF_TOKEN, HUGGINGFACE_TOKEN,
      HUGGINGFACEHUB_API_TOKEN, HUGGINGFACE_HUB_TOKEN
    - Gracefully skips on 401/403 with guidance.
    """
    from urllib.request import urlopen, Request
    import urllib.error as urlerr

    # Allow opting out via a sentinel value
    if not url or url.lower() in {"skip", "none"}:
        print("Skipping model download (per --model-url).")
        return

    models_dir = BASE_DIR / "models"
    models_dir.mkdir(exist_ok=True)
    target = models_dir / Path(url.split("?")[0]).name
    if target.exists():
        print(f"Model already exists at {target}")
        return

    # Collect possible Hugging Face tokens
    token = (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        or os.getenv("HUGGINGFACE_HUB_TOKEN")
    )

    headers = {}
    if token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {token}"

    print(f"Downloading model from {url} ...")
    try:
        req = Request(url, headers=headers)
        with urlopen(req) as r, open(target, "wb") as f:
            while True:
                chunk = r.read(8192)
                if not chunk:
                    break
                f.write(chunk)
        print(f"Model downloaded to {target}")
    except urlerr.HTTPError as e:
        if e.code in (401, 403):
            print(
                "Model download unauthorized. If this is a private or gated Hugging Face repo, set "
                "an access token via one of: HF_TOKEN, HUGGINGFACE_HUB_TOKEN, "
                "HUGGINGFACEHUB_API_TOKEN, or HUGGINGFACE_TOKEN. Alternatively, pass a public "
                "URL with --model-url, or pass --model-url skip to bypass."
            )
            print(f"Server returned HTTP {e.code}: {e.reason}")
            # Do not fail setup on auth errors; proceed without model
            return
        print(f"HTTP error while downloading model: {e}")
        return
    except urlerr.URLError as e:
        print(f"Network error while downloading model: {e}")
        return


def setup(args):
    """Setup project: ensure uv, install deps, download model, create dirs."""
    ensure_uv()
    install_requirements()
    if getattr(args, "skip_model", False):
        print("Skipping model download (--skip-model).")
    else:
        download_model(args.model_url)
    for path in ["wavs/raw", "wavs/processed/candidates", "wavs/sessions"]:
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
    # Add --reload flag if requested
    if args.reload:
        cmd.append("--reload")
        print("Starting server with auto-reload enabled...")
    else:
        print("Starting server in background...")
    
    # Run in background by redirecting output
    with open(BASE_DIR / ".server.log", "w") as log_file:
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    pid_file.write_text(str(proc.pid))
    print(f"Server started with PID {proc.pid}")
    if args.reload:
        print("Auto-reload enabled - server will restart on code changes")
    print(f"Open in browser: http://127.0.0.1:{args.port}")
    print(f"Logs: {BASE_DIR / '.server.log'}")


def stop(args):
    """Stop the background server."""
    pid_file = BASE_DIR / ".server_pid"
    stopped = False
    
    # Try PID file first
    if pid_file.exists():
        pid = int(pid_file.read_text())
        print(f"Stopping server {pid} from PID file...")
        try:
            os.kill(pid, 15)
            stopped = True
            print("Server stopped.")
        except OSError as exc:
            print(f"Error stopping server from PID file: {exc}")
        pid_file.unlink(missing_ok=True)
    
    # Also look for uvicorn processes
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'uvicorn' in ' '.join(cmdline) and 'app.web:app' in ' '.join(cmdline):
                    print(f"Found uvicorn process {proc.pid}, stopping...")
                    proc.terminate()
                    stopped = True
                    print(f"Stopped uvicorn process {proc.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except ImportError:
        # psutil not available, skip orphan process cleanup
        pass
    
    if not stopped:
        print("No server processes found.")


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
    themes_dir = BASE_DIR / "wavs/themes/demo"
    themes_path = themes_dir / "demo.wav"
    themes_dir.mkdir(parents=True, exist_ok=True)

    with wave.open(str(raw_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    print(f"Created {raw_path}")

    shutil.copy(raw_path, processed_path)
    print(f"Copied to {processed_path}")

    shutil.move(str(processed_path), str(themes_path))
    print(f"Moved to {themes_path}")


def status(args):
    """Show server status and running processes."""
    import psutil
    import requests
    
    pid_file = BASE_DIR / ".server_pid"
    
    # Check PID file
    if pid_file.exists():
        pid = int(pid_file.read_text())
        print(f"PID file exists: {pid}")
        try:
            proc = psutil.Process(pid)
            print(f"  Process {pid} is running: {proc.name()}")
        except psutil.NoSuchProcess:
            print(f"  Process {pid} is not running (stale PID file)")
    else:
        print("No PID file found")
    
    # Check for uvicorn processes
    print("\nUvicorn processes:")
    found_processes = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and 'uvicorn' in ' '.join(cmdline) and 'app.web:app' in ' '.join(cmdline):
                found_processes = True
                print(f"  PID {proc.pid}: {' '.join(cmdline[:5])}...")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if not found_processes:
        print("  No uvicorn processes found")
    
    # Check server endpoint
    print(f"\nServer status (port {args.port}):")
    try:
        response = requests.get(f"http://127.0.0.1:{args.port}/run/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print(f"  Server is responding")
            print(f"  Pipeline running: {data.get('running', False)}")
            if data.get('last_error'):
                print(f"  Last error: {data['last_error'].get('type', 'Unknown')}")
        else:
            print(f"  Server returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("  Server is not responding (connection refused)")
    except requests.exceptions.Timeout:
        print("  Server is not responding (timeout)")
    except Exception as e:
        print(f"  Error checking server: {e}")

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
    p_setup.add_argument("--model-url", default=DEFAULT_MODEL_URL,
                         help="Model URL to download, or 'skip' to bypass")
    p_setup.add_argument("--skip-model", action="store_true",
                         help="Skip downloading the model")
    p_setup.set_defaults(func=setup)

    p_start = sub.add_parser("start", help="Start web server")
    p_start.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    p_start.add_argument("--reload", action="store_true", 
                         help="Enable auto-reload on code changes (useful for development)")
    p_start.set_defaults(func=start)

    p_stop = sub.add_parser("stop", help="Stop web server")
    p_stop.set_defaults(func=stop)
    
    p_status = sub.add_parser("status", help="Show server status and running processes")
    p_status.add_argument("--port", type=int, default=8000, help="Server port to check")
    p_status.set_defaults(func=status)

    p_demo = sub.add_parser("demo", help="Generate wav and move files")
    p_demo.set_defaults(func=demo)

    p_run = sub.add_parser("run", help="Run sample pipeline")
    p_run.set_defaults(func=run_pipeline_cmd)

    # help command to print available subcommands
    p_help = sub.add_parser("help", help="Show help for commands")
    p_help.set_defaults(func=lambda args, p=parser: p.print_help())

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
