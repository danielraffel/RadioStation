from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI()

@app.get('/', response_class=HTMLResponse)
def index():
    """Serve the simple front end."""
    index_file = Path(__file__).parent / 'static' / 'index.html'
    if index_file.exists():
        return HTMLResponse(index_file.read_text())
    return HTMLResponse('<h1>Radio Station</h1><p>No front-end found.</p>')
