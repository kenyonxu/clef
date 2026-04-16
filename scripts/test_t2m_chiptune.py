#!/usr/bin/env python3
"""Text2music test with chiptune battle prompt."""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

print("=== text2music: chiptune battle, 37.8s ===")
data = {
    "task_type": "text2music",
    "prompt": "chiptune, 8-bit, retro game, energetic, battle, fast arpeggios, square wave lead",
    "lyrics": "[Intro - intense]\n[Verse - driving]\n[Chorus - powerful]\n[Outro]",
    "bpm": "120",
    "key_scale": "C Major",
    "time_signature": "4",
    "audio_duration": "37.8",
    "inference_steps": "20",
    "thinking": "true",
}
resp = requests.post(f"{API}/release_task", json=data, timeout=60)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    result = poll_result(resp.json()["data"]["task_id"], API)
    download_audio(result, API, OUT, "t2m_chiptune_battle")
else:
    print(f"Error: {resp.text[:300]}")

print("Done!")
