"""Build LLM prompts for compose phases."""

from clef_server.sf2_profile import midi_to_note


def build_plan_summary(plan: dict) -> dict:
    """Build a rich parameter summary from plan.json for the confirmation UI."""
    total_bars = plan.get("total_bars", 0)
    bpm = plan.get("bpm", 0)
    ts = plan.get("time_signature", "4/4")
    beats_per_bar = int(ts.split("/")[0]) if "/" in ts else 4

    # Duration
    duration_sec = (total_bars * beats_per_bar / bpm * 60) if bpm > 0 else 0
    if duration_sec >= 60:
        duration_str = f"~{int(duration_sec // 60)}分{int(duration_sec % 60)}秒"
    else:
        duration_str = f"~{duration_sec:.0f}秒"

    # Section structure compact form: "ABA（4+7+4 小节）"
    sections = plan.get("sections", [])
    bar_counts = [str(s.get("measures", "?")) for s in sections]
    section_structure = f"{plan.get('form', '')}（{'+'.join(bar_counts)} 小节）"

    # Orchestration description
    orch = plan.get("orchestration", {})
    voice_cn = {"melody": "旋律", "harmony": "和声", "bass": "低音", "drums": "鼓"}
    inst_parts = []
    for role in ["melody", "harmony", "bass", "drums"]:
        part = orch.get(role, {})
        if part:
            name = part.get("name", part.get("instrument", ""))
            inst_parts.append(f"{name}{voice_cn.get(role, role)}")

    # SF2 status
    sf2_count = sum(
        1
        for role in ["melody", "harmony", "bass"]
        if isinstance(orch.get(role), dict) and "sf2" in orch[role]
    )
    sf2_status = f"已加载 {sf2_count} 个声部音色" if sf2_count > 0 else "未配置"

    # Demo length with duration
    demo_bars = plan.get("demo_length_bars", 0)
    demo_sec = (demo_bars * beats_per_bar / bpm * 60) if bpm > 0 and demo_bars > 0 else 0
    demo_str = f"{demo_bars} 小节（~{demo_sec:.0f}秒）" if demo_sec > 0 else f"{demo_bars} 小节"

    return {
        "duration": duration_str,
        "section_structure": section_structure,
        "orchestration_desc": " + ".join(inst_parts),
        "sf2_status": sf2_status,
        "demo_length": demo_str,
    }


VOICE_MAP = {"melody": "V:1", "harmony": "V:2", "rhythm": "V:3+V:4"}


