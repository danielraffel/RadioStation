#!/usr/bin/env python3
"""Test single download with optimizations."""

import os
import sys
from pathlib import Path

# Add parent directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_env, load_themes
from app.downloader import download_candidates_for_term
from app import scoring

def main():
    print("=== Testing Single Download ===")
    
    # Load environment and override for testing
    load_env()
    os.environ['SLICES_PER_VIDEO'] = '5'  # Force override
    os.environ['DOWNLOAD_CHUNK_SECONDS'] = '10'
    
    print(f"SLICES_PER_VIDEO: {os.environ.get('SLICES_PER_VIDEO')}")
    print(f"DOWNLOAD_CHUNK_SECONDS: {os.environ.get('DOWNLOAD_CHUNK_SECONDS')}")
    
    # Load themes
    themes = load_themes()
    
    # Pick a theme with concrete search term
    test_theme = None
    for theme in themes:
        if theme['search'] in ['whisper', 'bell', 'drum', 'wind']:
            test_theme = theme
            break
    
    if not test_theme:
        test_theme = themes[0]
    
    print(f"\nTesting theme: {test_theme['name']}")
    print(f"Search term: '{test_theme['search']}'")
    print(f"Prompt: \"{test_theme['prompt'][:60]}...\"")
    
    # Download candidates
    candidates = download_candidates_for_term(
        test_theme['search'],
        clip_ms=2000,
        max_results=1,  # Just 1 video for quick test
        download_workers=1,
        slices_per_video=5,  # Explicitly set to 5
        slice_stride_ms=1000,
        log_cb=lambda msg: print(f"  {msg}"),
        theme_name=test_theme['name'],
        theme_prompt=test_theme['prompt'],
        original_search=test_theme['search']
    )
    
    if not candidates:
        print("❌ No candidates downloaded")
        return
    
    print(f"\n✓ Downloaded {len(candidates)} candidates")
    
    # Test CLAP scoring on each
    prompts = [{'name': test_theme['name'], 'prompt': test_theme['prompt']}]
    min_sim = float(os.environ.get('SCORING_MIN_SIMILARITY', '0.2'))
    
    scores = []
    pass_count = 0
    
    print(f"\nTesting CLAP scores (threshold: {min_sim}):")
    for i, candidate in enumerate(candidates):
        try:
            result = scoring.best_theme_for_wav(candidate, prompts, [test_theme['name']])
            if result:
                theme_name, score = result
                scores.append(score)
                passed = score >= min_sim
                if passed:
                    pass_count += 1
                status = "✓ PASS" if passed else "❌ FAIL"
                print(f"  {i+1}. {candidate.name}: {score:.3f} {status}")
            else:
                print(f"  {i+1}. {candidate.name}: scoring failed")
        except Exception as e:
            print(f"  {i+1}. {candidate.name}: error {e}")
    
    if scores:
        pass_rate = pass_count / len(scores) * 100
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        
        print(f"\n=== Results ===")
        print(f"Candidates tested: {len(scores)}")
        print(f"Passed threshold: {pass_count}")
        print(f"Pass rate: {pass_rate:.1f}%")
        print(f"Average score: {avg_score:.3f}")
        print(f"Score range: {min_score:.3f} to {max_score:.3f}")
        
        if pass_rate >= 60:
            print("🎉 Great! Already achieving target pass rate!")
        elif pass_rate >= 30:
            print("👍 Good progress, close to target")
        else:
            print("⚠ Need more optimization")

if __name__ == '__main__':
    main()