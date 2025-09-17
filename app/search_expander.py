"""Optional OpenAI-powered search term expansion."""

import os
import json
from typing import List, Dict

def batch_expand_search_terms(themes_config: List[Dict[str, any]], samples_per_theme: int = 16, search_terms_override: Dict[str, List[str]] = None) -> Dict[str, List[str]]:
    """
    Batch expand search terms for all themes at once.
    Returns a dict mapping theme_name -> list of YouTube-title-style search queries.
    
    Args:
        themes_config: List of dicts with 'name', 'search', and 'prompt' keys
        samples_per_theme: Number of unique search queries to generate per theme
    """
    # Check if expansion is enabled
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    use_expansion = os.environ.get('USE_OPENAI_EXPANSION', '0') == '1'
    
    # If not enabled, return original search terms repeated
    if not use_expansion or not api_key:
        return {theme['name']: [theme['search']] * samples_per_theme for theme in themes_config}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Build a single prompt for all themes
        system_prompt = """You are a JSON API that expands search terms into YouTube queries for audio sampling.

        CRITICAL: For EACH search term, create variations that combine:
        - The original word/term (e.g., "dog" or "phasianoid") 
        - The acoustic qualities from the CLAP prompt
        
        Example:
        Input: search_term="bell", clap_prompt="Metallic, ringing, resonant"
        Output: ["bell ringing sound effect", "metallic bell chime compilation", "resonant church bell sounds"]
        
        NEVER return the original word unchanged. ALWAYS add descriptive terms.
        
        Return ONLY valid JSON matching the exact format requested."""
        
        # Create the batch request
        themes_request = {}
        for theme in themes_config:
            theme_name = theme['name']
            # Use override search terms if provided (for word list mode)
            if search_terms_override and theme_name in search_terms_override:
                search_list = search_terms_override[theme_name]
                # For word list mode, each word needs to be expanded
                # Convert to a list of unique terms to expand
                unique_terms = list(set(search_list[:samples_per_theme]))
                themes_request[theme_name] = {
                    "search_terms": unique_terms,
                    "clap_prompt": theme['prompt'],
                    "num_queries": samples_per_theme  # Total queries wanted
                }
            else:
                themes_request[theme_name] = {
                    "search_terms": [theme['search']],  # Make it consistent format
                    "clap_prompt": theme['prompt'],  
                    "num_queries": samples_per_theme
                }
        
        # Create exact expected output structure
        expected_output = {theme_name: ["..."] * themes_request[theme_name]["num_queries"] 
                          for theme_name in themes_request}
        
        user_prompt = f"""Input:
{json.dumps(themes_request, indent=2)}

Output (exact format, replace "..." with actual queries):
{json.dumps(expected_output, indent=2)}"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,  # Lower temperature for more consistent formatting
                max_tokens=3000,  # More tokens for 16 themes * 24 queries
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse the JSON response (should be clean JSON with response_format)
            try:
                expanded = json.loads(content)
            except json.JSONDecodeError as e:
                import sys
                print(f"OpenAI returned invalid JSON: {e}", file=sys.stderr)
                print(f"Response content: {content[:500]}", file=sys.stderr)
                raise
            
            # Log successful expansion for debugging
            import sys
            print(f"OpenAI successfully expanded {len(expanded)} themes", file=sys.stderr)
            
            # Validate and ensure we have the right number of queries
            result = {}
            for theme in themes_config:
                theme_name = theme['name']
                if theme_name in expanded and isinstance(expanded[theme_name], list):
                    queries = expanded[theme_name]
                    # Log sample to verify expansion worked
                    if queries and queries[0] != "...":
                        print(f"Sample for {theme_name}: {queries[0][:60]}", file=sys.stderr)
                    # Pad or trim to samples_per_theme
                    if len(queries) < samples_per_theme:
                        # Repeat queries if we don't have enough
                        queries = queries * (samples_per_theme // len(queries) + 1)
                    result[theme_name] = queries[:samples_per_theme]
                else:
                    # Fallback to original search term
                    print(f"Warning: No expansion for {theme_name}, using fallback", file=sys.stderr)
                    result[theme_name] = [theme['search']] * samples_per_theme
            
            return result
            
        except Exception as e:
            import sys
            print(f"OpenAI batch expansion error: {e}", file=sys.stderr)
            # Fallback - use override terms if provided, otherwise original
            result = {}
            for theme in themes_config:
                theme_name = theme['name']
                if search_terms_override and theme_name in search_terms_override:
                    result[theme_name] = search_terms_override[theme_name][:samples_per_theme]
                else:
                    result[theme_name] = [theme['search']] * samples_per_theme
            return result
    
    except Exception as e:
        import sys  
        print(f"OpenAI import error: {e}", file=sys.stderr)
        return {theme['name']: [theme['search']] * samples_per_theme for theme in themes_config}


def expand_search_terms(theme_name: str, search_term: str, prompt: str, unique: bool = True) -> List[str]:
    """
    Legacy single-term expansion for backward compatibility.
    Now just returns the original term.
    """
    return [search_term]


def is_expansion_enabled() -> bool:
    """Check if OpenAI expansion is enabled and configured.
    
    API key can come from:
    1. Shell environment (export OPENAI_API_KEY in ~/.zshrc)
    2. .env file in project
    """
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    use_expansion = os.environ.get('USE_OPENAI_EXPANSION', '0') == '1'
    return bool(use_expansion and api_key)