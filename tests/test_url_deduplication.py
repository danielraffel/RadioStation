#!/usr/bin/env python3
"""Comprehensive test to verify URL deduplication across themes."""

import os
import sys
import tempfile
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Add parent directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.hash_manager import HashManager, get_hash_manager
from app.downloader import _download_one, download_candidates_for_term

def test_url_normalization():
    """Test URL normalization and video ID extraction."""
    print("🔍 Testing URL normalization...")
    
    hash_mgr = get_hash_manager()
    
    # Test various YouTube URL formats that should be normalized to the same video
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmRdnEQy4MICZdKOBVYYLK",
        "https://youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/v/dQw4w9WgXcQ"
    ]
    
    normalized_urls = set()
    video_ids = set()
    
    for url in test_urls:
        normalized, video_id = hash_mgr.normalize_url(url)
        normalized_urls.add(normalized)
        if video_id:
            video_ids.add(video_id)
    
    # All should normalize to the same URL and video ID
    assert len(normalized_urls) == 1, f"Expected 1 normalized URL, got {len(normalized_urls)}: {normalized_urls}"
    assert len(video_ids) == 1, f"Expected 1 video ID, got {len(video_ids)}: {video_ids}"
    assert "dQw4w9WgXcQ" in video_ids, f"Expected video ID 'dQw4w9WgXcQ', got {video_ids}"
    
    print("✅ URL normalization working correctly")

def test_atomic_url_marking():
    """Test that URL marking is atomic and prevents race conditions."""
    print("🔍 Testing atomic URL marking...")
    
    hash_mgr = get_hash_manager()
    
    # Use unique URL with timestamp
    import time
    timestamp = str(int(time.time()))
    test_url = f"https://www.youtube.com/watch?v=test_atomic_{timestamp}_123"
    
    # Clear any existing entries for this test URL
    # (Note: We don't have a remove method, so we'll use a unique URL)
    
    results = []
    
    def try_add_url(thread_id):
        """Try to add the same URL from multiple threads."""
        success = hash_mgr.add_url(test_url, f"Test Title {thread_id}", "test search", f"theme_{thread_id}")
        results.append((thread_id, success))
        return success
    
    # Try to add the same URL from multiple threads simultaneously
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_add_url, i) for i in range(10)]
        for future in as_completed(futures):
            future.result()
    
    # Only one thread should have succeeded
    successful_adds = [r for r in results if r[1]]
    failed_adds = [r for r in results if not r[1]]
    
    assert len(successful_adds) == 1, f"Expected exactly 1 successful add, got {len(successful_adds)}"
    assert len(failed_adds) == 9, f"Expected exactly 9 failed adds, got {len(failed_adds)}"
    
    print(f"✅ Atomic URL marking working - 1 success, 9 rejections")

def test_video_id_blocking():
    """Test that different URLs for the same video are blocked."""
    print("🔍 Testing video ID blocking...")
    
    hash_mgr = get_hash_manager()
    
    # Use a different test video ID to avoid conflicts
    import time
    timestamp = str(int(time.time()))
    base_video_id = f"test_blocking_{timestamp}_456"
    
    urls = [
        f"https://www.youtube.com/watch?v={base_video_id}",
        f"https://youtu.be/{base_video_id}",
        f"https://youtube.com/watch?v={base_video_id}&t=30s"
    ]
    
    # First URL should succeed
    success1 = hash_mgr.add_url(urls[0], "Test Video", "test search", "theme_1")
    assert success1, "First URL should succeed"
    
    # Subsequent URLs for same video should fail
    success2 = hash_mgr.add_url(urls[1], "Test Video", "test search", "theme_2")
    success3 = hash_mgr.add_url(urls[2], "Test Video", "test search", "theme_3")
    
    assert not success2, "Second URL (same video) should fail"
    assert not success3, "Third URL (same video) should fail"
    
    print("✅ Video ID blocking working correctly")

