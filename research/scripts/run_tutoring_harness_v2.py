#!/usr/bin/env python3
"""Run tutoring harness v2 and export reproducible report artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tutoring_harness import (
    TutoringHarnessV2,
    build_markdown_report,
    load_scenarios_from_json,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run tutoring harness v2")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--resource-id",
        default=None,
        help="Optional resource UUID. If omitted, first processed resource is used.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/tutoring_harness_v2",
        help="Output directory for run artifacts.",
    )
    parser.add_argument(
        "--docs-report",
        default="docs/TUTORING-HARNESS-V2-REPORT.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--topics",
        nargs="*",
        default=None,
        help="Optional selected topics passed to session creation.",
    )
    parser.add_argument(
        "--scenarios-file",
        default=None,
        help="Optional JSON file defining scenarios (see app.services.tutoring_harness.load_scenarios_from_json).",
    )
    parser.add_argument(
        "--tutoring-model",
        default=None,
        help="Optional override for tutoring model (sent as X-LLM-Model-Tutoring).",
    )
    parser.add_argument(
        "--evaluation-model",
        default=None,
        help="Optional override for evaluation/safety model (sent as X-LLM-Model-Evaluation).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    harness = TutoringHarnessV2(
        base_url=args.base_url,
        output_dir=args.output_dir,
        tutoring_model=args.tutoring_model,
        evaluation_model=args.evaluation_model,
    )
    scenarios = load_scenarios_from_json(args.scenarios_file) if args.scenarios_file else None
    summary = harness.run(
        resource_id=args.resource_id,
        selected_topics=args.topics,
        scenarios=scenarios,
    )

    run_dir = Path(summary["run_dir"])
    markdown = build_markdown_report(summary)
    docs_report_path = Path(args.docs_report)
    docs_report_path.parent.mkdir(parents=True, exist_ok=True)
    docs_report_path.write_text(markdown + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"report_markdown={docs_report_path}")
    print(f"artifacts_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())