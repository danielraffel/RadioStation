"""Generate HTML index files for easy playback of audio samples."""

import json
from pathlib import Path
from typing import List, Dict, Any


def generate_theme_index(theme_dir: Path, theme_name: str) -> None:
    """Generate index.html for a specific theme folder."""
    wav_files = sorted(theme_dir.glob("*.wav"))
    if not wav_files:
        return
    
    samples = []
    for wav_file in wav_files:
        sample = {
            'filename': wav_file.name,
            'path': wav_file.name,  # Relative path
        }
        
        # Load metadata if exists
        metadata_file = wav_file.with_suffix('.json')
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    sample['metadata'] = metadata
            except:
                pass
        
        samples.append(sample)
    
    html = generate_html_content(
        title=f"{theme_name} Samples",
        samples=samples,
        base_path=""
    )
    
    index_path = theme_dir / "index.html"
    with open(index_path, 'w') as f:
        f.write(html)


def generate_session_index(session_dir: Path) -> None:
    """Generate main index.html for the entire session folder."""
    themes_dir = session_dir / "themes"
    if not themes_dir.exists():
        return
    
    all_samples = []
    themes = sorted([d for d in themes_dir.iterdir() if d.is_dir()])
    
    for theme_folder in themes:
        theme_name = theme_folder.name
        wav_files = sorted(theme_folder.glob("*.wav"))
        
        for wav_file in wav_files:
            sample = {
                'filename': wav_file.name,
                'path': f"themes/{theme_name}/{wav_file.name}",  # Relative path from session root
                'theme': theme_name,
            }
            
            # Load metadata if exists
            metadata_file = wav_file.with_suffix('.json')
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        sample['metadata'] = metadata
                except:
                    pass
            
            all_samples.append(sample)
    
    html = generate_html_content(
        title="All Session Samples",
        samples=all_samples,
        base_path="",
        show_theme=True
    )
    
    index_path = session_dir / "index.html"
    with open(index_path, 'w') as f:
        f.write(html)


