#!/usr/bin/env python3
"""Quick test to verify the current optimization setup is working."""

import os
import sys
from pathlib import Path

# Add parent directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_env, load_themes
from app import scoring
from app.search_expander_v2 import batch_expand_search_terms_v2, expand_single_term

def test_basic_setup():
    """Test basic setup components."""
    print("=== Testing Basic Setup ===")
    
    # Load environment
    load_env()
    print(f"✓ Environment loaded")
    print(f"  SCORING_ENABLED: {os.environ.get('SCORING_ENABLED')}")
    print(f"  USE_OPENAI_EXPANSION: {os.environ.get('USE_OPENAI_EXPANSION')}")
    print(f"  SLICES_PER_VIDEO: {os.environ.get('SLICES_PER_VIDEO')}")
    print(f"  DOWNLOAD_CHUNK_SECONDS: {os.environ.get('DOWNLOAD_CHUNK_SECONDS')}")
    
    # Test CLAP scoring
    if scoring.is_enabled():
        print("✓ CLAP scoring enabled")
        try:
            # Try to initialize model
            scoring._ensure_model()
            print("✓ CLAP model loaded successfully")
        except Exception as e:
            print(f"❌ CLAP model failed to load: {e}")
            return False
    else:
        print("❌ CLAP scoring disabled")
        return False
    
    # Load themes
    themes = load_themes()
    print(f"✓ Loaded {len(themes)} themes")
    for i, theme in enumerate(themes[:3]):
        print(f"  {i+1}. {theme['name']}: '{theme['search']}' → \"{theme['prompt'][:50]}...\"")
    
    return True

def test_search_expansion():
    """Test search expansion functionality."""
    print("\n=== Testing Search Expansion ===")
    
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    print("✓ OpenAI API key found")
    
    # Test single expansion
    try:
        expansions = expand_single_term("whisper", "Quiet gentle whisper voice speaking softly", api_key)
        print(f"✓ Single expansion test: 'whisper' → {expansions[:2]}")
    except Exception as e:
        print(f"❌ Single expansion failed: {e}")
        return False
    
    # Test batch expansion
    try:
        themes = load_themes()[:2]  # Test 2 themes
        expanded = batch_expand_search_terms_v2(themes, samples_per_theme=4)
        print("✓ Batch expansion test:")
        for theme in themes:
            theme_name = theme['name']
            if theme_name in expanded:
                print(f"  {theme_name}: '{theme['search']}' → {expanded[theme_name][:2]}")
            else:
                print(f"  {theme_name}: No expansion")
    except Exception as e:
        print(f"❌ Batch expansion failed: {e}")
        return False
    
    return True

def test_single_download():
    """Test downloading and processing a single candidate."""
    print("\n=== Testing Single Download ===")
    
    try:
        from app.downloader import download_candidates_for_term
        
        # Test download for a simple theme
        themes = load_themes()
        test_theme = None
        for theme in themes:
            if theme['search'] in ['whisper', 'bell', 'drum']:
                test_theme = theme
                break
        
        if not test_theme:
            test_theme = themes[0]  # Fallback to first theme
        
        print(f"Testing download for theme: {test_theme['name']} (search: '{test_theme['search']}')")
        
        candidates = download_candidates_for_term(
            test_theme['search'],
            clip_ms=2000,
            max_results=1,  # Just 1 for quick test
            download_workers=1,
            slices_per_video=3,  # Try 3 slices
            slice_stride_ms=1000,
            log_cb=lambda msg: print(f"  {msg}"),
            theme_name=test_theme['name'],
            theme_prompt=test_theme['prompt'],
            original_search=test_theme['search']
        )
        
        if candidates:
            print(f"✓ Downloaded {len(candidates)} candidates")
            
            # Test CLAP scoring on first candidate
            candidate = candidates[0]
            prompts = [{'name': test_theme['name'], 'prompt': test_theme['prompt']}]
            
            result = scoring.best_theme_for_wav(candidate, prompts, [test_theme['name']])
            if result:
                theme_name, score = result
                print(f"✓ CLAP scoring: {theme_name} = {score:.3f}")
                
                # Check threshold
                min_sim = float(os.environ.get('SCORING_MIN_SIMILARITY', '0.2'))
                if score >= min_sim:
                    print(f"✓ Score passes threshold ({score:.3f} >= {min_sim})")
                else:
                    print(f"⚠ Score below threshold ({score:.3f} < {min_sim})")
            else:
                print("❌ CLAP scoring failed")
                return False
        else:
            print("❌ No candidates downloaded")
            return False
            
    except Exception as e:
        print(f"❌ Download test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Run all tests."""
    print("Quick Optimization Test Suite")
    print("=" * 50)
    
    success = True
    
    if not test_basic_setup():
        success = False
    
    if not test_search_expansion():
        success = False
    
    if not test_single_download():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! System is ready for optimization.")
    else:
        print("❌ Some tests failed. Fix issues before running full optimization.")
        sys.exit(1)

if __name__ == '__main__':
    main()