def build_create_message(voice: str, plan: dict) -> str:
    """Build a detailed prompt for the create phase, including section structure."""
    voice_label = VOICE_MAP.get(voice, f"V:{voice}")
    total_bars = plan.get("total_bars", 0)
    sections = plan.get("sections", [])
    orch = plan.get("orchestration", {})
    ts = plan.get("time_signature", "4/4")

    # Build section summary
    section_lines = []
    for sec in sections:
        section_lines.append(
            f"  - {sec.get('name', sec.get('id', '?'))}: "
            f"{sec.get('measures', '?')} bars, "
            f"energy={sec.get('energy_level', 'mid')}, "
            f"melody_strategy={sec.get('melody_strategy', 'new')}"
        )
    sections_text = "\n".join(section_lines)

    # Get voice-specific orchestration info
    role_map = {"melody": "melody", "harmony": "harmony", "rhythm": "bass"}
    role = role_map.get(voice, voice)
    voice_orch = orch.get(role, {})
    voice_info = (
        f"  Instrument: {voice_orch.get('instrument', 'N/A')}, "
        f"Range: {voice_orch.get('range', 'N/A')}, "
        f"Register: {voice_orch.get('register', 'N/A')}"
    )

    # SF2 constraints if available
    sf2_section = ""
    sf2 = voice_orch.get("sf2")
    if sf2:
        kr = sf2.get("key_range", [])
        ss = sf2.get("sweet_spot", [])
        chars = sf2.get("characteristics", [])
        char_text = ", ".join(chars) if chars else "N/A"
        sf2_section = (
            f"\n\n## SF2 Instrument Constraints\n"
            f"- Key range: [{kr[0]}, {kr[1]}] ({midi_to_note(kr[0])}-{midi_to_note(kr[1])})\n"
            f"- Sweet spot (recommended register): [{ss[0]}, {ss[1]}] ({midi_to_note(ss[0])}-{midi_to_note(ss[1])})\n"
            f"- Velocity layers: {sf2.get('vel_layers', 'N/A')}\n"
            f"- Characteristics: {char_text}\n"
            f"CRITICAL: Do NOT write notes outside the key range [{kr[0]}, {kr[1]}]!\n"
        )

    # Duration reference (shared by all voices)
    beats_per_measure = int(ts.split("/")[0])
    duration_ref = (
        f"\n\n## Duration Self-Check (MANDATORY)\n"
        f"Time signature: {ts} → {beats_per_measure} beats per measure.\n"
        f"With L:1/8, each measure = {beats_per_measure * 2} eighth-note units.\n"
        f"Duration reference (L:1/8):\n"
        f"  f = 1 unit (eighth note)\n"
        f"  f2 = 2 units (quarter note)\n"
        f"  f4 = 4 units (half note)\n"
        f"  f/2 = 0.5 units (sixteenth note)  ⚠ NOT 1 unit!\n"
        f"  [Ace]2 = 2 units,  z = 1 unit,  z2 = 2 units\n"
        f"VERIFY: sum of durations in EACH measure must = {beats_per_measure * 2}.\n"
        f"Before output, re-check every measure. Do NOT output if any measure is incomplete.\n"
    )

    # Voice-specific rhythm guidance
    voice_rules = ""
    if role == "melody":
        voice_rules = (
            "\n\n## Melody Rules\n"
            "- Follow plan.json melody_strategy per section (new/variation/sequence/development/recap/climax)\n"
            "- Rhythm variety: sections must have contrasting density (sparse vs dense)\n"
            "- Dynamics: at least 2 dynamic levels per section (!mf! base + !ff! climax)\n"
            "- Large intervals (>5 semitones): insert passing notes immediately\n"
        )
    elif role == "harmony":
        voice_rules = (
            "\n\n## Harmony Rules\n"
            "- EVERY measure must be COMPLETELY filled — sum of durations = "
            f"{beats_per_measure * 2} eighth-note units\n"
            "- Chord marks (\"D\") and chord notes ([FAc]) must appear in the SAME measure\n"
            "- Voice leading: common tones keep, non-common tones move by step (≤2 semitones)\n"
            "- Do NOT use the same rhythm pattern in every measure — vary rhythm between sections\n"
            "- Harmony notes must align with melody's strong beats\n"
        )
    elif role == "bass":
        voice_rules = (
            "\n\n## Bass & Drum Rules\n"
            "- Bass: prefer chord root or fifth, reference V:2 chord marks\n"
            "- Drums: adjust density by section energy (sparse in A, fills in B/C transitions)\n"
            "- Drum fills only at section transitions (last 1-2 bars), NOT at piece endings\n"
            "- Bass notes stay within register range from plan.json\n"
        )

    message = (
        f"Generate the full {voice} part as ABC notation.\n"
        f"Use voice label {voice_label}.\n\n"
        f"## Composition Structure\n"
        f"- Key: {plan.get('key', 'C')}\n"
        f"- Scale: {plan.get('scale', 'major')}\n"
        f"- Time: {ts}\n"
        f"- BPM: {plan.get('bpm', 120)}\n"
        f"- Form: {plan.get('form', 'ABA')}\n"
        f"- Total bars: {total_bars}\n\n"
        f"## Sections (must generate content for ALL sections)\n"
        f"{sections_text}\n\n"
        f"## Your Voice Configuration\n"
        f"{voice_info}"
        f"{voice_rules}"
        f"{duration_ref}"
        f"{sf2_section}"
        f"\nOutput only ABC notation for voice {voice_label}. "
        f"CRITICAL: Your output must contain EXACTLY {total_bars} bar lines (|). "
        f"Count your bars before outputting. If you have more than {total_bars} bars, "
        f"remove the excess. If fewer, add rest measures (z)."
    )
    return message
