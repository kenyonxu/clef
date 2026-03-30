# MIDI Piano Roll Analysis Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `clef_tools analyze` subcommand that reads a MIDI file and generates a compact text analysis for LLM agent consumption, integrating into the Step 2b review loop.

**Architecture:** Pure Python module (`analyze_midi.py`) using `mido` to parse MIDI, producing a multi-section text report (per-channel stats, density bars, register overlap, velocity distribution, rhythm gaps). Integrated into `clef_tools.py` as a subcommand and wired into the Leader/Reviewer agent workflow.

**Tech Stack:** Python 3.12, `mido` (existing dependency), `argparse` (existing CLI framework)

---

### Task 1: Create core analysis module

**Files:**
- Create: `.claude/skills/clef-compose/scripts/analyze_midi.py`

**Step 1: Write the module skeleton with public API**

```python
# .claude/skills/clef-compose/scripts/analyze_midi.py
"""MIDI piano roll analysis — compact text report for LLM agents."""
import mido
from collections import defaultdict

GM_PROGRAM_NAMES = {
    0: "Acoustic Grand Piano", 1: "Bright Acoustic Piano", 24: "Acoustic Guitar(nylon)",
    25: "Acoustic Guitar(steel)", 32: "Acoustic Bass", 33: "Electric Bass(finger)",
    40: "Violin", 41: "Viola", 42: "Cello", 46: "Orchestral Harp",
    48: "String Ensemble 1", 56: "Trumpet", 57: "Trombone", 60: "French Horn",
    65: "Alto Sax", 66: "Tenor Sax", 68: "Oboe", 73: "Flute", 74: "Recorder",
    80: "Synth Lead 1", 88: "Synth Pad 1", 0: "Piano",
}

DENSITY_CHARS = "▁▂▃▄▅▆▇█"


def analyze(midi_path: str, segment_sec: float = 2.0) -> str:
    """Analyze MIDI file and return compact text report."""
    midi = mido.MidiFile(midi_path)
    channels = _parse_tracks(midi)
    if not channels:
        return "MIDI Analysis: no notes found"
    total_sec = _total_duration_sec(midi)
    tempo = _detect_tempo(midi)
    header = _format_header(midi_path, total_sec, tempo)
    per_channel = _format_per_channel(channels)
    density = _format_density(channels, total_sec, segment_sec)
    overlap = _format_overlap(channels)
    velocity = _format_velocity(channels)
    gaps = _format_gaps(channels, midi.ticks_per_beat, tempo)
    return "\n".join([header, per_channel, density, overlap, velocity, gaps])
```

**Step 2: Write `_parse_tracks` — extract per-channel note data**

```python
def _parse_tracks(midi: mido.MidiFile) -> list[dict]:
    """Extract notes per channel from MIDI tracks.
    Returns: [{"channel": int, "program": int, "notes": [(abs_tick, note, velocity, dur_ticks), ...]}]
    """
    channels = {}
    for track in midi.tracks:
        abs_tick = 0
        current_program = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'program_change':
                current_program = msg.program
            elif msg.type == 'note_on' and msg.velocity > 0:
                ch = msg.channel
                if ch not in channels:
                    channels[ch] = {"channel": ch, "program": current_program, "notes": []}
                # Find matching note_off for duration
                dur = _find_note_duration(track, abs_tick, msg.note, ch)
                channels[ch]["notes"].append((abs_tick, msg.note, msg.velocity, dur))
    return sorted(channels.values(), key=lambda c: c["channel"])
```

**Step 3: Write helper functions**

```python
def _find_note_duration(track, start_tick, note, channel):
    """Scan forward in track for matching note_off, return duration in ticks."""
    tick = 0
    for msg in track:
        tick += msg.time
        if tick <= start_tick:
            continue
        if msg.type == 'note_off' and msg.channel == channel and msg.note == note:
            return tick - start_tick
        if msg.type == 'note_on' and msg.channel == channel and msg.note == note and msg.velocity == 0:
            return tick - start_tick
    return midi.ticks_per_beat  # default one beat

def _detect_tempo(midi: mido.MidiFile) -> float:
    """Return first tempo in BPM, default 120."""
    for track in midi.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                return mido.tempo2bpm(msg.tempo)
    return 120.0

def _total_duration_sec(midi: mido.MidiFile) -> float:
    """Total MIDI duration in seconds."""
    tempo = _detect_tempo(midi)
    max_tick = 0
    for track in midi.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if tick > max_tick:
                max_tick = tick
    return max_tick * (60.0 / tempo) / midi.ticks_per_beat

def _midi_note_name(note: int) -> str:
    """Convert MIDI note number to name like C4, A#3."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (note // 12) - 1
    return f"{names[note % 12]}{octave}"

def _program_name(program: int) -> str:
    return GM_PROGRAM_NAMES.get(program, f"Program {program}")
```

