#!/usr/bin/env python3
"""Benchmark tutoring harness v2 across multiple model IDs.

This runs the existing HTTP-based harness repeatedly, passing optional
per-request model override headers. It produces a combined JSON + Markdown
summary so you can compare regressions after prompt/runtime changes or
across candidate models.

Prereqs:
- Backend running (default: http://localhost:8000)
- If using model overrides, set ALLOW_LLM_MODEL_OVERRIDE_HEADERS=true in backend env
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tutoring_harness import (
    TutoringHarnessV2,
    load_scenarios_from_json,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark tutoring harness v2 across models")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--resource-id", default=None)
    p.add_argument("--topics", nargs="*", default=None)
    p.add_argument(
        "--tutoring-models",
        nargs="+",
        required=True,
        help="One or more tutoring model IDs to benchmark.",
    )
    p.add_argument(
        "--evaluation-model",
        default=None,
        help="Optional evaluation/safety model override.",
    )
    p.add_argument(
        "--scenarios-file",
        default=None,
        help="Optional JSON scenario file (same format as run_tutoring_harness_v2.py).",
    )
    p.add_argument(
        "--output-dir",
        default="artifacts/tutoring_harness_v2",
        help="Directory where each harness run writes artifacts.",
    )
    p.add_argument(
        "--combined-report-dir",
        default="artifacts/benchmarks",
        help="Directory for combined benchmark outputs.",
    )
    return p.parse_args()


def _build_markdown_matrix(results: list[dict]) -> str:
    scenario_keys: list[str] = []
    if results:
        scenario_keys = [s.get("scenario_key") for s in results[0].get("scenarios", [])]
        scenario_keys = [k for k in scenario_keys if k]

    lines: list[str] = []
    lines.append("# Tutoring Harness v2 Benchmark")
    lines.append("")
    lines.append("| Tutoring Model | Eval Model | Overall Pass | " + " | ".join([f"{k} pass" for k in scenario_keys]) + " |")
    lines.append("| --- | --- | --- | " + " | ".join(["---" for _ in scenario_keys]) + " |")

    for r in results:
        overrides = r.get("model_overrides") or {}
        tutoring_model = overrides.get("tutoring") or "(default)"
        eval_model = overrides.get("evaluation") or "(default)"
        overall = "PASS" if r.get("overall_pass") else "FAIL"

        scenario_map = {s.get("scenario_key"): s for s in (r.get("scenarios") or [])}
        cells = []
        for key in scenario_keys:
            s = scenario_map.get(key) or {}
            cells.append("PASS" if s.get("pass_fail") else "FAIL")

        lines.append(
            "| {tutor} | {eval} | {overall} | {cells} |".format(
                tutor=tutoring_model,
                eval=eval_model,
                overall=overall,
                cells=" | ".join(cells),
            )
        )

    lines.append("")
    lines.append("Notes:")
    lines.append("- Each row is a full harness run with its own artifacts directory.")
    lines.append("- Use the per-run summary.json files to inspect rubric score deltas.")
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    scenarios = load_scenarios_from_json(args.scenarios_file) if args.scenarios_file else None

    started_at = datetime.now(timezone.utc)
    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    combined_dir = Path(args.combined_report_dir) / f"harness_benchmark_{stamp}"
    combined_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for tutoring_model in args.tutoring_models:
        harness = TutoringHarnessV2(
            base_url=args.base_url,
            output_dir=args.output_dir,
            tutoring_model=tutoring_model,
            evaluation_model=args.evaluation_model,
        )
        summary = harness.run(
            resource_id=args.resource_id,
            selected_topics=args.topics,
            scenarios=scenarios,
        )
        results.append(summary)

    combined = {
        "started_at": started_at.isoformat(),
        "base_url": args.base_url,
        "resource_id": args.resource_id,
        "topics": args.topics,
        "scenarios_file": args.scenarios_file,
        "results": results,
    }

    (combined_dir / "combined.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    markdown = _build_markdown_matrix(results)
    (combined_dir / "combined.md").write_text(markdown + "\n", encoding="utf-8")

    print(json.dumps({"combined_dir": str(combined_dir)}, indent=2))
    print(f"combined_markdown={combined_dir / 'combined.md'}")
    print(f"combined_json={combined_dir / 'combined.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())