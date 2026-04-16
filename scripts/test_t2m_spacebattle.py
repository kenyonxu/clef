#!/usr/bin/env python3
"""Text2music test: space battle variations with different moods."""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

prompts = [
    ("serious", "8-bit chiptune, dark, serious, space battle, tense, dramatic, heavy bass, rapid arpeggios"),
    ("epic", "8-bit chiptune, epic space battle, ominous, intense, dramatic, minor key, driving rhythm"),
    ("dark", "chiptune, dark sci-fi, menacing, tension, space combat, minor key, aggressive, square wave bass"),
]

for label, prompt in prompts:
    print(f"=== text2music: {label} ===")
    data = {
        "task_type": "text2music",
        "prompt": prompt,
        "lyrics": "[Intro - ominous]\n[Verse - building tension]\n[Chorus - intense battle]\n[Bridge - dramatic]\n[Outro]",
        "bpm": "130",
        "key_scale": "C minor",
        "time_signature": "4",
        "audio_duration": "37.8",
        "inference_steps": "20",
        "thinking": "true",
    }
    resp = requests.post(f"{API}/release_task", json=data, timeout=60)
    if resp.status_code == 200:
        result = poll_result(resp.json()["data"]["task_id"], API)
        download_audio(result, API, OUT, f"t2m_spacebattle_{label}")
    else:
        print(f"  Error: {resp.text[:300]}")
    print()

print("Done!")
