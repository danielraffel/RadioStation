"""Improved OpenAI search term expansion for better CLAP scoring."""

import os
import json
from typing import List, Dict

def expand_single_term(word: str, clap_prompt: str, api_key: str) -> List[str]:
    """Expand a single word with CLAP context for better results."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Extract key descriptive words from CLAP prompt
        clap_keywords = []
        if 'quiet' in clap_prompt.lower() or 'soft' in clap_prompt.lower():
            clap_keywords.extend(['soft', 'quiet', 'gentle', 'whisper'])
        if 'loud' in clap_prompt.lower() or 'powerful' in clap_prompt.lower():
            clap_keywords.extend(['loud', 'powerful', 'intense', 'strong'])
        if 'metallic' in clap_prompt.lower():
            clap_keywords.extend(['metal', 'metallic', 'clang', 'ring'])
        if 'smooth' in clap_prompt.lower():
            clap_keywords.extend(['smooth', 'flowing', 'continuous'])
        if 'percussive' in clap_prompt.lower():
            clap_keywords.extend(['drum', 'hit', 'percussion', 'tap'])
        if 'sustained' in clap_prompt.lower():
            clap_keywords.extend(['long', 'sustained', 'drone', 'continuous'])
        
        # More aggressive prompt
        prompt = f"""Create 4 YouTube search queries for the word "{word}".
        
        MANDATORY: Each query MUST include:
        1. The word "{word}"
        2. At least one of these descriptive terms: {', '.join(clap_keywords[:3]) if clap_keywords else 'sound effect, audio, recording'}
        3. YouTube-style terms like: sound, effect, audio, ASMR, compilation, 10 hours
        
        Examples for word "cat" with "soft" context:
        - "cat soft purring ASMR"
        - "gentle cat meow sounds"
        - "quiet cat purr compilation"
        - "soft kitten sounds sleep"
        
        Return ONLY a JSON array of 4 search queries, nothing else.
        Format: ["query1", "query2", "query3", "query4"]"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a search query generator. Return only JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content.strip()
        
        # Try to extract array from JSON object
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                # Find the first array in the dict
                for value in data.values():
                    if isinstance(value, list):
                        return value[:4]
            elif isinstance(data, list):
                return data[:4]
        except:
            pass
            
        # Fallback
        return [f"{word} sound effect", f"{word} audio", f"{word} sounds", f"{word} compilation"]
        
    except Exception as e:
        import sys
        print(f"Error expanding '{word}': {e}", file=sys.stderr)
        return [f"{word} sound", f"{word} audio", f"{word} effect", f"{word} recording"]


def batch_expand_search_terms_v2(themes_config: List[Dict], samples_per_theme: int = 16, 
                                 search_terms_override: Dict[str, List[str]] = None) -> Dict[str, List[str]]:
    """Improved batch expansion with better CLAP alignment."""
    
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    use_expansion = os.environ.get('USE_OPENAI_EXPANSION', '0') == '1'
    
    if not use_expansion or not api_key:
        # No expansion - return original terms
        result = {}
        for theme in themes_config:
            theme_name = theme['name']
            if search_terms_override and theme_name in search_terms_override:
                result[theme_name] = search_terms_override[theme_name][:samples_per_theme]
            else:
                result[theme_name] = [theme['search']] * samples_per_theme
        return result
    
    # Expand each theme's terms
    result = {}
    for theme in themes_config:
        theme_name = theme['name']
        theme_prompt = theme['prompt']
        
        # Get the words to expand
        if search_terms_override and theme_name in search_terms_override:
            words = search_terms_override[theme_name]
        else:
            words = [theme['search']] * samples_per_theme
        
        # Expand each unique word
        expanded_queries = []
        unique_words = list(set(words[:samples_per_theme]))
        
        for word in unique_words:
            expansions = expand_single_term(word, theme_prompt, api_key)
            expanded_queries.extend(expansions)
        
        # Ensure we have enough queries
        while len(expanded_queries) < samples_per_theme:
            expanded_queries.extend(expanded_queries)
        
        result[theme_name] = expanded_queries[:samples_per_theme]
        
        # Log what we got
        import sys
        print(f"Expanded {theme_name}: '{unique_words[0]}' → '{result[theme_name][0]}'", file=sys.stderr)
    
    return result