"""Simple placeholder pipeline for filling themed banks."""

import os

from .config import load_env, load_prompts
from .downloader import download_and_process


def run_pipeline():
    """Download and organize clips for each theme term."""
    load_env()
    prompts = load_prompts()
    clip_ms = int(os.environ['CLIP_SECONDS']) * 1000
    themes = [os.environ[f'THEME{i}'] for i in range(1, 17)]

    for term in themes:
        download_and_process(term, term, clip_ms=clip_ms)

    return {
        'themes': themes,
        'clip_ms': clip_ms,
        'prompts': prompts,
    }


if __name__ == '__main__':
    result = run_pipeline()
    print(result)
