from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import threading
import traceback
from typing import Optional

from .config import get_config, save_env, save_prompts, save_themes
from .pipeline import run_pipeline
from .words_manager import get_words_manager

app = FastAPI()

_run_lock = threading.Lock()
_run_thread: Optional[threading.Thread] = None
_run_status = {
    "running": False,
    "last_result": None,
    "last_error": None,
    "progress": None,
    "stopping": False,
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
            _run_status["stopping"] = False
            # Don't clear logs, just mark where new run starts
            _logs.append("="*50)
            _logs.append(f"NEW RUN STARTED")
            _logs.append("="*50)
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
                _run_status["stopping"] = False

        _stop_event.clear()
        _run_thread = threading.Thread(target=_worker, daemon=True)
        _run_thread.start()
        return {"status": "started"}


@app.post('/continue')
def continue_run():
    """Continue a stopped pipeline session."""
    global _run_thread
    with _run_lock:
        if _run_status["running"]:
            return {"status": "already_running"}

        # Get the last session ID from progress
        session_id = None
        if _run_status.get("progress") and _run_status["progress"].get("session_id"):
            session_id = _run_status["progress"]["session_id"]
        elif _run_status.get("last_result") and _run_status["last_result"].get("session_id"):
            session_id = _run_status["last_result"]["session_id"]

        if not session_id:
            return {"status": "no_session_to_continue"}

        def _worker():
            _run_status["running"] = True
            _run_status["last_error"] = None
            # Keep existing progress so UI shows where we left off
            _run_status["stopping"] = False
            # Don't clear logs, just mark where continuation starts
            _logs.append("="*50)
            _logs.append(f"CONTINUING SESSION: {session_id}")
            _logs.append("="*50)
            try:
                def _progress_cb(p):
                    # Update shared progress snapshot
                    _run_status["progress"] = p
                def _log_cb(msg: str):
                    _logs.append(msg)
                    if len(_logs) > _max_logs:
                        del _logs[: len(_logs) - _max_logs]

                result = run_pipeline(
                    stop_cb=_stop_event.is_set,
                    progress_cb=_progress_cb,
                    log_cb=_log_cb,
                    continue_session=session_id
                )
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
                _run_status["stopping"] = False

        _stop_event.clear()
        _run_thread = threading.Thread(target=_worker, daemon=True)
        _run_thread.start()
        return {"status": "continued", "session_id": session_id}


@app.get('/run/status')
def run_status():
    """Return current run status and last result/error."""
    # Include session_dir for opening folder link
    payload = {**_run_status, "logs": list(_logs)}
    if _run_status.get('progress') and _run_status['progress'].get('session_id'):
        session_id = _run_status['progress']['session_id']
        session_dir = str(Path(__file__).parent.parent / 'wavs' / 'sessions' / session_id)
        payload['session_dir'] = session_dir
    return JSONResponse(payload)


@app.post('/run/stop')
def stop_run():
    """Signal the background pipeline to stop."""
    import subprocess
    import signal
    with _run_lock:
        if not _run_status["running"]:
            return {"status": "not_running"}
        _stop_event.set()
        _run_status["stopping"] = True

        # Force kill any ffmpeg and yt-dlp processes
        try:
            # Kill ffmpeg processes downloading to RadioStation wavs directory
            subprocess.run(['pkill', '-9', '-f', 'ffmpeg.*wavs/raw'], check=False)
            # Kill any remaining ffmpeg with RadioStation in path
            subprocess.run(['pkill', '-9', '-f', 'ffmpeg.*RadioStation'], check=False)
            # Kill yt-dlp processes
            subprocess.run(['pkill', '-9', '-f', 'yt-dlp'], check=False)
            _logs.append("Force stopped all download processes")

            # Wait a moment for the pipeline to notice the killed processes
            import time
            time.sleep(0.5)

            # If still running after a second, force reset the status
            if _run_thread and _run_thread.is_alive():
                _logs.append("Pipeline thread still running, will clean up on next check")
                # Thread should exit on its own when it sees stop event is set
                # But we'll add a timeout mechanism
                def cleanup_stuck_thread():
                    time.sleep(3)  # Give it 3 more seconds
                    if _run_thread and _run_thread.is_alive():
                        _run_status["running"] = False
                        _run_status["stopping"] = False
                        _logs.append("Force cleaned up stuck pipeline state")

                cleanup_thread = threading.Thread(target=cleanup_stuck_thread, daemon=True)
                cleanup_thread.start()

        except Exception as e:
            _logs.append(f"Error killing processes: {e}")

        return {"status": "stopping"}


@app.post('/config')
async def update_config(request: Request):
    """Update configuration values, themes, and prompts."""
    data = await request.json()
    
    # Handle new theme structure
    themes = data.get('themes')
    if themes is not None:
        if isinstance(themes[0], dict):  # New structure
            save_themes(themes)
            # Update prompts to match themes
            save_prompts([{'name': t['name'], 'prompt': t['prompt']} for t in themes])
        else:  # Old structure (list of strings)
            # Convert to new structure maintaining backward compatibility
            theme_objects = []
            prompts = data.get('prompts', [])
            prompts_dict = {p['name']: p['prompt'] for p in prompts} if prompts else {}
            
            for i, name in enumerate(themes[:16]):
                theme_objects.append({
                    "name": name,
                    "search": name,
                    "prompt": prompts_dict.get(name, "Generic sound")
                })
            
            save_themes(theme_objects)
            save_prompts([{'name': t['name'], 'prompt': t['prompt']} for t in theme_objects])
    
    # Save other env variables
    save_env(data)
    return get_config()


@app.get('/words/status')
def words_status():
    """Check if words list is available and return count."""
    manager = get_words_manager()
    return {
        "available": manager.is_available(),
        "count": len(manager.words)
    }
