"""Simple placeholder pipeline for filling themed banks."""

import os
from random import choice
from pathlib import Path

from .config import load_env, load_prompts


def run_pipeline():
    """Run a dummy pipeline that fills banks with simulated samples."""
    load_env()
    prompts = load_prompts()
    clip_seconds = int(os.environ['CLIP_SECONDS'])
    samples_per_bank = int(os.environ['SAMPLES_PER_BANK'])
    num_banks = int(os.environ['NUM_BANKS'])
    max_retries = int(os.environ['MAX_RETRIES_PER_THEME'])

    counts = [0] * num_banks
    retries = 0
    downloads = 0

    while min(counts) < samples_per_bank:
        if max_retries > 0 and retries >= max_retries:
            break
        downloads += 1
        # In real code, download and score sample with CLAP. Here, randomly assign to a theme or None.
        assigned = choice(list(range(num_banks)) + [None])
        if assigned is None:
            retries += 1
            continue
        counts[assigned] += 1

    return {
        'counts': counts,
        'downloads': downloads,
        'retries': retries,
        'complete': min(counts) >= samples_per_bank,
        'clip_seconds': clip_seconds,
        'prompts': prompts,
    }


if __name__ == '__main__':
    result = run_pipeline()
    print(result)
