#!/usr/bin/env python3
"""Cover test: higher strength + style prompt to preserve original character."""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")
ref = Path(".tmp_acestep/SpaceBattle_8bit.wav")
audio_bytes = ref.read_bytes()

# Test 1: strength=1.0, no prompt — maximum structure preservation
print("=== Test 1: strength=1.0, no prompt ===")
data1 = {
    "task_type": "cover",
    "bpm": "120",
    "key_scale": "C Major",
    "time_signature": "4",
    "audio_duration": "37.8",
    "audio_cover_strength": "1.0",
    "inference_steps": "20",
}
files1 = {"src_audio": (ref.name, audio_bytes, "audio/wav")}
resp1 = requests.post(f"{API}/release_task", data=data1, files=files1, timeout=60)
if resp1.status_code == 200:
    result1 = poll_result(resp1.json()["data"]["task_id"], API)
    download_audio(result1, API, OUT, "cover_strength10_noprompt")
else:
    print(f"  Error: {resp1.text[:300]}")

# Test 2: strength=0.9, with style-matching prompt
print("\n=== Test 2: strength=0.9, chiptune battle prompt ===")
data2 = dict(data1)
data2["audio_cover_strength"] = "0.9"
data2["prompt"] = "chiptune, 8-bit, retro game, energetic, battle, fast arpeggios, square wave lead"
data2["lyrics"] = "[Intro - intense]\n[Verse - driving]\n[Chorus - powerful]\n[Outro]"
files2 = {"src_audio": (ref.name, audio_bytes, "audio/wav")}
resp2 = requests.post(f"{API}/release_task", data=data2, files=files2, timeout=60)
if resp2.status_code == 200:
    result2 = poll_result(resp2.json()["data"]["task_id"], API)
    download_audio(result2, API, OUT, "cover_strength09_chiptune")
else:
    print(f"  Error: {resp2.text[:300]}")

# Test 3: strength=1.0, with style-matching prompt
print("\n=== Test 3: strength=1.0, chiptune battle prompt ===")
data3 = dict(data2)
data3["audio_cover_strength"] = "1.0"
files3 = {"src_audio": (ref.name, audio_bytes, "audio/wav")}
resp3 = requests.post(f"{API}/release_task", data=data3, files=files3, timeout=60)
if resp3.status_code == 200:
    result3 = poll_result(resp3.json()["data"]["task_id"], API)
    download_audio(result3, API, OUT, "cover_strength10_chiptune")
else:
    print(f"  Error: {resp3.text[:300]}")

print("\nDone!")
