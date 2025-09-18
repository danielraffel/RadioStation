#!/usr/bin/env python3
"""
Session Browser for CLAP Evaluation
Browse and select sessions for evaluation.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import json
import asyncio
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, Optional
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from evaluator import load_session_metadata, evaluate_session, discovery_mode_analysis
from report_generator import generate_enhanced_html_report
from clap_prompt_generator import (
    load_evaluator_config,
    generate_prompts_for_session,
    save_prompts_to_samples
)
from prompt_manager import (
    get_prompt_status,
    bless_prompt as bless_single_prompt,
    bulk_bless_prompts,
    get_blessed_prompt,
    get_evaluation_prompts
)

app = FastAPI()
logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).parent.parent.parent / 'wavs' / 'sessions'
RESULTS_DIR = Path(__file__).parent / 'results'
STATIC_DIR = Path(__file__).parent / 'static'

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get('/', response_class=HTMLResponse)
def index():
    """Serve the modern UI"""
    html_path = STATIC_DIR / 'evaluator.html'
    if html_path.exists():
        return FileResponse(html_path)

    # Fallback to inline HTML if file doesn't exist
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLAP Evaluation - Session Browser</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, system-ui, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 10px;
            color: #4a9eff;
        }
        .subtitle {
            color: #999;
            margin-bottom: 30px;
        }
        .sessions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .session-card {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .session-card:hover {
            background: #2a2a2a;
            border-color: #4a9eff;
            transform: translateY(-2px);
        }
        .session-id {
            font-size: 16px;
            font-weight: bold;
            color: #4a9eff;
            margin-bottom: 10px;
        }
        .session-stats {
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            font-size: 14px;
        }
        .stat {
            color: #999;
        }
        .stat-value {
            color: #e0e0e0;
            font-weight: bold;
        }
        .themes {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .theme-tag {
            background: #2a2a2a;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        .evaluation-panel {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            display: none;
        }
        .evaluation-panel.active {
            display: block;
        }
        h2 {
            font-size: 20px;
            margin-bottom: 15px;
        }
        .test-config {
            margin-bottom: 20px;
        }
        .test-run {
            background: #0a0a0a;
            border: 1px solid #2a2a2a;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .test-run h3 {
            font-size: 16px;
            margin-bottom: 10px;
            color: #4a9eff;
        }
        .prompt-config {
            margin-bottom: 10px;
        }
        .prompt-config label {
            display: block;
            font-size: 12px;
            color: #999;
            margin-bottom: 4px;
        }
        .prompt-config textarea {
            width: 100%;
            background: #1a1a1a;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
            padding: 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            resize: vertical;
        }
        .threshold-config {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
        }
        .threshold-config input {
            width: 80px;
            background: #1a1a1a;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
            padding: 4px 8px;
            border-radius: 4px;
        }
        .buttons {
            display: flex;
            gap: 10px;
        }
        button {
            background: #4a9eff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #3a8eef;
        }
        button.secondary {
            background: #3a3a3a;
        }
        button.secondary:hover {
            background: #4a4a4a;
        }
        .loading {
            display: none;
            color: #4a9eff;
            margin-top: 10px;
        }
        .loading.active {
            display: block;
        }
        .results-link {
            display: none;
            margin-top: 15px;
            padding: 15px;
            background: #0a0a0a;
            border: 1px solid #4a9eff;
            border-radius: 4px;
        }
        .results-link.active {
            display: block;
        }
        .results-link a {
            color: #4a9eff;
            text-decoration: none;
        }
        .results-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>CLAP Evaluation Tool</h1>
        <p class="subtitle">Select a session to evaluate with different CLAP prompts and thresholds</p>

        <div class="sessions-grid" id="sessions-grid">
            <!-- Sessions will be loaded here -->
        </div>

        <div class="evaluation-panel" id="evaluation-panel">
            <h2>Evaluate Session: <span id="selected-session"></span></h2>

            <div class="test-config" id="test-config">
                <div class="test-run">
                    <h3>Test Configuration 1</h3>
                    <div id="prompts-config-1"></div>
                    <div class="threshold-config">
                        <label>Similarity Threshold:</label>
                        <input type="number" id="threshold-1" value="0.40" min="0" max="1" step="0.05">
                    </div>
                </div>

                <div class="test-run">
                    <h3>Test Configuration 2 (Stricter)</h3>
                    <div id="prompts-config-2"></div>
                    <div class="threshold-config">
                        <label>Similarity Threshold:</label>
                        <input type="number" id="threshold-2" value="0.50" min="0" max="1" step="0.05">
                    </div>
                </div>

                <div class="test-run">
                    <h3>Test Configuration 3 (Custom)</h3>
                    <div id="prompts-config-3"></div>
                    <div class="threshold-config">
                        <label>Similarity Threshold:</label>
                        <input type="number" id="threshold-3" value="0.35" min="0" max="1" step="0.05">
                    </div>
                </div>
            </div>

            <div class="buttons">
                <button onclick="runEvaluation()">Run Evaluation</button>
                <button class="secondary" onclick="cancelEvaluation()">Cancel</button>
            </div>

            <div class="loading" id="loading">
                Running evaluation... This may take a few minutes.
            </div>

            <div class="results-link" id="results-link">
                <strong>Evaluation complete!</strong><br>
                <a href="" target="_blank" id="results-url">View Results →</a>
            </div>
        </div>
    </div>

    <script>
        let selectedSession = null;
        let sessionMetadata = {};

        async function loadSessions() {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();

            const grid = document.getElementById('sessions-grid');
            grid.innerHTML = '';

            for (const session of sessions) {
                const card = document.createElement('div');
                card.className = 'session-card';
                card.onclick = () => selectSession(session);

                const themeTags = Object.keys(session.themes).map(theme =>
                    `<div class="theme-tag">${theme} (${session.themes[theme].sample_count})</div>`
                ).join('');

                card.innerHTML = `
                    <div class="session-id">${session.session_id}</div>
                    <div class="session-stats">
                        <div class="stat">Samples: <span class="stat-value">${session.total_samples}</span></div>
                        <div class="stat">Themes: <span class="stat-value">${Object.keys(session.themes).length}</span></div>
                    </div>
                    <div class="themes">${themeTags}</div>
                `;

                grid.appendChild(card);
                sessionMetadata[session.session_id] = session;
            }
        }

        function selectSession(session) {
            selectedSession = session.session_id;
            document.getElementById('selected-session').textContent = session.session_id;
            document.getElementById('evaluation-panel').classList.add('active');

            // Set up prompt configurations
            for (let i = 1; i <= 3; i++) {
                const container = document.getElementById(`prompts-config-${i}`);
                container.innerHTML = '';

                for (const [theme, data] of Object.entries(session.themes)) {
                    const promptDiv = document.createElement('div');
                    promptDiv.className = 'prompt-config';

                    let defaultPrompt = data.original_prompt || `${theme.toLowerCase()} audio`;

                    // For config 2, enhance the prompt
                    if (i === 2 && data.original_prompt) {
                        defaultPrompt = data.original_prompt + ' clear distinct characteristic';
                    }

                    // For config 3, allow full customization
                    if (i === 3) {
                        defaultPrompt = `${theme.toLowerCase()} sounds with specific characteristics`;
                    }

                    promptDiv.innerHTML = `
                        <label>${theme} prompt:</label>
                        <textarea id="prompt-${i}-${theme}" rows="2">${defaultPrompt}</textarea>
                    `;
                    container.appendChild(promptDiv);
                }
            }

            // Scroll to evaluation panel
            document.getElementById('evaluation-panel').scrollIntoView({ behavior: 'smooth' });
        }

        function cancelEvaluation() {
            document.getElementById('evaluation-panel').classList.remove('active');
            selectedSession = null;
        }

        async function runEvaluation() {
            if (!selectedSession) return;

            const session = sessionMetadata[selectedSession];

            // Build test configuration
            const testConfig = {
                test_runs: []
            };

            for (let i = 1; i <= 3; i++) {
                const prompts = {};
                for (const theme of Object.keys(session.themes)) {
                    const textarea = document.getElementById(`prompt-${i}-${theme}`);
                    if (textarea) {
                        prompts[theme] = textarea.value;
                    }
                }

                const threshold = parseFloat(document.getElementById(`threshold-${i}`).value);

                testConfig.test_runs.push({
                    name: `Configuration ${i}`,
                    prompts: prompts,
                    threshold: threshold
                });
            }

            // Show loading
            document.getElementById('loading').classList.add('active');
            document.getElementById('results-link').classList.remove('active');

            // Run evaluation
            const response = await fetch('/api/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: selectedSession,
                    test_config: testConfig
                })
            });

            const result = await response.json();

            // Hide loading
            document.getElementById('loading').classList.remove('active');

            if (result.success) {
                // Show results link
                document.getElementById('results-link').classList.add('active');
                document.getElementById('results-url').href = result.report_url;
            } else {
                alert('Evaluation failed: ' + result.error);
            }
        }

        // Load sessions on page load
        loadSessions();
    </script>
</body>
</html>"""
    return HTMLResponse(html)


