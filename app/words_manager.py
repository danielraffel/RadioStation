"""Manage random word selection from words.txt file."""

import random
from pathlib import Path
from typing import List, Set, Optional

# words.txt is now in the app folder
APP_DIR = Path(__file__).resolve().parent
WORDS_FILE_LOCATIONS = [
    APP_DIR / "words.txt",  # Location in app folder
]

# Use first available location
WORDS_FILE = None
for location in WORDS_FILE_LOCATIONS:
    if location.exists():
        WORDS_FILE = location
        break

if not WORDS_FILE:
    WORDS_FILE = WORDS_FILE_LOCATIONS[0]  # Default to preferred location

class WordsManager:
    """Manager for loading and selecting random words from the words list."""
    
    def __init__(self):
        self.words: List[str] = []
        self.used_words: Set[str] = set()
        self._load_words()
    
    def _load_words(self):
        """Load words from the words.txt file."""
        if WORDS_FILE.exists():
            try:
                with open(WORDS_FILE, 'r') as f:
                    # Read all lines and filter out empty ones
                    self.words = [line.strip() for line in f if line.strip()]
                # Filter to only reasonable search terms (avoid numbers, special chars)
                self.words = [
                    w for w in self.words 
                    if len(w) > 2 and w.isalpha() and not w.isupper()
                ]
                print(f"Loaded {len(self.words)} words from words.txt")
            except Exception as e:
                print(f"Failed to load words.txt: {e}")
                self.words = []
        else:
            print(f"Words file not found: {WORDS_FILE}")
            self.words = []
    
    def get_random_word(self) -> str:
        """Get a random word from the list."""
        if not self.words:
            return "sound"  # fallback
        return random.choice(self.words)
    
    def get_unique_random_word(self) -> str:
        """Get a random word that hasn't been used yet in this session."""
        if not self.words:
            return "sound"  # fallback
        
        # If we've used all words, reset
        if len(self.used_words) >= len(self.words):
            self.used_words.clear()
        
        # Find an unused word
        available_words = [w for w in self.words if w not in self.used_words]
        if available_words:
            word = random.choice(available_words)
            self.used_words.add(word)
            return word
        
        # Fallback: return any random word
        return random.choice(self.words)
    
    def is_available(self) -> bool:
        """Check if words list is loaded and available."""
        return len(self.words) > 0


# Global instance
_words_manager: Optional[WordsManager] = None

def get_words_manager() -> WordsManager:
    """Get or create the global words manager instance."""
    global _words_manager
    if _words_manager is None:
        _words_manager = WordsManager()
    return _words_manager