#!/usr/bin/env python3
"""
CLAP Evaluation Tool
Test different CLAP prompts and thresholds on existing session data.
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import shutil

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app import scoring
from pydub import AudioSegment
import numpy as np


def load_session_metadata(session_path: Path) -> Dict:
    """Load metadata about a session"""
    metadata = {
        'session_id': session_path.name,
        'themes': {},
        'total_samples': 0
    }

    themes_dir = session_path / 'themes'
    if not themes_dir.exists():
        return metadata

    for theme_dir in themes_dir.iterdir():
        if not theme_dir.is_dir():
            continue

        theme_name = theme_dir.name
        wav_files = list(theme_dir.glob('*.wav'))
        json_files = list(theme_dir.glob('*.json'))

        # Get original prompt from first JSON file
        original_prompt = None
        if json_files:
            with open(json_files[0], 'r') as f:
                data = json.load(f)
                original_prompt = data.get('theme_prompt', '')

        metadata['themes'][theme_name] = {
            'sample_count': len(wav_files),
            'original_prompt': original_prompt,
            'samples': []
        }

        # Load sample metadata
        for json_file in json_files:
            with open(json_file, 'r') as f:
                sample_data = json.load(f)
                wav_file = json_file.with_suffix('.wav')
                if wav_file.exists():
                    sample_metadata = {
                        'wav_path': str(wav_file),
                        'json_path': str(json_file),
                        'search_term': sample_data.get('search_term', ''),
                        'url': sample_data.get('url', ''),
                        'title': sample_data.get('title', ''),
                        'tags': sample_data.get('tags', []),
                        'categories': sample_data.get('categories', [])
                    }

                    # Check for AI-generated prompts
                    if 'best_clap_prompt' in sample_data:
                        sample_metadata['best_clap_prompt'] = sample_data['best_clap_prompt']
                    if 'generated_clap_prompts' in sample_data:
                        sample_metadata['generated_clap_prompts'] = sample_data['generated_clap_prompts']

                    metadata['themes'][theme_name]['samples'].append(sample_metadata)

        metadata['total_samples'] += len(wav_files)

    return metadata


def score_audio_with_prompts(wav_path: Path, prompts: Dict[str, str]) -> Dict:
    """Score a single audio file against multiple prompts"""
    try:
        if not scoring.is_enabled():
            # Enable scoring temporarily
            import os
            os.environ['SCORING_ENABLED'] = '1'

        scoring._ensure_model()
    except Exception as e:
        print(f"\nWARNING: CLAP model not available: {e}")
        print("Running in simulation mode - generating random scores for testing\n")
        # Return simulated scores for testing
        import random
        random.seed(str(wav_path))  # Consistent scores for same file
        theme_names = list(prompts.keys())
        scores = {name: random.uniform(0.2, 0.8) for name in theme_names}
        best_theme = max(scores.items(), key=lambda x: x[1])
        return {
            'best_theme': best_theme[0],
            'best_score': best_theme[1],
            'all_scores': scores
        }

    # Check if model is loaded
    if scoring._model is None:
        # Already returned simulated scores above
        return {
            'best_theme': None,
            'best_score': 0.0,
            'all_scores': {}
        }

    # Prepare prompts in the format expected by scoring module
    prompt_list = [{'name': name, 'prompt': text} for name, text in prompts.items()]
    theme_names = list(prompts.keys())

    # Get best theme and score
    result = scoring.best_theme_for_wav(wav_path, prompt_list, theme_names)

    if result is None:
        return {
            'best_theme': None,
            'best_score': 0.0,
            'all_scores': {}
        }

    best_theme, best_score = result

    # Get all scores for detailed analysis
    all_scores = {}
    if scoring._model is not None:
        try:
            import torch

            # Compute embeddings
            audio_emb = scoring._model.get_audio_embedding_from_filelist(x=[str(wav_path)], use_tensor=True)
            text_emb = scoring._model.get_text_embedding(list(prompts.values()), use_tensor=True)

            # Normalize and compute similarities
            a = torch.nn.functional.normalize(audio_emb, dim=-1)
            t = torch.nn.functional.normalize(text_emb, dim=-1)
            sims = (a @ t.T).squeeze(0)

            for i, theme_name in enumerate(theme_names):
                all_scores[theme_name] = float(sims[i].item())
        except Exception as e:
            print(f"Warning: Could not compute all scores: {e}")
            all_scores = {best_theme: best_score}

    return {
        'best_theme': best_theme,
        'best_score': best_score,
        'all_scores': all_scores
    }


def evaluate_session(session_path: Path, test_config: Dict, progress_callback=None) -> Dict:
    """Run evaluation on a session with specified test configuration

    Args:
        session_path: Path to session directory
        test_config: Test configuration with prompts and thresholds
        progress_callback: Optional callback function(percent, message, theme_progress)
    """
    results = {
        'session_id': session_path.name,
        'timestamp': datetime.now().isoformat(),
        'test_runs': []
    }

    # Load session metadata
    metadata = load_session_metadata(session_path)
    results['metadata'] = metadata

    # Calculate total samples for progress tracking
    total_samples = sum(len(theme_data['samples']) for theme_data in metadata['themes'].values())
    total_tests = len(test_config.get('test_runs', []))
    samples_processed = 0

    # Run each test configuration
    for test_idx, test_run in enumerate(test_config.get('test_runs', [])):
        print(f"\nRunning test: {test_run['name']}")
        print(f"  Threshold: {test_run['threshold']}")

        run_results = {
            'name': test_run['name'],
            'threshold': test_run['threshold'],
            'prompts': test_run['prompts'],
            'themes': {}
        }

        # Initialize theme results
        for theme_name in test_run['prompts'].keys():
            run_results['themes'][theme_name] = {
                'passed': [],
                'failed': [],
                'cross_assigned': []  # Samples that were assigned to different themes
            }

        # Evaluate each sample
        for theme_name, theme_data in metadata['themes'].items():
            theme_samples = theme_data['samples']
            for sample_idx, sample in enumerate(theme_samples):
                wav_path = Path(sample['wav_path'])
                if not wav_path.exists():
                    continue

                # Update progress
                samples_processed += 1
                if progress_callback:
                    overall_percent = (samples_processed / (total_samples * total_tests)) * 100
                    theme_progress = {
                        'theme': theme_name,
                        'current': sample_idx + 1,
                        'total': len(theme_samples)
                    }
                    progress_callback(
                        overall_percent,
                        f"Test {test_idx + 1}/{total_tests}: Evaluating {theme_name}",
                        theme_progress
                    )

                # Use AI-generated prompt if available, otherwise use test config prompt
                eval_prompts = test_run['prompts'].copy()

                # Check if this sample has an AI-generated prompt
                if 'best_clap_prompt' in sample:
                    # Replace the theme's prompt with the AI-generated one
                    eval_prompts[theme_name] = sample['best_clap_prompt']
                    print(f"  Using AI prompt: {sample['best_clap_prompt'][:50]}...")

                # Score against all prompts
                scores = score_audio_with_prompts(wav_path, eval_prompts)

                sample_result = {
                    'wav_path': str(wav_path),
                    'original_theme': theme_name,
                    'best_theme': scores['best_theme'],
                    'best_score': scores['best_score'],
                    'all_scores': scores['all_scores'],
                    'search_term': sample['search_term'],
                    'title': sample['title']
                }

                # Categorize result
                if scores['best_score'] >= test_run['threshold']:
                    if scores['best_theme'] == theme_name:
                        run_results['themes'][theme_name]['passed'].append(sample_result)
                    else:
                        # Cross-assigned to different theme
                        run_results['themes'][theme_name]['cross_assigned'].append(sample_result)
                        if scores['best_theme'] in run_results['themes']:
                            run_results['themes'][scores['best_theme']]['cross_assigned'].append(sample_result)
                else:
                    run_results['themes'][theme_name]['failed'].append(sample_result)

                print(f"  {wav_path.name}: {theme_name} -> {scores['best_theme']} ({scores['best_score']:.3f})")

        # Calculate statistics
        stats = {}
        for theme_name in run_results['themes']:
            theme_results = run_results['themes'][theme_name]
            total = len(theme_results['passed']) + len(theme_results['failed']) + len(theme_results['cross_assigned'])

            stats[theme_name] = {
                'total': total,
                'passed': len(theme_results['passed']),
                'failed': len(theme_results['failed']),
                'cross_assigned': len(theme_results['cross_assigned']),
                'pass_rate': len(theme_results['passed']) / total if total > 0 else 0,
                'avg_score': np.mean([s['best_score'] for s in theme_results['passed']]) if theme_results['passed'] else 0
            }

        run_results['statistics'] = stats
        results['test_runs'].append(run_results)

    return results


def discovery_mode_analysis(session_path: Path, sample_limit: int = 10) -> Dict:
    """Analyze a session to understand CLAP score distributions

    Args:
        session_path: Path to session directory
        sample_limit: Number of samples to analyze per theme

    Returns:
        Discovery analysis with score distributions and recommendations
    """
    metadata = load_session_metadata(session_path)
    analysis = {
        'session_id': session_path.name,
        'themes': {},
        'recommendations': []
    }

    # Create generic prompts for each theme
    generic_prompts = {}
    for theme_name in metadata['themes'].keys():
        variations = [
            f"{theme_name.lower()} sounds",
            f"{theme_name.lower()} audio",
            f"sounds that are {theme_name.lower()}",
            f"{theme_name.lower()} noise",
            f"{theme_name.lower()} characteristics"
        ]
        generic_prompts[theme_name] = variations

    print(f"\n=== Discovery Mode for {session_path.name} ===")

    # Analyze each theme
    for theme_name, theme_data in metadata['themes'].items():
        theme_analysis = {
            'sample_count': theme_data['sample_count'],
            'scores': [],
            'best_prompts': [],
            'score_distribution': {}
        }

        samples_to_analyze = theme_data['samples'][:sample_limit]
        print(f"\nAnalyzing {theme_name} ({len(samples_to_analyze)} samples)...")

        for sample in samples_to_analyze:
            wav_path = Path(sample['wav_path'])
            if not wav_path.exists():
                continue

            # Test with original prompt
            if theme_data.get('original_prompt'):
                scores = score_audio_with_prompts(wav_path, {theme_name: theme_data['original_prompt']})
                theme_analysis['scores'].append(scores['all_scores'][theme_name])

            # Test with variations to find what works best
            best_score = 0
            best_prompt = ""
            for variation in generic_prompts[theme_name]:
                test_scores = score_audio_with_prompts(wav_path, {theme_name: variation})
                score = test_scores['all_scores'][theme_name]
                if score > best_score:
                    best_score = score
                    best_prompt = variation

            theme_analysis['best_prompts'].append({
                'prompt': best_prompt,
                'score': best_score
            })

        # Calculate statistics
        if theme_analysis['scores']:
            scores_array = np.array(theme_analysis['scores'])
            theme_analysis['score_distribution'] = {
                'mean': float(np.mean(scores_array)),
                'std': float(np.std(scores_array)),
                'min': float(np.min(scores_array)),
                'max': float(np.max(scores_array)),
                'median': float(np.median(scores_array)),
                'percentile_25': float(np.percentile(scores_array, 25)),
                'percentile_75': float(np.percentile(scores_array, 75))
            }

            # Recommend threshold based on distribution
            recommended_threshold = float(np.percentile(scores_array, 30))
            analysis['recommendations'].append({
                'theme': theme_name,
                'recommended_threshold': recommended_threshold,
                'reasoning': f"Based on score distribution (median: {theme_analysis['score_distribution']['median']:.3f})"
            })

        analysis['themes'][theme_name] = theme_analysis

    # Overall recommendations
    all_medians = [t['score_distribution']['median']
                   for t in analysis['themes'].values()
                   if 'score_distribution' in t and 'median' in t['score_distribution']]

    if all_medians:
        overall_median = np.median(all_medians)
        analysis['overall_recommendation'] = {
            'threshold': float(overall_median * 0.8),
            'reasoning': f"Set to 80% of overall median score ({overall_median:.3f})"
        }

    return analysis


def generate_html_report(results: Dict, output_dir: Path):
    """Generate an interactive HTML report"""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLAP Evaluation Results - {session_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, system-ui, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 20px;
        }}
        .header {{
            background: #2a2a2a;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .metadata {{
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: #999;
        }}
        .test-runs {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .test-run {{
            background: #2a2a2a;
            border-radius: 8px;
            padding: 15px;
        }}
        .test-run h2 {{
            font-size: 18px;
            margin-bottom: 10px;
            color: #4a9eff;
        }}
        .threshold {{
            display: inline-block;
            background: #3a3a3a;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-bottom: 10px;
        }}
        .prompts {{
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 12px;
        }}
        .prompt-line {{
            margin-bottom: 5px;
            display: flex;
            gap: 10px;
        }}
        .prompt-theme {{
            font-weight: bold;
            color: #4a9eff;
            min-width: 80px;
        }}
        .stats {{
            display: grid;
            gap: 10px;
        }}
        .theme-stats {{
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
        }}
        .theme-name {{
            font-weight: bold;
            margin-bottom: 8px;
            color: #4a9eff;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            font-size: 12px;
        }}
        .stat {{
            display: flex;
            justify-content: space-between;
        }}
        .stat-label {{ color: #999; }}
        .stat-value {{ font-weight: bold; }}
        .passed {{ color: #4ade80; }}
        .failed {{ color: #f87171; }}
        .cross {{ color: #fbbf24; }}
        .samples {{
            margin-top: 20px;
        }}
        .sample-grid {{
            display: grid;
            gap: 10px;
        }}
        .sample {{
            background: #2a2a2a;
            padding: 10px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .sample.pass {{ border-left: 3px solid #4ade80; }}
        .sample.fail {{ border-left: 3px solid #f87171; }}
        .sample.cross {{ border-left: 3px solid #fbbf24; }}
        audio {{ height: 32px; }}
        .sample-info {{
            flex: 1;
            font-size: 12px;
        }}
        .sample-title {{
            font-weight: bold;
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .sample-scores {{
            display: flex;
            gap: 10px;
            font-size: 11px;
            color: #999;
        }}
        .score-item {{
            display: flex;
            gap: 4px;
        }}
        .score-value {{
            font-weight: bold;
            color: #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>CLAP Evaluation Results</h1>
        <div class="metadata">
            <span>Session: {session_id}</span>
            <span>Total Samples: {total_samples}</span>
            <span>Evaluated: {timestamp}</span>
        </div>
    </div>

    <div class="test-runs">
        {test_runs_html}
    </div>

    <div class="samples">
        <h2>Detailed Results</h2>
        {samples_html}
    </div>

    <script>
        // Add interactive features if needed
        document.querySelectorAll('audio').forEach(audio => {{
            audio.addEventListener('play', () => {{
                document.querySelectorAll('audio').forEach(other => {{
                    if (other !== audio) other.pause();
                }});
            }});
        }});
    </script>
</body>
</html>"""

    # Generate test runs HTML
    test_runs_html = ""
    for run in results['test_runs']:
        prompts_html = "".join([
            f'<div class="prompt-line"><span class="prompt-theme">{theme}:</span><span>{prompt[:50]}...</span></div>'
            for theme, prompt in run['prompts'].items()
        ])

        stats_html = ""
        for theme, stats in run['statistics'].items():
            stats_html += f"""
            <div class="theme-stats">
                <div class="theme-name">{theme}</div>
                <div class="stat-grid">
                    <div class="stat">
                        <span class="stat-label">Total:</span>
                        <span class="stat-value">{stats['total']}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Pass Rate:</span>
                        <span class="stat-value">{stats['pass_rate']:.1%}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label passed">Passed:</span>
                        <span class="stat-value passed">{stats['passed']}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label failed">Failed:</span>
                        <span class="stat-value failed">{stats['failed']}</span>
                    </div>
                </div>
            </div>
            """

        test_runs_html += f"""
        <div class="test-run">
            <h2>{run['name']}</h2>
            <div class="threshold">Threshold: {run['threshold']}</div>
            <div class="prompts">{prompts_html}</div>
            <div class="stats">{stats_html}</div>
        </div>
        """

    # Generate samples HTML (simplified for now)
    samples_html = "<div class='sample-grid'>"
    if results['test_runs']:
        first_run = results['test_runs'][0]
        for theme_name, theme_results in first_run['themes'].items():
            for sample in theme_results['passed'][:5]:  # Show first 5 passed samples
                wav_name = Path(sample['wav_path']).name
                samples_html += f"""
                <div class="sample pass">
                    <audio controls src="../../{Path(sample['wav_path']).relative_to(Path(sample['wav_path']).parent.parent.parent)}"></audio>
                    <div class="sample-info">
                        <div class="sample-title">{wav_name}</div>
                        <div class="sample-scores">
                            <span class="score-item">Theme: <span class="score-value">{sample['best_theme']}</span></span>
                            <span class="score-item">Score: <span class="score-value">{sample['best_score']:.3f}</span></span>
                        </div>
                    </div>
                </div>
                """
    samples_html += "</div>"

    # Fill in template
    html = html.format(
        session_id=results['session_id'],
        total_samples=results['metadata']['total_samples'],
        timestamp=results['timestamp'],
        test_runs_html=test_runs_html,
        samples_html=samples_html
    )

    # Write HTML file
    html_path = output_dir / 'index.html'
    with open(html_path, 'w') as f:
        f.write(html)

    print(f"Generated report: {html_path}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate CLAP scoring on session data')
    parser.add_argument('--session', type=str, help='Session ID to evaluate')
    parser.add_argument('--config', type=str, help='Path to test configuration JSON')
    parser.add_argument('--list', action='store_true', help='List available sessions')

    args = parser.parse_args()

    sessions_dir = Path(__file__).parent.parent.parent / 'wavs' / 'sessions'

    if args.list:
        print("Available sessions:")
        for session_dir in sorted(sessions_dir.iterdir()):
            if session_dir.is_dir():
                metadata = load_session_metadata(session_dir)
                print(f"  {session_dir.name}: {metadata['total_samples']} samples, {len(metadata['themes'])} themes")
        return

    if not args.session:
        print("Please specify --session or use --list to see available sessions")
        return

    session_path = sessions_dir / args.session
    if not session_path.exists():
        print(f"Session not found: {args.session}")
        return

    # Load or create test configuration
    if args.config:
        with open(args.config, 'r') as f:
            test_config = json.load(f)
    else:
        # Default test configuration
        metadata = load_session_metadata(session_path)

        # Build default prompts from session
        default_prompts = {}
        for theme_name, theme_data in metadata['themes'].items():
            if theme_data['original_prompt']:
                default_prompts[theme_name] = theme_data['original_prompt']

        test_config = {
            'test_runs': [
                {
                    'name': 'Original Prompts (0.40)',
                    'prompts': default_prompts,
                    'threshold': 0.40
                },
                {
                    'name': 'Stricter Threshold (0.50)',
                    'prompts': default_prompts,
                    'threshold': 0.50
                },
                {
                    'name': 'Relaxed Threshold (0.30)',
                    'prompts': default_prompts,
                    'threshold': 0.30
                }
            ]
        }

    # Run evaluation
    print(f"Evaluating session: {args.session}")
    results = evaluate_session(session_path, test_config)

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(__file__).parent / 'results' / args.session / f'evaluation_{timestamp}'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON results
    results_path = output_dir / 'results.json'
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved results: {results_path}")

    # Save test configuration
    config_path = output_dir / 'config.json'
    with open(config_path, 'w') as f:
        json.dump(test_config, f, indent=2)

    # Generate HTML report
    generate_html_report(results, output_dir)

    print(f"\nEvaluation complete! View results at:")
    print(f"  {output_dir / 'index.html'}")


if __name__ == '__main__':
    main()