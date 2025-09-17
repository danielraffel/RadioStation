#!/usr/bin/env python3
"""Test script to verify hashing and metadata functionality."""

import json
import sys
from pathlib import Path

# Add parent directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.downloader import _init_tracking, _is_duplicate, _save_hash
from app.hash_manager import get_hash_manager, calculate_file_hash

# Initialize tracking
_init_tracking()

# Get hash manager
hash_mgr = get_hash_manager()

# Test file hashing
test_file = Path("app/static/index.html")
if test_file.exists():
    hash1 = calculate_file_hash(test_file)
    print(f"✓ File hash calculated: {hash1[:8]}...")
    
    # Test saving hash
    _save_hash(hash1)
    print("✓ Hash saved to database")
    
    # Test duplicate detection
    is_dup = _is_duplicate(test_file)
    print(f"✓ Duplicate detection working: {is_dup}")
    
    # Check database stats
    stats = hash_mgr.get_stats()
    print(f"✓ Database contains {stats['total_hashes']} hashes, {stats['total_urls']} URLs")
    
    # Check aria2c availability
    import shutil
    has_aria = shutil.which('aria2c') is not None
    print(f"✓ aria2c available: {has_aria}")
    
    # Check yt-dlp availability
    has_ytdlp = shutil.which('yt-dlp') is not None
    print(f"✓ yt-dlp available: {has_ytdlp}")
    
    # Test words manager
    from app.words_manager import get_words_manager
    words_mgr = get_words_manager()
    if words_mgr.is_available():
        word = words_mgr.get_random_word()
        print(f"✓ Words manager loaded, sample word: '{word}'")
    else:
        print("⚠ Words manager not available (words.txt not found)")
    
    # Check themes
    themes_file = Path("app/themes.json")
    if themes_file.exists():
        with open(themes_file) as f:
            themes = json.load(f)
            print(f"✓ Loaded {len(themes)} themes")
    
    # Test search expansion (optional)
    from app.search_expander import is_expansion_enabled
    if is_expansion_enabled():
        print("✓ OpenAI expansion enabled")
    else:
        print("⚠ OpenAI expansion disabled (set USE_OPENAI_EXPANSION=1 to enable)")
    
    print("\n✅ All tests passed!")
else:
    print("❌ Test file not found")
    sys.exit(1)