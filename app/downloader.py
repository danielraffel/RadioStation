"""Download and process audio clips from YouTube using yt-dlp and pydub.

Main function:
- download_candidates_for_term(): Downloads videos, extracts center sections,
  processes into candidate clips, and runs CLAP scoring.
"""

from pathlib import Path
import glob
import os
import hashlib
import json
import datetime
import shutil
import threading
from typing import List, Tuple, Set, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from yt_dlp import YoutubeDL
from pydub import AudioSegment, effects
from .hash_manager import get_hash_manager, calculate_file_hash
from . import scoring

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "wavs" / "raw"
PROCESSED_DIR = BASE_DIR / "wavs" / "processed" / "candidates"

# Centralized data directory for tracking files
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Hash and URL tracking files in data directory
HASHES_FILE = DATA_DIR / "audio_hashes.json"
USED_URLS_FILE = DATA_DIR / "used_urls.json"

# Session-wide URL tracking for additional protection against race conditions
# This provides an extra layer of protection during active pipeline runs
_session_used_urls: Set[str] = set()
_session_used_video_ids: Set[str] = set()
_session_lock = threading.Lock()

# Session-wide URL tracking functions
def clear_session_urls():
    """Clear session-wide URL tracking. Call at start of new pipeline runs."""
    global _session_used_urls, _session_used_video_ids
    with _session_lock:
        _session_used_urls.clear()
        _session_used_video_ids.clear()

def is_url_used_in_session(url: str) -> bool:
    """Check if URL is already used in current session (fast in-memory check)."""
    hash_manager = get_hash_manager()
    normalized_url, video_id = hash_manager.normalize_url(url)
    
    with _session_lock:
        # Check session tracking first (fastest)
        if url in _session_used_urls or normalized_url in _session_used_urls:
            return True
        if video_id and video_id in _session_used_video_ids:
            return True
    return False

def mark_url_used_in_session(url: str):
    """Mark URL as used in current session (for fast session-wide deduplication)."""
    hash_manager = get_hash_manager()
    normalized_url, video_id = hash_manager.normalize_url(url)
    
    with _session_lock:
        _session_used_urls.add(url)
        _session_used_urls.add(normalized_url)
        if video_id:
            _session_used_video_ids.add(video_id)

# Legacy JSON tracking (kept for backward compatibility)
def _init_tracking():
    """Initialize tracking using the new hash manager."""
    # Now handled by HashManager initialization
    pass