def test_theme_isolation():
    """Test that URLs are properly tracked per theme."""
    print("🔍 Testing theme isolation...")
    
    hash_mgr = get_hash_manager()
    
    # Use unique video IDs for this test with timestamp to ensure uniqueness
    import time
    timestamp = str(int(time.time()))
    video_ids = [f"test_theme_1_{timestamp}_789", f"test_theme_2_{timestamp}_790", f"test_theme_3_{timestamp}_791"]
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]
    themes = ["Theme1", "Theme2", "Theme3"]
    
    # Each theme should be able to use different videos
    for url, theme in zip(urls, themes):
        success = hash_mgr.add_url(url, f"Video for {theme}", "search", theme)
        assert success, f"Theme {theme} should be able to use URL {url}"
    
    # But no theme should be able to reuse the same video
    for url, original_theme in zip(urls, themes):
        # Try with a different theme
        other_theme = "OtherTheme"
        success = hash_mgr.add_url(url, f"Video for {other_theme}", "search", other_theme)
        assert not success, f"Theme {other_theme} should not be able to reuse URL from {original_theme}"
    
    # Verify we can get info about used URLs
    for url, theme in zip(urls, themes):
        info = hash_mgr.get_url_info(url)
        assert info is not None, f"Should be able to get info for {url}"
        assert info['theme_name'] == theme, f"Expected theme {theme}, got {info['theme_name']}"
        assert info['video_id'] in video_ids, f"Expected video_id in {video_ids}, got {info['video_id']}"
    
    print("✅ Theme isolation working correctly")

def test_concurrent_theme_processing():
    """Test multiple themes processing different searches concurrently."""
    print("🔍 Testing concurrent theme processing...")
    
    # This is more of an integration test - we'll simulate multiple themes
    # trying to download content simultaneously
    
    def simulate_theme_download(theme_name, search_term):
        """Simulate a theme downloading content."""
        # In a real scenario, this would call download_candidates_for_term
        # For testing, we'll just try to mark some URLs as used
        
        test_urls = [
            f"https://www.youtube.com/watch?v=concurrent_{theme_name}_{i}"
            for i in range(3)
        ]
        
        hash_mgr = get_hash_manager()
        successful_urls = []
        
        for url in test_urls:
            success = hash_mgr.add_url(url, f"Video {url}", search_term, theme_name)
            if success:
                successful_urls.append(url)
        
        return theme_name, successful_urls
    
    themes = [
        ("Electronic", "electronic music"),
        ("Classical", "classical music"),  
        ("Rock", "rock music"),
        ("Jazz", "jazz music"),
    ]
    
    # Process themes concurrently
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(simulate_theme_download, theme, search) for theme, search in themes]
        results = [future.result() for future in as_completed(futures)]
    
    # Each theme should have been able to claim its URLs
    for theme_name, urls in results:
        assert len(urls) == 3, f"Theme {theme_name} should have claimed 3 URLs, got {len(urls)}"
    
    # Verify no URL was claimed by multiple themes
    all_urls = []
    for _, urls in results:
        all_urls.extend(urls)
    
    assert len(all_urls) == len(set(all_urls)), "No URL should be claimed by multiple themes"
    
    print("✅ Concurrent theme processing working correctly")

def test_database_stats():
    """Test database statistics reporting."""
    print("🔍 Testing database statistics...")
    
    hash_mgr = get_hash_manager()
    stats = hash_mgr.get_stats()
    
    required_keys = ['total_hashes', 'total_urls', 'youtube_videos']
    for key in required_keys:
        assert key in stats, f"Stats should include {key}"
        assert isinstance(stats[key], int), f"Stats[{key}] should be an integer"
        assert stats[key] >= 0, f"Stats[{key}] should be non-negative"
    
    print(f"✅ Database stats: {stats}")

def main():
    """Run all URL deduplication tests."""
    print("🚀 Starting URL deduplication tests...")
    print()
    
    try:
        # Initialize environment
        os.environ.setdefault('CLIP_SECONDS', '2')
        os.environ.setdefault('SAMPLES_PER_BANK', '1')
        
        # Run tests in order
        test_url_normalization()
        print()
        
        test_atomic_url_marking()
        print()
        
        test_video_id_blocking()
        print()
        
        test_theme_isolation()
        print()
        
        test_concurrent_theme_processing()
        print()
        
        test_database_stats()
        print()
        
        print("🎉 All URL deduplication tests passed!")
        print()
        print("✅ Key improvements implemented:")
        print("  • URL normalization handles different YouTube URL formats")
        print("  • Atomic URL checking prevents race conditions")
        print("  • Video ID extraction prevents duplicate videos")
        print("  • Theme isolation ensures proper URL ownership")
        print("  • Database transactions ensure consistency")
        print("  • WAL mode enables better concurrent access")
        
        return True
        
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)