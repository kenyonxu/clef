"""End-to-end test: submit compose, poll status, collect results."""
import json
import sys
import time

import requests

BASE = "http://localhost:8900"

PROMPT = (
    "RPG village theme, C major, 4/4, 80BPM, ABA form, ~45s. "
    "Orchestral: flute melody, strings harmony, cello bass, timpani. "
    "Warm and peaceful atmosphere."
)


def main():
    # Submit
    r = requests.post(f"{BASE}/compose", json={"prompt": PROMPT})
    print(f"POST /compose -> {r.status_code}")
    if r.status_code != 200:
        print(r.text)
        return
    data = r.json()
    sid = data["session_id"]
    print(f"Session: {sid}")

    # Poll until awaiting_confirm, done, or failed
    for i in range(200):
        time.sleep(3)
        r = requests.get(f"{BASE}/status/{sid}")
        s = r.json()
        status = s.get("status", "?")
        phase = s.get("current_phase", "?")
        error = s.get("error")

        if i % 5 == 0 or status != "created":
            print(f"[{i*3}s] status={status} phase={phase}")

        if error:
            print(f"ERROR: {error}")
            return

        if status == "awaiting_confirm":
            cd = s.get("confirmation_data", {})
            cp = cd.get("phase", "?")
            print(f"\n=== AWAITING CONFIRM at phase: {cp} ===")
            if cd.get("summary"):
                print(f"Summary: {json.dumps(cd['summary'], ensure_ascii=False)}")
            if cd.get("plan"):
                plan = cd["plan"]
                print(f"Plan: {plan.get('title')} key={plan.get('key')} bpm={plan.get('bpm')} bars={plan.get('total_bars')}")

            # Auto-continue through all phases
            print("Auto-continuing...")
            r = requests.post(f"{BASE}/confirm/{sid}", json={"action": "continue"})
            print(f"  confirm -> {r.status_code}")
            continue

        if status == "done":
            print(f"\n=== SESSION DONE ===")
            print(f"Output files: {s.get('output_files', [])}")
            print(f"Iterations: {s.get('iteration_count', 0)}")
            break

        if status in ("failed", "cancelled"):
            print(f"\n=== SESSION {status.upper()} ===")
            print(f"Error: {error}")
            break

    print("\nDone.")


if __name__ == "__main__":
    main()