def _save_hash(audio_hash: str) -> bool:
    """Save a new audio hash using the hash manager.
    
    Returns:
        True if hash was successfully saved (wasn't duplicate)
        False if hash was already present (duplicate)
    """
    hash_manager = get_hash_manager()
    success = hash_manager.add_hash(audio_hash)
    
    if success:
        # Also save to legacy JSON for backward compatibility
        data = []
        if HASHES_FILE.exists():
            try:
                with open(HASHES_FILE, 'r') as f:
                    data = json.load(f)
            except:
                data = []
        
        data.append({
            'hash': audio_hash,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
        # Keep last 5000 entries for better deduplication
        data = data[-5000:]
        
        try:
            with open(HASHES_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass
    
    return success

def _save_used_url(url: str, title: str = None, search_term: str = None, theme_name: str = None) -> bool:
    """Save a URL that has been used atomically.
    
    Returns:
        True if URL was successfully marked as used (wasn't already used)
        False if URL was already used by another process/theme
    """
    hash_manager = get_hash_manager()
    success = hash_manager.add_url(url, title, search_term, theme_name)
    
    if success:
        # Also save to legacy JSON for backward compatibility
        try:
            urls = []
            if USED_URLS_FILE.exists():
                with open(USED_URLS_FILE, 'r') as f:
                    urls = json.load(f)
            if url not in urls:
                urls.append(url)
            with open(USED_URLS_FILE, 'w') as f:
                json.dump(urls, f, indent=2)
        except:
            pass
    
    return success

def _is_duplicate(file_path: Path) -> bool:
    """Check if file is duplicate based on hash."""
    file_hash = calculate_file_hash(file_path)
    if file_hash:
        hash_manager = get_hash_manager()
        return hash_manager.has_hash(file_hash)
    return False


def _ydl_opts(term: str, max_results: int = 1, clip_ms: int | None = None, logger=None) -> dict:
    # Check for aria2c availability
    import shutil
    has_aria2c = shutil.which('aria2c') is not None

    # Get download method configuration
    download_method = os.environ.get("DOWNLOAD_METHOD", "smart")
    audio_quality = os.environ.get("AUDIO_QUALITY", "best")

    # Determine if we should use aria2c
    use_aria = False
    if download_method == "aria2c":
        use_aria = has_aria2c
        if not has_aria2c and logger:
            logger.warning("aria2c requested but not available, falling back to native downloader")
    elif download_method == "smart":
        # Smart mode: use aria2c only when not doing segment downloads
        use_aria = has_aria2c and os.environ.get("ARIA2C_ENABLED", "1") not in ("0", "false", "False")
    
    if use_aria:
        # Use aria2c settings from environment/config
        conn_per_server = os.environ.get('ARIA2C_CONN_PER_SERVER', '4')
        split = os.environ.get('ARIA2C_SPLIT', '4')
        chunk_size = os.environ.get('ARIA2C_CHUNK_SIZE', '10M')
        
        aria_args = [
            f'--min-split-size={chunk_size}',  # Chunk size from config
            f'--max-connection-per-server={conn_per_server}',  # From config (default 4)
            '--max-concurrent-downloads=4',  # Process fewer files at once
            f'--split={split}',  # From config (default 4)
            '--max-tries=3',  # Retry failed chunks
            '--retry-wait=5',  # Wait between retries
            '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',  # Browser UA
            '--file-allocation=none',  # Faster for streaming downloads
            '--allow-overwrite=true',  # Allow retrying failed downloads
            '--auto-file-renaming=false'  # Keep exact filenames
        ]

    # Determine audio format based on quality setting
    audio_quality = os.environ.get("AUDIO_QUALITY", "best")
    if audio_quality == "worst":
        ytdlp_format = "worstaudio/worst"
    else:
        # Default to best quality with filesize limit
        ytdlp_format = os.environ.get("YTDLP_FORMAT", "bestaudio[filesize<10M]/bestaudio/best")

    opts = {
        "format": ytdlp_format,
        "noplaylist": True,
        "quiet": True,
        "paths": {"home": str(RAW_DIR)},
        "outtmpl": {"default": f"{term}_%(id)s.%(ext)s"},
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
    }
    
    # Only add WAV conversion for non-sectioned downloads
    # For sectioned downloads, we'll convert after downloading the section
    if clip_ms is not None:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]

    if use_aria:
        # Use aria2c for all protocols to ensure sections work
        opts["external_downloader"] = {
            "default": "aria2c",
            "dash": "aria2c",
            "m3u8": "aria2c",
            "http": "aria2c",
            "https": "aria2c"
        }
        opts["external_downloader_args"] = {"aria2c": aria_args}
        if logger:
            logger.info("Downloader: aria2c (acceleration enabled)")

    # Limit downloads to just the first clip duration when supported
    # Note: This is only for beginning-of-video downloads
    # Center downloads are handled separately in _download_one
    use_sections = os.environ.get("YTDLP_USE_SECTIONS", "1") not in ("0","false","False")
    if use_sections and clip_ms is not None and clip_ms > 0:
        sec = max(1, int(round(clip_ms/1000)))
        # Format as *0-SEC for yt-dlp --download-sections (from start)
        opts["download_sections"] = [f"*0-{sec}"]
        # Also speed up fragmented downloads
        try:
            opts["concurrent_fragment_downloads"] = int(os.environ.get("CONCURRENT_FRAGMENT_DOWNLOADS", "4"))
        except Exception:
            pass
    if logger is not None:
        opts["logger"] = logger

    # Use ytsearchN to fetch multiple results when requested
    opts["_search_count"] = int(max_results)
    return opts


def _process_to_candidate(path: Path, clip_ms: int) -> Path | None:
    sound = AudioSegment.from_file(path, "wav")
    if len(sound) < clip_ms:
        path.unlink(missing_ok=True)
        return None
    clip = sound[:clip_ms]
    fade = clip_ms // 4
    clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / path.name
    clip.export(out_path, format="wav")
    path.unlink(missing_ok=True)
    return out_path


def _process_to_candidate_slices(path: Path, clip_ms: int, slices_per_video: int, slice_stride_ms: int, metadata: Dict[str, Any] = None, log_cb=None) -> List[Tuple[Path, Dict[str, Any]]]:
    """Produce up to N slices per video with metadata, sequentially with given stride.
    
    Runs CLAP scoring immediately if enabled and theme information is available.
    """
    if log_cb:
        log_cb(f"Processing {path.name} to candidate slices...")
    
    sound = AudioSegment.from_file(path, "wav")
    out: List[Tuple[Path, Dict[str, Any]]] = []
    if len(sound) < clip_ms:
        if log_cb:
            log_cb(f"Audio too short ({len(sound)}ms < {clip_ms}ms), skipping")
        path.unlink(missing_ok=True)
        return out
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    taken = 0
    start = 0
    
    # Check if we should run CLAP scoring
    run_clap = scoring.is_enabled() and metadata and 'theme_prompt' in metadata
    if log_cb:
        log_cb(f"CLAP scoring enabled: {scoring.is_enabled()}, Has theme_prompt: {'theme_prompt' in (metadata or {})}, Will run CLAP: {run_clap}")
    
    while taken < slices_per_video and start + clip_ms <= len(sound):
        clip = sound[start:start+clip_ms]
        fade = clip_ms // 4
        clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
        suffix = f"_s{taken+1}"
        out_path = PROCESSED_DIR / f"{path.stem}{suffix}{path.suffix}"
        clip.export(out_path, format="wav")
        
        # Calculate unique hash for this slice
        slice_hash = calculate_file_hash(out_path)
        hash_manager = get_hash_manager()
        
        # Check and register slice hash atomically
        if not hash_manager.add_hash(slice_hash, str(out_path)):
            if log_cb:
                log_cb(f"Duplicate detected: {out_path.name} (skipping to next slice position)")
            try:
                out_path.unlink()
                # Move to next slice position after removing duplicate
                start += stride_ms
                continue
            except Exception as e:
                if log_cb:
                    log_cb(f"Failed to remove duplicate {out_path.name}: {e}")
                # IMPORTANT: Break the loop to prevent infinite retries on same file
                # The hash is already in the database, so this file is a duplicate
                break
        
        # Create slice metadata
        slice_metadata = (metadata or {}).copy()
        slice_metadata['slice_index'] = taken + 1
        slice_metadata['slice_start_ms'] = start
        slice_metadata['slice_duration_ms'] = clip_ms
        slice_metadata['audio_hash'] = slice_hash  # Use slice-specific hash
        slice_metadata['processed_timestamp'] = datetime.datetime.now().isoformat()
        
        # Run CLAP scoring immediately if enabled
        if run_clap:
            try:
                theme_prompt = metadata['theme_prompt']
                theme_name = metadata.get('theme_name', 'Unknown')
                if log_cb:
                    log_cb(f"Running CLAP scoring for {out_path.name}...")
                
                # Format prompts as expected by scoring module
                prompts = [{'name': theme_name, 'prompt': theme_prompt}]
                result = scoring.best_theme_for_wav(out_path, prompts, [theme_name])
                if result:
                    _, score = result
                    if score is not None:
                        slice_metadata['clap_score'] = float(score)
                        slice_metadata['clap_theme'] = theme_name
                        if log_cb:
                            log_cb(f"CLAP scored {out_path.name}: {theme_name} (score: {score:.3f})")
                    else:
                        if log_cb:
                            log_cb(f"CLAP scoring returned None for {out_path.name}")
                else:
                    if log_cb:
                        log_cb(f"CLAP scoring failed for {out_path.name}")
            except Exception as e:
                if log_cb:
                    log_cb(f"CLAP scoring error for {out_path.name}: {e}")
        
        out.append((out_path, slice_metadata))
        taken += 1
        start += max(slice_stride_ms, 1)
    path.unlink(missing_ok=True)
    return out


def _process_to_best_candidate_slices(path: Path, clip_ms: int, slices_per_video: int, slice_stride_ms: int, metadata: Dict[str, Any] = None, log_cb=None) -> List[Tuple[Path, Dict[str, Any]]]:
    """Process larger audio chunk to find the best scoring segments.
    
    Downloads larger chunks (e.g., 10 seconds) and tests multiple 2-second segments
    to find the ones with highest CLAP scores for the target theme.
    """
    if log_cb:
        log_cb(f"Processing {path.name} to find best candidate segments...")
    
    sound = AudioSegment.from_file(path, "wav")
    out: List[Tuple[Path, Dict[str, Any]]] = []
    
    # Need at least clip_ms duration
    if len(sound) < clip_ms:
        if log_cb:
            log_cb(f"Audio too short ({len(sound)}ms < {clip_ms}ms), skipping")
        path.unlink(missing_ok=True)
        return out
    
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if we should run CLAP scoring for optimization
    run_clap = scoring.is_enabled() and metadata and 'theme_prompt' in metadata
    if not run_clap:
        # Fall back to regular processing if CLAP not available
        return _process_to_candidate_slices(path, clip_ms, slices_per_video, slice_stride_ms, metadata, log_cb)
    
    theme_prompt = metadata['theme_prompt']
    theme_name = metadata.get('theme_name', 'Unknown')
    prompts = [{'name': theme_name, 'prompt': theme_prompt}]
    
    if log_cb:
        log_cb(f"Testing multiple segments from {len(sound)}ms audio for best CLAP score...")
    
    # Generate all possible segments with small stride
    test_stride_ms = max(200, slice_stride_ms // 4)  # Test every 200ms or smaller stride
    candidate_segments = []
    
    start = 0
    segment_idx = 0
    while start + clip_ms <= len(sound) and segment_idx < 20:  # Limit to 20 tests max
        clip = sound[start:start+clip_ms]
        fade = clip_ms // 4
        clip = effects.normalize(clip.fade_in(fade).fade_out(fade))
        
        # Create temporary file for CLAP testing
        temp_path = PROCESSED_DIR / f"temp_{path.stem}_{segment_idx}.wav"
        clip.export(temp_path, format="wav")
        
        # Test CLAP score
        try:
            result = scoring.best_theme_for_wav(temp_path, prompts, [theme_name])
            if result:
                _, score = result
                if score is not None:
                    candidate_segments.append({
                        'start_ms': start,
                        'score': float(score),
                        'temp_path': temp_path,
                        'segment_idx': segment_idx
                    })
                    if log_cb and segment_idx % 5 == 0:  # Log every 5th test
                        log_cb(f"Tested segment {segment_idx}: start={start}ms, score={score:.3f}")
                else:
                    temp_path.unlink(missing_ok=True)
            else:
                temp_path.unlink(missing_ok=True)
        except Exception as e:
            if log_cb:
                log_cb(f"CLAP scoring error for segment {segment_idx}: {e}")
            temp_path.unlink(missing_ok=True)
        
        start += test_stride_ms
        segment_idx += 1
    
    # Sort by score (highest first) and take the best segments
    if candidate_segments:
        candidate_segments.sort(key=lambda x: x['score'], reverse=True)
        best_segments = candidate_segments[:slices_per_video]
        
        if log_cb:
            best_score = best_segments[0]['score']
            worst_score = best_segments[-1]['score'] if len(best_segments) > 1 else best_score
            log_cb(f"Selected {len(best_segments)} best segments: scores {best_score:.3f} to {worst_score:.3f}")
        
        # Create final files from best segments
        for i, segment_info in enumerate(best_segments):
            suffix = f"_s{i+1}"
            final_path = PROCESSED_DIR / f"{path.stem}{suffix}{path.suffix}"
            
            # Move temp file to final location
            segment_info['temp_path'].replace(final_path)
            
            # Calculate unique hash for this slice
            slice_hash = calculate_file_hash(final_path)
            hash_manager = get_hash_manager()
            
            # Check and register slice hash atomically
            if not hash_manager.add_hash(slice_hash, str(final_path)):
                if log_cb:
                    log_cb(f"Duplicate detected: {final_path.name} (skipping this segment)")
                try:
                    final_path.unlink()
                except Exception as e:
                    if log_cb:
                        log_cb(f"Failed to remove duplicate {final_path.name}: {e}")
                    # Skip this duplicate but continue with other segments
                continue
            
            # Create metadata
            slice_metadata = (metadata or {}).copy()
            slice_metadata['slice_index'] = i + 1
            slice_metadata['slice_start_ms'] = segment_info['start_ms']
            slice_metadata['slice_duration_ms'] = clip_ms
            slice_metadata['audio_hash'] = slice_hash  # Use slice-specific hash
            slice_metadata['clap_score'] = segment_info['score']
            slice_metadata['clap_theme'] = theme_name
            slice_metadata['processed_timestamp'] = datetime.datetime.now().isoformat()
            slice_metadata['selection_method'] = 'best_clap_score'
            slice_metadata['tested_segments'] = len(candidate_segments)
            
            out.append((final_path, slice_metadata))
        
        # Clean up remaining temp files
        for segment_info in candidate_segments:
            if segment_info['temp_path'].exists():
                segment_info['temp_path'].unlink(missing_ok=True)
    else:
        if log_cb:
            log_cb("No valid segments found, falling back to regular processing")
        # Fall back to regular processing
        return _process_to_candidate_slices(path, clip_ms, slices_per_video, slice_stride_ms, metadata, log_cb)
    
    path.unlink(missing_ok=True)
    return out


def _extract_search(term: str, max_results: int, logger=None, theme_name: str = None) -> List[Tuple[str, str]]:
    """Return list of (video_id, url) for search results, filtered to exclude already-used URLs.
    
    This is the critical function that ensures no duplicate URLs are returned across themes.
    URLs are filtered out at search extraction time, not just download time.
    """
    # For search extraction, we need minimal options - no downloading!
    opts = {
        "quiet": True,
        "extract_flat": True,  # CRITICAL: Only get basic info, don't download
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if logger is not None:
        opts["logger"] = logger
    
    # Get hash manager for URL checking
    hash_manager = get_hash_manager()
    ydl = YoutubeDL(opts)
    info = ydl.extract_info(f"ytsearch{int(max_results)}:{term}", download=False)
    entries = info.get("entries") or []
    
    all_results: List[Tuple[str, str]] = []
    filtered_results: List[Tuple[str, str]] = []
    
    for e in entries:
        vid = e.get("id")
        url = e.get("webpage_url") or e.get("url")
        if vid and url:
            all_results.append((vid, url))
            
            # CRITICAL: Multi-layered URL filtering at extraction time
            # Layer 1: Check persistent database (all previous sessions)
            if hash_manager.has_url(url):
                if logger:
                    existing_info = hash_manager.get_url_info(url)
                    existing_theme = existing_info.get('theme_name') if existing_info else 'Unknown'
                    logger.info(f"Filtering out database-used URL from search '{term}': {url} (used by theme '{existing_theme}')")
                continue
            
            # Layer 2: Check session-wide tracking (current session across themes)
            if is_url_used_in_session(url):
                if logger:
                    logger.info(f"Filtering out session-used URL from search '{term}': {url} (used earlier in this session)")
                continue
            
            # Layer 3: Also check by video ID to catch different URL formats of same video
            if hash_manager.has_video_id(vid):
                if logger:
                    logger.info(f"Filtering out already-used video ID from search '{term}': {vid} (different URL format)")
                continue
                
            filtered_results.append((vid, url))
    
    if logger:
        theme_info = f" for theme '{theme_name}'" if theme_name else ""
        logger.info(f"Search '{term}'{theme_info}: Found {len(all_results)} total results, {len(filtered_results)} after filtering used URLs")
        if len(all_results) > len(filtered_results):
            filtered_count = len(all_results) - len(filtered_results)
            logger.info(f"Filtered out {filtered_count} duplicate URLs at search extraction time")
    
    return filtered_results


def _download_one(url: str, term: str, vid: str, clip_ms: int, logger=None, extra_metadata: Dict[str, Any] = None) -> Tuple[Path | None, Dict[str, Any]]:
    """Download a single url and return expected wav path and metadata if present."""
    hash_manager = get_hash_manager()
    theme_name = extra_metadata.get('theme_name') if extra_metadata else None
    
    # CRITICAL: Immediate session-wide URL marking to prevent race conditions
    # Mark URL as used in session BEFORE any checks to block other threads immediately
    mark_url_used_in_session(url)
    
    # Double-check if URL was already used in database (should have been filtered by _extract_search)
    if hash_manager.has_url(url):
        if logger:
            existing_info = hash_manager.get_url_info(url)
            if existing_info and existing_info.get('theme_name'):
                logger.info(f"Skipping duplicate URL: {url} (already used by theme '{existing_info['theme_name']}')")  
            else:
                logger.info(f"Skipping duplicate URL: {url}")
        return None, {}
    
    # Atomically mark URL as used in persistent database - this prevents race conditions
    # If another thread/process already marked it, we skip
    if not _save_used_url(url, None, term, theme_name):
        if logger:
            logger.info(f"URL was marked as used by another process: {url}")
        return None, {}
    
    # First, extract metadata without downloading to check duration
    ydl_info = YoutubeDL(_ydl_opts(term, max_results=1, clip_ms=None, logger=logger))
    
    try:
        info = ydl_info.extract_info(url, download=False)

        # Check if this is a live stream and skip it
        is_live = info.get('is_live', False)
        if is_live:
            if logger:
                logger.warning(f"Skipping live stream: {info.get('title', 'Unknown')} - {url}")
            return None, {'error': 'live_stream', 'url': url, 'title': info.get('title', 'Unknown')}

        video_duration = info.get('duration', 0)
        metadata = {
            'url': url,
            'title': info.get('title', 'Unknown'),
            'duration': video_duration,
            'uploader': info.get('uploader', ''),
            'description': info.get('description', ''),
            'tags': info.get('tags', []),  # Extract YouTube tags (empty list if none)
            'categories': info.get('categories', []),  # Extract video categories (empty list if none)
            'upload_date': info.get('upload_date', ''),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0),
            'download_timestamp': datetime.datetime.now().isoformat(),
            'search_term': term
        }
        # Add extra metadata if provided
        if extra_metadata:
            metadata.update(extra_metadata)
            
        # Check if video is long enough for our clip
        clip_seconds = clip_ms / 1000.0
        if video_duration and video_duration < clip_seconds:
            if logger:
                logger.warning(f"Video too short ({video_duration}s < {clip_seconds}s), skipping: {metadata.get('title')}")
            # URL is already marked as used, which is correct for short videos
            return None, metadata
            
        # Calculate center section for download - use larger chunk for better selection
        download_chunk_seconds = int(os.environ.get('DOWNLOAD_CHUNK_SECONDS', '10'))
        effective_download_seconds = max(download_chunk_seconds, clip_seconds)

        # Check download method configuration
        download_method = os.environ.get("DOWNLOAD_METHOD", "smart")

        # Determine if we should use segment downloading
        use_segments = False
        if download_method == "segment":
            use_segments = True
            if logger:
                logger.info("Download method: segment (forced)")
        elif download_method == "aria2c":
            use_segments = False
            if logger:
                logger.info("Download method: aria2c (full download forced)")
        else:  # smart mode
            # Use segments if video is longer than the segment size we want to download
            use_segments = video_duration and video_duration > effective_download_seconds
            if logger:
                if use_segments:
                    logger.info(f"Download method: smart (using segments - video {video_duration}s > segment size {effective_download_seconds}s)")
                else:
                    logger.info(f"Download method: smart (full download - video {video_duration}s <= segment size {effective_download_seconds}s)")

        if use_segments:
            # Download from center of video
            center_time = int(video_duration / 2)
            # Calculate start time ensuring we get the full chunk centered
            start_time = max(0, center_time - int(effective_download_seconds / 2))
            # End time is start + download duration (plus small buffer)
            end_time = min(video_duration, start_time + effective_download_seconds + 2)
            
            if logger:
                logger.info(f"Video duration: {video_duration}s. Downloading CENTER section: {start_time}-{end_time}s (chunk: {effective_download_seconds}s for {clip_seconds}s clips)")
            
            # Update options to download specific section
            # yt-dlp format: "*START-END" where START/END can be seconds or MM:SS format
            # Using seconds format for precision
            # IMPORTANT: When using download_sections, don't use aria2c as it downloads full file first
            opts = _ydl_opts(term, max_results=1, clip_ms=None, logger=logger)
            
            # Use download_sections with force_keyframes_at_cuts
            # This is the most reliable method for segment downloading
            download_range = f"*{start_time}-{end_time}"
            opts["download_sections"] = [download_range]

            # Force keyframes at cuts for precise trimming
            # This ensures yt-dlp/ffmpeg only downloads the needed segment
            opts['force_keyframes_at_cuts'] = True

            # Remove postprocessors - we'll convert manually after download
            # Having postprocessors can cause full file downloads
            if 'postprocessors' in opts:
                del opts['postprocessors']

            # Remove aria2c if it was set
            if 'external_downloader' in opts and isinstance(opts['external_downloader'], dict):
                if logger:
                    logger.info("Disabling aria2c for segment download")
                del opts['external_downloader']

            # Try ffmpeg external downloader with proper args
            opts['external_downloader'] = 'ffmpeg'
            opts['external_downloader_args'] = {
                'ffmpeg_i': ['-ss', str(start_time), '-to', str(end_time)]
            }

            if logger:
                logger.info("Downloader: ffmpeg (segment mode)")

            # Additional options
            opts['noplaylist'] = True

            # Use configured audio quality
            audio_quality = os.environ.get("AUDIO_QUALITY", "best")
            if audio_quality == "worst":
                opts['format'] = 'worstaudio/worst'
                if logger:
                    logger.info(f"Audio format: worstaudio/worst (minimal size)")
            else:
                opts['format'] = 'bestaudio/best'
                if logger:
                    logger.info(f"Audio format: bestaudio/best (higher quality)")

            if logger:
                logger.info(f"Using download_sections with force_keyframes_at_cuts: {download_range}")
            
            # Store section info in metadata
            metadata['download_section_start'] = start_time
            metadata['download_section_end'] = end_time
            metadata['download_section'] = 'center'
            
            ydl = YoutubeDL(opts)
        else:
            # Video is short, use original approach with beginning section
            if logger:
                logger.info(f"Downloading beginning section (video duration: {video_duration}s)")
            ydl = YoutubeDL(_ydl_opts(term, max_results=1, clip_ms=clip_ms, logger=logger))
            metadata['download_section'] = 'beginning'
            
        # Update the URL entry with title now that we have it
        # Since we already marked it as used atomically, this should always succeed  
        _save_used_url(url, metadata.get('title'), term, theme_name)
            
    except Exception as e:
        if logger:
            logger.error(f"Failed to extract metadata: {e}")
        metadata = {'url': url, 'search_term': term}
        # Update URL with what info we have
        _save_used_url(url, None, term, theme_name)
        # Fallback to original download method
        ydl = YoutubeDL(_ydl_opts(term, max_results=1, clip_ms=clip_ms, logger=logger))
    
    try:
        if logger:
            logger.info(f"Starting download of {metadata.get('title', url)}")
        ydl.download([url])
        if logger:
            logger.info(f"Download completed for {vid}")
    except Exception as e:
        if logger:
            logger.error(f"Download failed: {e}")
        # For failed downloads, we keep the URL marked as used to avoid
        # repeatedly trying broken URLs. This prevents wasting time on
        # videos that consistently fail to download.
        return None, metadata
    
    # For sectioned downloads, file might be webm/m4a/mp4, need to convert to WAV
    expected_wav = RAW_DIR / f"{term}_{vid}.wav"
    webm_file = RAW_DIR / f"{term}_{vid}.webm"
    m4a_file = RAW_DIR / f"{term}_{vid}.m4a"
    mp4_file = RAW_DIR / f"{term}_{vid}.mp4"

    # Find the downloaded file (could be .wav, .webm, .m4a, or .mp4)
    p = None
    if expected_wav.exists():
        p = expected_wav
    elif webm_file.exists():
        # Convert webm to wav using pydub
        if logger:
            logger.info(f"Converting {webm_file} to WAV")
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(webm_file)
            audio.export(expected_wav, format="wav")
            webm_file.unlink()  # Remove original
            p = expected_wav
        except Exception as e:
            if logger:
                logger.error(f"Failed to convert webm to wav: {e}")
    elif m4a_file.exists():
        # Convert m4a to wav
        if logger:
            logger.info(f"Converting {m4a_file} to WAV")
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(m4a_file)
            audio.export(expected_wav, format="wav")
            m4a_file.unlink()  # Remove original
            p = expected_wav
        except Exception as e:
            if logger:
                logger.error(f"Failed to convert m4a to wav: {e}")
    elif mp4_file.exists():
        # Convert mp4 to wav
        if logger:
            logger.info(f"Converting {mp4_file} to WAV")
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(mp4_file)
            audio.export(expected_wav, format="wav")
            mp4_file.unlink()  # Remove original
            p = expected_wav
        except Exception as e:
            if logger:
                logger.error(f"Failed to convert mp4 to wav: {e}")

    if logger:
        logger.info(f"Looking for downloaded file: {p}")
        if p and p.exists():
            file_size_mb = p.stat().st_size / (1024 * 1024)
            logger.info(f"Downloaded file size: {file_size_mb:.2f} MB")
            # Warn if segment is suspiciously large (>50MB for a 10-second clip is unusual)
            if file_size_mb > 50 and metadata.get('download_section') == 'center':
                logger.warning(f"Segment download may have failed - file is {file_size_mb:.2f} MB for a {effective_download_seconds}s segment")

    # Check if file exists and handle duplicates atomically
    if p and p.exists():
        file_hash = calculate_file_hash(p)
        if not hash_manager.add_hash(file_hash, str(p), url, metadata):
            if logger:
                logger.info(f"Removing duplicate file: {p.name}")
            p.unlink()
            return None, metadata
        else:
            _save_hash(file_hash)  # Also save to legacy format
            metadata['audio_hash'] = file_hash
    
    return (p if p.exists() else None), metadata


def download_candidates_for_term(
    term: str,
    clip_ms: int = 2000,
    max_results: int = 1,
    download_workers: int = 1,
    slices_per_video: int = 1,
    slice_stride_ms: int = None,
    log_cb=None,
    theme_name: str = None,
    theme_prompt: str = None,
    original_search: str = None,
    expanded_search: List[str] = None,
    search_index: int = None,
    total_search_terms: int = None,
) -> List[Path]:
    """Download up to max_results items in parallel and return candidate slice paths."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if slice_stride_ms is None:
        slice_stride_ms = clip_ms
    # optional yt-dlp logger that forwards to pipeline logs
    logger = None
    if log_cb is not None:
        class YDLLogger:
            def debug(self, msg):
                try:
                    txt = str(msg)
                except Exception:
                    txt = "(debug msg)"
                if not txt.startswith('[debug] '):
                    log_cb(txt)
            def info(self, msg):
                log_cb(str(msg))
            def warning(self, msg):
                log_cb("WARN: " + str(msg))
            def error(self, msg):
                log_cb("ERROR: " + str(msg))
        logger = YDLLogger()
    
    # Get extra search results to account for filtering, but not too many to waste API calls
    search_multiplier = 2  # Get 2x results to account for filtering and short videos
    items = _extract_search(term, min(96, max_results * search_multiplier), logger=logger, theme_name=theme_name)  # Cap at 96 to avoid excessive API calls
    candidates: List[Path] = []
    if not items:
        return candidates
    # Prepare extra metadata to pass to downloads
    extra_metadata = {}
    if theme_name:
        extra_metadata['theme_name'] = theme_name
    if theme_prompt:
        extra_metadata['theme_prompt'] = theme_prompt
    if original_search:
        extra_metadata['search_term'] = original_search  # The actual term being searched
    if expanded_search:
        # Only include if this was actually AI-expanded
        extra_metadata['expanded_search'] = expanded_search
        extra_metadata['is_ai_expanded'] = True
    else:
        extra_metadata['is_ai_expanded'] = False
    if search_index is not None:
        extra_metadata['search_index'] = search_index
    if total_search_terms is not None:
        extra_metadata['total_search_terms'] = total_search_terms
    
    workers = max(1, int(download_workers))
    successful_downloads = 0
    item_index = 0
    
    # Process in batches until we get enough successful downloads
    while successful_downloads < max_results and item_index < len(items):
        # Determine batch size for this iteration
        batch_size = min(workers, max_results - successful_downloads, len(items) - item_index)
        batch_items = items[item_index:item_index + batch_size]
        item_index += batch_size
        
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_download_one, url, term, vid, clip_ms, logger=logger, extra_metadata=extra_metadata) 
                   for (vid, url) in batch_items]
            for fut in as_completed(futs):
                wav_path, metadata = fut.result()
                if wav_path and wav_path.exists():
                    # Use smart processing if we downloaded larger chunks
                    download_chunk_ms = int(os.environ.get('DOWNLOAD_CHUNK_SECONDS', '10')) * 1000
                    if download_chunk_ms > clip_ms and scoring.is_enabled() and metadata and 'theme_prompt' in metadata:
                        slice_results = _process_to_best_candidate_slices(wav_path, clip_ms, int(slices_per_video), int(slice_stride_ms), metadata, log_cb)
                    else:
                        slice_results = _process_to_candidate_slices(wav_path, clip_ms, int(slices_per_video), int(slice_stride_ms), metadata, log_cb)
                    if slice_results:
                        successful_downloads += 1
                        for slice_path, slice_metadata in slice_results:
                            candidates.append(slice_path)
                            # Save metadata file for each slice
                            metadata_path = slice_path.with_suffix('.json')
                            try:
                                with open(metadata_path, 'w') as f:
                                    json.dump(slice_metadata, f, indent=2)
                                if log_cb:
                                    log_cb(f"Created metadata file: {metadata_path.name}")
                            except Exception as e:
                                if log_cb:
                                    log_cb(f"Failed to save metadata: {e}")
                        
                        # Check if we have enough successful downloads
                        if successful_downloads >= max_results:
                            break
                elif metadata and metadata.get('duration', 0):
                    # Video was too short, log it and continue
                    # URL is already marked as used to prevent re-attempting
                    if log_cb:
                        log_cb(f"Skipped short video: {metadata.get('title')} ({metadata.get('duration')}s)")
        
        # If we've collected enough candidates, stop
        if successful_downloads >= max_results:
            break
            
    if log_cb and successful_downloads < max_results:
        log_cb(f"Only got {successful_downloads}/{max_results} successful downloads from {len(items)} search results")
    
    return candidates


# Legacy functions removed - we now use session-based storage only
