#!/usr/bin/env python3
"""Compatibility wrapper for the research harness runner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.scripts.run_tutoring_harness_v2 import main


if __name__ == "__main__":
    raise SystemExit(main())
