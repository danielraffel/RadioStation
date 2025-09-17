"""Pipeline to fill themed banks with scored clips."""

import os
import datetime
import random
import string
import json
from pathlib import Path
from typing import List, Dict

from .config import load_env, load_prompts, load_themes
from .downloader import download_candidates_for_term, clear_session_urls
from . import scoring
from .search_expander_v2 import batch_expand_search_terms_v2 as batch_expand_search_terms
from .search_expander import is_expansion_enabled
from .html_generator import generate_theme_index, generate_session_index
from .words_manager import get_words_manager

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "wavs" / "sessions"
PROCESSED_DIR = BASE_DIR / "wavs" / "processed" / "candidates"

def _generate_session_id() -> str:
    """Generate a unique session ID with timestamp and random suffix."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{timestamp}_{random_suffix}"


def _count_in_bank(theme: str, session_dir: Path) -> int:
    d = session_dir / "themes" / theme
    if not d.exists():
        return 0
    return len([p for p in d.glob("*.wav")])


def _move_to_theme(path: Path, theme: str, session_dir: Path) -> Path:
    out_dir = session_dir / "themes" / theme
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Find the next available number for this theme
    existing_files = sorted(out_dir.glob(f"{theme}_*.wav"))
    if existing_files:
        # Extract numbers from existing files
        numbers = []
        for f in existing_files:
            try:
                # Extract number from filename like "ThemeName_01.wav"
                num_str = f.stem.replace(f"{theme}_", "")
                numbers.append(int(num_str))
            except ValueError:
                continue
        next_num = max(numbers) + 1 if numbers else 1
    else:
        next_num = 1
    
    # Create numbered filename
    out_path = out_dir / f"{theme}_{next_num:02d}.wav"
    
    # Double-check it doesn't exist (shouldn't happen, but be safe)
    while out_path.exists():
        next_num += 1
        out_path = out_dir / f"{theme}_{next_num:02d}.wav"
    
    path.replace(out_path)
    return out_path


def _assign_with_scoring(wav_path: Path, themes: List[str], prompts: list, min_sim: float, log_cb=None) -> tuple[str | None, float | None]:
    """Return (best_theme, score) using CLAP scoring; None if below threshold.

    Falls back to the first provided theme if scoring is disabled.
    """
    if scoring.is_enabled():
        try:
            if log_cb:
                log_cb(f"Running CLAP scoring for {wav_path.name}...")
            res = scoring.best_theme_for_wav(wav_path, prompts, themes)
            if res:
                name, score = res
                if log_cb:
                    log_cb(f"CLAP scored {wav_path.name}: {name} (score: {score:.3f})")
                if score is not None and score < min_sim:
                    return None, score
                return name, score
        except Exception as _exc:  # noqa: BLE001
            # fall back to original theme if scoring fails
            if log_cb:
                log_cb(f"CLAP scoring failed for {wav_path.name}, using fallback")
            return themes[0], None
    # fallback: keep by search term – caller passes the intended target theme name
    return themes[0], None


def run_pipeline(stop_cb=None, progress_cb=None, log_cb=None, continue_session=None):
    """Download, score, and organize clips until banks are filled.

    stop_cb: optional callable returning True when a stop has been requested.
    progress_cb: optional callable receiving a dict of live progress.
    log_cb: optional log callback function
    continue_session: optional session_id to continue from a previous run
    """
    load_env()

    # Load themes with new structure
    theme_objects = load_themes()
    theme_names = [t['name'] for t in theme_objects]
    theme_search_map = {t['name']: t['search'] for t in theme_objects}
    theme_prompts = [{'name': t['name'], 'prompt': t['prompt']} for t in theme_objects]

    clip_ms = int(os.environ['CLIP_SECONDS']) * 1000
    samples_per_bank = int(os.environ['SAMPLES_PER_BANK'])
    max_retries = int(os.environ.get('MAX_RETRIES_PER_THEME', '0'))
    search_batch = int(os.environ.get('SEARCH_RESULTS_PER_THEME', '32'))
    download_workers = int(os.environ.get('DOWNLOAD_WORKERS', '4'))
    slices_per_video = int(os.environ.get('SLICES_PER_VIDEO', '1'))
    slice_stride_ms = int(float(os.environ.get('SLICE_STRIDE_SECONDS', os.environ['CLIP_SECONDS'])) * 1000)
    min_sim = float(os.environ.get('SCORING_MIN_SIMILARITY', '0.0'))

    # Words list configuration
    use_words_list = os.environ.get('USE_WORDS_LIST', '0') == '1'
    words_mode = os.environ.get('WORDS_MODE', 'one_per_theme')  # 'one_per_theme' or 'unique_per_query'
    theme_words_opt_out = os.environ.get('THEME_WORDS_OPT_OUT', '').split(',')
    theme_words_opt_out = [t.strip() for t in theme_words_opt_out if t.strip()]
    words_manager = None
    if use_words_list:
        words_manager = get_words_manager()
        if not words_manager.is_available():
            if log_cb:
                log_cb("Warning: Words list enabled but not available")
            use_words_list = False

    # Session management - continue existing or create new
    if continue_session:
        session_id = continue_session
        session_dir = SESSIONS_DIR / session_id
        if not session_dir.exists():
            if log_cb:
                log_cb(f"Session {session_id} not found, starting fresh")
            session_id = _generate_session_id()
            session_dir = SESSIONS_DIR / session_id
            continue_session = None  # Reset flag since we're starting fresh
        else:
            if log_cb:
                log_cb(f"Continuing session {session_id}")
    else:
        session_id = os.environ.get('SESSION_ID') or _generate_session_id()
        session_dir = SESSIONS_DIR / session_id

    session_dir.mkdir(parents=True, exist_ok=True)

    # Only clear URLs for new sessions, not continuations
    if not continue_session:
        # CRITICAL: Clear session-wide URL tracking at start of new pipeline run
        # This ensures no URL can be used twice within this session, even across themes
        clear_session_urls()
        if log_cb:
            log_cb("Cleared session-wide URL tracking for duplicate prevention")
    else:
        if log_cb:
            log_cb("Continuing session - preserving URL tracking to avoid re-downloading")
    
    # Set up session-specific log file
    log_file = session_dir / f"session_{session_id}.log"
    
    def log_with_file(message):
        """Log to both callback and file."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        
        # Write to file
        with open(log_file, 'a') as f:
            f.write(log_line + '\n')
        
        # Call original callback
        if log_cb:
            log_cb(message)
    
    # Use the wrapped logger
    local_log = log_with_file
    
    if local_log:
        local_log(f"Session ID: {session_id}")
        local_log(f"Output directory: {session_dir}")
        local_log(f"CLAP scoring enabled: {scoring.is_enabled()}")
        local_log(f"OpenAI expansion enabled: {is_expansion_enabled()}")
        local_log(f"Words list enabled: {use_words_list}")
    
    results = {t: _count_in_bank(t, session_dir) for t in theme_names}
    retries = {t: 0 for t in theme_names}

    # When continuing, log the current state
    if continue_session and local_log:
        local_log(f"Continuing session: {session_id}")
        local_log("Current progress:")
        for theme in theme_names:
            count = results[theme]
            if count >= samples_per_bank:
                local_log(f"  {theme}: COMPLETE ({count}/{samples_per_bank})")
            else:
                local_log(f"  {theme}: {count}/{samples_per_bank}")
        completed = sum(1 for c in results.values() if c >= samples_per_bank)
        local_log(f"Completed themes: {completed}/{len(theme_names)}")
        total_samples = sum(results.values())
        local_log(f"Total samples collected: {total_samples}/{samples_per_bank * len(theme_names)}")
    
    # Pre-generate all search queries using batch expansion
    if local_log:
        local_log("Generating search queries for all themes...")
    
    if use_words_list:
        # Generate word-based searches for all themes
        words_for_expansion = {}
        for theme in theme_objects:
            theme_name = theme['name']
            # Skip themes opted out from words
            if theme_name in theme_words_opt_out:
                continue
                
            if words_mode == 'one_per_theme':
                # One word repeated for the theme
                word = words_manager.get_unique_random_word()
                words_for_expansion[theme_name] = [word] * samples_per_bank
            else:
                # Unique words for each sample
                words_for_expansion[theme_name] = [
                    words_manager.get_unique_random_word() 
                    for _ in range(samples_per_bank)
                ]
        
        if is_expansion_enabled():
            # Expand the words using OpenAI with CLAP context
            expanded_searches = batch_expand_search_terms(
                theme_objects, 
                samples_per_bank,
                search_terms_override=words_for_expansion
            )
            
            # Save expansion results to session folder
            expansion_file = session_dir / "openai_expansions.json"
            try:
                expansion_data = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'original_words': words_for_expansion if use_words_list else None,
                    'expanded_searches': expanded_searches,
                    'themes': {t['name']: {'search': t['search'], 'prompt': t['prompt']} for t in theme_objects}
                }
                with open(expansion_file, 'w') as f:
                    json.dump(expansion_data, f, indent=2)
                if local_log:
                    local_log(f"Saved OpenAI expansions to {expansion_file.name}")
            except Exception as e:
                if local_log:
                    local_log(f"Failed to save expansions: {e}")
            
            if local_log:
                local_log(f"Expanded {len(words_for_expansion)} themes with word-based searches")
                # Log sample of expansions to verify they're working
                for theme_name in list(expanded_searches.keys())[:3]:
                    if expanded_searches[theme_name] and len(expanded_searches[theme_name]) > 0:
                        original = words_for_expansion.get(theme_name, [''])[0] if use_words_list else theme_search_map.get(theme_name, '')
                        expanded = expanded_searches[theme_name][0]
                        if original != expanded:
                            local_log(f"Expansion worked for {theme_name}: '{original}' → '{expanded}'")
                        else:
                            local_log(f"WARNING: No expansion for {theme_name}, still '{original}'")
        else:
            # Use words directly without expansion
            expanded_searches = words_for_expansion
            if local_log:
                local_log(f"Using raw words for {len(words_for_expansion)} themes")
    elif is_expansion_enabled():
        # Use OpenAI to batch generate all queries upfront
        expanded_searches = batch_expand_search_terms(theme_objects, samples_per_bank)
        if local_log:
            local_log(f"Generated {sum(len(v) for v in expanded_searches.values())} unique search queries")
    else:
        # No expansion - use original search terms
        expanded_searches = None

    def emit_progress(current_theme=None, note: str | None = None):
        if not progress_cb:
            return
        banks_completed = sum(1 for t in theme_names if results[t] >= samples_per_bank)
        overall_filled = sum(results.values())
        overall_target = samples_per_bank * len(theme_names)
        percent = int(100 * overall_filled / overall_target) if overall_target else 100
        payload = {
            'themes': theme_names,
            'session_id': session_id,
            'filled': dict(results),
            'retries': dict(retries),
            'target_per_bank': samples_per_bank,
            'banks_completed': banks_completed,
            'total_banks': len(theme_names),
            'overall_filled': overall_filled,
            'overall_target': overall_target,
            'percent': percent,
            'current_theme': current_theme,
        }
        if note:
            payload['note'] = note
        progress_cb(payload)

    for idx, theme_obj in enumerate(theme_objects):
        theme_name = theme_obj['name']
        search_term = theme_obj['search']
        theme_prompt = theme_obj['prompt']

        # Skip already completed themes when continuing
        if results[theme_name] >= samples_per_bank:
            if local_log:
                local_log(f"Skipping {theme_name} - already complete ({results[theme_name]}/{samples_per_bank})")
            continue

        # Check if this theme should use words list
        use_words_for_theme = use_words_list and theme_name not in theme_words_opt_out
        
        # Get pre-generated searches for this theme
        search_idx = 0
        
        if expanded_searches and theme_name in expanded_searches:
            # Use pre-generated (possibly expanded) searches
            searches_for_theme = expanded_searches[theme_name]
            if local_log:
                local_log(f"Using {len(searches_for_theme)} pre-generated queries for {theme_name}")
        else:
            # Fallback to original search term - split comma-separated values
            if ',' in search_term:
                # Split comma-separated search terms
                individual_searches = [s.strip() for s in search_term.split(',') if s.strip()]
                # Repeat the list to fill up to samples_per_bank
                searches_for_theme = []
                while len(searches_for_theme) < samples_per_bank:
                    searches_for_theme.extend(individual_searches)
                # Trim to exact number needed
                searches_for_theme = searches_for_theme[:samples_per_bank]
                if local_log:
                    local_log(f"Split '{search_term[:50]}...' into {len(individual_searches)} individual searches for {theme_name}")
            else:
                # Single search term - repeat it
                searches_for_theme = [search_term] * samples_per_bank
                if local_log:
                    local_log(f"Using original search term '{search_term}' for {theme_name}")
        
        if local_log:
            local_log(f"Starting to process theme: {theme_name}")
        emit_progress(current_theme=theme_name, note=f"Processing {theme_name}")
        if stop_cb and stop_cb():
            break
        target_theme = theme_name
        
        # Track successful downloads to move to next search query
        downloads_with_current_search = 0
        max_per_search = max(1, search_batch // 4)  # Try to spread across queries
        
        while results[target_theme] < samples_per_bank:
            if stop_cb and stop_cb():
                break
            if max_retries and retries[target_theme] >= max_retries:
                break
            
            # Get next search query
            if search_idx >= len(searches_for_theme):
                # We've used all queries, wrap around
                search_idx = 0
            
            current_search = searches_for_theme[search_idx]
            
            # Move to next search after using it a few times or on failure
            if downloads_with_current_search >= max_per_search:
                search_idx += 1
                downloads_with_current_search = 0
                if local_log and search_idx < len(searches_for_theme):
                    local_log(f"Moving to next search query for {theme_name}")
            
            if local_log:
                local_log(f"Downloading candidates for '{theme_name}' using search: '{current_search}'")
            
            # download candidates for this term
            candidates = download_candidates_for_term(
                current_search,
                clip_ms=clip_ms,
                max_results=search_batch,
                download_workers=download_workers,
                slices_per_video=slices_per_video,
                slice_stride_ms=slice_stride_ms,
                log_cb=local_log,
                theme_name=theme_name,
                theme_prompt=theme_prompt,
                original_search=search_term,
                expanded_search=[current_search] if current_search != search_term else None,
            )
            if not candidates:
                # nothing new came in; try next search query
                if local_log:
                    local_log(f"No results for '{current_search}', trying next query")
                search_idx += 1
                downloads_with_current_search = 0
                if search_idx >= len(searches_for_theme):
                    if local_log:
                        local_log(f"Exhausted all search queries for {theme_name}")
                    break
                continue
            
            downloads_with_current_search += len(candidates)
            if local_log:
                local_log(f"Got {len(candidates)} candidates for {theme_name} using '{current_search}'")
            for cand in candidates:
                if stop_cb and stop_cb():
                    break
                # best_theme uses scoring if enabled; otherwise assigns to target_theme
                best_theme, score = _assign_with_scoring(cand, [target_theme] + [t for t in theme_names if t != target_theme], theme_prompts, min_sim, local_log)
                if best_theme is None:
                    # below threshold, treat as unmatched and discard
                    cand.unlink(missing_ok=True)
                    retries[target_theme] += 1
                    if local_log:
                        local_log(f"Discarded {cand.name} (score {score:.3f} < {min_sim:.3f})")
                    continue
                final_path = _move_to_theme(cand, best_theme, session_dir)
                
                # Move metadata file if it exists
                metadata_src = cand.with_suffix('.json')
                if metadata_src.exists():
                    metadata_dst = final_path.with_suffix('.json')
                    try:
                        # Read metadata and add scoring info
                        with open(metadata_src, 'r') as f:
                            metadata = json.load(f)
                        metadata['assigned_theme'] = best_theme
                        metadata['clap_score'] = score if score is not None else None
                        metadata['final_path'] = str(final_path)
                        # Write to new location
                        with open(metadata_dst, 'w') as f:
                            json.dump(metadata, f, indent=2)
                        # Remove original metadata file
                        metadata_src.unlink()
                    except Exception as e:
                        if local_log:
                            local_log(f"Failed to move metadata: {e}")
                
                if local_log:
                    local_log(f"Assigned {cand.name} -> {best_theme} (score {score if score is not None else 'n/a'})")
                # Update results for the theme that actually received the file
                results[best_theme] += 1
                if best_theme != target_theme:
                    # This was meant for target_theme but went elsewhere
                    retries[target_theme] += 1
                if results[target_theme] >= samples_per_bank:
                    break
                emit_progress(current_theme=theme_name)
        
        # Generate HTML index for this theme
        if session_dir:
            theme_folder = session_dir / "themes" / theme_name
            if theme_folder.exists():
                try:
                    generate_theme_index(theme_folder, theme_name)
                    if local_log:
                        local_log(f"Generated index.html for {theme_name}")
                except Exception as e:
                    if local_log:
                        local_log(f"Failed to generate index for {theme_name}: {e}")

    # Generate main session index
    if session_dir:
        try:
            generate_session_index(session_dir)
            if local_log:
                local_log(f"Generated main index.html for session")
        except Exception as e:
            if local_log:
                local_log(f"Failed to generate session index: {e}")
    
    final = {
        'themes': theme_names,
        'session_id': session_id,
        'session_dir': str(session_dir),
        'clip_ms': clip_ms,
        'prompts': theme_prompts,
        'filled': results,
        'retries': retries,
        'scoring_enabled': scoring.is_enabled(),
        'openai_expansion_enabled': is_expansion_enabled(),
        'words_list_enabled': use_words_list,
        'words_mode': words_mode if use_words_list else None,
        'words_available': words_manager.is_available() if words_manager else False,
    }
    emit_progress(current_theme=None)
    return final


if __name__ == '__main__':
    result = run_pipeline()
    print(result)
