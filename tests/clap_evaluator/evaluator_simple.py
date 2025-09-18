#!/usr/bin/env python3
"""
Simplified CLAP Evaluation Tool for testing without heavy dependencies
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import numpy as np
import random


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
            try:
                with open(json_files[0], 'r') as f:
                    data = json.load(f)
                    original_prompt = data.get('theme_prompt', '')
            except:
                pass

        metadata['themes'][theme_name] = {
            'sample_count': len(wav_files),
            'original_prompt': original_prompt,
            'samples': []
        }

        # Load sample metadata
        for json_file in json_files[:5]:  # Limit to first 5 for testing
            try:
                with open(json_file, 'r') as f:
                    sample_data = json.load(f)
                    wav_file = json_file.with_suffix('.wav')
                    if wav_file.exists():
                        metadata['themes'][theme_name]['samples'].append({
                            'wav_path': str(wav_file),
                            'json_path': str(json_file),
                            'search_term': sample_data.get('search_term', ''),
                            'title': sample_data.get('title', '')[:50]
                        })
            except:
                pass

        metadata['total_samples'] += len(wav_files)

    return metadata


def score_audio_simulated(wav_path: Path, prompts: Dict[str, str]) -> Dict:
    """Simulate scoring for testing without CLAP model"""
    random.seed(str(wav_path))
    theme_names = list(prompts.keys())
    scores = {name: random.uniform(0.2, 0.8) for name in theme_names}
    best_theme = max(scores.items(), key=lambda x: x[1])
    return {
        'best_theme': best_theme[0],
        'best_score': best_theme[1],
        'all_scores': scores
    }


def evaluate_session_simple(session_path: Path, test_config: Dict) -> Dict:
    """Simplified evaluation for testing"""
    results = {
        'session_id': session_path.name,
        'timestamp': datetime.now().isoformat(),
        'test_runs': []
    }

    metadata = load_session_metadata(session_path)
    results['metadata'] = metadata

    print(f"Testing {len(metadata['themes'])} themes with {metadata['total_samples']} total samples")

    for test_run in test_config.get('test_runs', []):
        print(f"\nRunning: {test_run['name']} (threshold: {test_run['threshold']})")

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
                'cross_assigned': []
            }

        # Evaluate samples (limited for testing)
        sample_count = 0
        for theme_name, theme_data in metadata['themes'].items():
            for sample in theme_data['samples'][:3]:  # Limit samples for testing
                wav_path = Path(sample['wav_path'])
                if not wav_path.exists():
                    continue

                scores = score_audio_simulated(wav_path, test_run['prompts'])
                sample_count += 1

                sample_result = {
                    'wav_path': str(wav_path),
                    'original_theme': theme_name,
                    'best_theme': scores['best_theme'],
                    'best_score': scores['best_score'],
                    'all_scores': scores['all_scores']
                }

                if scores['best_score'] >= test_run['threshold']:
                    if scores['best_theme'] == theme_name:
                        run_results['themes'][theme_name]['passed'].append(sample_result)
                    else:
                        run_results['themes'][theme_name]['cross_assigned'].append(sample_result)
                else:
                    run_results['themes'][theme_name]['failed'].append(sample_result)

        print(f"  Evaluated {sample_count} samples (simulated)")

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
                'pass_rate': len(theme_results['passed']) / total if total > 0 else 0
            }

        run_results['statistics'] = stats
        results['test_runs'].append(run_results)

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Simplified CLAP Evaluator for Testing')
    parser.add_argument('--session', type=str, help='Session ID')
    parser.add_argument('--list', action='store_true', help='List sessions')
    args = parser.parse_args()

    sessions_dir = Path(__file__).parent.parent.parent / 'wavs' / 'sessions'

    if args.list:
        print("Available sessions:")
        for session_dir in sorted(sessions_dir.iterdir()):
            if session_dir.is_dir():
                metadata = load_session_metadata(session_dir)
                print(f"  {session_dir.name}: {metadata['total_samples']} samples")
        return

    if not args.session:
        print("Use --list to see sessions or --session to test one")
        return

    session_path = sessions_dir / args.session
    if not session_path.exists():
        print(f"Session not found: {args.session}")
        return

    # Simple test config
    metadata = load_session_metadata(session_path)
    default_prompts = {}
    for theme_name, theme_data in metadata['themes'].items():
        default_prompts[theme_name] = theme_data['original_prompt'] or f"{theme_name} audio"

    test_config = {
        'test_runs': [{
            'name': 'Test Run',
            'prompts': default_prompts,
            'threshold': 0.40
        }]
    }

    print(f"\n=== Simplified Evaluation (Simulated Scores) ===")
    print(f"Session: {args.session}")

    results = evaluate_session_simple(session_path, test_config)

    # Save results
    output_dir = Path(__file__).parent / 'results' / 'test_run'
    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / 'results.json'
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {results_path}")
    print("\nNote: This is using simulated scores for testing.")
    print("Use the full evaluator.py with CLAP model for real evaluation.")


if __name__ == '__main__':
    main()