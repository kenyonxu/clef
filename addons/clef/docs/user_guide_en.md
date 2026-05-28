# Clef User Manual

## Contents

1. [Installation & Setup](#1-installation--setup)
2. [Playing MIDI Files](#2-playing-midi-files)
3. [Inspector Preview](#3-inspector-preview)
4. [Clef Station Workstation](#4-clef-station-workstation)
5. [JSON ↔ MIDI Conversion](#5-json--midi-conversion)
6. [MidiStreamPlayer Properties](#6-midistreamplayer-properties)
7. [Script API](#7-script-api)
8. [LLM-Assisted Composition](#8-llm-assisted-composition)
9. [Python Toolchain](#9-python-toolchain)
10. [FAQ](#10-faq)

---

## 1. Installation & Setup

### Installing the Plugin

1. Copy the `addons/clef/` directory into your project's `addons/` folder
2. Open the Godot editor → **Project → Project Settings → Plugins**
3. Find **Clef** and click **Enable**

### Configuring the Default SoundFont

1. Open **Project → Project Settings → General**
2. Find **Clef → Default Soundfont**
3. Select a `.sf2` file

Once configured, `MidiStreamPlayer` nodes will automatically use this SoundFont (unless a different file is specified manually).

---

## 2. Playing MIDI Files

### Method 1: Scene Node

1. Drag a `.mid` file into the project resource directory (Godot auto-imports it as `MidiResource`)
2. Create a `Node` in the scene
3. Attach the `MidiStreamPlayer` script
4. In the Inspector:
   - **Midi Resource**: drag in the imported `.tres` file
   - **Soundfont**: select a `.sf2` file (leave empty to use the default)
5. Run the scene

### Method 2: Code

```gdscript
var player := MidiStreamPlayer.new()
player.midi_resource = preload("res://music/song.tres")
player.soundfont = "res://soundfonts/piano.sf2"
player.loop = true
add_child(player)
player.start_playback()
```

### Playback Controls

| Method | Description |
|--------|-------------|
| `start_playback(from_position)` | Start playback, optional starting position (seconds) |
| `stop()` | Stop and reset to beginning |
| `pause()` | Pause |
| `resume()` | Resume playback |
| `seek(position)` | Jump to position (seconds) |
| `get_playback_position()` | Get current playback position (seconds) |
| `is_playing()` | Whether currently playing |

---

## 3. Inspector Preview

Preview MIDI resources directly in the editor without running the scene.

1. Select a `MidiResource` (`.tres`) file in the FileSystem panel
2. A Clef preview panel appears at the bottom of the Inspector:
   - **▶ Play** — start playback
   - **⏸ Pause** — pause / resume
   - **⏹ Stop** — stop playback
   - Progress bar — drag to seek
   - Time label — current time / total duration
   - **Export JSON** — export as Clef JSON v2.0 (for LLM composition)

> Requires a default SoundFont configured in project settings. The play button is disabled and shows a hint when unconfigured.

---

## 4. Clef Station Workstation

Clef Station is an integrated MIDI workstation panel at the bottom of the editor. It provides patch browsing, playback control, mixing, and real-time MIDI event monitoring. It appears automatically when the Clef plugin is enabled.

### Panel Layout

The panel uses a three-column draggable split layout. Split positions and panel visibility are saved automatically and restored on the next editor launch.

| Column | Content | Hideable |
|--------|---------|----------|
| Left | SoundFont Browser | Yes (**SF2 Browser** toggle) |
| Center | Playback controls + Mini Mixer | Always visible |
| Right | MIDI Monitor | Yes (**MIDI Monitor** toggle) |

Drag the divider between columns to resize.

### 4.1 Loading and Playing MIDI

#### Loading Files

Three file formats are supported: `.mid`, `.tres` (MidiResource), `.json` (Clef JSON).

1. Click **Load MIDI** and select a file from the dialog
2. Or drag a file from the FileSystem panel onto the Clef Station panel

#### Auto-Load

Enable the **Auto** button to automatically reload the last played file when opening the editor.

#### Playback Controls

| Control | Description |
|---------|-------------|
| **Play** | Start playback |
| **Pause** | Pause / resume |
| **Stop** | Stop and return to beginning |
| **Loop** | Loop playback (auto-restart on end) |
| Progress bar | Shows current position / total duration, click to seek |

> Playback uses the editor audio bus — no need to run the game scene for preview.

### 4.2 Piano Roll

The piano roll sits between the transport bar and the mixer. It displays MIDI notes on a timeline in real time and supports editing and review feedback.

**Display:**
- X-axis: time (seconds), Y-axis: pitch (MIDI 0-127)
- Notes from all channels overlaid, color-coded by channel
- Velocity mapped to brightness: higher velocity = brighter color
- C notes have brighter grid lines for octave identification

**During playback:**
- A white vertical line follows the playback position in real time
- The line returns to the start when stopped

> The pitch range is auto-calculated from the current MIDI file, with one octave of padding on each side.

#### 4.2.1 Legend Bar

The legend bar at the top of the piano roll shows track information and quick-action buttons:

| Area | Description |
|------|-------------|
| Track list | Shows channel number and instrument name per track; click to switch the active editing track |
| **+** button | Add new track (edit mode only, grayed out otherwise) |
| **⩩** button | Export Agent feedback JSON (feedback mode only) |
| **⤓** button | Export edited MIDI file (edit mode only) |

Right-click a track name to open the **Change Instrument** menu with the GM instrument selector (128 standard instruments grouped by category). If an SF2 bank is loaded, actual available patches are prioritized; otherwise falls back to the GM hardcoded list.

#### 4.2.2 Three-Mode System

The piano roll provides three mutually exclusive working modes, switched via the mode bar buttons (active mode highlighted with blue border):

| Mode | Button | Description |
|------|--------|-------------|
| **Playback** | ▶ Playback | Read-only browsing; click to seek |
| **Edit** | ✏ Edit | Full editing: move, resize, delete notes |
| **Feedback** | ❗ Feedback | Review annotations: select, mute, annotate problem notes |

The mode bar and transport controls (Play/Stop/Pause) operate independently — you can play/pause MIDI in any mode.

##### Playback Mode

The default mode for browsing and previewing MIDI files.

- Click anywhere on the piano roll to seek to that time
- Use the transport bar for play/pause/stop
- Cannot select or edit notes

##### Edit Mode

Full note editing for tweaking and modifying MIDI content.

- **Create notes**: drag horizontally in empty space, release to finish
- **Select**: click a note, Ctrl+click to add/remove from selection
- **Box select**: drag in empty space to select multiple notes
- **Move**: drag selected notes horizontally/vertically
- **Resize**: drag the left/right edge of a note
- **Delete**: press Delete, or right-click → Delete Notes
- **Copy/Paste**: Ctrl+C to copy, Ctrl+V to paste at current playback position
- **Pitch adjust**: right-click → Pitch +1 / Pitch -1
- **Velocity**: right-click → Edit Velocity..., set 0-127 in the dialog
- **Mute**: right-click → Mute Selected / Invert Mute
- **Undo/Redo**: Ctrl+Z / Ctrl+Shift+Z
- **Export MIDI**: click the **⤓** button or right-click → Export Modified MIDI
- **Export ABC**: right-click → Export Modified ABC
- **Zoom**: Ctrl+= zoom in, Ctrl+- zoom out
- **Pan**: middle-drag to pan the view
- Edits sync to the player in real time (preview without saving)

> The playback cursor is hidden during editing. Changes only affect in-memory data — the original MIDI file is untouched unless explicitly exported. Copy/paste and batch operations all support undo.

##### Feedback Mode

Focused review and annotation of problem notes, designed for quality review after LLM composition.

- **Select**: click/box-select/Ctrl+click (same as edit mode)
- **Annotate**: right-click → Add Annotation..., choose severity (info/warning/error) and enter a note
- **Mute**: right-click → Mute Selected / Invert Mute
- **Generate feedback**: click the **⩩** button or right-click → Generate Agent Feedback, choose a path to export structured JSON for LLM iteration
- **Playback**: transport bar works normally; listen while annotating
- Annotations are only visible in feedback mode (colored triangle markers above notes)

> Invert Mute mutes all unselected notes, useful for soloing a specific passage.

##### Agent Feedback JSON Format (v2)

The feedback JSON contains two sections:

```json
{
  "version": 2,
  "selection": {
    "count": 5,
    "pitches": [60, 62, 64, 67, 72],
    "channels": [0],
    "time_range": {"start": 1.5, "end": 4.0}
  },
  "annotations": [
    {"note_index": 2, "pitch": 64, "severity": "error", "note": "avoid leap"}
  ]
}
```

- **selection** — context about the current selection (note count, pitch set, channels, time range), helping the Agent distinguish single vs. multi-select intent
- **annotations** — user annotations, each tied to a specific note index

### 4.3 Mini Mixer

The mixer shows volume controls for all 16 MIDI channels plus a Master fader.

#### Channel Controls

Each channel includes:

- **Ch label** — channel number (Ch 1 – Ch 16)
- **Instrument name** — current GM patch name (auto-updates on Program Change, e.g. "Acoustic Grand Piano")
- **Volume slider** — drag to adjust channel volume (range -80 dB to +6 dB)
- **Mute button** — click to mute/unmute

#### Master Control

- **Master** label + volume slider — controls overall output volume

#### Pan

Hover over a channel label to view the current pan value via tooltip. Pan is controlled via MIDI CC10.

### 4.4 MIDI Monitor

The MIDI Monitor displays all MIDI events in real time, useful for debugging and learning MIDI data.

#### Event Format

Each event is shown as one line in the format `ChXX Type Data`, color-coded by type:

| Type | Color | Display |
|------|-------|---------|
| NoteOn | Green | Channel, pitch, velocity |
| NoteOff | Gray | Channel, pitch |
| CC | Blue | Channel, controller number, value |
| PB | Orange | Channel, pitch bend value |
| PC | Purple | Channel, program number |

Example output:
```
Ch 1 NoteOn   60  vel:100
Ch 1 CC#7    val:80
Ch 2 PC      24
```

#### Filtering

- **Ch** — channel filter button (currently All only)
- **NoteOn / CC / PB / PC** — toggle each event type on/off

#### Toolbar

| Button | Description |
|--------|-------------|
| **Auto** | Auto-scroll to latest events |
| **Clear** | Clear event log and statistics |
| **Copy** | Copy visible events to system clipboard |

#### Status Bar

The bottom status bar shows three real-time statistics:

- **Events** — total event count (since last Clear)
- **Notes** — currently active notes (NoteOn triggered but not yet released)
- **Rate** — events per second (live)

> The event log caps at 500 entries; older entries are trimmed automatically.

### 4.5 SoundFont Browser

The left column displays all patches from the currently loaded SF2 bank, organized by instrument category.

- Search box supports fuzzy name matching
- Category headers are collapsible
- Click a patch entry to audition it

> Requires a default SoundFont configured in project settings (**Project → Project Settings → General → Clef → Default Soundfont**).

---

## 5. JSON ↔ MIDI Conversion

Clef provides three ways to convert between JSON and MIDI.

### Method 1: Top Menu

Select a file, then:

- **Project → Clef Utility → Compose MIDI from JSON...** — convert `.json` to `.mid`
- **Project → Clef Utility → Export MIDI to JSON...** — export `.mid` / `.tres` as `.json`

A save dialog appears; choose the output location.

### Method 2: FileSystem Right-Click Menu

Right-click a file in the FileSystem panel:

- Right-click `.json` (Clef format) → **Convert to MIDI**
- Right-click `.mid` / `.tres` → **Export to JSON**

> Only `.json` files matching Clef JSON format (containing a `format_version` field) show the "Convert to MIDI" option.

### Method 3: Inspector Export

Select a `MidiResource` file, then click the **Export JSON** button at the bottom of the Inspector.

### Round-Trip Fidelity

JSON ↔ MIDI conversion is reversible. Export to JSON and re-import to MIDI; notes, controllers, pitch bends, and tempo changes are preserved.

> Note: Binary-level differences may occur due to MIDI format constraints (e.g. running status, Meta Event ordering), but musical content is identical.

---

## 6. MidiStreamPlayer Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `midi_resource` | `MidiResource` | — | MIDI resource to play |
| `soundfont` | `String` | `""` | SF2 file path |
| `loop` | `bool` | `false` | Loop playback |
| `release_multiplier` | `float` | `1.0` | Release time multiplier (0.1–2.0) |
| `autoplay` | `bool` | `false` | Auto-play when scene is ready |
| `volume_db` | `float` | `-20.0` | Master volume (dB) |
| `pitch_scale` | `float` | `1.0` | Global pitch scale |
| `max_polyphony` | `int` | `64` | Max simultaneous voices (1–128) |
| `bus` | `String` | `Master` | Output audio bus |

### Bus Effects

The ClefMaster bus provides three built-in effects, adjustable via the Inspector:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `reverb_enabled` | `bool` | `true` | Enable reverb |
| `reverb_room_size` | `float` | `0.29` | Reverb room size (0–1) |
| `reverb_wet` | `float` | `0.15` | Reverb wet mix (0–1) |
| `chorus_enabled` | `bool` | `true` | Enable chorus |
| `chorus_wet` | `float` | `0.2` | Chorus wet mix (0–1) |
| `compressor_enabled` | `bool` | `false` | Enable dynamic compression |
| `compressor_threshold_db` | `float` | `-12.0` | Compression threshold (-60–0 dB) |
| `compressor_ratio` | `float` | `4.0` | Compression ratio (1–64) |
| `compressor_gain_db` | `float` | `0.0` | Makeup gain (-20–20 dB) |
| `eq_enabled` | `bool` | `false` | Enable 6-band EQ (adjust in Audio panel) |

---

## 7. Script API

### Signals

| Signal | Parameters | Description |
|--------|-----------|-------------|
| `note_triggered` | `channel, pitch, velocity` | Emitted each time a note is triggered |
| `finished` | — | Emitted when playback ends (non-loop mode) |

### Methods

| Method | Description |
|--------|-------------|
| `start_playback(from_position: float = 0.0)` | Start playback from position (seconds) |
| `stop()` | Stop and reset |
| `pause()` | Pause playback |
| `resume()` | Resume playback |
| `seek(position: float)` | Jump to position (seconds) |
| `get_playback_position() -> float` | Get current position (seconds) |
| `is_playing() -> bool` | Whether currently playing |
| `get_duration() -> float` | Get total duration (seconds) |

---

## 8. LLM-Assisted Composition

Clef includes a Claude Code-powered multi-agent composition system. Use `/clef-compose` in Claude Code to generate MIDI music from natural language descriptions.

For full details, see [LLM Composition Guide](user_docs/llm_midi_composer_guide_en.md).

---

## 9. Python Toolchain

The Clef composition system uses Python scripts for ABC notation processing. To set up:

1. Open a terminal in the `.claude/` directory
2. Run `setup.bat` (Windows) or `bash setup.sh` (Linux/macOS)
3. This creates an isolated `.venv` with `mido` and `music21`

Key scripts (under `.claude/skills/clef-compose/scripts/`):

| Script | Purpose |
|--------|---------|
| `abc_to_midi.py` | Convert ABC notation to MIDI |
| `validate_abc.py` | Validate ABC score (6 checks) |
| `merge_abc.py` | Merge multi-voice ABC files |
| `inject_expression.py` | Inject CC/pitch bend expression into MIDI |
| `clef_tools.py` | Analyze MIDI output |

---

## 10. FAQ

**Q: No sound on playback?**
A: Check that a SoundFont is configured in Project Settings → Clef → Default Soundfont, and that the `.sf2` file path is valid.

**Q: The SoundFont browser is empty?**
A: The browser loads after a profile JSON is found. Ensure you have a profile file (bundled profiles are included for GeneralUser GS). See Section 4.5.

**Q: MIDI sounds different from other players?**
A: SoundFont synthesis varies between implementations. Try a different SoundFont or adjust the bus effects (reverb, chorus, EQ).

**Q: Can I use this at runtime in a game?**
A: Yes. `MidiStreamPlayer` is a regular Godot node that works at runtime. Use the script API to control playback in your game.

**Q: How do I get the AI composition feature?**
A: Clone the full repository from GitHub (the Asset Store package only includes the Godot plugin). Then follow the Python toolchain setup in Section 9.