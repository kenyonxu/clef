#!/usr/bin/env python3
"""Text2music test: 8-bit style variations."""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

prompts = [
    ("nes", "NES soundtrack, 8-bit console, Famicom, pulse wave, triangle wave, noise channel, dark space battle, tense, dramatic"),
    ("gameboy", "Game Boy, 4-channel, square wave lead, dark, serious, space battle, tense, dramatic"),
    ("fm_synth", "FM synthesis, Sega Genesis, retro video game, dark space battle, tense, dramatic, bass-heavy"),
    ("retro_vgm", "retro video game music, VGM, PSG synth, dark, serious, space battle, tense, driving rhythm"),
]

for label, prompt in prompts:
    print(f"=== {label} ===")
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
        download_audio(result, API, OUT, f"t2m_8bit_{label}")
    else:
        print(f"  Error: {resp.text[:300]}")
    print()

print("Done!")