@app.get('/api/sessions')
def get_sessions():
    """Get list of available sessions"""
    sessions = []

    if SESSIONS_DIR.exists():
        for session_dir in sorted(SESSIONS_DIR.iterdir()):
            if session_dir.is_dir():
                metadata = load_session_metadata(session_dir)
                # Format for UI
                themes = []
                for theme_name, theme_data in metadata['themes'].items():
                    themes.append({
                        'name': theme_name,
                        'count': theme_data['sample_count']
                    })

                sessions.append({
                    'session_id': metadata['session_id'],
                    'total_samples': metadata['total_samples'],
                    'theme_count': len(metadata['themes']),
                    'themes': themes
                })

    return JSONResponse(sessions)


@app.get('/api/session/{session_id}')
def get_session_metadata(session_id: str):
    """Get detailed metadata for a specific session"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    metadata = load_session_metadata(session_path)
    return JSONResponse(metadata)


@app.get('/api/evaluate/{session_id}/stream')
async def evaluation_stream(session_id: str):
    """SSE stream for evaluation progress"""
    async def generate():
        # Simulated progress for now - will be replaced with actual progress
        for i in range(101):
            await asyncio.sleep(0.1)
            data = {
                'type': 'progress',
                'percent': i,
                'message': f'Evaluating session... {i}%'
            }
            yield f"data: {json.dumps(data)}\n\n"

        # Send completion
        data = {
            'type': 'complete',
            'summary': {
                'overall_pass_rate': 45  # Example
            },
            'results_url': f'/results/{session_id}/latest/index.html'
        }
        yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post('/api/evaluate/single')
async def run_single_evaluation(request: Request):
    """Run evaluation for a single test configuration"""
    data = await request.json()
    session_id = data.get('session_id')
    test_config = data.get('test_config')

    if not session_id or not test_config:
        return JSONResponse({
            'success': False,
            'error': 'Missing session_id or test_config'
        })

    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({
            'success': False,
            'error': f'Session not found: {session_id}'
        })

    try:
        # Run single configuration evaluation
        single_config = {'test_runs': [test_config]}
        results = evaluate_session(session_path, single_config)

        # Return quick summary
        test_run = results['test_runs'][0]
        stats = test_run['statistics']

        overall_passed = sum(s['passed'] for s in stats.values())
        overall_total = sum(s['total'] for s in stats.values())
        pass_rate = (overall_passed / overall_total * 100) if overall_total > 0 else 0

        return JSONResponse({
            'success': True,
            'results': {
                'pass_rate': pass_rate,
                'stats': stats
            }
        })

    except Exception as e:
        return JSONResponse({
            'success': False,
            'error': str(e)
        })


@app.post('/api/evaluate')
async def run_evaluation(request: Request):
    """Run evaluation on a session"""
    data = await request.json()
    session_id = data.get('session_id')
    test_config = data.get('test_config')

    if not session_id or not test_config:
        return JSONResponse({
            'success': False,
            'error': 'Missing session_id or test_config'
        })

    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({
            'success': False,
            'error': f'Session not found: {session_id}'
        })

    try:
        # Run evaluation
        logger.info(f"Starting evaluation for session {session_id}")
        results = evaluate_session(session_path, test_config)

        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = RESULTS_DIR / session_id / f'evaluation_{timestamp}'
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create evaluation log
        log_path = output_dir / 'evaluation.log'
        with open(log_path, 'w') as log_file:
            log_file.write(f"Evaluation Log - Session: {session_id}\n")
            log_file.write(f"Timestamp: {timestamp}\n")
            log_file.write(f"Configuration: {json.dumps(test_config, indent=2)}\n\n")
            log_file.write(f"Total samples evaluated: {results['metadata']['total_samples']}\n")
            log_file.write(f"Test runs: {len(test_config.get('test_runs', []))}\n\n")

            # Log results summary
            for run in results.get('test_runs', []):
                log_file.write(f"\n{run['name']} (threshold: {run['threshold']}):\n")
                for theme, stats in run.get('statistics', {}).items():
                    log_file.write(f"  {theme}: {stats['passed']}/{stats['total']} passed ({stats['pass_rate']*100:.1f}%)\n")

        logger.info(f"Evaluation log saved to {log_path}")

        # Save JSON results
        results_path = output_dir / 'results.json'
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)

        # Save test configuration
        config_path = output_dir / 'config.json'
        with open(config_path, 'w') as f:
            json.dump(test_config, f, indent=2)

        # Generate HTML report
        generate_enhanced_html_report(results, output_dir, session_id)

        # Create symlink to latest evaluation
        latest_link = RESULTS_DIR / session_id / 'latest'
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(output_dir.name)

        # Return success with report URL
        report_url = f'/results/{session_id}/evaluation_{timestamp}/index.html'
        logger.info(f"Evaluation complete. Report URL: {report_url}")

        return JSONResponse({
            'success': True,
            'report_url': report_url,
            'results_path': str(results_path),
            'log_path': str(log_path)
        })

    except Exception as e:
        return JSONResponse({
            'success': False,
            'error': str(e)
        })


@app.post('/api/discovery/{session_id}')
async def run_discovery(session_id: str):
    """Run discovery mode analysis on a session"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    try:
        # Run discovery analysis
        analysis = discovery_mode_analysis(session_path, sample_limit=5)

        return JSONResponse({
            'success': True,
            'analysis': analysis
        })

    except Exception as e:
        logger.error(f"Discovery mode error: {e}")
        return JSONResponse({
            'success': False,
            'error': str(e)
        })


