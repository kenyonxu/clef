#!/usr/bin/env python3
"""Cover mode e2e test for ACE-Step prototype."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from acestep_prototype import (
    build_acestep_params, submit_task, poll_result, download_audio,
)

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

plan = json.loads(open(".clef-work/plan.json", encoding="utf-8").read())

# Test 1: Cover with text2music output as reference
print("=== Cover Test 1: text2music output as reference (strength=0.7) ===")
params1 = build_acestep_params(plan, "cover",
    "E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3")
print(f"  src_audio: {params1.get('src_audio')}")
print(f"  prompt: {params1.get('prompt')}")
t1 = submit_task(params1, API)
r1 = poll_result(t1, API)
download_audio(r1, API, OUT, "cover_text2music_ref")
print()

# Test 2: Cover with clef candidate_2.wav as reference
print("=== Cover Test 2: clef candidate_2.wav as reference (strength=0.5) ===")
params2 = build_acestep_params(plan, "cover",
    "E:/GitHub/clef-dev/.clef-work/candidates/candidate_2.wav")
params2["audio_cover_strength"] = 0.5
print(f"  src_audio: {params2.get('src_audio')}")
t2 = submit_task(params2, API)
r2 = poll_result(t2, API)
download_audio(r2, API, OUT, "cover_clef_candidate2")
print()

print("Done!")
