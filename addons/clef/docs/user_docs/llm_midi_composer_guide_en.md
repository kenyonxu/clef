# LLM Composition Guide

Clef offers two ways to compose with LLMs. **Clef Compose** is the recommended approach, using Claude Code's multi-agent collaboration to automate the full pipeline from requirements to MIDI. **Template composition** is for users without Claude Code — manually submit JSON to any LLM.

---

## Method 1: Clef Compose (Recommended)

Trigger with the `/clef-compose` command in Claude Code. Describe your music needs in natural language, and the system automatically handles planning, creation, validation, iteration, and output.

### Workflow

```
Requirements → Plan (plan.json) → Direction demo (user confirms) → Full composition → Quality review → Auto-iteration → Expression injection → MIDI output
```

There are 3 user confirmation checkpoints:

1. **Plan confirmation** — the system shows key, BPM, section structure, and instrumentation; confirm to proceed
2. **Direction demo confirmation** — a 4-8 bar snippet is generated for preview; confirm the direction is correct
3. **Final confirmation** — the full MIDI is output; preview and provide feedback for changes

### What to Include When Describing Your Needs

No music theory knowledge required. Just be specific about:

1. **Scene / Atmosphere** — Where in the game does this play? (battle, exploration, menu, cutscene, boss fight, etc.)
2. **Mood** — Tense, relaxed, epic, mysterious, warm, sad, heroic...
3. **Style / Reference** — 8-bit, orchestral, electronic, jazz, solo piano, or "like Hollow Knight's City of Tears"
4. **Duration** — 30 seconds, 1 minute, 2 minutes; whether it should loop

For more precision, add:
- **Instrument preference** — "mainly piano", "no drums", "like NES/Famicom sounds"
- **Rhythm feel** — "fast-paced", "slow and relaxed", "gradually speeding up"

### Usage Examples

```
/clef-compose Write a boss battle theme, D major, 140 BPM, 30 seconds, orchestral style

/clef-compose Forest exploration background music, flute and strings, no drums, 90 second loop

/clef-compose Main menu piano solo, warm and quiet, 30 seconds, Stardew Valley vibe
```

### Iterating on Results

Not satisfied? Provide feedback and the system will locate and fix issues:

- **Specific feedback** ("the B section melody is too monotonous") → directly modifies the corresponding voice
- **Vague feedback** ("something sounds off in the middle") → generates solo track files for per-track auditioning
- **Global feedback** ("not tense enough overall") → adjusts overall plan parameters

### Advanced Options

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--ref` | Provide a reference MIDI file for style | `--ref boss_theme.mid` |
| `--import` | Import an existing ABC/MIDI as a starting point | `--import draft.abc` |
| `--sf2` | Target a specific SoundFont (auto-adapts to patch characteristics) | `--sf2 GeneralUser-GS` |

---

## Method 2: Template Composition

If you don't have Claude Code, you can submit the system prompt and template files to ChatGPT, Claude, or another LLM, then manually convert JSON → MIDI.

### Steps

1. Use [templates/default.json](../../templates/default.json) as a starting template
2. Describe your requirements to the LLM, including the system prompt
3. The LLM returns Clef JSON
4. In the Godot editor, right-click the `.json` file → **Convert to MIDI**
5. Preview in the Inspector

### Template Files

| File | Purpose |
|------|---------|
| `templates/default.json` | Minimal valid JSON, good for quick tests |
| `templates/example_full.json` | Full example with multi-track, CC, pitch bend, tempo changes |
| `templates/llm_compose_guide.json` | Condensed spec reference sheet |

---

## Quick Reference: Description Examples

> **Battle music**: For a side-scrolling action game's first level, tense and exciting, fast tempo, about 1 minute

> **Forest exploration**: Background music for exploration, relaxed and leisurely, slower tempo, no drums, flute or piano is fine

> **Boss fight**: Starts quiet, then erupts, gets faster and faster, about 2 minutes, needs impact

> **Main menu**: Solo piano, warm and quiet, 30 seconds, loop

> **Shop interface**: Light and cheerful, medium tempo, a touch of jazz, 1 minute