@app.get('/api/settings')
async def get_settings():
    """Get current AI configuration settings"""
    config = load_evaluator_config()
    # Don't expose the full API key
    if config.get('openai_api_key'):
        key = config['openai_api_key']
        if len(key) > 8:
            config['openai_api_key'] = key[:4] + '...' + key[-4:]
    return JSONResponse(config)


@app.post('/api/settings')
async def save_settings(request: Request):
    """Save AI configuration settings"""
    data = await request.json()

    config_path = Path(__file__).parent / 'evaluator_config.json'

    # Load existing config
    existing = load_evaluator_config()

    # Update with new values (preserve API key if not changed)
    if 'openai_api_key' in data:
        if '...' in data['openai_api_key']:
            # Key was masked, don't update
            data['openai_api_key'] = existing.get('openai_api_key', '')

    existing.update(data)

    # Save to file
    try:
        with open(config_path, 'w') as f:
            json.dump(existing, f, indent=2)
        return JSONResponse({'success': True})
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return JSONResponse({'success': False, 'error': str(e)})


@app.get('/audio/{session_id}/{theme}/{filename}')
async def serve_audio(session_id: str, theme: str, filename: str):
    """Serve audio files from session directories"""
    audio_path = SESSIONS_DIR / session_id / 'themes' / theme / filename

    if not audio_path.exists() or not filename.endswith('.wav'):
        return JSONResponse({'error': 'Audio file not found'}, status_code=404)

    return FileResponse(audio_path, media_type='audio/wav')

