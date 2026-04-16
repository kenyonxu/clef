#!/usr/bin/env python3
"""Cover test: SpaceBattle_8bit MIDI-rendered WAV, no prompt."""
import sys
import wave
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import poll_result, download_audio

API = "http://localhost:8001"
OUT = Path(".tmp_acestep")

ref = Path(".tmp_acestep/SpaceBattle_8bit.wav")
w = wave.open(str(ref), "rb")
dur = w.getnframes() / w.getframerate()
print(f"SpaceBattle_8bit.wav: {dur:.1f}s, {w.getnchannels()}ch, {w.getframerate()}Hz")
w.close()

audio_bytes = ref.read_bytes()

print("=== Cover: SpaceBattle_8bit.wav, no prompt, strength=0.7 ===")
data = {
    "task_type": "cover",
    "bpm": "120",
    "key_scale": "C Major",
    "time_signature": "4",
    "audio_duration": str(dur),
    "audio_cover_strength": "0.7",
    "inference_steps": "20",
}
files = {"src_audio": (ref.name, audio_bytes, "audio/wav")}
resp = requests.post(f"{API}/release_task", data=data, files=files, timeout=60)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    result = poll_result(resp.json()["data"]["task_id"], API)
    download_audio(result, API, OUT, "cover_spacebattle_noprompt")
else:
    print(f"Error: {resp.text[:300]}")

print("Done!")
