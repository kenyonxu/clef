#!/usr/bin/env python3
"""Test cover mode with minimal/no prompt."""
import json
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

# Use text2music output as reference (better quality than clef candidate)
ref_path = Path("E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3")
audio_bytes = ref_path.read_bytes()

# Test 1: No prompt at all, just src_audio
print("=== Test 1: cover with NO prompt ===")
data1 = {
    "task_type": "cover",
    "bpm": "84",
    "key_scale": "G Major",
    "time_signature": "4",
    "audio_duration": "45.7",
    "audio_cover_strength": "0.7",
    "inference_steps": "20",
}
files1 = {"src_audio": (ref_path.name, audio_bytes, "audio/mpeg")}
resp1 = requests.post(f"{API}/release_task", data=data1, files=files1, timeout=60)
print(f"  Status: {resp1.status_code}")
if resp1.status_code == 200:
    result1 = poll_result(resp1.json()["data"]["task_id"], API)
    download_audio(result1, API, OUT, "cover_noprompt")
else:
    print(f"  Error: {resp1.text[:300]}")

# Test 2: Minimal prompt - just "instrumental"
print("\n=== Test 2: cover with minimal prompt 'instrumental' ===")
data2 = dict(data1)
data2["prompt"] = "instrumental"
files2 = {"src_audio": (ref_path.name, audio_bytes, "audio/mpeg")}
resp2 = requests.post(f"{API}/release_task", data=data2, files=files2, timeout=60)
print(f"  Status: {resp2.status_code}")
if resp2.status_code == 200:
    result2 = poll_result(resp2.json()["data"]["task_id"], API)
    download_audio(result2, API, OUT, "cover_minimal_prompt")
else:
    print(f"  Error: {resp2.text[:300]}")

# Test 3: Style transfer - same structure but different style
print("\n=== Test 3: cover with style transfer prompt ===")
data3 = dict(data1)
data3["prompt"] = "jazz, piano trio, smooth, relaxing, late night"
data3["lyrics"] = "[Intro - gentle]\n[Verse - smooth]\n[Outro - fade out]"
files3 = {"src_audio": (ref_path.name, audio_bytes, "audio/mpeg")}
resp3 = requests.post(f"{API}/release_task", data=data3, files=files3, timeout=60)
print(f"  Status: {resp3.status_code}")
if resp3.status_code == 200:
    result3 = poll_result(resp3.json()["data"]["task_id"], API)
    download_audio(result3, API, OUT, "cover_jazz_transfer")
else:
    print(f"  Error: {resp3.text[:300]}")

print("\nDone!")
