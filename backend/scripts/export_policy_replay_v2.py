#!/usr/bin/env python3
"""Export Track D policy replay dataset (v2) from tutor turns."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.db.database import async_session_factory
from app.models.session import TutorTurn
from app.services.policy_replay import (
    build_policy_replay_rows,
    export_policy_replay_jsonl,
    summarize_policy_replay,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export policy replay v2 dataset")
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSONL path (e.g. artifacts/policy_replay_v2.jsonl)",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session UUID to export a single session.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum number of turns to export.",
    )
    return parser.parse_args()


async def _load_turns(session_id: str | None, limit: int) -> list[TutorTurn]:
    async with async_session_factory() as db:
        query = select(TutorTurn).order_by(TutorTurn.created_at.asc())
        if session_id:
            query = query.where(TutorTurn.session_id == uuid.UUID(session_id))
        query = query.limit(max(1, limit))
        result = await db.execute(query)
        return list(result.scalars().all())


async def _run() -> None:
    args = _parse_args()
    turns = await _load_turns(args.session_id, args.limit)
    rows = build_policy_replay_rows(turns)
    written = export_policy_replay_jsonl(rows, args.output)
    summary = summarize_policy_replay(rows)

    print(f"exported_rows={written}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_run())