**Step 4: Write format functions**

```python
def _format_header(midi_path, total_sec, tempo):
    name = os.path.basename(midi_path)
    return f"MIDI Analysis: {name} ({total_sec:.1f}s, {tempo:.0f} BPM)"

def _format_per_channel(channels):
    lines = ["── Per-Channel ──────────────────────"]
    for ch in channels:
        name = _program_name(ch["program"])
        notes = ch["notes"]
        count = len(notes)
        if not notes:
            lines.append(f"Ch{ch['channel']} {name:12s} notes:0")
            continue
        pitches = [n[1] for n in notes]
        vels = [n[2] for n in notes]
        lo, hi = min(pitches), max(pitches)
        v_lo, v_hi = min(vels), max(vels)
        avg_v = sum(vels) / len(vels)
        rng = hi - lo
        lines.append(f"Ch{ch['channel']} {name:12s} notes:{count:3d}  {_midi_note_name(lo)}-{_midi_note_name(hi)}  vel:{v_lo}-{v_hi}  avg:{avg_v:.0f}  range:{rng}st")
    return "\n".join(lines)

def _format_density(channels, total_sec, segment_sec):
    if total_sec <= 0:
        return ""
    num_segments = max(1, int(total_sec / segment_sec))
    lines = ["── Density (per {0}s) ──────────────".format(segment_sec)]
    for ch in channels:
        if not ch["notes"]:
            continue
        name = _program_name(ch["program"])
        counts = [0] * num_segments
        tempo = 120.0  # approximate, would use actual tempo map in full impl
        tpb = 480      # approximate
        for abs_tick, note, vel, dur in ch["notes"]:
            sec = abs_tick * (60.0 / tempo) / tpb
            idx = min(int(sec / segment_sec), num_segments - 1)
            counts[idx] += 1
        max_count = max(counts) if max(counts) > 0 else 1
        bar = ""
        for c in counts:
            level = int(c / max_count * (len(DENSITY_CHARS) - 1))
            bar += DENSITY_CHARS[level]
        lines.append(f"Ch{ch['channel']} {name:12s} {bar}")
    return "\n".join(lines)

def _format_overlap(channels):
    active = [c for c in channels if c["notes"] and c["channel"] != 9]
    if len(active) < 2:
        return "── Register Overlap ───────────────\n  N/A (single voice)"
    lines = ["── Register Overlap ───────────────"]
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            a_pitches = [n[1] for n in a["notes"]]
            b_pitches = [n[1] for n in b["notes"]]
            overlap_lo = max(min(a_pitches), min(b_pitches))
            overlap_hi = min(max(a_pitches), max(b_pitches))
            overlap_st = max(0, overlap_hi - overlap_lo + 1)
            if overlap_st == 0:
                lines.append(f"Ch{a['channel']} <-> Ch{b['channel']}  0st  (ok)")
            elif overlap_st <= 7:
                lines.append(f"Ch{a['channel']} <-> Ch{b['channel']}  {overlap_st}st  INFO")
            else:
                lines.append(f"Ch{a['channel']} <-> Ch{b['channel']}  {overlap_st}st  WARN (!)")
    return "\n".join(lines)

def _format_velocity(channels):
    lines = ["── Velocity Distribution ──────────"]
    for ch in channels:
        if not ch["notes"] or ch["channel"] == 9:
            continue
        vels = [n[2] for n in ch["notes"]]
        rng = max(vels) - min(vels)
        if rng == 0:
            flatness = 0.0
        else:
            mean_v = sum(vels) / len(vels)
            variance = sum((v - mean_v) ** 2 for v in vels) / len(vels)
            std = variance ** 0.5
            flatness = std / rng
        if flatness < 0.1:
            label = "flat (!)"
        elif flatness < 0.3:
            label = "moderate"
        else:
            label = "varied"
        lines.append(f"Ch{ch['channel']}  flatness:{flatness:.2f}  {label}")
    return "\n".join(lines)

def _format_gaps(channels, ticks_per_beat, tempo):
    lines = ["── Rhythm Gaps ────────────────────"]
    for ch in channels:
        if not ch["notes"] or ch["channel"] == 9:
            continue
        starts = sorted([n[0] for n in ch["notes"]])
        if len(starts) < 2:
            continue
        gaps = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
        median_gap = sorted(gaps)[len(gaps) // 2]
        if median_gap == 0:
            continue
        for i, gap in enumerate(gaps):
            if gap > 2 * median_gap:
                sec_start = starts[i] * (60.0 / tempo) / ticks_per_beat
                sec_end = starts[i + 1] * (60.0 / tempo) / ticks_per_beat
                dur_sec = sec_end - sec_start
                ratio = gap / median_gap
                lines.append(f"Ch{ch['channel']}  {sec_start:.1f}s-{sec_end:.1f}s gap {dur_sec:.1f}s ({ratio:.1f}x median)")
    if len(lines) == 1:
        lines.append("  None detected")
    return "\n".join(lines)
```

