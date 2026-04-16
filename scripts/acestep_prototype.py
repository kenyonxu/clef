#!/usr/bin/env python3
"""ACE-Step 1.5 music generation prototype for clef.

Validates whether ACE-Step 1.5 local API can replace clef's create+iterate phase.
Requires ACE-Step API server running at localhost:8001.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests
import yaml


def main():
    parser = argparse.ArgumentParser(description="ACE-Step 1.5 music generation prototype")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", type=str, help="User text description to generate plan.json")
    group.add_argument("--plan", type=str, help="Path to existing plan.json")
    parser.add_argument("--mode", choices=["text2music", "cover", "both"], default="text2music",
                        help="Generation mode (default: text2music)")
    parser.add_argument("--reference", type=str, default=None,
                        help="Reference audio path for cover mode (absolute path on ACE-Step server)")
    parser.add_argument("--api-url", type=str, default="http://localhost:8001",
                        help="ACE-Step API server URL (default: http://localhost:8001)")
    parser.add_argument("--api-key", type=str, default=None,
                        help="ACE-Step API key (if authentication is enabled)")
    parser.add_argument("--output-dir", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Health check
    if not check_server_health(args.api_url):
        print(f"ERROR: ACE-Step server not reachable at {args.api_url}")
        print("Start it with: cd E:/GitHub/ACE-Step-1.5 && start_api_server.bat")
        sys.exit(1)

    # Resolve plan.json
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"ERROR: plan file not found: {plan_path}")
            sys.exit(1)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    else:
        plan = generate_plan(args.prompt, output_dir)

    # Map plan to ACE-Step parameters
    ace_params = build_acestep_params(plan, args.mode, args.reference)
    print(f"[ACE-Step Params] {json.dumps(ace_params, indent=2, ensure_ascii=False)}")

    # Call API based on mode
    if args.mode in ("text2music", "both"):
        print("[Mode: text2music] Submitting task...")
        audio_path = call_acestep_generate(ace_params, args.api_url, args.api_key, output_dir, "acestep_text2music")
        print(f"Saved: {audio_path}")

    if args.mode in ("cover", "both"):
        print("[Mode: cover] Submitting task...")
        cover_params = build_acestep_params(plan, "cover", args.reference)
        audio_path = call_acestep_generate(cover_params, args.api_url, args.api_key, output_dir, "acestep_cover")
        print(f"Saved: {audio_path}")


# --- Plan Generation (--prompt mode) ---

def load_first_provider(config_path: Path = Path("server/config/providers.yaml")) -> dict:
    """Load the first available provider from providers.yaml."""
    if not config_path.exists():
        raise FileNotFoundError(f"providers config not found: {config_path}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    compat = cfg.get("anthropic_compat", {})
    for name, prov in compat.items():
        if isinstance(prov, dict) and prov.get("api_key") and prov.get("base_url"):
            return {"name": name, **prov}
    anthro = cfg.get("anthropic", {})
    if anthro.get("api_key"):
        return {
            "name": "anthropic",
            "api_key": anthro["api_key"],
            "base_url": "https://api.anthropic.com",
            "model_id": anthro.get("default_model", "claude-sonnet-4-20250514"),
        }
    raise RuntimeError("No usable provider found in providers.yaml")


def call_llm_for_plan(user_prompt: str, provider: dict) -> dict:
    """Call LLM to generate a clef-style plan.json from user text."""
    system_prompt = (
        "You are a music planning assistant. Given a user's description, "
        "output a JSON object matching clef's plan.json structure with these fields:\n"
        '- "title": string (song title)\n'
        '- "key": string (e.g., "C", "G", "F#")\n'
        '- "scale": "major" or "minor"\n'
        '- "bpm": integer (60-180)\n'
        '- "time_signature": string (e.g., "4/4")\n'
        '- "total_bars": integer\n'
        '- "form": string (e.g., "ABA", "AB")\n'
        '- "sections": array of {id, name, measures, energy_level(1-10), dynamics}\n'
        '- "orchestration": object with melody/harmony/bass/drums, each {name, instrument}\n'
        '- "style": string\n'
        '- "mood": string\n'
        "Output ONLY the raw JSON, no markdown."
    )
    headers = {
        "x-api-key": provider["api_key"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": provider["model_id"],
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(
        f"{provider['base_url'].rstrip('/')}/v1/messages",
        headers=headers, json=payload, timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    return json.loads(content)


def generate_plan(user_prompt: str, output_dir: Path) -> dict:
    """Generate plan.json via LLM from user text description."""
    provider = load_first_provider()
    print(f"[Plan] Using provider: {provider['name']} ({provider['model_id']})")
    plan = call_llm_for_plan(user_prompt, provider)
    plan_path = output_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved plan: {plan_path}")
    return plan


# --- API Client ---

def check_server_health(api_url: str) -> bool:
    """Check if ACE-Step API server is reachable."""
    try:
        resp = requests.get(f"{api_url}/health", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def _get_auth_headers(api_key: str | None) -> dict:
    """Build authorization headers if API key is provided."""
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def submit_task(params: dict, api_url: str, api_key: str | None = None) -> str:
    """Submit a generation task to ACE-Step API. Returns task_id."""
    headers = {"Content-Type": "application/json"}
    headers.update(_get_auth_headers(api_key))

    resp = requests.post(f"{api_url}/release_task", json=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 200:
        raise RuntimeError(f"ACE-Step API error: {data.get('error')}")

    task_id = data["data"]["task_id"]
    print(f"  Task submitted: {task_id}")
    return task_id


def poll_result(task_id: str, api_url: str, api_key: str | None = None,
                timeout: int = 300, interval: int = 5) -> dict:
    """Poll task result until completion or timeout. Returns result dict."""
    headers = {"Content-Type": "application/json"}
    headers.update(_get_auth_headers(api_key))
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = requests.post(
            f"{api_url}/query_result",
            json={"task_id_list": [task_id]},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        tasks = data.get("data", [])
        if tasks:
            task = tasks[0]
            status = task.get("status")

            if status == 1:
                print("  Generation completed.")
                return task
            elif status == 2:
                raise RuntimeError(f"ACE-Step generation failed: {task.get('result', '')}")

        elapsed = int(time.time() - (deadline - timeout))
        print(f"  Waiting... ({elapsed}s elapsed)")
        time.sleep(interval)

    raise TimeoutError(f"ACE-Step task {task_id} timed out after {timeout}s")


def download_audio(result: dict, api_url: str, output_dir: Path, prefix: str) -> Path:
    """Download generated audio from ACE-Step server. Returns local file path."""
    result_data = json.loads(result["result"])
    if not result_data:
        raise RuntimeError("No audio result data returned")

    audio_info = result_data[0]
    audio_url_path = audio_info["file"]
    metas = audio_info.get("metas", {})
    duration = metas.get("duration", "?")
    bpm = metas.get("bpm", "?")
    key = metas.get("keyscale", "?")
    print(f"  Duration: {duration}s, BPM: {bpm}, Key: {key}")

    # Download audio file
    download_url = f"{api_url}{audio_url_path}"
    resp = requests.get(download_url, timeout=120)
    resp.raise_for_status()

    fmt = "mp3"
    out_path = output_dir / f"{prefix}_output.{fmt}"
    out_path.write_bytes(resp.content)
    return out_path


def call_acestep_generate(params: dict, api_url: str, api_key: str | None,
                          output_dir: Path, prefix: str) -> Path:
    """Full workflow: submit task → poll → download audio."""
    task_id = submit_task(params, api_url, api_key)
    result = poll_result(task_id, api_url, api_key)
    return download_audio(result, api_url, output_dir, prefix)


# --- Parameter Mapping ---

_INSTRUMENT_DESC = {
    "Violin": "violin", "Viola": "viola", "Cello": "cello",
    "Flute": "flute", "Clarinet": "clarinet", "Oboe": "oboe", "Bassoon": "bassoon",
    "Trumpet": "trumpet", "Trombone": "trombone", "French Horn": "french horn", "Horn": "french horn",
    "Acoustic Guitar": "acoustic guitar", "Nylon Guitar": "nylon string guitar",
    "Electric Guitar": "electric guitar",
    "Acoustic Bass": "acoustic bass", "Bass": "bass", "Electric Bass": "electric bass",
    "Harp": "harp", "Organ": "organ", "Accordion": "accordion",
    "Saxophone": "saxophone", "Sax": "saxophone",
    "Percussion": "percussion", "Drums": "drums", "Drum": "drums",
    "Strings": "strings", "String Ensemble": "string ensemble",
    "Synth": "synthesizer", "Synthesizer": "synthesizer", "Pad": "synth pad",
    "Piano": "piano", "Marimba": "marimba", "Vibraphone": "vibraphone",
}


def _calc_duration(plan: dict) -> float:
    """Calculate target duration in seconds from plan sections."""
    total_bars = plan.get("total_bars", 0)
    if not total_bars:
        sections = plan.get("sections", [])
        total_bars = sum(s.get("measures", s.get("bars", 0)) for s in sections)
    bpm = plan.get("bpm", 120)
    time_sig = plan.get("time_signature", "4/4")
    beats_per_bar = int(time_sig.split("/")[0]) if "/" in time_sig else 4
    return round(total_bars * beats_per_bar * 60 / bpm, 1)


def _map_key_scale(plan: dict) -> str:
    """Map clef key+scale to ACE-Step key_scale format."""
    key = plan.get("key", "C")
    scale = plan.get("scale", "major")
    scale_name = "minor" if "min" in scale.lower() else "Major"
    return f"{key} {scale_name}"


def _map_time_signature(plan: dict) -> str:
    """Map clef time_signature to ACE-Step format (just the numerator)."""
    ts = plan.get("time_signature", "4/4")
    if "/" in ts:
        return ts.split("/")[0]
    return ts


def _build_prompt(plan: dict) -> str:
    """Build English music description prompt from plan.json."""
    parts: list[str] = []

    style = plan.get("genre") or plan.get("style", "")
    if style:
        parts.append(style)

    mood = plan.get("mood") or plan.get("emotion", "")
    if mood:
        parts.append(mood)

    orch = plan.get("orchestration", {})
    instruments: list[str] = []
    for role in ["melody", "harmony", "bass", "drums"]:
        if role in orch and isinstance(orch[role], dict):
            name = orch[role].get("name")
            if name and name not in instruments:
                instruments.append(name)
    layers = orch.get("layers", {})
    for layer_name, layer_cfg in layers.items():
        if isinstance(layer_cfg, dict):
            name = layer_cfg.get("name")
            if name and name not in instruments:
                instruments.append(name)
    if instruments:
        descs = [_INSTRUMENT_DESC.get(n, n) for n in instruments]
        parts.append(f"featuring {', '.join(descs)}")

    form = plan.get("form", "")
    if form:
        parts.append(f"{form} form")

    parts.append("instrumental")
    parts.append("game background music, seamless loop")

    return ", ".join(parts)


def build_acestep_params(plan: dict, mode: str, reference_path: str | None) -> dict:
    """Map clef plan.json to ACE-Step /release_task parameters."""
    params = {
        "prompt": _build_prompt(plan),
        "bpm": plan.get("bpm", 120),
        "key_scale": _map_key_scale(plan),
        "time_signature": _map_time_signature(plan),
        "audio_duration": _calc_duration(plan),
        "thinking": True,
        "audio_format": "mp3",
        "inference_steps": 8,
    }

    if mode == "cover" and reference_path:
        params["task_type"] = "cover"
        params["src_audio_path"] = reference_path
        params["audio_cover_strength"] = 0.8
    else:
        params["task_type"] = "text2music"

    return params


if __name__ == "__main__":
    main()
