from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pathlib import Path

from .config import get_config, save_env, save_prompts

app = FastAPI()


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
