#!/usr/bin/env python3
"""
CLAP Prompt Generator using OpenAI
Generates optimized CLAP prompts based on YouTube metadata (title, description, tags)
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def load_evaluator_config() -> Dict:
    """Load evaluator configuration including OpenAI settings"""
    config_path = Path(__file__).parent / 'evaluator_config.json'

    # Default configuration
    default_config = {
        'ai_enabled': False,
        'openai_api_key': os.environ.get('OPENAI_API_KEY', ''),
        'system_prompt': DEFAULT_SYSTEM_PROMPT,
        'batch_size': 10,
        'use_tags': True,
        'use_description': True,
        'max_prompt_words': 10,
        'model': 'gpt-4o-mini',
        'temperature': 0.7
    }

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
        except Exception as e:
            logger.error(f"Error loading config: {e}")

    return default_config


DEFAULT_SYSTEM_PROMPT = """You are a CLAP audio prompt expert. Generate 3 specific, descriptive prompts for audio classification.

For each sample, you receive:
- sample_id: Unique identifier (MUST be preserved in output)
- title: YouTube video title
- description: Video description (truncated)
- tags: YouTube tags array
- search_term: Original search used
- theme: Target audio theme

Rules:
1. Use literal audio descriptions (not metaphorical)
2. Keep prompts 5-10 words maximum
3. Focus on acoustic/sonic properties
4. Incorporate relevant tags when available
5. Return EXACT sample_id to maintain mapping
6. Describe what you would HEAR, not see

Good examples:
- "metallic clang ringing echo sound"
- "soft whisper gentle voice speaking"
- "loud explosive boom crash noise"

Bad examples:
- "the sound of happiness" (too metaphorical)
- "a beautiful symphony of nature's orchestra playing" (too long)
- "metal" (too short, not descriptive)

Return JSON with exact structure shown in examples."""


def generate_prompts_batch(samples_metadata: List[Dict], config: Optional[Dict] = None) -> Dict[str, List[str]]:
    """
    Generate prompts for multiple samples with guaranteed mapping.

    Args:
        samples_metadata: List of sample metadata dictionaries
        config: Optional configuration override

    Returns:
        Dict mapping sample_id -> [prompt1, prompt2, prompt3]
        Empty dict if AI is disabled or on error
    """
    if config is None:
        config = load_evaluator_config()

    if not config.get('ai_enabled'):
        logger.info("AI prompt generation is disabled")
        return {}

    api_key = config.get('openai_api_key', '').strip()
    if not api_key:
        logger.warning("No OpenAI API key configured")
        return {}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except ImportError:
        logger.error("OpenAI library not installed. Run: pip install openai")
        return {}
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return {}

    # Build batch request with explicit IDs
    batch_request = []
    for sample in samples_metadata:
        # Extract sample ID from path or use provided ID
        if 'final_path' in sample:
            sample_id = Path(sample['final_path']).stem  # e.g., "Metallic_01"
        elif 'sample_id' in sample:
            sample_id = sample['sample_id']
        else:
            logger.warning(f"Sample missing ID, skipping: {sample}")
            continue

        # Prepare metadata for prompt generation
        request_item = {
            'sample_id': sample_id,
            'title': sample.get('title', '')[:100],  # Limit length
            'search_term': sample.get('search_term', ''),
            'theme': sample.get('theme_name', '')
        }

        # Add optional fields based on config
        if config.get('use_description'):
            request_item['description'] = sample.get('description', '')[:200]

        if config.get('use_tags'):
            tags = sample.get('tags', [])
            if tags:
                request_item['tags'] = tags[:10]  # Top 10 tags

        batch_request.append(request_item)

    if not batch_request:
        logger.warning("No valid samples to process")
        return {}

    # Create the prompt for OpenAI
    user_prompt = f"""Generate CLAP prompts for these {len(batch_request)} audio samples.

Input samples:
{json.dumps(batch_request, indent=2)}

Return a JSON object with this EXACT structure:
{{
  "prompts": [
    {{
      "sample_id": "exact_id_from_input",
      "generated": ["prompt1", "prompt2", "prompt3"]
    }},
    ...
  ]
}}