@app.get('/api/prompts/status/{session_id}')
async def get_prompts_status(session_id: str):
    """Get status of prompts for a session"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    status = get_prompt_status(session_path)
    return JSONResponse(status)

@app.get('/api/prompts/details/{session_id}')
async def get_prompts_details(session_id: str):
    """Get detailed AI prompts with metadata for review"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    prompt_details = []

    for theme_dir in session_path.glob('themes/*'):
        if not theme_dir.is_dir():
            continue

        theme_name = theme_dir.name

        for json_file in theme_dir.glob('*.json'):
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Get AI prompts if available - check both field names
            ai_prompts = data.get('generated_clap_prompts', []) or data.get('clap_prompts_v1', [])
            best_prompt = data.get('best_clap_prompt')

            # Only add if we have AI prompts
            if ai_prompts or best_prompt:
                prompt_details.append({
                    'sample_id': json_file.stem,
                    'theme': theme_name,
                    'title': data.get('title', 'Unknown')[:100],
                    'tags': data.get('tags', [])[:5],
                    'ai_prompts': ai_prompts if ai_prompts else [best_prompt] if best_prompt else [],
                    'best_prompt': best_prompt,
                    'final_prompt': data.get('final_clap_prompt'),
                    'has_blessed': bool(data.get('final_clap_prompt'))
                })

    return JSONResponse({
        'total_samples': len(prompt_details),
        'with_ai_prompts': len([p for p in prompt_details if p['ai_prompts']]),
        'with_blessed': len([p for p in prompt_details if p['has_blessed']]),
        'samples': prompt_details
    })