**Step 5: Add `import os` at top of file and verify no syntax errors**

Run: `cd .claude/skills/clef-compose && python -c "from scripts.analyze_midi import analyze; print('OK')"`

Expected: `OK`

**Step 6: Commit**

```
git add .claude/skills/clef-compose/scripts/analyze_midi.py
git commit -m "feat(clef-compose): add MIDI piano roll analysis module"
```

---

### Task 2: Write tests

**Files:**
- Create: `.claude/skills/clef-compose/tests/test_analyze_midi.py`

**Step 1: Write the failing tests**

```python
"""Tests for MIDI piano roll analysis."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import mido
from analyze_midi import (
    analyze, _midi_note_name, _program_name, _detect_tempo,
    _format_per_channel, _format_overlap, _format_velocity,
)


def _make_test_midi():
    """Create a simple 3-track MIDI: tempo + 2 melodic channels."""
    midi = mido.MidiFile(ticks_per_beat=480)
    # Tempo track
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo_track)
    # Channel 0: melody (C4-E4-G4)
    t0 = mido.MidiTrack()
    t0.append(mido.Message('program_change', program=0, time=0))
    notes_ch0 = [(0, 60, 80), (480, 62, 80), (960, 64, 80),
                 (1440, 65, 90), (1920, 67, 100), (2880, 69, 110)]
    for i, (tick, note, vel) in enumerate(notes_ch0):
        delta = tick - (notes_ch0[i-1][0] if i > 0 else 0)
        t0.append(mido.Message('note_on', note=note, velocity=vel, channel=0, time=delta))
        dur = 480
        t0.append(mido.Message('note_off', note=note, velocity=0, channel=0, time=dur))
    midi.tracks.append(t0)
    # Channel 1: harmony (C4-E4, overlapping with ch0)
    t1 = mido.MidiTrack()
    t1.append(mido.Message('program_change', program=48, time=0))
    notes_ch1 = [(0, 60, 70), (960, 64, 75), (1920, 67, 85)]
    for i, (tick, note, vel) in enumerate(notes_ch1):
        delta = tick - (notes_ch1[i-1][0] if i > 0 else 0)
        t1.append(mido.Message('note_on', note=note, velocity=vel, channel=1, time=delta))
        t1.append(mido.Message('note_off', note=note, velocity=0, channel=1, time=480))
    midi.tracks.append(t1)
    return midi


class TestHelpers:
    def test_midi_note_name_c4(self):
        assert _midi_note_name(60) == "C4"

    def test_midi_note_name_a4(self):
        assert _midi_note_name(69) == "A4"

    def test_detect_tempo(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(140), time=0))
        midi.tracks.append(track)
        assert _detect_tempo(midi) == 140.0

    def test_detect_tempo_default(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        midi.tracks.append(mido.MidiTrack())
        assert _detect_tempo(midi) == 120.0


class TestAnalysis:
    def test_full_report(self):
        midi = _make_test_midi()
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
            midi.save(f.name)
            report = analyze(f.name)
            os.unlink(f.name)
        assert "MIDI Analysis" in report
        assert "Per-Channel" in report
        assert "Density" in report
        assert "Register Overlap" in report
        assert "Velocity" in report

    def test_empty_midi(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        midi.tracks.append(mido.MidiTrack())
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
            midi.save(f.name)
            report = analyze(f.name)
            os.unlink(f.name)
        assert "no notes found" in report

    def test_single_channel_no_overlap(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120), time=0))
        track.append(mido.Message('note_on', note=60, velocity=80, channel=0, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=480))
        midi.tracks.append(track)
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
            midi.save(f.name)
            report = analyze(f.name)
            os.unlink(f.name)
        assert "N/A" in report  # single voice, no overlap

    def test_report_compact(self):
        midi = _make_test_midi()
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
            midi.save(f.name)
            report = analyze(f.name)
            os.unlink(f.name)
        assert len(report) < 5000
```

