#!/usr/bin/env python3
"""Compatibility shim for legacy v2 ingestion runner.

Delegates to the canonical `run_ingestion.py` implementation.
"""
import asyncio

from run_ingestion import main


if __name__ == "__main__":
    asyncio.run(main())