@app.post('/api/prompts/bless')
async def bless_prompt(request: Request):
    """Bless a prompt as the final production prompt"""
    data = await request.json()
    session_id = data.get('session_id')
    sample_name = data.get('sample_name')
    prompt = data.get('prompt')
    score = data.get('score')

    if not all([session_id, sample_name, prompt]):
        return JSONResponse({'error': 'Missing required fields'}, status_code=400)

    session_path = SESSIONS_DIR / session_id
    sample_path = session_path / f"{sample_name}.json"

    if not sample_path.exists():
        return JSONResponse({'error': f'Sample not found: {sample_name}'}, status_code=404)

    try:
        bless_single_prompt(sample_path, prompt, score)
        return JSONResponse({'success': True, 'message': f'Blessed prompt for {sample_name}'})
    except Exception as e:
        logger.error(f"Error blessing prompt: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

@app.post('/api/prompts/bless-bulk')
async def bless_prompts_bulk(request: Request):
    """Bless multiple prompts from evaluation results"""
    data = await request.json()
    session_id = data.get('session_id')
    prompt_map = data.get('prompt_map')  # {sample_name: prompt}

    if not all([session_id, prompt_map]):
        return JSONResponse({'error': 'Missing required fields'}, status_code=400)

    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    try:
        blessed_count = bulk_bless_prompts(session_path, prompt_map)
        return JSONResponse({
            'success': True,
            'blessed_count': blessed_count,
            'message': f'Blessed {blessed_count} prompts'
        })
    except Exception as e:
        logger.error(f"Error bulk blessing prompts: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

@app.get('/api/generate-prompts-sse/{session_id}')
async def generate_prompts_sse(session_id: str):
    """Generate AI prompts with Server-Sent Events for real-time progress"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    async def event_generator():
        try:
            # Import here to avoid circular imports
            from clap_prompt_generator import load_session_samples, load_evaluator_config, generate_prompts_batch

            # Send initial status
            yield f"data: {json.dumps({'status': 'starting', 'message': 'Loading samples...'})}\n\n"

            samples = load_session_samples(session_path)
            total_samples = len(samples)

            yield f"data: {json.dumps({'status': 'loaded', 'total_samples': total_samples, 'message': f'Found {total_samples} samples'})}\n\n"

            # Load config
            config = load_evaluator_config()
            batch_size = config.get('batch_size', 10)
            total_batches = (total_samples + batch_size - 1) // batch_size

            # Estimate time
            estimated_time = total_batches * 3  # ~3 seconds per batch
            yield f"data: {json.dumps({'status': 'info', 'message': f'Processing {total_batches} batches (~{estimated_time}s)'})}\n\n"

            # Process in batches
            all_prompts = {}
            for i in range(0, total_samples, batch_size):
                batch = samples[i:i + batch_size]
                batch_num = (i // batch_size) + 1

                # Send batch start
                yield f"data: {json.dumps({'status': 'processing', 'batch': batch_num, 'total_batches': total_batches, 'progress': (i/total_samples)*100, 'message': f'Processing batch {batch_num}/{total_batches}'})}\n\n"

                # Generate prompts for batch
                batch_prompts = generate_prompts_batch(batch, config)
                all_prompts.update(batch_prompts)

                # Send progress update
                progress = len(all_prompts) / total_samples * 100
                yield f"data: {json.dumps({'status': 'progress', 'progress': progress, 'completed': len(all_prompts), 'total': total_samples})}\n\n"

                # Small delay to prevent overwhelming
                await asyncio.sleep(0.1)

            if not all_prompts:
                yield f"data: {json.dumps({'status': 'error', 'message': 'No prompts generated. Check AI settings.'})}\n\n"
                return

            # Save prompts
            yield f"data: {json.dumps({'status': 'saving', 'message': 'Saving prompts to files...'})}\n\n"
            updated = save_prompts_to_samples(session_path, all_prompts)

            # Send completion
            yield f"data: {json.dumps({'status': 'complete', 'prompts_generated': len(all_prompts), 'samples_updated': updated, 'message': f'Generated {len(all_prompts)} prompts'})}\n\n"

        except Exception as e:
            logger.error(f"Error in SSE prompt generation: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post('/api/generate-prompts/{session_id}')
async def generate_prompts(session_id: str):
    """Generate AI prompts for all samples in a session"""
    session_path = SESSIONS_DIR / session_id
    if not session_path.exists():
        return JSONResponse({'error': f'Session not found: {session_id}'}, status_code=404)

    try:
        # First check how many samples we have
        from clap_prompt_generator import load_session_samples, load_evaluator_config, generate_prompts_batch

        samples = load_session_samples(session_path)
        total_samples = len(samples)

        logger.info(f"Generating prompts for session {session_id} ({total_samples} samples)")

        # For large sessions, warn the user
        if total_samples > 100:
            logger.warning(f"Large session with {total_samples} samples. This may take several minutes.")

        # Load config
        config = load_evaluator_config()
        batch_size = config.get('batch_size', 10)

        # Process in batches with progress logging
        all_prompts = {}
        for i in range(0, total_samples, batch_size):
            batch = samples[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_samples + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} samples)")

            batch_prompts = generate_prompts_batch(batch, config)
            all_prompts.update(batch_prompts)

            # Log progress
            progress = len(all_prompts) / total_samples * 100
            logger.info(f"Progress: {progress:.1f}% ({len(all_prompts)}/{total_samples} samples)")

        if not all_prompts:
            return JSONResponse({
                'success': False,
                'error': 'No prompts generated. Check AI settings and logs.'
            })

        # Save to sample files
        logger.info(f"Saving prompts to {len(all_prompts)} sample files...")
        updated = save_prompts_to_samples(session_path, all_prompts)

        return JSONResponse({
            'success': True,
            'generated': len(all_prompts),
            'updated_files': updated,
            'total_samples': total_samples
        })

    except Exception as e:
        logger.error(f"Error generating prompts: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse({
            'success': False,
            'error': str(e)
        })


@app.post('/api/export/themes')
async def export_themes(request: Request):
    """Export successful configurations to themes.json format"""
    data = await request.json()
    theme_configs = data.get('themes', [])

    # Format for RadioStation themes.json
    themes_export = []
    for config in theme_configs:
        theme_entry = {
            'name': config['name'],
            'search': config.get('search', ''),  # Will need to be provided by user
            'prompt': config['prompt']
        }
        themes_export.append(theme_entry)

    return JSONResponse({
        'success': True,
        'themes': themes_export,
        'filename': 'themes_export.json'
    })


# Serve results files
from fastapi.staticfiles import StaticFiles

# Ensure results directory exists
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount results directory if it exists
if RESULTS_DIR.exists():
    app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")
else:
    logger.warning(f"Results directory not found: {RESULTS_DIR}")


if __name__ == '__main__':
    import uvicorn
    print("Starting CLAP Evaluation Browser...")
    print("Navigate to: http://localhost:8001")
    uvicorn.run(app, host='0.0.0.0', port=8001)