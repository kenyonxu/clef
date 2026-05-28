# Clef

[Download on Godot Asset Store](https://store.godotengine.org/...) · Free & Open Source (MIT)

Clef is an **open-source MIDI music plugin for Godot 4.6+**, made of two core modules:

- **MIDI Playback Engine** — Real-time SF2 SoundFont synthesis, piano roll editor, CC/pitch bend/modulation, and JSON ↔ MIDI bidirectional conversion
- **7-Agent AI Composition System** — Claude Code-powered multi-agent collaboration for composing, arranging, reviewing, and expression injection. Turn natural language descriptions into MIDI music.

---

## Features

### MIDI Playback Engine

- Real-time MIDI stream playback via an AudioStreamPlayer pool
- SF2 SoundFont synthesis with multi-timbre support
- Real-time CC (Volume / Expression / Pan / Reverb / Vibrato), Pitch Bend, Modulation
- Configurable polyphony limit, loop playback, and release time multiplier
- In-Inspector preview playback, JSON ↔ MIDI bidirectional conversion

### Piano Roll Editor

- Three modes: Playback (read-only), Edit (full modification), Feedback (annotated review)
- Visual note editing: drag to create, move, resize, box-select batch operations
- Ctrl+C/V copy/paste, Delete removal, Ctrl+Z/Shift+Z undo/redo
- Multi-track management: add/switch tracks, GM patch selection (128 standard instruments)
- Velocity editing, fine pitch adjustment, mute/inverse mute
- Export edited MIDI, export Agent feedback JSON (with selection context)

### AI-Powered Composition (Clef Compose)

- Triggered via `/clef-compose` — describe your music in natural language, get MIDI
- 7 specialized Agents: Composer, Harmonist, Rhythmist, Orchestrator, Reviewer, Revision, Leader
- ABC notation → MIDI fully automated pipeline (validate → merge → convert)
- music21 technical validation (6 checks: key, range, leaps, duration, alignment, overlaps)
- Interactive direction demo + Leader-driven iteration (up to 3 rounds of auto-optimization)
- SF2 soundfont-aware, automatically adapts to target instrument characteristics

---

## Quick Start

### Install the Godot Plugin

1. Copy the `addons/clef/` directory into your Godot project's `addons/` directory
2. Enable the plugin: **Project → Project Settings → Plugins → Clef**
3. Configure the default SoundFont: **Project → Project Settings → General → Clef → Default Soundfont**, select a `.sf2` file

We recommend [GeneralUser GS](https://schristiancollins.com/generaluser.php) (~30 MB, CC BY 3.0).

### Play a MIDI File

Add a `MidiStreamPlayer` node to your scene and configure the MIDI resource and SoundFont path in the Inspector.

```gdscript
@onready var player: MidiStreamPlayer = $MidiStreamPlayer

func _ready():
    player.start_playback()
    player.finished.connect(_on_song_end)
```

### AI Composition

Use the `/clef-compose` command in Claude Code with a natural language description:

```
/clef-compose Write a boss battle theme in D major, 140 BPM, 30 seconds, orchestral style
```

The system handles the full pipeline: requirement analysis → music planning → direction demo → full composition → quality review → iterative refinement → expression injection → MIDI output.

See the [LLM Composition Guide](addons/clef/docs/user_docs/llm_midi_composer_guide_cn.md) (Chinese) for details.

---

## Editor Tools

| Tool | Description |
|------|-------------|
| Inspector Preview | Playback controls appear at the bottom of Inspector when a `MidiStreamPlayer` node is selected |
| JSON → MIDI | Menu **Clef Utility → Compose MIDI from JSON** or right-click `.json` files |
| MIDI → JSON | Menu **Clef Utility → Export MIDI to JSON** or right-click `.mid` / `.tres` files |
| File Import | `.mid` files auto-import as `MidiResource`, drag-and-drop into scenes |

---

## Supported MIDI Events

| Event Type | Description |
|------------|-------------|
| Note On/Off | Note on/off with velocity |
| CC 1 (Modulation) | Vibrato depth |
| CC 7 (Volume) | Channel volume |
| CC 10 (Pan) | Stereo panning |
| CC 11 (Expression) | Expression / velocity scaling |
| CC 64 (Sustain) | Sustain pedal |
| CC 91 (Reverb) | Reverb depth |
| Pitch Bend | Pitch bend (±2 semitones) |
| Tempo Change | Tempo changes |

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](addons/clef/docs/user_guide.md) | Complete plugin guide (installation, playback, API, FAQ) |
| [Clef JSON v2.0 Spec](addons/clef/docs/clef_json_spec.md) | Detailed JSON format specification |
| [LLM Composition Guide](addons/clef/docs/user_docs/llm_midi_composer_guide_cn.md) | Tips and examples for describing music in natural language (Chinese) |
| [Music Theory Reference](addons/clef/docs/theory.md) | Scales, chords, orchestration, rhythm knowledge base (Chinese) |
| [Plugin Localization](docs/plugin-localization.md) | TranslationDomain multi-language technical approach (Chinese) |
| [Design Philosophy](docs/clef-compose-zhihu-article.md) | 7-Agent architecture design and workflow (Chinese) |
| [Composition Techniques](docs/音乐编曲技巧.md) | 15 emotional chord progressions reference (Chinese) |

---

## Project Structure

```
addons/clef/              # Godot plugin
  player/                 # Playback engine (MidiStreamPlayer, SF2 synthesis, voice pool)
  converter.gd            # JSON ↔ MidiData conversion
  midi_reader.gd          # MIDI binary parser
  midi_writer.gd          # MidiData → MIDI output
  midi_resource.gd        # Resource subclass
  editor/                 # Editor plugin (context menu, Inspector)
  ui/                     # Player UI
  templates/              # LLM composition templates
  knowledge/              # SoundFont instrument profiles
  sound_front/            # SoundFont files
  tests/                  # Tests

.claude/                  # Claude Code composition system
  skills/clef-compose/    # Main Skill + Python toolchain
    SKILL.md              # Composition workflow definition
    references/           # On-demand reference docs
    scripts/              # abc_to_midi, validate_abc, merge_abc, inject_expression, etc.
    tests/                # Python tests
  agents/                 # 7 Agent definitions
```

---

## Requirements

- Godot 4.6+
- Python 3.10+ (LLM composition toolchain)
- music21 (`pip install music21`, composition validation)
- mido (`pip install mido`, MIDI I/O)
- FluidSynth (`midi-to-audio` export, optional)
- ffmpeg (OGG / MP3 export, optional)
- Claude Code (LLM composition features)

---

## Acknowledgements

Audio playback references implementation ideas from [arlez80/Godot-MIDI-Player](https://github.com/arlez80/Godot-MIDI-Player), including mix latency compensation, ADSR envelope interpolation, and the release delay mechanism.

## License

MIT