def generate_html_content(title: str, samples: List[Dict[str, Any]], base_path: str = "", show_theme: bool = False) -> str:
    """Generate the HTML content for an index page."""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        /* Safari-specific performance optimizations */
        @supports (-webkit-touch-callout: none) {{
            .sample-item {{
                -webkit-transform: translateZ(0);
                transform: translateZ(0);
            }}
            audio {{
                -webkit-transform: translateZ(0);
            }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .controls {{
            position: sticky;
            top: 0;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            z-index: 100;
        }}
        .controls button {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
            font-size: 14px;
            position: relative;
            transition: all 0.3s;
        }}
        .controls button:hover {{
            background: #45a049;
        }}
        .controls button:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        .controls button.active-mode {{
            background: #2196F3;
            box-shadow: 0 0 10px rgba(33, 150, 243, 0.5);
        }}
        .controls button.active-mode:hover {{
            background: #1976D2;
        }}
        .controls button.active-mode::after {{
            content: ' ▶';
        }}
        .sample-list {{
            background: white;
            border-radius: 8px;
            padding: 20px;
        }}
        .sample-item {{
            padding: 15px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
            transition: background 0.3s;
        }}
        .sample-item:hover {{
            background: #f9f9f9;
        }}
        .sample-item.playing {{
            background: #e8f5e9;
        }}
        .sample-info {{
            flex: 1;
            margin-right: 20px;
        }}
        .sample-name {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .download-btn {{
            background: none;
            border: none;
            cursor: pointer;
            padding: 2px;
            color: #666;
            font-size: 16px;
            transition: color 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
        }}
        .download-btn:hover {{
            color: #2196F3;
        }}
        .sample-metadata {{
            font-size: 12px;
            color: #666;
            line-height: 1.4;
        }}
        .sample-controls {{
            display: flex;
            gap: 10px;
        }}
        .sample-controls button {{
            background: #2196F3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }}
        .sample-controls button:hover {{
            background: #1976D2;
        }}
        audio {{
            display: none;
        }}
        .theme-badge {{
            display: inline-block;
            background: #673AB7;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            margin-right: 10px;
        }}
        .status {{
            padding: 10px;
            background: #333;
            color: #0f0;
            font-family: monospace;
            border-radius: 4px;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    
    <div class="controls">
        <div class="status" id="status">Ready - Press Space to play/pause, ←↑ previous, →↓ next</div>
        <button onclick="playNext()" id="playNextBtn">Play Next</button>
        <button onclick="playAll()" id="playAllBtn">Play All</button>
        <button onclick="stopAll()" id="stopBtn">Stop</button>
        <button onclick="shufflePlay()" id="shuffleBtn">Shuffle Play</button>
        <label style="margin-left: 20px; color: #666; font-size: 14px;">
            <input type="checkbox" id="loopCheckbox" style="margin-right: 5px;">
            Loop playlist
        </label>
    </div>
    
    <div class="sample-list">
"""
    
    for i, sample in enumerate(samples):
        metadata = sample.get('metadata', {})
        
        # Build metadata display
        meta_lines = []
        if show_theme or 'theme' in sample:
            meta_lines.append(f"<span class='theme-badge'>{sample.get('theme', metadata.get('theme_name', 'Unknown'))}</span>")
        
        if metadata:
            if 'title' in metadata:
                meta_lines.append(f"Title: {metadata['title'][:50]}...")
            if 'search_term' in metadata:
                # Add JSON link on same line as search term
                json_filename = sample['filename'].replace('.wav', '.json')
                # Use the same path as the audio file, just replace extension
                json_path = sample['path'].replace('.wav', '.json')
                meta_lines.append(f"Search: {metadata['search_term']} <a href='{base_path}{json_path}' target='_blank' style='color: #9E9E9E; text-decoration: none;' title='View metadata JSON'>📄</a>")
            if 'clap_score' in metadata and metadata['clap_score'] is not None:
                meta_lines.append(f"CLAP Score: {metadata['clap_score']:.3f}")
            if 'duration' in metadata:
                meta_lines.append(f"Original video: {metadata['duration']}s")

            # Add YouTube link with timestamp
            if 'url' in metadata:
                # Calculate the actual timestamp in the YouTube video
                timestamp = metadata.get('download_section_start', 0)
                if 'slice_start_ms' in metadata:
                    # Add the offset within the downloaded section
                    timestamp += metadata['slice_start_ms'] / 1000.0

                # Convert to integer seconds for YouTube URL
                timestamp_seconds = int(timestamp)

                # Build YouTube URL with timestamp
                youtube_url = metadata['url']
                if '?' in youtube_url:
                    youtube_url += f"&t={timestamp_seconds}"
                else:
                    youtube_url += f"?t={timestamp_seconds}"

                meta_lines.append(f"<a href='{youtube_url}' target='_blank' style='color: #2196F3; text-decoration: none;'>📺 YouTube (starts at {timestamp_seconds}s)</a>")
        
        meta_html = "<br>".join(meta_lines) if meta_lines else "No metadata"
        
        # Get the full path for the copy functionality
        full_path = sample['path']

        html += f"""
        <div class="sample-item" id="sample-{i}" data-index="{i}">
            <div class="sample-info">
                <div class="sample-name">
                    <span>{sample['filename']}</span>
                    <a href="{base_path}{sample['path']}" download="{sample['filename']}" class="download-btn" title="Download file">💾</a>
                </div>
                <div class="sample-metadata">{meta_html}</div>
            </div>
            <div class="sample-controls">
                <button onclick="playSample({i})">Play</button>
            </div>
            <audio id="audio-{i}" src="{base_path}{sample['path']}" preload="none"></audio>
        </div>
"""
    
    html += """
    </div>
    
    <script>
        let currentIndex = -1;
        let isPlaying = false;
        let playMode = 'sequential'; // 'sequential' or 'shuffle'
        let shuffledIndices = [];
        let loopEnabled = false;
        let currentAudio = null; // Safari optimization: track current audio
        const totalSamples = """ + str(len(samples)) + """;

        // Load loop preference from localStorage
        const savedLoop = localStorage.getItem('loopPlaylist');
        if (savedLoop === 'true') {
            document.getElementById('loopCheckbox').checked = true;
            loopEnabled = true;
        }

        // Handle loop checkbox changes
        document.getElementById('loopCheckbox').addEventListener('change', function(e) {
            loopEnabled = e.target.checked;
            localStorage.setItem('loopPlaylist', loopEnabled);
        });
        
        function updateStatus(msg) {
            document.getElementById('status').textContent = msg;
        }

        function updatePlayModeButtons() {
            // Clear all active states
            document.querySelectorAll('.controls button').forEach(btn => {
                btn.classList.remove('active-mode');
            });

            // Set active state based on current play mode
            if (isPlaying) {
                if (playMode === 'sequential') {
                    document.getElementById('playAllBtn').classList.add('active-mode');
                } else if (playMode === 'shuffle') {
                    document.getElementById('shuffleBtn').classList.add('active-mode');
                }
            }
        }
        
        function playSample(index) {
            // Stop any currently playing audio without resetting playMode
            stopCurrentAudio();

            // Play the selected sample
            const audio = document.getElementById(`audio-${index}`);
            const item = document.getElementById(`sample-${index}`);

            currentAudio = audio; // Safari optimization
            currentIndex = index;
            isPlaying = true;

            // Update visual state - Safari optimization: more efficient
            const prevPlaying = document.querySelector('.sample-item.playing');
            if (prevPlaying) prevPlaying.classList.remove('playing');
            item.classList.add('playing');

            // Update button states
            updatePlayModeButtons();

            // Play audio
            audio.play();
            updateStatus(`Playing: ${index + 1}/${totalSamples}`);

            // Set up event listener for when audio ends
            audio.onended = function() {
                item.classList.remove('playing');
                if (playMode === 'sequential' || playMode === 'shuffle') {
                    // Continue to next track in the playlist
                    if (playMode === 'shuffle' && shuffledIndices.length > 0) {
                        const currentShuffleIndex = shuffledIndices.indexOf(currentIndex);
                        if (currentShuffleIndex < shuffledIndices.length - 1) {
                            playSample(shuffledIndices[currentShuffleIndex + 1]);
                        } else if (loopEnabled) {
                            // Loop back to start of shuffle
                            playSample(shuffledIndices[0]);
                        } else {
                            isPlaying = false;
                            playMode = 'single';
                            updatePlayModeButtons();
                            updateStatus('Playlist complete');
                        }
                    } else if (playMode === 'sequential') {
                        if (currentIndex < totalSamples - 1) {
                            playSample(currentIndex + 1);
                        } else if (loopEnabled) {
                            // Loop back to start
                            playSample(0);
                        } else {
                            isPlaying = false;
                            playMode = 'single';
                            updatePlayModeButtons();
                            updateStatus('Playlist complete');
                        }
                    }
                } else {
                    isPlaying = false;
                    playMode = 'single';
                    updatePlayModeButtons();
                    updateStatus('Stopped');
                }
            };
        }

        function stopCurrentAudio() {
            // Safari optimization: only stop the current audio
            if (currentAudio) {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio = null;
            }

            // Remove playing state
            const playingItem = document.querySelector('.sample-item.playing');
            if (playingItem) {
                playingItem.classList.remove('playing');
            }
        }
        
        function playNext() {
            let nextIndex;

            if (playMode === 'shuffle' && shuffledIndices.length > 0) {
                const currentShuffleIndex = shuffledIndices.indexOf(currentIndex);
                if (currentShuffleIndex < shuffledIndices.length - 1) {
                    nextIndex = shuffledIndices[currentShuffleIndex + 1];
                } else if (loopEnabled || currentIndex === -1) {
                    // Restart from beginning of shuffle
                    nextIndex = shuffledIndices[0] || 0;
                } else {
                    // At the end, restart from beginning anyway
                    nextIndex = shuffledIndices[0] || 0;
                    updateStatus('Restarting from beginning');
                }
            } else {
                if (currentIndex < totalSamples - 1) {
                    nextIndex = currentIndex + 1;
                } else {
                    // At the end, restart from beginning
                    nextIndex = 0;
                    updateStatus('Restarting from beginning');
                }
            }

            playSample(nextIndex);
        }
        
        function playAll() {
            stopAll();  // Reset everything first
            playMode = 'sequential';
            currentIndex = -1;
            if (totalSamples > 0) {
                playSample(0);
            }
        }

        function shufflePlay() {
            stopAll();  // Reset everything first
            playMode = 'shuffle';

            // Create shuffled array of indices
            shuffledIndices = Array.from({length: totalSamples}, (_, i) => i);
            for (let i = shuffledIndices.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [shuffledIndices[i], shuffledIndices[j]] = [shuffledIndices[j], shuffledIndices[i]];
            }

            currentIndex = -1;
            if (shuffledIndices.length > 0) {
                playSample(shuffledIndices[0]);
            }
        }
        
        function stopAll() {
            // Safari optimization: stop current audio first
            if (currentAudio) {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio = null;
            }

            // Remove playing state
            const playingItem = document.querySelector('.sample-item.playing');
            if (playingItem) {
                playingItem.classList.remove('playing');
            }

            isPlaying = false;
            playMode = 'single';
            updatePlayModeButtons();
            updateStatus('Stopped - Press Space to play/pause, ←↑ previous, →↓ next');
        }

        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.code === 'Space') {
                e.preventDefault();
                if (isPlaying) {
                    stopAll();
                } else if (currentIndex >= 0) {
                    playSample(currentIndex);
                } else {
                    playAll();
                }
            } else if (e.code === 'ArrowRight' || e.code === 'ArrowDown') {
                e.preventDefault();
                playNext();
            } else if (e.code === 'ArrowLeft' || e.code === 'ArrowUp') {
                e.preventDefault();
                if (playMode === 'shuffle' && shuffledIndices.length > 0) {
                    const currentShuffleIndex = shuffledIndices.indexOf(currentIndex);
                    if (currentShuffleIndex > 0) {
                        playSample(shuffledIndices[currentShuffleIndex - 1]);
                    } else if (loopEnabled && currentShuffleIndex === 0) {
                        // Loop to end of shuffle playlist
                        playSample(shuffledIndices[shuffledIndices.length - 1]);
                    }
                } else {
                    if (currentIndex > 0) {
                        playSample(currentIndex - 1);
                    } else if (loopEnabled && currentIndex === 0) {
                        // Loop to end
                        playSample(totalSamples - 1);
                    } else if (currentIndex === -1 && totalSamples > 0) {
                        // If nothing is selected, start from the beginning
                        playSample(0);
                    }
                }
            }
        });
        
        updateStatus('Ready - Press Space to play/pause, ←↑ previous, →↓ next');
    </script>
</body>
</html>
"""
    
    return html