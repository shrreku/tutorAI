#!/usr/bin/env python3
"""Compatibility wrapper for the research replay exporter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.scripts.export_policy_replay_v2 import main


if __name__ == "__main__":
    raise SystemExit(main())
