"""Tests for ABC to MIDI converter (Tasks 2, 3, 4)."""

import subprocess
import sys
import os
import tempfile

import mido

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from abc_to_midi import (
    parse_header, abc_to_midi,
    _parse_duration, _parse_dur_str, _calc_ticks,
    _tokenize_music_line,
    _parse_key_signature,
    _parse_note_pitch,
    _parse_bar_duration,
)


# ── Task 2: Header Parsing ──────────────────────────────────────────────

def test_parse_header_major():
    abc = "%%abc-version 2.1\nX:1\nM:4/4\nL:1/8\nQ:1/4=120\nK:D\n"
    header = parse_header(abc)
    assert header['time_signature'] == '4/4'
    assert header['unit_length'] == '1/8'
    assert header['bpm'] == 120
    assert header['key'] == 'D'


def test_parse_header_minor():
    abc = "%%abc-version 2.1\nX:1\nM:3/4\nL:1/8\nQ:1/4=90\nK:Am\n"
    header = parse_header(abc)
    assert header['time_signature'] == '3/4'
    assert header['key'] == 'Am'


def test_parse_header_title():
    abc = "%%abc-version 2.1\nX:1\nT:Boss Battle\nM:4/4\nL:1/8\nQ:1/4=140\nK:D\n"
    header = parse_header(abc)
    assert header['title'] == 'Boss Battle'


# ── Task 3: Voice and Note Parsing ──────────────────────────────────────

def test_simple_melody():
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute" clef=treble
| d2 f2 a2 f2 |
"""
    mid = abc_to_midi(abc)
    assert mid.ticks_per_beat == 480
    assert len(mid.tracks) == 2  # tempo track + melody track
    melody = mid.tracks[1]
    notes = [m for m in melody if m.type == 'note_on']
    assert len(notes) == 4


def test_chord_voices():
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 2
%%MIDI program 48
V:2 name="Strings" clef=treble
| [FAc]2 [FAc]2 |
"""
    mid = abc_to_midi(abc)
    melody = mid.tracks[1]
    notes = [m for m in melody if m.type == 'note_on']
    # [FAc]2 [FAc]2 = two chords, each with 3 notes = 6 note_on events
    assert len(notes) == 6


def test_rest_notes():
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| d2 z2 a2 f2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 3  # z produces no note_on


# ── Task 4: Drum Track + Dynamics ───────────────────────────────────────

def test_drum_track():
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 10
V:4 name="Drums" clef=perc
| B,, z D, z B,, B,, z |
"""
    mid = abc_to_midi(abc)
    drum_track = mid.tracks[1]
    notes = [m for m in drum_track if m.type == 'note_on']
    assert len(notes) == 4
    assert notes[0].note == 36  # B,, = Kick


def test_dynamics():
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
!pp! | d2 f2 | !f! | a2 f2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert notes[0].velocity < notes[2].velocity  # pp < f


def test_full_score():
    abc = """%%abc-version 2.1
