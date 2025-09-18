#!/usr/bin/env python3
"""
Enhanced HTML Report Generator for CLAP Evaluation
Shows prompts used, scores, and allows for blessing prompts
"""

from pathlib import Path
from typing import Dict, List
import json


def generate_enhanced_html_report(results: Dict, output_dir: Path, session_id: str):
    """Generate an enhanced interactive HTML report with prompt details"""

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLAP Evaluation Results - {session_id}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .audio-player {{ width: 100%; max-width: 300px; }}
        .prompt-text {{
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .prompt-text:hover {{
            overflow: visible;
            white-space: normal;
            background: #2a2a2a;
            padding: 8px;
            border-radius: 4px;
            position: relative;
            z-index: 10;
        }}
    </style>
</head>
<body class="bg-gray-900 text-gray-100">
    <div class="container mx-auto px-4 py-8">
        <header class="bg-gray-800 rounded-lg p-6 mb-6">
            <h1 class="text-2xl font-bold mb-2">CLAP Evaluation Results</h1>
            <div class="text-sm text-gray-400">
                <span>Session: {session_id}</span> •
                <span>Total Samples: {total_samples}</span> •
                <span>Evaluated: {timestamp}</span>
            </div>
        </header>

        <!-- Summary Section -->
        <div class="grid grid-cols-1 md:grid-cols-{num_configs} gap-4 mb-8">
            {config_summaries}
        </div>

        <!-- Theme Results -->
        <div class="space-y-8">
            {theme_sections}
        </div>

        <!-- Blessing Interface -->
        <div class="fixed bottom-4 right-4">
            <button onclick="showBlessingModal()"
                    class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg shadow-lg">
                Bless Selected Prompts ({bless_count})
            </button>
        </div>
    </div>

    <script>
        let selectedPrompts = {{}};

        function togglePromptSelection(sampleId, prompt, score) {{
            if (selectedPrompts[sampleId]) {{
                delete selectedPrompts[sampleId];
            }} else {{
                selectedPrompts[sampleId] = {{prompt: prompt, score: score}};
            }}
            updateBlessCount();
        }}

        function updateBlessCount() {{
            const count = Object.keys(selectedPrompts).length;
            document.querySelector('.fixed button').textContent = `Bless Selected Prompts (${{count}})`;
        }}

        function showBlessingModal() {{
            if (Object.keys(selectedPrompts).length === 0) {{
                alert('No prompts selected for blessing');
                return;
            }}

            if (!confirm(`Bless ${{Object.keys(selectedPrompts).length}} prompts as final?`)) {{
                return;
            }}

            // Send to backend
            fetch('/api/prompts/bless-bulk', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    session_id: '{session_id}',
                    prompt_map: Object.fromEntries(
                        Object.entries(selectedPrompts).map(([k, v]) => [k, v.prompt])
                    )
                }})
            }}).then(response => response.json())
              .then(data => {{
                  if (data.success) {{
                      alert(`Successfully blessed ${{data.blessed_count}} prompts`);
                      selectedPrompts = {{}};
                      updateBlessCount();
                  }} else {{
                      alert('Error: ' + data.error);
                  }}
              }});
        }}
    </script>
