#!/usr/bin/env python3
"""Test ACE-Step cover mode with multipart audio upload."""
import json
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

plan = json.loads(open(".clef-work/plan.json", encoding="utf-8").read())

# Read audio file bytes
ref_path = Path("E:/GitHub/clef-dev/.clef-work/candidates/candidate_3.wav")
audio_bytes = ref_path.read_bytes()
print(f"Audio file: {ref_path.name} ({len(audio_bytes)} bytes)")

# Test 1: Upload via multipart with src_audio field
print("\n=== Test 1: multipart upload with 'src_audio' field ===")
data = {
    "task_type": "cover",
    "prompt": "pastoral folk, warm, violin, moderate tempo, instrumental",
    "lyrics": "[Verse - gentle]\n[Verse - moderately]",
    "bpm": "84",
    "key_scale": "G Major",
    "time_signature": "4",
    "audio_duration": "45.7",
    "audio_cover_strength": "0.7",
    "inference_steps": "20",
}
files = {
    "src_audio": (ref_path.name, audio_bytes, "audio/wav"),
}
resp = requests.post(f"{API}/release_task", data=data, files=files, timeout=60)
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    task_id = resp.json()["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    result = poll_result(task_id, API)
    download_audio(result, API, OUT, "cover_upload_src_audio")
else:
    print(f"  Error: {resp.text[:300]}")

# Test 2: Upload via multipart with ctx_audio field
print("\n=== Test 2: multipart upload with 'ctx_audio' field ===")
files2 = {
    "ctx_audio": (ref_path.name, audio_bytes, "audio/wav"),
}
resp2 = requests.post(f"{API}/release_task", data=data, files=files2, timeout=60)
print(f"  Status: {resp2.status_code}")
if resp2.status_code == 200:
    task_id = resp2.json()["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    result2 = poll_result(task_id, API)
    download_audio(result2, API, OUT, "cover_upload_ctx_audio")
else:
    print(f"  Error: {resp2.text[:300]}")

# Test 3: Try with mp3 from text2music output
print("\n=== Test 3: multipart upload with mp3 via 'src_audio' ===")
mp3_path = Path("E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3")
mp3_bytes = mp3_path.read_bytes()
files3 = {
    "src_audio": (mp3_path.name, mp3_bytes, "audio/mpeg"),
}
resp3 = requests.post(f"{API}/release_task", data=data, files=files3, timeout=60)
print(f"  Status: {resp3.status_code}")
if resp3.status_code == 200:
    task_id = resp3.json()["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    result3 = poll_result(task_id, API)
    download_audio(result3, API, OUT, "cover_upload_mp3")
else:
    print(f"  Error: {resp3.text[:300]}")

print("\nDone!")
