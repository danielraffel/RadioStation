from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import threading
import traceback
from typing import Optional

from .config import get_config, save_env, save_prompts
from .pipeline import run_pipeline

app = FastAPI()

_run_lock = threading.Lock()
_run_thread: Optional[threading.Thread] = None
_run_status = {
    "running": False,
    "last_result": None,
    "last_error": None,
    "progress": None,
}
_stop_event = threading.Event()
_logs: list[str] = []
_max_logs = 200


@app.get('/', response_class=HTMLResponse)
def index():
    """Serve the simple front end."""
    index_file = Path(__file__).parent / 'static' / 'index.html'
    if index_file.exists():
        return HTMLResponse(index_file.read_text())
    return HTMLResponse('<h1>Radio Station</h1><p>No front-end found.</p>')


@app.get('/config')
def read_config():
    """Return current configuration and prompts."""
    return get_config()


@app.post('/run')
def trigger_run():
    """Kick off the pipeline in a background thread if not already running."""
    global _run_thread
    with _run_lock:
        if _run_status["running"]:
            return {"status": "already_running"}

        def _worker():
            _run_status["running"] = True
            _run_status["last_error"] = None
            _run_status["progress"] = None
            _logs.clear()
            try:
                def _progress_cb(p):
                    # Update shared progress snapshot
                    _run_status["progress"] = p
                def _log_cb(msg: str):
                    _logs.append(msg)
                    if len(_logs) > _max_logs:
                        del _logs[: len(_logs) - _max_logs]

                result = run_pipeline(stop_cb=_stop_event.is_set, progress_cb=_progress_cb, log_cb=_log_cb)
                if _stop_event.is_set():
                    result = {**(result or {}), "stopped": True}
                _run_status["last_result"] = result
            except Exception as exc:  # noqa: BLE001
                _run_status["last_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            finally:
                _run_status["running"] = False
                _stop_event.clear()

        _stop_event.clear()
        _run_thread = threading.Thread(target=_worker, daemon=True)
        _run_thread.start()
        return {"status": "started"}


@app.get('/run/status')
def run_status():
    """Return current run status and last result/error."""
    payload = {**_run_status, "logs": list(_logs)}
    return JSONResponse(payload)


@app.post('/run/stop')
def stop_run():
    """Signal the background pipeline to stop."""
    with _run_lock:
        if not _run_status["running"]:
            return {"status": "not_running"}
        _stop_event.set()
        return {"status": "stopping"}


@app.post('/config')
async def update_config(request: Request):
    """Update configuration values and prompts."""
    data = await request.json()
    prompts = data.get('prompts')
    if prompts is not None:
        save_prompts(prompts)
    themes = data.get('themes')
    if themes is not None:
        for idx, term in enumerate(themes, start=1):
            data[f'THEME{idx}'] = term
    save_env(data)
    return get_config()
