#!/usr/bin/env python
"""End-to-end demo entry point.

Kept at the repo root for muscle memory; the implementation lives in
`pricecast.cli` so the same code is reachable as `python -m pricecast.cli`
or the installed `pricecast` console script.

    python run_demo.py                          # honest: staleness vs today
    python run_demo.py --as-of per_commodity    # exercise the model on old extracts
    python run_demo.py --reference-date 2026-07-25
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pricecast.cli import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["demo", *argv]
    main(argv)
