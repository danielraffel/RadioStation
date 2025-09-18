#!/usr/bin/env python3
"""
Prompt Manager for CLAP Evaluator
Manages evaluation prompts vs blessed final prompts
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def load_sample_json(sample_path: Path) -> Dict:
    """Load a sample JSON file"""
    with open(sample_path, 'r') as f:
        return json.load(f)

def save_sample_json(sample_path: Path, data: Dict):
    """Save a sample JSON file"""
    with open(sample_path, 'w') as f:
        json.dump(data, f, indent=2)

def get_evaluation_prompts(sample_data: Dict) -> List[str]:
    """
    Get prompts for evaluation (can be multiple)
    These are stored in generated_clap_prompts or clap_prompts_v1 field
    """
    return sample_data.get('generated_clap_prompts', []) or sample_data.get('clap_prompts_v1', [])

def get_blessed_prompt(sample_data: Dict) -> Optional[str]:
    """
    Get the blessed/final prompt for production use
    This is stored in final_clap_prompt field
    """
    return sample_data.get('final_clap_prompt')

def set_evaluation_prompts(sample_path: Path, prompts: List[str]):
    """
    Set evaluation prompts for a sample
    These are temporary and used for testing
    """
    data = load_sample_json(sample_path)
    data['clap_prompts_v1'] = prompts
    # Also set best_clap_prompt for compatibility
    if prompts:
        data['best_clap_prompt'] = prompts[0]
    save_sample_json(sample_path, data)
    logger.info(f"Set {len(prompts)} evaluation prompts for {sample_path.name}")

def bless_prompt(sample_path: Path, prompt: str, score: float = None):
    """
    Bless a prompt as the final production prompt
    This is what RadioStation will use
    """
    data = load_sample_json(sample_path)
    data['final_clap_prompt'] = prompt
    if score is not None:
        data['final_clap_score'] = score
    save_sample_json(sample_path, data)
    logger.info(f"Blessed prompt for {sample_path.name}: {prompt[:50]}...")

def clear_blessed_prompt(sample_path: Path):
    """Remove the blessed prompt from a sample"""
    data = load_sample_json(sample_path)
    if 'final_clap_prompt' in data:
        del data['final_clap_prompt']
    if 'final_clap_score' in data:
        del data['final_clap_score']
    save_sample_json(sample_path, data)
    logger.info(f"Cleared blessed prompt for {sample_path.name}")

def get_prompt_status(session_path: Path) -> Dict:
    """
    Get status of prompts for all samples in a session
    Returns counts of samples with evaluation prompts, blessed prompts, etc.
    """
    status = {
        'total_samples': 0,
        'with_evaluation_prompts': 0,
        'with_blessed_prompts': 0,
        'samples': []
    }

    for sample_json in session_path.glob('*.json'):
        if sample_json.name == 'session_metadata.json':
            continue

        data = load_sample_json(sample_json)
        status['total_samples'] += 1

        eval_prompts = get_evaluation_prompts(data)
        blessed_prompt = get_blessed_prompt(data)

        if eval_prompts:
            status['with_evaluation_prompts'] += 1
        if blessed_prompt:
            status['with_blessed_prompts'] += 1

        status['samples'].append({
            'name': sample_json.stem,
            'has_eval_prompts': bool(eval_prompts),
            'num_eval_prompts': len(eval_prompts),
            'has_blessed_prompt': bool(blessed_prompt),
            'blessed_prompt': blessed_prompt[:50] + '...' if blessed_prompt else None
        })

    return status

def bulk_bless_prompts(session_path: Path, prompt_map: Dict[str, str]):
    """
    Bless multiple prompts at once
    prompt_map: {sample_name: prompt_to_bless}
    """
    blessed_count = 0
    for sample_name, prompt in prompt_map.items():
        sample_path = session_path / f"{sample_name}.json"
        if sample_path.exists():
            bless_prompt(sample_path, prompt)
            blessed_count += 1

    logger.info(f"Blessed {blessed_count} prompts in session")
    return blessed_count