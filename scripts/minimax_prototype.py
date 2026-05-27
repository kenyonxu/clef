#!/usr/bin/env python3
"""MiniMax music generation prototype for clef.

Validates whether MiniMax API can replace clef's create+iterate phase.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import requests
import yaml


def main():
    parser = argparse.ArgumentParser(description="MiniMax music generation prototype")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", type=str, help="User text description to generate plan.json")
    group.add_argument("--plan", type=str, help="Path to existing plan.json")
    parser.add_argument("--mode", choices=["text", "cover", "both"], default="text",
                        help="Generation mode (default: text)")
    parser.add_argument("--reference", type=str, default=None,
                        help="Reference audio path for cover mode")
    parser.add_argument("--api-key", type=str, required=True, help="MiniMax API key")
    parser.add_argument("--output-dir", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve plan.json
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"ERROR: plan file not found: {plan_path}")
            sys.exit(1)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    else:
        plan = generate_plan(args.prompt, output_dir)

    # Resolve prompt
    minimax_prompt = build_minimax_prompt(plan)
    print(f"[MiniMax Prompt] {minimax_prompt}")

    # Call API based on mode
    if args.mode in ("text", "both"):
        print("[Mode: text] Calling MiniMax music-2.6...")
        audio_data = call_minimax_text(minimax_prompt, args.api_key, plan)
        text_out = output_dir / "minimax_text_output.mp3"
        text_out.write_bytes(audio_data)
        print(f"Saved: {text_out}")

    if args.mode in ("cover", "both"):
        print("[Mode: cover] Preparing reference audio...")
        ref_path = resolve_reference_audio(args.reference, plan, output_dir)
        if ref_path is None:
            print("WARN: No reference audio found or conversion failed, skipping cover mode.")
        else:
            print("[Mode: cover] Calling MiniMax music-cover-free...")
            audio_data = call_minimax_cover(minimax_prompt, ref_path, args.api_key)
            cover_out = output_dir / "minimax_cover_output.mp3"
            cover_out.write_bytes(audio_data)
            print(f"Saved: {cover_out}")


def load_first_provider(config_path: Path = Path("server/config/providers.yaml")) -> dict:
    """Load the first available provider from providers.yaml."""
    if not config_path.exists():
        raise FileNotFoundError(f"providers config not found: {config_path}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # Search anthropic_compat entries first (they have base_url + api_key)
    compat = cfg.get("anthropic_compat", {})
    for name, prov in compat.items():
        if isinstance(prov, dict) and prov.get("api_key") and prov.get("base_url"):
            return {"name": name, **prov}
    # Fallback to anthropic default
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
        '- "title": string (song title in Chinese or English)\n'
        '- "key": string (e.g., "C", "G", "F#")\n'
        '- "scale": "major" or "minor"\n'
        '- "bpm": integer (60-180)\n'
        '- "time_signature": string (e.g., "4/4")\n'
        '- "total_bars": integer\n'
        '- "form": string (e.g., "ABA", "AB", "ABABC")\n'
        '- "sections": array of {id, name, measures, start_beat, energy_level(1-10), dynamics(mp/mf/f), melody_strategy(new/variation/recap)}\n'
        '- "orchestration": object with melody/harmony/bass/drums, each {name, channel, instrument(0-127), range, register}\n'
        '- "style": string\n'
        '- "mood": string\n'
        "Output ONLY the raw JSON, no markdown, no explanations."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    headers = {
        "x-api-key": provider["api_key"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": provider["model_id"],
        "max_tokens": 2048,
        "messages": messages,
    }

    resp = requests.post(
        f"{provider['base_url'].rstrip('/')}/v1/messages",
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["content"][0]["text"]

    # Strip markdown fences if any
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


# Instrument name translations (English → Chinese)
_INSTRUMENT_CN = {
    "Piano": "钢琴", "Violin": "小提琴", "Viola": "中提琴", "Cello": "大提琴",
    "Flute": "长笛", "Clarinet": "单簧管", "Oboe": "双簧管", "Bassoon": "大管",
    "Trumpet": "小号", "Trombone": "长号", "French Horn": "圆号", "Horn": "圆号",
    "Acoustic Guitar": "木吉他", "Nylon Guitar": "尼龙弦吉他", "Electric Guitar": "电吉他",
    "Acoustic Bass": "低音提琴", "Bass": "贝斯", "Electric Bass": "电贝斯",
    "Harp": "竖琴", "Organ": "管风琴", "Accordion": "手风琴",
    "Saxophone": "萨克斯", "Sax": "萨克斯",
    "Percussion": "打击乐", "Drums": "鼓组", "Drum": "鼓",
    "Strings": "弦乐", "String Ensemble": "弦乐合奏",
    "Synth": "合成器", "Synthesizer": "合成器", "Pad": "合成垫音",
    "Choir": "合唱", "Voice": "人声",
    "Marimba": "马林巴", "Vibraphone": "颤音琴", "Xylophone": "木琴",
    "Banjo": "班卓琴", "Mandolin": "曼陀林", "Ukulele": "尤克里里",
    "Harpsichord": "大键琴", "Celesta": "钢片琴",
    "Bagpipes": "风笛", "Recorder": "竖笛",
}

_SCALE_CN = {"major": "大调", "minor": "小调", "dorian": "多利亚调式",
             "mixolydian": "混合利底亚调式", "pentatonic": "五声音阶", "blues": "布鲁斯"}


def build_minimax_prompt(plan: dict) -> str:
    """Construct a Chinese prompt string for MiniMax from clef plan.json."""
    parts: list[str] = []

    # Genre / Style — infer from title/sections if missing
    style = plan.get("genre") or plan.get("style", "")
    if not style:
        title = plan.get("title", "")
        sections = plan.get("sections", [])
        energy = sum(s.get("energy_level", 5) for s in sections) / max(len(sections), 1)
        if any(kw in title for kw in ["战斗", "Battle", "Boss", "战斗"]):
            style = "史诗战斗"
        elif any(kw in title for kw in ["晨", "Morning", "Dawn", "Awakening"]):
            style = "田园晨曲"
        elif energy >= 7:
            style = "激昂"
        elif energy <= 3:
            style = "宁静抒情"
        else:
            style = "抒情流行"
    parts.append(style)

    # Mood / Emotion — infer from energy/dynamics if missing
    mood = plan.get("mood") or plan.get("emotion", "")
    if not mood:
        sections = plan.get("sections", [])
        dynamics_list = [s.get("dynamics", "mf") for s in sections]
        if "f" in dynamics_list or "ff" in dynamics_list:
            mood = "激昂有力"
        elif "pp" in dynamics_list or "p" in dynamics_list:
            mood = "温柔细腻"
        else:
            mood = "温暖平和"
    parts.append(mood)

    # Key and scale in Chinese
    key = plan.get("key", "")
    scale = plan.get("scale", "major")
    scale_cn = _SCALE_CN.get(scale, scale)
    if key:
        parts.append(f"{key}{scale_cn}")

    # Tempo / BPM
    bpm = plan.get("bpm", 0)
    if bpm:
        if bpm <= 60:
            parts.append("慢板")
        elif bpm <= 80:
            parts.append("中慢板")
        elif bpm <= 110:
            parts.append("中板")
        elif bpm <= 140:
            parts.append("快板")
        else:
            parts.append("急板")

    # Instrumentation
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
        cn_instruments = [_INSTRUMENT_CN.get(n, n) for n in instruments]
        parts.append(f"以{'、'.join(cn_instruments)}为主")

    # Form
    form = plan.get("form", "")
    if form:
        parts.append(f"{form}曲式")

    # Duration hint from sections
    sections = plan.get("sections", [])
    total_bars = plan.get("total_bars", 0)
    if not total_bars and sections:
        total_bars = sum(s.get("measures", s.get("bars", 0)) for s in sections)
    if total_bars:
        bpm_val = plan.get("bpm", 120)
        duration_sec = int(total_bars * 4 * 60 / bpm_val)
        parts.append(f"约{duration_sec}秒")

    # Loop hint — encourage short, seamlessly loopable output
    parts.append("适合游戏背景音乐循环播放，首尾衔接自然")

    return ", ".join(parts)


def build_instrumental_lyrics(plan: dict) -> str:
    """Build short lyrics structure tags from plan sections to control duration.

    MiniMax has no duration parameter, but section tags in lyrics influence length.
    We map plan sections to structure tags and keep them minimal to encourage brevity.
    """
    sections = plan.get("sections", [])
    if not sections:
        return "[Intro]\n[Verse]\n[Outro]"

    tags = []
    for sec in sections:
        name = sec.get("name", "").lower()
        # Map common section names to MiniMax-compatible tags
        if "intro" in name or "前奏" in name:
            tags.append("[Intro]")
        elif "outro" in name or "尾奏" in name or "coda" in name:
            tags.append("[Outro]")
        elif "chorus" in name or "副歌" in name:
            tags.append("[Chorus]")
        elif "bridge" in name or "桥段" in name:
            tags.append("[Bridge]")
        elif "verse" in name or "主歌" in name or "a段" in name:
            tags.append("[Verse]")
        elif "interlude" in name or "间奏" in name:
            tags.append("[Interlude]")
        else:
            # Fallback: use section id as generic tag
            sec_id = sec.get("id", "")
            tags.append(f"[Section_{sec_id}]" if sec_id else "[Verse]")

    # Remove consecutive duplicates
    seen = []
    for t in tags:
        if not seen or seen[-1] != t:
            seen.append(t)
    return "\n".join(seen)


def call_minimax_text(prompt: str, api_key: str, plan: dict = None) -> bytes:
    """Call MiniMax music-2.6 API and return decoded audio bytes."""
    url = "https://api.minimaxi.com/v1/music_generation"
    lyrics = build_instrumental_lyrics(plan) if plan else "[Intro]\n[Verse]\n[Outro]"
    payload = {
        "model": "music-2.6",
        "prompt": prompt,
        "lyrics": lyrics,
        "is_instrumental": True,
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=300,
                         proxies={"http": None, "https": None})
    resp.raise_for_status()
    data = resp.json()

    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") != 0:
        raise RuntimeError(f"MiniMax API error: {base_resp.get('status_msg')}")

    hex_audio = data["data"]["audio"]
    extra = data.get("extra_info", {})
    print(f"  duration_ms={extra.get('music_duration')}, "
          f"sample_rate={extra.get('music_sample_rate')}, "
          f"size={extra.get('music_size')}")

    return bytes.fromhex(hex_audio)


def call_minimax_cover(prompt: str, ref_path: Path, api_key: str) -> bytes:
    """Call MiniMax music-cover API with reference audio."""
    url = "https://api.minimaxi.com/v1/music_generation"
    audio_bytes = ref_path.read_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # Cover mode prompt must be 10-300 chars; trim to style + mood only
    cover_prompt = prompt
    if len(cover_prompt) > 300:
        # Keep first two segments (style, mood) before first duration hint
        parts = [p.strip() for p in cover_prompt.split(",")]
        cover_prompt = ", ".join(parts[:4])
        if len(cover_prompt) > 300:
            cover_prompt = cover_prompt[:297] + "..."

    payload = {
        "model": "music-cover",
        "prompt": cover_prompt,
        "audio_base64": audio_b64,
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=300,
                         proxies={"http": None, "https": None})
    resp.raise_for_status()
    data = resp.json()

    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") != 0:
        raise RuntimeError(f"MiniMax API error: {base_resp.get('status_msg')}")

    hex_audio = data["data"]["audio"]
    extra = data.get("extra_info", {})
    print(f"  duration_ms={extra.get('music_duration')}, "
          f"sample_rate={extra.get('music_sample_rate')}, "
          f"size={extra.get('music_size')}")

    return bytes.fromhex(hex_audio)


def resolve_reference_audio(reference: str | None, plan: dict, output_dir: Path) -> Path | None:
    """Resolve reference audio path for cover mode.

    Priority:
    1. User-specified --reference path
    2. Existing .wav or .mp3 next to plan.json
    3. Convert sample_r0.mid via clef_tools.py midi-to-audio
    """
    if reference:
        ref = Path(reference)
        if ref.exists():
            return ref
        print(f"WARN: specified reference not found: {ref}")
        return None

    # Try to find audio files near plan or in standard clef output dirs
    candidates: list[Path] = []
    plan_dir = output_dir if output_dir.exists() else Path(".")
    candidates.extend([
        plan_dir / "sample_r0.wav",
        plan_dir / "sample_r0.mp3",
        Path(".clef-work") / "sample_r0.wav",
        Path(".clef-work") / "sample_r0.mp3",
        Path("addons/clef/output") / "sample_r0.wav",
        Path("addons/clef/output") / "sample_r0.mp3",
    ])
    for c in candidates:
        if c.exists():
            return c

    # Try MIDI conversion via clef_tools.py
    midi_candidates = [
        plan_dir / "sample_r0.mid",
        Path(".clef-work") / "sample_r0.mid",
        Path("addons/clef/output") / "sample_r0.mid",
    ]
    for mid in midi_candidates:
        if mid.exists():
            wav_out = output_dir / "sample_r0_converted.wav"
            print(f"Converting MIDI to audio: {mid} -> {wav_out}")
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        ".claude/skills/clef-compose/scripts/clef_tools.py",
                        "midi-to-audio",
                        str(mid),
                        "-o", str(wav_out),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if wav_out.exists():
                    return wav_out
            except subprocess.CalledProcessError as e:
                print(f"WARN: midi-to-audio failed: {e.stderr}")
                return None

    print("WARN: No reference audio (.wav/.mp3/.mid) found for cover mode.")
    return None


if __name__ == "__main__":
    main()