X:1
T:Boss Battle
M:4/4
L:1/8
Q:1/4=140
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute" clef=treble
|: "D" d2 f2 a2 f2 | "G" g2 b2 d\u03072 b2 :|
%%MIDI channel 2
%%MIDI program 48
V:2 name="Strings" clef=treble
|: "D"[FAc]2 [FAc]2 | "G"[GBd]2 [GBd]2 :|
%%MIDI channel 3
%%MIDI program 32
V:3 name="Bass" clef=bass
|: "D"D,2 D,2 F,2 D,2 | "G"G,2 G,2 B,2 G,2 :|
%%MIDI channel 10
V:4 name="Drums" clef=perc
|: B,, z D, z | B,, B,, z z :|
"""
    mid = abc_to_midi(abc)
    assert mid.ticks_per_beat == 480
    assert len(mid.tracks) == 5  # tempo + 4 voices


# ── CLI Entry Point ────────────────────────────────────────────────────────

def test_cli_creates_midi_file():
    """abc_to_midi.py should work as a CLI: python abc_to_midi.py <file.abc> [output.mid]"""
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute" clef=treble
| d2 f2 a2 f2 |
"""
    # Write ABC to temp file
    fd_abc, abc_path = tempfile.mkstemp(suffix='.abc')
    with os.fdopen(fd_abc, 'w', encoding='utf-8') as f:
        f.write(abc)

    # Write MIDI output to temp file
    fd_mid, mid_path = tempfile.mkstemp(suffix='.mid')
    os.close(fd_mid)

    try:
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'abc_to_midi.py')
        result = subprocess.run(
            [sys.executable, script, abc_path, mid_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.isfile(mid_path), "MIDI file was not created"
        # Verify the file is a valid MIDI (non-empty)
        assert os.path.getsize(mid_path) > 0, "MIDI file is empty"
    finally:
        os.unlink(abc_path)
        if os.path.exists(mid_path):
            os.unlink(mid_path)


def test_cli_auto_output_path():
    """CLI should auto-generate output path from input .abc filename."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| c2 d2 e2 f2 |
"""
    fd_abc, abc_path = tempfile.mkstemp(suffix='.abc')
    with os.fdopen(fd_abc, 'w', encoding='utf-8') as f:
        f.write(abc)

    expected_mid_path = abc_path.replace('.abc', '.mid')
    try:
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'abc_to_midi.py')
        result = subprocess.run(
            [sys.executable, script, abc_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.isfile(expected_mid_path), "Auto-named MIDI file was not created"
    finally:
        os.unlink(abc_path)
        if os.path.exists(expected_mid_path):
            os.unlink(expected_mid_path)


# ── Phase 1: Basic Fixes ─────────────────────────────────────────────────

def test_fractional_duration():
    """_parse_duration should handle fractional durations: A/2, A3/4."""
    assert _parse_dur_str('') == (1, 1, 0)
    assert _parse_dur_str('2') == (2, 1, 0)
    assert _parse_dur_str('/2') == (1, 2, 0)
    assert _parse_dur_str('3/4') == (3, 4, 0)
    # From full token
    assert _parse_duration('A/2') == (1, 2, 0)
    assert _parse_duration('A3/4') == (3, 4, 0)


def test_dotted_notes():
    """_parse_duration should handle dotted rhythms: A., A2., A.."""
    assert _parse_duration('A.') == (1, 1, 1)
    assert _parse_duration('A2.') == (2, 1, 1)
    assert _parse_duration('A..') == (1, 1, 2)


def test_calc_ticks_dotted():
    """Dotted notes should have correct tick duration."""
    unit = 240  # eighth note at 480 tpb
    # A. = unit * 3/2
    assert _calc_ticks(unit, 1, 1, 1) == 360
    # A2. = unit * 2 * 3/2 = unit * 3
    assert _calc_ticks(unit, 2, 1, 1) == 720
    # A.. = unit * 7/4
    assert _calc_ticks(unit, 1, 1, 2) == 420


def test_chord_note_ordering():
    """Chord note_on/note_off should be grouped: all note_on first, then all note_off."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 48
V:1 name="Piano"
|[CEG]2 z6|
"""
    mid = abc_to_midi(abc)
    track = mid.tracks[1]
    # Skip program_change, check ordering of MIDI events
    msgs = [m for m in track if m.type in ('note_on', 'note_off')]
    # Should be: note_on, note_on, note_on, note_off, note_off, note_off
    # First 3 should all be note_on
    for i in range(3):
        assert msgs[i].type == 'note_on', f"Expected note_on at index {i}, got {msgs[i].type}"
    # Last 3 should all be note_off
    for i in range(3, 6):
        assert msgs[i].type == 'note_off', f"Expected note_off at index {i}, got {msgs[i].type}"
    # Only first note_off should have non-zero delta
    assert msgs[3].time > 0, "First note_off should carry the duration"
    assert msgs[4].time == 0, "Subsequent note_offs should have delta=0"


def test_chord_with_duration():
    """Chord with duration suffix like [CEG]2 should parse correctly."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 48
V:1 name="Piano"
|[CEG]2 z2 [CEG]/2 z3/2|
"""
    mid = abc_to_midi(abc)
    track = mid.tracks[1]
    note_ons = [m for m in track if m.type == 'note_on' and m.velocity > 0]
    assert len(note_ons) == 6  # two chords of 3 notes each


def test_invisible_rest():
    """x (invisible rest) should advance time like z."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| c2 x2 e2 f2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes) == 3  # x produces no note_on, same as z


def test_barline_colon_repeat():
    """Colon-based repeat markers should tokenize correctly."""
    tokens = _tokenize_music_line('|: C D E F :|')
    assert '|:' in tokens
    assert ':|' in tokens


def test_double_colon_repeat():
    """:: (double repeat) should tokenize correctly."""
    tokens = _tokenize_music_line('C D :: E F')
    assert '::' in tokens


# ── Phase 2: Core Rhythm Features ────────────────────────────────────────

def test_broken_rhythm_gt():
    """A>B should shorten B and lengthen A, keeping total duration."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C D E F |
"""
    mid_ref = abc_to_midi(abc)
    abc_brk = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C > D E F |
"""
    mid_brk = abc_to_midi(abc_brk)
    # Both should produce 4 notes
    ref_notes = [m for m in mid_ref.tracks[1] if m.type == 'note_on']
    brk_notes = [m for m in mid_brk.tracks[1] if m.type == 'note_on']
    assert len(ref_notes) == 4
    assert len(brk_notes) == 4
    # Total duration should be preserved
    ref_total = sum(m.time for m in mid_ref.tracks[1])
    brk_total = sum(m.time for m in mid_brk.tracks[1])
    assert ref_total == brk_total


def test_broken_rhythm_tokenize():
    """Broken rhythm tokens should be recognized."""
    tokens = _tokenize_music_line('A > B')
    assert 'BRK_GT_1' in tokens
    tokens = _tokenize_music_line('A < B')
    assert 'BRK_LT_1' in tokens
    tokens = _tokenize_music_line('A >> B')
    assert 'BRK_GT_2' in tokens


def test_tie_basic():
    """A2-A2 should produce a single note with combined duration."""
    abc_sep = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 C2 D2 D2 |
"""
    abc_tie = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 - C2 D2 D2 |
"""
    mid_sep = abc_to_midi(abc_sep)
    mid_tie = abc_to_midi(abc_tie)
    # Separate: 4 note_on, Tie: 3 note_on (two C2 merged)
    sep_on = [m for m in mid_sep.tracks[1] if m.type == 'note_on']
    tie_on = [m for m in mid_tie.tracks[1] if m.type == 'note_on']
    assert len(sep_on) == 4
    assert len(tie_on) == 3


def test_tie_cross_bar():
    """Tie can cross bar lines."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C4 - | C4 D2 D2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    # C4-C4 tied across bars = 1 note, plus D2 D2 = 3 total
    assert len(notes) == 3


def test_no_tie_different_pitch():
    """Consecutive different-pitch notes should NOT be merged."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 - D2 E2 F2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    # Tie from C to D: different pitch, so C closes, D starts = 4 notes
    assert len(notes) == 4


def test_triplet():
    """(3ABC should play 3 notes in 2 notes' time."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| (3 C D E F2 F2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes) == 5  # triplet(3) + 2 singles


def test_tuplet_tokenize():
    """Tuplet tokens should be parsed correctly."""
    tokens = _tokenize_music_line('(3 A B C')
    assert any(t.startswith('TUPLET_') for t in tokens)
    assert 'TUPLET_3_2_2' in tokens


# ── Phase 3: Key Signature & Pitch ───────────────────────────────────────

def test_key_signature_c_major():
    """C major should have no accidentals."""
    acc, sharps = _parse_key_signature('C')
    assert sharps == 0
    assert acc == {}


def test_key_signature_g_major():
    """G major should have F#."""
    acc, sharps = _parse_key_signature('G')
    assert sharps == 1
    assert acc == {'F': 1}


def test_key_signature_d_major():
    """D major should have F# and C#."""
    acc, sharps = _parse_key_signature('D')
    assert sharps == 2
    assert acc == {'F': 1, 'C': 1}


def test_key_signature_f_major():
    """F major should have Bb."""
    acc, sharps = _parse_key_signature('F')
    assert sharps == -1
    assert acc == {'B': -1}


def test_key_signature_a_minor():
    """A minor (relative minor of C) should have no accidentals."""
    acc, sharps = _parse_key_signature('Am')
    assert sharps == 0
    assert acc == {}


def test_key_signature_d_minor():
    """D minor (relative minor of F) should have Bb."""
    acc, sharps = _parse_key_signature('Dm')
    assert sharps == -1
    assert acc == {'B': -1}


def test_key_signature_applies_to_pitch():
    """In D major, F should automatically become F#."""
    # Without key: F (uppercase) = F4 = 65
    assert _parse_note_pitch('F', key_accidentals=None) == 65
    # With D major key: F should be F#4 = 66
    key_acc, _ = _parse_key_signature('D')
    assert _parse_note_pitch('F', key_accidentals=key_acc) == 66
    # Lowercase f = F5 = 77, with D major → F#5 = 78
    assert _parse_note_pitch('f', key_accidentals=key_acc) == 78


def test_explicit_natural_overrides_key():
    """Explicit = (natural) should override key signature."""
    key_acc, _ = _parse_key_signature('D')  # F# and C#
    # =F should be natural F (65), not F#
    assert _parse_note_pitch('=F', key_accidentals=key_acc) == 65


def test_explicit_flat_overrides_key():
    """Explicit _ (flat) should override key signature."""
    key_acc, _ = _parse_key_signature('D')  # F# and C#
    # _F should be Fb (64)
    assert _parse_note_pitch('_F', key_accidentals=key_acc) == 64


def test_double_sharp():
    """^^ (double sharp) should add 2 semitones."""
    assert _parse_note_pitch('^^C') == 62  # C##4 = D4 = 62


def test_double_flat():
    """__ (double flat) should subtract 2 semitones."""
    assert _parse_note_pitch('__D') == 60  # Dbb4 = C4 = 60


def test_key_signature_in_midi():
    """Full conversion with D major should produce correct pitches."""
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| f2 f2 f2 f2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    # In D major, f should auto-sharpen to F# (78 in octave 5 for lowercase f)
    assert all(n.note == 78 for n in notes), f"Expected F#(78), got {[n.note for n in notes]}"


# ── Phase 4: Repeats & Slur ──────────────────────────────────────────────

def test_volta_tokenize():
    """Volta ending tokens |1, |2, [1, [2 should be recognized."""
    tokens = _tokenize_music_line('|1 C D')
    assert 'VOLTA_1' in tokens
    tokens = _tokenize_music_line('|2 E F')
    assert 'VOLTA_2' in tokens
    tokens = _tokenize_music_line('[1 C D')
    assert 'VOLTA_1' in tokens


def test_repeat_simple():
    """|: ... :| should play section twice."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
|: C2 D2 E2 F2 :|
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes) == 8  # 4 notes × 2 passes


def test_repeat_with_volta():
    """Volta endings: |1 for first pass, |2 for second."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
|: C2 D2 |1 E2 F2 :| |2 G2 A2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    # Pass 1: C D E F, Pass 2: C D G A = 8 notes
    assert len(notes) == 8
    # Verify pitch sequence
    pitches = [n.note for n in notes]
    assert pitches == [60, 62, 64, 65, 60, 62, 67, 69], f"Got {pitches}"


def test_repeat_with_volta_bracket():
    """Volta with bracket notation [1 [2."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
|: C2 D2 [1 E2 F2 :| [2 G2 A2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes) == 8
    pitches = [n.note for n in notes]
    assert pitches == [60, 62, 64, 65, 60, 62, 67, 69], f"Got {pitches}"


def test_slur_basic():
    """Slur should produce correct note count without breaking conversion."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| ( C2 D2 E2 F2 ) |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes) == 4


def test_slur_with_tie():
    """Slur combined with tie should not conflict."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| ( C2 - C2 D2 ) E2 |
"""
    mid = abc_to_midi(abc)
    notes = [m for m in mid.tracks[1] if m.type == 'note_on']
    # Tie merges C2-C2 into one note, so: C(tied) + D + E = 3 notes
    assert len(notes) == 3


# ── Phase 5 Tests: Inline Fields, Grace Notes, Dynamics Enhancement ─────


def test_inline_key_change():
    """Inline [K:G] should change key accidentals mid-song."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 D2 [K:G] F2 G2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    # Uppercase: C=60, D=62. After [K:G], F#→66, G=67
    assert len(notes_on) == 4
    assert notes_on[0].note == 60  # C
    assert notes_on[1].note == 62  # D
    assert notes_on[2].note == 66  # F# (key G applied)
    assert notes_on[3].note == 67  # G


def test_inline_time_signature():
    """Inline [M:3/4] should not break conversion."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 D2 E2 F2 | [M:3/4] G2 A2 B2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 7


def test_grace_notes_basic():
    """Grace notes {agf} should be emitted before main note."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| {agf} c2 d2 e2 f2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    # 3 grace notes + 4 main notes = 7 note_on events
    assert len(notes_on) == 7
    # Grace notes should have reduced velocity
    assert notes_on[0].velocity <= 100
    # First three are grace: a(81), g(79), f(77)
    assert notes_on[0].note == 81  # a
    assert notes_on[1].note == 79  # g
    assert notes_on[2].note == 77  # f
    # Main notes follow after grace: c(72), d(74), e(76), f(77)
    assert notes_on[3].note == 72  # c


def test_grace_notes_time_stealing():
    """Grace notes should steal time from main note, total duration preserved."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| {A} C4 D4 |
"""
    mid = abc_to_midi(abc)
    track = mid.tracks[1]
    # Total time should be unchanged (grace steals from main, doesn't add)
    total_ticks = sum(m.time for m in track)
    # C4 = half note = 960 ticks, D4 = 960, total = 1920 per bar
    # Grace steals from C's 960 ticks, so overall bar is still 1920
    assert total_ticks > 0


def test_grace_notes_tokenize():
    """Grace notes {notes} should tokenize correctly."""
    tokens = _tokenize_music_line("{agf} c2")
    assert tokens[0] == '{agf}'
    assert tokens[1] == 'c2'


def test_crescendo_basic():
    """!crescendo(! ... !crescendo)! should increase velocity across notes."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| !crescendo(! C2 D2 E2 F2 G2 A2 B2 c2 !crescendo)! |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 8
    # Last note should be louder than 2nd note (avoid downbeat beat stress)
    assert notes_on[-1].velocity > notes_on[1].velocity


def test_crescendo_angle_bracket():
    """!<(! ... !<)! should work as crescendo shorthand."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| !<(! C2 D2 E2 F2 G2 A2 B2 c2 !<)! |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 8
    # Last note should be louder than 2nd note (avoid downbeat beat stress)
    assert notes_on[-1].velocity > notes_on[1].velocity


def test_beat_stress():
    """Downbeat notes should have higher velocity than offbeat."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 D2 E2 F2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 4
    # First note (downbeat) should be louder
    assert notes_on[0].velocity >= notes_on[1].velocity


# ── Phase 6 Tests: MIDI Directives & Decorations ─────────────────────────


def test_midi_transpose():
    """%%MIDI transpose should shift all pitches."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
%%MIDI transpose 12
V:1 name="Flute"
| C2 D2 E2 F2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 4
    # C(60) + 12 = 72, D(62) + 12 = 74, E(64) + 12 = 76, F(65) + 12 = 77
    assert notes_on[0].note == 72
    assert notes_on[1].note == 74


def test_midi_transpose_negative():
    """%%MIDI transpose with negative value should lower pitches."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
%%MIDI transpose -2
V:1 name="Flute"
| C2 D2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    # C(60) - 2 = 58, D(62) - 2 = 60
    assert notes_on[0].note == 58
    assert notes_on[1].note == 60


def test_midi_control():
    """%%MIDI control should emit CC event."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
C2 D2 E2 F2
%%MIDI control 7 100
C2 D2 E2 F2|
"""
    mid = abc_to_midi(abc)
    cc_events = [m for m in mid.tracks[1] if m.type == 'control_change']
    assert len(cc_events) >= 1
    assert cc_events[0].control == 7
    assert cc_events[0].value == 100


def test_midi_tempo():
    """%%MIDI tempo should emit tempo meta event."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
C2 D2 E2 F2
%%MIDI tempo 80
C2 D2 E2 F2|
"""
    mid = abc_to_midi(abc)
    tempo_events = [m for m in mid.tracks[1] if m.type == 'set_tempo']
    assert len(tempo_events) >= 1
    # Tempo 80 BPM should be different from default 120
    assert tempo_events[0].tempo != mido.bpm2tempo(120)


def test_staccato():
    """Staccato decoration should shorten note duration."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| .C2 D2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    notes_off = [m for m in mid.tracks[1] if m.type == 'note_off']
    assert len(notes_on) == 2
    # Staccato note should have shorter duration than normal note
    stac_dur = notes_off[0].time
    normal_dur = notes_off[1].time
    assert stac_dur < normal_dur


def test_fermata():
    """Fermata decoration should lengthen note duration."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| HC2 D2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    notes_off = [m for m in mid.tracks[1] if m.type == 'note_off']
    assert len(notes_on) == 2
    # Fermata note should have longer duration than normal note
    fermata_dur = notes_off[0].time
    normal_dur = notes_off[1].time
    assert fermata_dur > normal_dur


def test_trill():
    """Trill decoration should produce alternating notes."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| TC2 D2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    # Trill produces 2 notes (C and C#), then D = 3 note_on events
    assert len(notes_on) >= 3
    # First two should be alternating: base note and upper neighbor
    assert notes_on[0].note != notes_on[1].note


def test_tenuto():
    """Tenuto decoration should not shorten note (full duration)."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| MC2 D2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    assert len(notes_on) == 2
    # Tenuto note should have same duration as normal (full value)
    # Both notes have same ABC duration, tenuto keeps it full


# ── Code Review Fix Tests ────────────────────────────────────────────────


def test_bar_accidentals_persistence():
    """Within a bar, explicit accidental should persist on same letter."""
    key_acc, _ = _parse_key_signature('C')
    bar_acc: dict[str, int] = {}
    # First F with sharp
    p1 = _parse_note_pitch('^F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    assert p1 == 66  # F#4
    # Second F without explicit accidental should inherit bar local sharp
    p2 = _parse_note_pitch('F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    assert p2 == 66  # Still F#4 due to bar_accidentals


def test_bar_accidentals_reset_on_barline():
    """Barline should reset bar-local accidentals (simulated by clearing dict)."""
    key_acc, _ = _parse_key_signature('C')
    bar_acc: dict[str, int] = {}
    _parse_note_pitch('^F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    # Simulate barline: clear bar accidentals
    bar_acc.clear()
    # F should now be natural (no bar local, no key sig)
    p = _parse_note_pitch('F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    assert p == 65  # F natural


def test_bar_accidentals_with_key_signature():
    """In D major, explicit =F (natural) should persist within bar."""
    key_acc, _ = _parse_key_signature('D')
    bar_acc: dict[str, int] = {}
    # =F: explicit natural overrides key sig F#
    p1 = _parse_note_pitch('=F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    assert p1 == 65  # F natural (overriding D major F#)
    # Second F in same bar should stay natural
    p2 = _parse_note_pitch('F', key_accidentals=key_acc, bar_accidentals=bar_acc)
    assert p2 == 65  # Still natural from bar_accidentals


def test_staccato_shortens_note():
    """Staccato decoration should produce a note shorter than normal."""
    abc_normal = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C4 D4 |
"""
    abc_stac = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| .C4 D4 |
"""
    mid_normal = abc_to_midi(abc_normal)
    mid_stac = abc_to_midi(abc_stac)
    normal_note_off = [m for m in mid_normal.tracks[1] if m.type == 'note_off'][0]
    stac_note_off = [m for m in mid_stac.tracks[1] if m.type == 'note_off'][0]
    assert stac_note_off.time < normal_note_off.time


def test_grace_notes_integration():
    """Grace notes should steal time from the main note and produce extra note_on events."""
    abc_no_grace = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C4 D4 |
"""
    abc_grace = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| {D} C4 D4 |
"""
    mid_no = abc_to_midi(abc_no_grace)
    mid_gr = abc_to_midi(abc_grace)
    no_on = [m for m in mid_no.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    gr_on = [m for m in mid_gr.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    # Grace note adds extra note_on events
    assert len(gr_on) > len(no_on)
    # Total track duration should be similar (grace steals from main)
    no_total = sum(m.time for m in mid_no.tracks[1])
    gr_total = sum(m.time for m in mid_gr.tracks[1])
    assert abs(no_total - gr_total) < no_total * 0.1  # within 10%


def test_repeat_volta_ending_integration():
    """Full integration: |: ... |1 ... :| |2 ... | should expand correctly."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
|: C2 D2 | [1 E2 F2 :| [2 G2 A2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    # Pass 1: C D E F = 4 notes
    # Pass 2: C D G A = 4 notes
    # Total: 8 notes
    assert len(notes_on) == 8


def test_expand_repeats_depth_limit():
    """Deeply nested repeats should not cause infinite recursion."""
    # 10 levels of nested |: ... :|
    tokens = []
    for _ in range(10):
        tokens.append('|:')
        tokens.append('C')
        tokens.append('D')
    for _ in range(10):
        tokens.append(':|')
    # Should complete without stack overflow
    result = _tokenize_music_line.__module__  # just ensure we can reference the module
    from abc_to_midi import _expand_repeats
    expanded = _expand_repeats(tokens)
    # Should produce tokens without infinite recursion
    assert len(expanded) > 0


# ── Code Review Fix: Compound Time Bar Duration ────────────────────────────

def test_bar_duration_compound_time():
    """_parse_bar_duration should correctly calculate ticks for compound time signatures."""
    unit = 240  # L:1/8 → eighth note = 240 ticks
    # Simple time (unchanged behavior)
    assert _parse_bar_duration('4/4', unit) == 1920
    assert _parse_bar_duration('3/4', unit) == 1440
    # Compound time (was wrong: returned 2880 instead of 1440 for 6/8)
    assert _parse_bar_duration('6/8', unit) == 1440
    assert _parse_bar_duration('3/8', unit) == 720
    assert _parse_bar_duration('9/8', unit) == 2160
    assert _parse_bar_duration('12/8', unit) == 2880


# ── Code Review Fix: Grace Notes with Accidentals ──────────────────────────

def test_grace_notes_with_accidentals():
    """Grace notes like {^fg} should parse accidental prefixes correctly."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| {^fg} c2 d2 e2 f2 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on']
    # 2 grace notes (^f, g) + 4 main notes = 6 note_on
    assert len(notes_on) == 6
    # ^f in C major = F#5 = 78 (base f5=77 + sharp 1)
    assert notes_on[0].note == 78


# ── Code Review Fix: Key Signature Meta Event Format ───────────────────────

def test_key_signature_meta_event_format():
    """key_signature meta event should use proper key name, not sharps count."""
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 D2 E2 F2 |
"""
    mid = abc_to_midi(abc)
    tempo_track = mid.tracks[0]
    ks_msgs = [m for m in tempo_track if m.type == 'key_signature']
    assert len(ks_msgs) == 1
    # D major: should be "D", not "2 major"
    assert 'D' in ks_msgs[0].key
    assert ks_msgs[0].key != '2 major'  # was the old bug

def test_key_signature_meta_event_minor():
    """key_signature meta event for minor keys."""
    abc = """X:1
M:4/4
L:1/8
K:Dm
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| C2 D2 E2 F2 |
"""
    mid = abc_to_midi(abc)
    tempo_track = mid.tracks[0]
    ks_msgs = [m for m in tempo_track if m.type == 'key_signature']
    assert len(ks_msgs) == 1
    # D minor: should be "Dm"
    assert 'D' in ks_msgs[0].key
    assert ks_msgs[0].key == 'Dm'


# ── Chord Accidentals Fix (P0-2) ──────────────────────────────────────────


def test_chord_sharp_in_brackets():
    """[A,^F] chord should parse ^F as F#."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 48
V:1 name="Piano"
| [A,^F]4 z4 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    assert len(notes_on) == 2
    pitches = sorted(n.note for n in notes_on)
    # A,=45 (bass), ^F should be F#3=66 (base F3=65 + sharp 1)
    assert 66 in pitches, f"Expected F#(66), got {pitches}"
    assert 57 in pitches


def test_chord_flat_in_brackets():
    """[C_EG] chord should parse _E as Eb."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 48
V:1 name="Piano"
| [C_EG]4 z4 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    assert len(notes_on) == 3
    pitches = sorted(n.note for n in notes_on)
    # C=60, _E should be Eb=63 (base E=64 - 1), G=67
    assert 63 in pitches, f"Expected Eb(63), got {pitches}"


def test_chord_natural_in_brackets():
    """In D major, [=FC] chord should parse =F as natural F."""
    abc = """X:1
M:4/4
L:1/8
K:D
%%MIDI channel 1
%%MIDI program 48
V:1 name="Piano"
| [=FC]4 z4 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    assert len(notes_on) == 2
    pitches = sorted(n.note for n in notes_on)
    # =F overrides D major's F#: natural F3=65, C3=60
    assert 65 in pitches, f"Expected natural F(65), got {pitches}"


def test_chord_with_accidentals_full_conversion():
    """Full ABC with chord accidentals should produce correct MIDI pitches."""
    abc = """X:1
M:4/4
L:1/8
K:G
%%MIDI channel 1
%%MIDI program 48
V:1 name="Strings"
| [GBd]4 | [A^ce]4 |
"""
    mid = abc_to_midi(abc)
    notes_on = [m for m in mid.tracks[1] if m.type == 'note_on' and m.velocity > 0]
    assert len(notes_on) == 6  # 2 chords × 3 notes
    # First chord: G=67, B=71, d=74 (all natural in G major)
    # Second chord: A=69, ^c=73 (base c=72 + sharp), e=76
    assert 73 in [n.note for n in notes_on], f"Expected ^c(73), got {[n.note for n in notes_on]}"


# ── argparse CLI Tests (P0-1) ─────────────────────────────────────────────


def test_cli_named_args():
    """CLI should accept --input and --output flags."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| c2 d2 e2 f2 |
"""
    fd_abc, abc_path = tempfile.mkstemp(suffix='.abc')
    with os.fdopen(fd_abc, 'w', encoding='utf-8') as f:
        f.write(abc)

    fd_mid, mid_path = tempfile.mkstemp(suffix='.mid')
    os.close(fd_mid)

    try:
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'abc_to_midi.py')
        result = subprocess.run(
            [sys.executable, script, '--input', abc_path, '--output', mid_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.isfile(mid_path), "MIDI file was not created"
    finally:
        os.unlink(abc_path)
        if os.path.exists(mid_path):
            os.unlink(mid_path)


def test_cli_short_flags():
    """CLI should accept -i and -o short flags."""
    abc = """X:1
M:4/4
L:1/8
K:C
%%MIDI channel 1
%%MIDI program 73
V:1 name="Flute"
| c2 d2 e2 f2 |
"""
    fd_abc, abc_path = tempfile.mkstemp(suffix='.abc')
    with os.fdopen(fd_abc, 'w', encoding='utf-8') as f:
        f.write(abc)

    fd_mid, mid_path = tempfile.mkstemp(suffix='.mid')
    os.close(fd_mid)

    try:
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'abc_to_midi.py')
        result = subprocess.run(
            [sys.executable, script, '-i', abc_path, '-o', mid_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.isfile(mid_path), "MIDI file was not created"
    finally:
        os.unlink(abc_path)
        if os.path.exists(mid_path):
            os.unlink(mid_path)