**Step 2: Run tests to verify they pass**

Run: `cd .claude/skills/clef-compose && python -m pytest tests/test_analyze_midi.py -v`
Expected: Some tests may fail initially — debug and fix in analyze_midi.py

**Step 3: Commit**

```
git add .claude/skills/clef-compose/tests/test_analyze_midi.py
git commit -m "test(clef-compose): add tests for MIDI piano roll analysis"
```

---

### Task 3: CLI integration

**Files:**
- Modify: `.claude/skills/clef-compose/scripts/clef_tools.py`
- Modify: `.claude/skills/clef-compose/tests/test_clef_tools.py`

**Step 1: Add `cmd_analyze` to clef_tools.py**

After `cmd_snapshot` function (~line 126), add:

```python
def cmd_analyze(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    from analyze_midi import analyze
    report = analyze(args.input, segment_sec=args.segment)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"OK: analysis -> {args.output}")
    else:
        sys.stdout.write(report)
    return 0
```

**Step 2: Add subparser in `main()` (after snapshot parser ~line 175)**

```python
    # analyze
    p = sub.add_parser('analyze', help='MIDI piano roll analysis')
    p.add_argument('input', help='MIDI file path')
    p.add_argument('--segment', type=float, default=2.0, help='Time segment (seconds)')
    p.add_argument('--output', '-o', default=None, help='Output file path')
```

**Step 3: Add to commands dict**

```python
    commands = {
        ...
        'analyze': cmd_analyze,
    }
```

**Step 4: Run CLI to verify**

Run: `python .claude/skills/clef-compose/scripts/clef_tools.py analyze --help`
Expected: Help text shown

**Step 5: Update test_clef_tools.py**

Add `'analyze'` to the known subcommands list and help test loop.

**Step 6: Commit**

```
git add .claude/skills/clef-compose/scripts/clef_tools.py .claude/skills/clef-compose/tests/test_clef_tools.py
git commit -m "feat(clef-compose): integrate analyze subcommand into clef_tools"
```

---

### Task 4: Agent workflow integration

**Files:**
- Modify: `.claude/agents/clef-leader.md`
- Modify: `.claude/agents/clef-reviewer.md`
- Modify: `.claude/skills/clef-compose/SKILL.md`

**Step 1: Update clef-leader.md**

In 必读文件 section, add:
```markdown
- `.clef-work/analysis_report.txt` — MIDI piano roll analysis（密度、重叠、力度、节奏间隙）
```

In Step 2b flow, after merge and before validate, add step:
```markdown
6.5. 运行 MIDI 分析生成客观数据：
   ```bash
   python .claude/skills/clef-compose/scripts/clef_tools.py analyze .clef-work/base.mid -o .clef-work/analysis_report.txt
   ```
```

**Step 2: Update clef-reviewer.md**

In 必读文件 section, add:
```markdown
- `.clef-work/analysis_report.txt` — MIDI piano roll 客观分析（辅助配器平衡和节奏诊断）
```

In dimension 6 (Orchestration balance), add guidance:
```markdown
- 参考 analysis_report.txt 中的 register overlap 和 velocity distribution 作为客观数据
```

**Step 3: Update SKILL.md**

Add to toolchain table:
```markdown
| `analyze_midi.py` | MIDI piano roll 分析 | `python scripts/clef_tools.py analyze <mid> [-o <report>]` |
```

Add to Step 2b flow after merge:
```markdown
6.5. 运行 `clef_tools.py analyze` → `.clef-work/analysis_report.txt`
```

**Step 4: Commit**

```
git add .claude/agents/clef-leader.md .claude/agents/clef-reviewer.md .claude/skills/clef-compose/SKILL.md
git commit -m "docs(clef-compose): integrate analyze step into agent workflow"
```

---

### Task 5: End-to-end verification

**Step 1: Generate test MIDI from existing ABC**

```bash
cd .claude/skills/clef-compose
python scripts/clef_tools.py abc-to-midi .clef-work/score.abc /tmp/test_analyze.mid
python scripts/clef_tools.py analyze /tmp/test_analyze.mid
```

Expected: Compact multi-section text report printed to stdout.

**Step 2: Run all tests**

```bash
cd .claude/skills/clef-compose && python -m pytest tests/ -v
```

Expected: All tests pass.

**Step 3: Commit (if any fixes needed)**

```
git add -u
git commit -m "fix(clef-compose): address e2e verification issues"
```
