#!/usr/bin/env python3
"""Quick test to find correct cover mode parameter names."""
import requests
import json

API = "http://localhost:8001"

base_params = {
    "task_type": "cover",
    "prompt": "pastoral folk, warm, violin, moderate tempo, instrumental",
    "bpm": 84,
    "key_scale": "G Major",
    "time_signature": "4",
    "audio_duration": 45.7,
    "audio_cover_strength": 0.7,
}

variants = [
    ("src_audio_path", "E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3"),
    ("src_audio", "E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3"),
    ("audio_path", "E:/GitHub/clef-dev/.tmp_acestep/acestep_text2music_output.mp3"),
]

for key, val in variants:
    params = {**base_params, key: val}
    try:
        resp = requests.post(f"{API}/release_task", json=params, timeout=30)
        print(f"[{key}] Status: {resp.status_code}")
        body = resp.text[:400]
        if resp.status_code == 200:
            data = resp.json()
            print(f"  OK! task_id={data.get('data', {}).get('task_id')}")
        else:
            print(f"  Error: {body}")
    except Exception as e:
        print(f"[{key}] Exception: {e}")
    print()
