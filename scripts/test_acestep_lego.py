#!/usr/bin/env python3
"""ACE-Step 1.5 Lego/Extract test script.

Validates the turbo-then-base workflow:
  Step 1: xl-turbo text2music → backing track
  Step 2: xl-base lego → add tracks on top
  Step 3: xl-base extract → separate stems from mix

Requires ACE-Step API server running at localhost:8001 with XL models loaded.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# Reuse API client from acestep_prototype
sys.path.insert(0, str(Path(__file__).parent))
from acestep_prototype import (
    build_acestep_params,
    check_server_health,
    download_audio,
    poll_result,
    _build_prompt,
    _build_lyrics,
)

API_URL = "http://localhost:8001"
XL_TURBO = "acestep-v15-xl-turbo"
XL_BASE = "acestep-v15-xl-base"

TRACK_NAMES = [
    "woodwinds", "brass", "fx", "synth", "strings", "percussion",
    "keyboard", "guitar", "bass", "drums", "backing_vocals", "vocals",
]

LEGO_INSTRUCTION = "Generate the {track_name} track based on the audio context:"
EXTRACT_INSTRUCTION = "Extract the {track_name} track from the audio:"


def submit_task_json(params: dict, api_url: str = API_URL) -> str:
    """Submit a JSON task. Returns task_id."""
    resp = requests.post(f"{api_url}/release_task", json=params, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"API error: {data.get('error')}")
    task_id = data["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    return task_id


def submit_task_multipart(params: dict, src_audio_path: Path, api_url: str = API_URL) -> str:
    """Submit a multipart task with audio file upload. Returns task_id."""
    audio_bytes = src_audio_path.read_bytes()
    mime = "audio/wav" if src_audio_path.suffix == ".wav" else "audio/mpeg"
    form_data = {k: str(v) for k, v in params.items()}
    form_data.pop("src_audio", None)
    files = {"src_audio": (src_audio_path.name, audio_bytes, mime)}
    resp = requests.post(f"{api_url}/release_task", data=form_data, files=files, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"API error: {data.get('error')}")
    task_id = data["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    return task_id


def run_and_download(task_id: str, api_url: str, output_dir: Path, prefix: str,
                     timeout: int = 300) -> Path:
    """Poll result and download audio."""
    result = poll_result(task_id, api_url, timeout=timeout, interval=5)
    return download_audio(result, api_url, output_dir, prefix)


# --- Step 1: text2music with xl-turbo ---

def step1_text2music(plan: dict, output_dir: Path) -> Path:
    """Generate backing track with xl-turbo."""
    print("\n" + "=" * 60)
    print("STEP 1: text2music (xl-turbo, 8 steps)")
    print("=" * 60)

    params = build_acestep_params(plan, "text2music", None)
    params["model"] = XL_TURBO
    params["inference_steps"] = 8
    params["audio_duration"] = 22.9  # Shorter for faster test

    print(f"  Params: model={params['model']}, steps={params['inference_steps']}, "
          f"duration={params['audio_duration']}s")
    print(f"  Prompt: {params['prompt'][:100]}...")

    task_id = submit_task_json(params)
    return run_and_download(task_id, API_URL, output_dir, "step1_backing", timeout=120)


# --- Step 2: lego with xl-base ---

def step2_lego(src_audio: Path, track_names: list[str],
               prompt: str = "", plan: dict | None = None,
               output_dir: Path | None = None) -> list[Path]:
    """Add tracks via lego on top of backing track."""
    print("\n" + "=" * 60)
    print("STEP 2: lego (xl-base, 50 steps)")
    print("=" * 60)

    if output_dir is None:
        output_dir = src_audio.parent

    # Lock metadata from plan so lego output matches source
    meta = {
        "bpm": plan.get("bpm", 120) if plan else 120,
        "key_scale": f"{plan.get('key', 'C')} {'minor' if 'min' in plan.get('scale', '').lower() else 'Major'}" if plan else "C Major",
        "time_signature": str(plan.get("time_signature", "4/4").split("/")[0]) if plan else "4",
        "audio_duration": 22.9,
    }
    if plan:
        sections = plan.get("sections", [])
        total_bars = plan.get("total_bars", sum(s.get("measures", 0) for s in sections))
        bpm = plan.get("bpm", 120)
        beats_per_bar = int(plan.get("time_signature", "4/4").split("/")[0])
        meta["audio_duration"] = round(total_bars * beats_per_bar * 60 / bpm, 1)

    results: list[Path] = []
    for track_name in track_names:
        print(f"\n  --- Adding track: {track_name} ---")
        params = {
            "task_type": "lego",
            "model": XL_BASE,
            "instruction": LEGO_INSTRUCTION.format(track_name=track_name),
            "prompt": prompt or f"high quality {track_name}",
            "inference_steps": 50,
            "thinking": False,
            "audio_format": "mp3",
            **meta,
        }
        print(f"  Locked meta: bpm={meta['bpm']}, key={meta['key_scale']}, dur={meta['audio_duration']}s")

        task_id = submit_task_multipart(params, src_audio)
        path = run_and_download(task_id, API_URL, output_dir,
                                f"step2_lego_{track_name}", timeout=600)
        results.append(path)
        print(f"  Saved: {path}")

    return results


# --- Step 3: extract with xl-base ---

def step3_extract(src_audio: Path, track_names: list[str],
                  plan: dict | None = None, output_dir: Path | None = None) -> list[Path]:
    """Extract/stems from mixed audio."""
    print("\n" + "=" * 60)
    print("STEP 3: extract (xl-base, 50 steps)")
    print("=" * 60)

    if output_dir is None:
        output_dir = src_audio.parent

    meta = {
        "bpm": plan.get("bpm", 120) if plan else 120,
        "key_scale": f"{plan.get('key', 'C')} {'minor' if 'min' in plan.get('scale', '').lower() else 'Major'}" if plan else "C Major",
    }

    results: list[Path] = []
    for track_name in track_names:
        print(f"\n  --- Extracting track: {track_name} ---")
        params = {
            "task_type": "extract",
            "model": XL_BASE,
            "instruction": EXTRACT_INSTRUCTION.format(track_name=track_name),
            "inference_steps": 50,
            "thinking": False,
            "audio_format": "mp3",
            **meta,
        }

        task_id = submit_task_multipart(params, src_audio)
        path = run_and_download(task_id, API_URL, output_dir,
                                f"step3_extract_{track_name}", timeout=600)
        results.append(path)
        print(f"  Saved: {path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="ACE-Step 1.5 Lego/Extract test")
    parser.add_argument("--plan", type=str, default=".clef-work/plan.json",
                        help="Path to plan.json (default: .clef-work/plan.json)")
    parser.add_argument("--output-dir", type=str, default=".tmp_lego",
                        help="Output directory (default: .tmp_lego)")
    parser.add_argument("--skip-extract", action="store_true",
                        help="Skip Step 3 (extract) to save time")
    parser.add_argument("--lego-tracks", type=str, nargs="+",
                        default=["drums", "bass"],
                        help="Tracks to add via lego (default: drums bass)")
    parser.add_argument("--extract-tracks", type=str, nargs="+",
                        default=["drums", "bass"],
                        help="Tracks to extract (default: drums bass)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not check_server_health(API_URL):
        print(f"ERROR: ACE-Step server not reachable at {API_URL}")
        sys.exit(1)
    print(f"Server OK at {API_URL}")

    # Validate track names
    for t in args.lego_tracks + args.extract_tracks:
        if t not in TRACK_NAMES:
            print(f"ERROR: Invalid track name '{t}'. Valid: {TRACK_NAMES}")
            sys.exit(1)

    # Load plan
    plan_path = Path(args.plan)
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        print(f"Loaded plan: {plan.get('title', '?')} ({plan.get('bpm', '?')} BPM, "
              f"{plan.get('key', '?')} {plan.get('scale', '?')})")
    else:
        # Fallback defaults
        plan = {
            "title": "Test Track",
            "key": "C", "scale": "major", "bpm": 120,
            "time_signature": "4/4", "total_bars": 8,
            "style": "pop rock", "mood": "energetic",
            "orchestration": {
                "melody": {"name": "Guitar"},
                "harmony": {"name": "Keyboard"},
                "bass": {"name": "Bass"},
                "drums": {"name": "Drums"},
            },
        }
        print(f"No plan found at {plan_path}, using defaults")

    # Step 1: Generate backing track
    backing_path = step1_text2music(plan, output_dir)
    print(f"\n  Backing track: {backing_path}")

    # Step 2: Lego add tracks
    lego_paths = step2_lego(
        backing_path, args.lego_tracks,
        prompt=_build_prompt(plan),
        plan=plan,
        output_dir=output_dir,
    )
    print(f"\n  Lego tracks: {[str(p) for p in lego_paths]}")

    # Step 3: Extract stems (optional)
    if not args.skip_extract:
        extract_paths = step3_extract(
            backing_path, args.extract_tracks,
            plan=plan,
            output_dir=output_dir,
        )
        print(f"\n  Extracted tracks: {[str(p) for p in extract_paths]}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Output dir: {output_dir.resolve()}")
    for f in sorted(output_dir.glob("*.mp3")):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.0f} KB")
    print("\nDone! Listen to the files to evaluate quality.")


if __name__ == "__main__":
    main()