CRITICAL: Each sample_id in output MUST match exactly one from the input."""

    try:
        # Make API request
        response = client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": config.get('system_prompt', DEFAULT_SYSTEM_PROMPT)},
                {"role": "user", "content": user_prompt}
            ],
            temperature=config.get('temperature', 0.7),
            max_tokens=500 * len(batch_request),  # ~500 tokens per sample
            response_format={"type": "json_object"}
        )

        # Parse response
        content = response.choices[0].message.content.strip()
        result = json.loads(content)

        # Validate and extract prompts with guaranteed mapping
        output = {}

        # Handle different response structures
        if 'prompts' in result:
            prompt_list = result['prompts']
        elif isinstance(result, list):
            prompt_list = result
        else:
            logger.error(f"Unexpected response structure: {result}")
            return {}

        # Map responses to sample IDs
        for item in prompt_list:
            if 'sample_id' not in item:
                logger.warning(f"Missing sample_id in response item: {item}")
                continue

            sample_id = item['sample_id']
            prompts = item.get('generated', [])

            if not prompts:
                logger.warning(f"No prompts generated for {sample_id}")
                continue

            # Ensure we have exactly 3 prompts
            if len(prompts) < 3:
                # Pad with variations
                while len(prompts) < 3:
                    prompts.append(prompts[0] if prompts else f"{sample_id} sound")
            elif len(prompts) > 3:
                prompts = prompts[:3]

            output[sample_id] = prompts

        # Verify all inputs have outputs
        input_ids = {item['sample_id'] for item in batch_request}
        output_ids = set(output.keys())
        missing = input_ids - output_ids

        if missing:
            logger.warning(f"Missing prompts for samples: {missing}")
            # Generate fallback prompts for missing samples
            for sample_id in missing:
                # Find the original sample data
                sample_data = next((s for s in batch_request if s['sample_id'] == sample_id), None)
                if sample_data:
                    theme = sample_data.get('theme', 'audio')
                    output[sample_id] = [
                        f"{theme.lower()} sound effect",
                        f"{theme.lower()} audio sample",
                        f"{theme.lower()} noise recording"
                    ]

        logger.info(f"Successfully generated prompts for {len(output)} samples")
        return output

    except Exception as e:
        logger.error(f"Error generating prompts: {e}")
        return {}


def save_prompts_to_samples(session_path: Path, prompts: Dict[str, List[str]]) -> int:
    """
    Save generated prompts back to individual sample JSON files.

    Args:
        session_path: Path to session directory
        prompts: Dict mapping sample_id -> [prompts]

    Returns:
        Number of files updated
    """
    updated = 0
    themes_dir = session_path / 'themes'

    if not themes_dir.exists():
        logger.error(f"Themes directory not found: {themes_dir}")
        return 0

    for theme_dir in themes_dir.iterdir():
        if not theme_dir.is_dir():
            continue

        for json_file in theme_dir.glob('*.json'):
            sample_id = json_file.stem

            if sample_id not in prompts:
                continue

            try:
                # Load existing JSON
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Add generated prompts
                data['generated_clap_prompts'] = prompts[sample_id]
                data['prompt_generation_timestamp'] = datetime.now().isoformat()

                # Set the best prompt (first one by default)
                if prompts[sample_id]:
                    data['best_clap_prompt'] = prompts[sample_id][0]

                # Save back
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)

                updated += 1
                logger.debug(f"Updated {json_file.name} with prompts")

            except Exception as e:
                logger.error(f"Error updating {json_file}: {e}")

    logger.info(f"Updated {updated} sample files with generated prompts")
    return updated


def load_session_samples(session_path: Path) -> List[Dict]:
    """
    Load all sample JSON files from a session.

    Args:
        session_path: Path to session directory

    Returns:
        List of sample metadata dictionaries
    """
    samples = []
    themes_dir = session_path / 'themes'

    if not themes_dir.exists():
        logger.error(f"Themes directory not found: {themes_dir}")
        return samples

    for theme_dir in themes_dir.iterdir():
        if not theme_dir.is_dir():
            continue

        for json_file in theme_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    # Ensure sample_id is set
                    data['sample_id'] = json_file.stem
                    samples.append(data)
            except Exception as e:
                logger.error(f"Error loading {json_file}: {e}")

    return samples


def generate_prompts_for_session(session_path: Path, config: Optional[Dict] = None) -> Dict[str, List[str]]:
    """
    Generate prompts for all samples in a session.

    Args:
        session_path: Path to session directory
        config: Optional configuration override

    Returns:
        Dict mapping sample_id -> [prompts]
    """
    if config is None:
        config = load_evaluator_config()

    # Load all samples
    samples = load_session_samples(session_path)

    if not samples:
        logger.warning(f"No samples found in session: {session_path}")
        return {}

    logger.info(f"Processing {len(samples)} samples from session {session_path.name}")

    # Process in batches
    batch_size = config.get('batch_size', 10)
    all_prompts = {}

    for i in range(0, len(samples), batch_size):
        batch = samples[i:i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1} ({len(batch)} samples)")

        batch_prompts = generate_prompts_batch(batch, config)
        all_prompts.update(batch_prompts)

    return all_prompts


if __name__ == '__main__':
    # Test the generator
    import sys

    if len(sys.argv) > 1:
        session_path = Path(sys.argv[1])
        if session_path.exists():
            print(f"Generating prompts for session: {session_path}")

            # Generate prompts
            prompts = generate_prompts_for_session(session_path)

            if prompts:
                print(f"Generated prompts for {len(prompts)} samples")

                # Save to files
                updated = save_prompts_to_samples(session_path, prompts)
                print(f"Updated {updated} sample files")

                # Show sample output
                for sample_id, prompt_list in list(prompts.items())[:3]:
                    print(f"\n{sample_id}:")
                    for p in prompt_list:
                        print(f"  - {p}")
            else:
                print("No prompts generated. Check configuration and logs.")
        else:
            print(f"Session path not found: {session_path}")
    else:
        print("Usage: python clap_prompt_generator.py <session_path>")
        print("\nExample:")
        print("  python clap_prompt_generator.py ../../wavs/sessions/20250917_193013_ix78")