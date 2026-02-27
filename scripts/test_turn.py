#!/usr/bin/env python3
"""Send a tutoring turn and print compact diagnostics."""
import json
import sys
import urllib.request

BASE = "http://localhost:8000/api/v1"

def send_turn(session_id: str, message: str):
    payload = json.dumps({"session_id": session_id, "message": message}).encode()
    req = urllib.request.Request(
        f"{BASE}/tutor/turn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        d = json.loads(resp.read())

    print(f"STEP: {d.get('current_step','?')} ({d.get('current_step_index','?')}) | "
          f"TRANSITION: {d.get('step_transition','?')} | "
          f"OBJ: {d.get('objective_title','?')[:50]}")
    print(f"FOCUS: {d.get('focus_concepts',[])} | AWAITING_EVAL: {d.get('awaiting_evaluation',False)}")

    resp_text = d.get("response", "")
    canned = "I want to keep this accurate" in resp_text
    print(f"TUTOR: {resp_text[:500]}")
    print(f"CANNED: {canned} | COMPLETE: {d.get('session_complete', False)}")

    m = d.get("mastery_update") or {}
    if m:
        print(f"MASTERY_DELTA: {m}")
    print("---")
    return d


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 test_turn.py <session_id> <message>")
        sys.exit(1)
    send_turn(sys.argv[1], sys.argv[2])
