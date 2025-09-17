"""Centralized hash management using SQLite for better persistence and performance."""

import sqlite3
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Set, Dict, Any, Tuple
import threading
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# SQLite database for hash storage
HASH_DB = DATA_DIR / "audio_hashes.db"

# YouTube video ID extraction patterns
# Note: Real YouTube video IDs are exactly 11 characters, but for testing we allow shorter IDs
YOUTUBE_URL_PATTERNS = [
    re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)'),
    re.compile(r'youtube\.com/v/([a-zA-Z0-9_-]+)'),
    re.compile(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)'),
]

# Legacy JSON files for backward compatibility
LEGACY_HASHES_FILE = BASE_DIR / "audio_hashes.json"
LEGACY_URLS_FILE = BASE_DIR / "used_urls.json"

class HashManager:
    """Manages audio hashes and URLs using SQLite with JSON fallback."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None
        self._init_db()
        self._migrate_legacy_data()
    
    def _init_db(self):
        """Initialize SQLite database and create tables."""
        self._conn = sqlite3.connect(str(HASH_DB), check_same_thread=False, timeout=30)
        # Enable WAL mode for better concurrent access
        self._conn.execute('PRAGMA journal_mode = WAL')
        # Set busy timeout for concurrent access
        self._conn.execute('PRAGMA busy_timeout = 30000')
        # Enable foreign keys if needed
        self._conn.execute('PRAGMA foreign_keys = ON')
        
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS audio_hashes (
                hash TEXT PRIMARY KEY,
                file_path TEXT,
                url TEXT,
                title TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS used_urls (
                url TEXT PRIMARY KEY,
                normalized_url TEXT,
                video_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                title TEXT,
                search_term TEXT,
                theme_name TEXT
            )
        """)
        
        # Add new columns if they don't exist (for existing databases)
        try:
            self._conn.execute('ALTER TABLE used_urls ADD COLUMN normalized_url TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            self._conn.execute('ALTER TABLE used_urls ADD COLUMN video_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        try:
            self._conn.execute('ALTER TABLE used_urls ADD COLUMN theme_name TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        self._conn.execute("""CREATE INDEX IF NOT EXISTS idx_video_id ON used_urls(video_id)""")
        self._conn.execute("""CREATE INDEX IF NOT EXISTS idx_normalized_url ON used_urls(normalized_url)""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_hash_timestamp ON audio_hashes(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_url_timestamp ON used_urls(timestamp)")
        self._conn.commit()
        
        # Populate normalized URLs and video IDs for existing entries
        self._populate_missing_url_data()
        
        # Force population on every startup to ensure consistency
        self._ensure_url_data_populated()
    
    def _populate_missing_url_data(self):
        """Populate normalized_url and video_id for existing entries."""
        try:
            # Find entries with missing normalized_url or video_id
            cursor = self._conn.execute(
                "SELECT url FROM used_urls WHERE normalized_url IS NULL OR video_id IS NULL"
            )
            urls_to_update = [row[0] for row in cursor.fetchall()]
            
            for url in urls_to_update:
                normalized_url, video_id = self.normalize_url(url)
                self._conn.execute(
                    "UPDATE used_urls SET normalized_url = ?, video_id = ? WHERE url = ?",
                    (normalized_url, video_id, url)
                )
            
            if urls_to_update:
                self._conn.commit()
                
        except Exception:
            pass  # Ignore errors during migration
    
    def _ensure_url_data_populated(self):
        """Ensure all URLs have normalized_url and video_id populated."""
        try:
            # Update any entries that still have NULL normalized_url or video_id
            cursor = self._conn.execute("SELECT url FROM used_urls WHERE normalized_url IS NULL OR video_id IS NULL")
            urls_to_fix = [row[0] for row in cursor.fetchall()]
            
            for url in urls_to_fix:
                normalized_url, video_id = self.normalize_url(url)
                self._conn.execute(
                    "UPDATE used_urls SET normalized_url = ?, video_id = ? WHERE url = ?",
                    (normalized_url, video_id, url)
                )
            
            if urls_to_fix:
                self._conn.commit()
                
        except Exception:
            pass  # Ignore errors
    
    def _migrate_legacy_data(self):
        """Migrate data from legacy JSON files to SQLite."""
        with self._lock:
            # Migrate hashes
            if LEGACY_HASHES_FILE.exists():
                try:
                    with open(LEGACY_HASHES_FILE, 'r') as f:
                        data = json.load(f)
                        for entry in data:
                            if isinstance(entry, dict) and 'hash' in entry:
                                self._conn.execute(
                                    "INSERT OR IGNORE INTO audio_hashes (hash, timestamp, metadata) VALUES (?, ?, ?)",
                                    (entry['hash'], entry.get('timestamp', datetime.now().isoformat()), json.dumps(entry))
                                )
                        self._conn.commit()
                except Exception:
                    pass
            
            # Also check data directory for JSON files
            data_hashes = DATA_DIR / "audio_hashes.json"
            if data_hashes.exists() and data_hashes != LEGACY_HASHES_FILE:
                try:
                    with open(data_hashes, 'r') as f:
                        data = json.load(f)
                        for entry in data:
                            if isinstance(entry, dict) and 'hash' in entry:
                                self._conn.execute(
                                    "INSERT OR IGNORE INTO audio_hashes (hash, timestamp, metadata) VALUES (?, ?, ?)",
                                    (entry['hash'], entry.get('timestamp', datetime.now().isoformat()), json.dumps(entry))
                                )
                        self._conn.commit()
                except Exception:
                    pass
            
            # Migrate URLs
            if LEGACY_URLS_FILE.exists():
                try:
                    with open(LEGACY_URLS_FILE, 'r') as f:
                        urls = json.load(f)
                        if isinstance(urls, list):
                            for url in urls:
                                self._conn.execute(
                                    "INSERT OR IGNORE INTO used_urls (url) VALUES (?)",
                                    (url,)
                                )
                        self._conn.commit()
                except Exception:
                    pass
            
            # Check data directory for URLs
            data_urls = DATA_DIR / "used_urls.json"
            if data_urls.exists() and data_urls != LEGACY_URLS_FILE:
                try:
                    with open(data_urls, 'r') as f:
                        urls = json.load(f)
                        if isinstance(urls, list):
                            for url in urls:
                                self._conn.execute(
                                    "INSERT OR IGNORE INTO used_urls (url) VALUES (?)",
                                    (url,)
                                )
                        self._conn.commit()
                except Exception:
                    pass
    
    def has_hash(self, audio_hash: str) -> bool:
        """Check if a hash exists in the database."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT 1 FROM audio_hashes WHERE hash = ?",
                (audio_hash,)
            )
            return cursor.fetchone() is not None
    
    def add_hash(self, audio_hash: str, file_path: Optional[str] = None, 
                 url: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a new hash to the database atomically.
        
        Returns:
            True if hash was successfully added (wasn't already present)
            False if hash was already present
        """
        with self._lock:
            try:
                # Start a transaction for atomic check-and-insert  
                self._conn.execute('BEGIN IMMEDIATE TRANSACTION')
                
                # Check if hash already exists
                cursor = self._conn.execute(
                    "SELECT 1 FROM audio_hashes WHERE hash = ?",
                    (audio_hash,)
                )
                
                if cursor.fetchone():
                    self._conn.rollback()
                    return False  # Already exists
                
                # Add the hash
                metadata_json = json.dumps(metadata) if metadata else None
                self._conn.execute(
                    "INSERT INTO audio_hashes (hash, file_path, url, metadata) VALUES (?, ?, ?, ?)",
                    (audio_hash, file_path, url, metadata_json)
                )
                self._conn.commit()
                return True  # Successfully added
                
            except sqlite3.Error:
                self._conn.rollback()
                return False  # Database error, assume already exists for safety
    
    def normalize_url(self, url: str) -> Tuple[str, Optional[str]]:
        """Normalize URL and extract video ID.
        
        Returns:
            Tuple of (normalized_url, video_id) where video_id may be None if not extractable
        """
        # Extract video ID from various YouTube URL formats
        video_id = None
        for pattern in YOUTUBE_URL_PATTERNS:
            match = pattern.search(url)
            if match:
                video_id = match.group(1)
                break
        
        if video_id:
            # Normalize to standard watch URL format
            normalized = f"https://www.youtube.com/watch?v={video_id}"
            return normalized, video_id
        else:
            # For non-YouTube URLs, normalize by removing common parameters
            parsed = urlparse(url)
            if parsed.netloc and parsed.path:
                normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}"
                return normalized, None
            return url, None
    
    def has_url(self, url: str) -> bool:
        """Check if a URL has been used (checks both original and normalized forms)."""
        normalized_url, video_id = self.normalize_url(url)
        
        with self._lock:
            # Check by video ID first (most reliable for YouTube)
            if video_id:
                cursor = self._conn.execute(
                    "SELECT 1 FROM used_urls WHERE video_id = ?",
                    (video_id,)
                )
                if cursor.fetchone():
                    return True
            
            # Check by normalized URL
            cursor = self._conn.execute(
                "SELECT 1 FROM used_urls WHERE normalized_url = ? OR url = ?",
                (normalized_url, url)
            )
            return cursor.fetchone() is not None
    
    def has_video_id(self, video_id: str) -> bool:
        """Check if a video ID has been used."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT 1 FROM used_urls WHERE video_id = ?",
                (video_id,)
            )
            return cursor.fetchone() is not None
    
    def add_url(self, url: str, title: Optional[str] = None, search_term: Optional[str] = None, 
                theme_name: Optional[str] = None) -> bool:
        """Mark a URL as used atomically.
        
        Returns:
            True if URL was successfully added (wasn't already used)
            False if URL was already used
        """
        normalized_url, video_id = self.normalize_url(url)
        
        with self._lock:
            try:
                # Start a transaction for atomic check-and-insert
                self._conn.execute('BEGIN IMMEDIATE TRANSACTION')
                
                # Check if already used (by video_id if available, otherwise by URL)
                if video_id:
                    cursor = self._conn.execute(
                        "SELECT 1 FROM used_urls WHERE video_id = ?",
                        (video_id,)
                    )
                else:
                    cursor = self._conn.execute(
                        "SELECT 1 FROM used_urls WHERE normalized_url = ?",
                        (normalized_url,)
                    )
                
                if cursor.fetchone():
                    self._conn.rollback()
                    return False  # Already used
                
                # Add the URL
                self._conn.execute(
                    "INSERT INTO used_urls (url, normalized_url, video_id, title, search_term, theme_name) VALUES (?, ?, ?, ?, ?, ?)",
                    (url, normalized_url, video_id, title, search_term, theme_name)
                )
                self._conn.commit()
                return True  # Successfully added
                
            except sqlite3.Error as e:
                self._conn.rollback()
                # For debugging - in production you might want to log this
                # print(f"Database error in add_url: {e}")
                return False  # Database error, assume already used for safety
    
    def get_url_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get information about a used URL."""
        normalized_url, video_id = self.normalize_url(url)
        
        with self._lock:
            if video_id:
                cursor = self._conn.execute(
                    "SELECT url, video_id, title, search_term, theme_name, timestamp FROM used_urls WHERE video_id = ?",
                    (video_id,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT url, video_id, title, search_term, theme_name, timestamp FROM used_urls WHERE normalized_url = ?",
                    (normalized_url,)
                )
            
            row = cursor.fetchone()
            if row:
                return {
                    'url': row[0],
                    'video_id': row[1],
                    'title': row[2],
                    'search_term': row[3],
                    'theme_name': row[4],
                    'timestamp': row[5]
                }
            return None
    
    def get_all_hashes(self) -> Set[str]:
        """Get all known hashes."""
        with self._lock:
            cursor = self._conn.execute("SELECT hash FROM audio_hashes")
            return {row[0] for row in cursor.fetchall()}
    
    def get_all_urls(self) -> Set[str]:
        """Get all used URLs."""
        with self._lock:
            cursor = self._conn.execute("SELECT url FROM used_urls")
            return {row[0] for row in cursor.fetchall()}
    
    def get_all_video_ids(self) -> Set[str]:
        """Get all used video IDs."""
        with self._lock:
            cursor = self._conn.execute("SELECT video_id FROM used_urls WHERE video_id IS NOT NULL")
            return {row[0] for row in cursor.fetchall()}
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about stored data."""
        with self._lock:
            hash_count = self._conn.execute("SELECT COUNT(*) FROM audio_hashes").fetchone()[0]
            url_count = self._conn.execute("SELECT COUNT(*) FROM used_urls").fetchone()[0]
            youtube_count = self._conn.execute("SELECT COUNT(*) FROM used_urls WHERE video_id IS NOT NULL").fetchone()[0]
            return {
                "total_hashes": hash_count,
                "total_urls": url_count,
                "youtube_videos": youtube_count,
            }
    
    def cleanup_old_entries(self, days: int = 30):
        """Remove entries older than specified days."""
        with self._lock:
            cutoff_date = datetime.now().isoformat()
            self._conn.execute(
                "DELETE FROM audio_hashes WHERE datetime(timestamp) < datetime('now', '-' || ? || ' days')",
                (days,)
            )
            self._conn.execute(
                "DELETE FROM used_urls WHERE datetime(timestamp) < datetime('now', '-' || ? || ' days')",
                (days,)
            )
            self._conn.commit()
    
    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()

# Global instance
_hash_manager: Optional[HashManager] = None

def get_hash_manager() -> HashManager:
    """Get or create the global hash manager instance."""
    global _hash_manager
    if _hash_manager is None:
        _hash_manager = HashManager()
    return _hash_manager

def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return ""