</body>
</html>"""

    # Generate config summaries
    config_summaries = ""
    for i, run in enumerate(results['test_runs']):
        overall_pass_rate = 0
        total_passed = 0
        total_samples = 0

        for theme_results in run['themes'].values():
            total_passed += len(theme_results['passed'])
            total_samples += len(theme_results['passed']) + len(theme_results['failed'])

        if total_samples > 0:
            overall_pass_rate = (total_passed / total_samples) * 100

        config_summaries += f"""
        <div class="bg-gray-800 rounded-lg p-4">
            <h2 class="text-lg font-semibold text-blue-400 mb-2">Configuration {i+1}</h2>
            <div class="text-sm text-gray-300">
                <div>Threshold: {run['threshold']}</div>
                <div>Pass Rate: {overall_pass_rate:.1f}%</div>
            </div>
            <div class="mt-2 space-y-1">
                {generate_prompt_list(run['prompts'])}
            </div>
        </div>
        """

    # Generate theme sections with detailed results
    theme_sections = ""
    if results['test_runs']:
        first_run = results['test_runs'][0]  # Use first config for detailed view

        for theme_name, theme_results in first_run['themes'].items():
            passed_count = len(theme_results['passed'])
            failed_count = len(theme_results['failed'])
            total = passed_count + failed_count
            pass_rate = (passed_count / total * 100) if total > 0 else 0

            theme_sections += f"""
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-semibold mb-4">
                    {theme_name}
                    <span class="text-sm font-normal text-gray-400">
                        ({passed_count}/{total} passed - {pass_rate:.1f}%)
                    </span>
                </h3>

                <div class="space-y-2">
                    {generate_sample_rows(theme_name, theme_results, session_id)}
                </div>
            </div>
            """

    # Fill in template
    html = html.format(
        session_id=session_id,
        total_samples=results['metadata']['total_samples'],
        timestamp=results['timestamp'],
        num_configs=len(results['test_runs']),
        config_summaries=config_summaries,
        theme_sections=theme_sections,
        bless_count=0
    )

    # Write HTML file
    html_path = output_dir / 'index.html'
    with open(html_path, 'w') as f:
        f.write(html)

    return html_path


def generate_prompt_list(prompts: Dict[str, str]) -> str:
    """Generate HTML for prompt list"""
    html = ""
    for theme, prompt in prompts.items():
        html += f"""
        <div class="text-xs">
            <span class="text-gray-500">{theme}:</span>
            <span class="prompt-text" title="{prompt}">{prompt}</span>
        </div>
        """
    return html


def generate_sample_rows(theme_name: str, theme_results: Dict, session_id: str) -> str:
    """Generate HTML rows for each sample"""
    rows = ""

    # Show all samples (passed and failed)
    all_samples = []

    for sample in theme_results.get('passed', []):
        sample['status'] = 'pass'
        all_samples.append(sample)

    for sample in theme_results.get('failed', []):
        sample['status'] = 'fail'
        all_samples.append(sample)

    # Sort by filename
    all_samples.sort(key=lambda x: Path(x['wav_path']).name)

    for sample in all_samples:
        wav_name = Path(sample['wav_path']).stem
        wav_file = Path(sample['wav_path']).name
        best_score = sample.get('best_score', 0)
        best_theme = sample.get('best_theme', 'Unknown')
        prompt_used = sample.get('prompt_used', sample.get('scores', {}).get(theme_name, {}).get('prompt', 'N/A'))

        # Determine status color
        status_color = 'green' if sample['status'] == 'pass' else 'red'
        status_icon = '✓' if sample['status'] == 'pass' else '✗'

        # Audio URL - using our new endpoint
        audio_url = f"/audio/{session_id}/{theme_name}/{wav_file}"

        rows += f"""
        <div class="flex items-center gap-4 p-3 bg-gray-700/50 rounded hover:bg-gray-700/70">
            <div class="text-{status_color}-500 text-lg">{status_icon}</div>

            <audio controls class="audio-player" src="{audio_url}"></audio>

            <div class="flex-1">
                <div class="font-medium">{wav_name}</div>
                <div class="text-xs text-gray-400">
                    Theme: {best_theme} • Score: {best_score:.3f}
                </div>
                <div class="text-xs text-gray-500 prompt-text mt-1" title="{prompt_used}">
                    Prompt: {prompt_used}
                </div>
            </div>

            <div class="flex gap-2">
                <button onclick="togglePromptSelection('{wav_name}', '{prompt_used.replace("'", "\\'")}', {best_score})"
                        class="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded">
                    Select for Blessing
                </button>
            </div>
        </div>
        """

    return rows