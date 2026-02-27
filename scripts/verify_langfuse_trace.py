#!/usr/bin/env python3
import argparse
import base64
import json
import ssl
import urllib.request
from pathlib import Path


def read_env() -> dict[str, str]:
    env_path = Path("backend/.env") if Path("backend/.env").exists() else Path(".env")
    env: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    env = read_env()
    pk = env.get("LANGFUSE_PUBLIC_KEY", "")
    sk = env.get("LANGFUSE_SECRET_KEY", "")
    base_url = env.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")

    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    ssl_ctx = ssl._create_unverified_context()
    list_req = urllib.request.Request(
        f"{base_url}/api/public/traces?limit={args.limit}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(list_req, timeout=30, context=ssl_ctx) as response:
        traces = json.loads(response.read()).get("data", [])

    matching = []
    for trace in traces:
        metadata = trace.get("metadata") or {}
        if str(metadata.get("session_id")) == args.session_id:
            matching.append(trace)

    selected = None
    if matching:
        selected = max(
            matching,
            key=lambda trace: str(
                trace.get("timestamp")
                or trace.get("createdAt")
                or trace.get("updatedAt")
                or ""
            ),
        )

    if not selected:
        print("TRACE_NOT_FOUND_FOR_SESSION")
        return

    trace_id = selected.get("id")
    detail_req = urllib.request.Request(
        f"{base_url}/api/public/traces/{trace_id}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(detail_req, timeout=30, context=ssl_ctx) as response:
        detail = json.loads(response.read())

    observations = detail.get("observations") or []
    span_names = sorted({(obs.get("name") or "") for obs in observations if isinstance(obs, dict)})

    output = detail.get("output") or {}
    keys = list(output.keys()) if isinstance(output, dict) else []

    print("TRACE_ID", trace_id)
    print("TRACE_NAME", detail.get("name"))
    print("TRACE_METADATA_SESSION", (detail.get("metadata") or {}).get("session_id"))
    print("SPAN_NAMES", ", ".join(span_names))
    print("ROOT_OUTPUT_KEYS", ", ".join(keys))
    print("HAS_TURN", isinstance(output, dict) and ("turn" in output))
    print("HAS_AGENT_OUTCOME", isinstance(output, dict) and ("agent_outcome" in output))
    print("HAS_LEARNING_STATE", isinstance(output, dict) and ("learning_state" in output))
    print("HAS_SIGNALS", isinstance(output, dict) and ("signals" in output))


if __name__ == "__main__":
    main()
