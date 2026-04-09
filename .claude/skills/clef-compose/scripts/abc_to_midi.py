"""ABC notation to MIDI converter.

Supports a subset of ABC 2.1 notation as defined in the clef-compose design:
- Header fields: X, T, M, L, Q, K, %%abc-version
- MIDI directives: %%MIDI channel, %%MIDI program
- Voice declarations: V:N name="..." clef=...
- Notes with octave marks (U+0307 dot above, U+0323 dot below)
- Durations, rests, chords, bar lines, dynamics
- GM percussion mapping for channel 10
"""

import io
import re
import sys
from pathlib import Path
from typing import Optional

import mido


# ── Constants ────────────────────────────────────────────────────────────

TICKS_PER_BEAT = 480
DEFAULT_VELOCITY = 96

# Pre-compiled regex patterns
_RE_DURATION_SUFFIX = re.compile(r'[\d/\.]+$')
_RE_BPM = re.compile(r'(\d+)/\d+=(\d+)')
_RE_MIDI_CHANNEL = re.compile(r'channel\s+(\d+)')
_RE_MIDI_PROGRAM = re.compile(r'program\s+(\d+)')
_RE_MIDI_TRANSPOSE = re.compile(r'transpose\s+(-?\d+)')
_RE_MIDI_CONTROL = re.compile(r'control\s+(\d+)\s+(\d+)')
_RE_MIDI_TEMPO = re.compile(r'tempo\s+(\d+)')
_RE_VOLTA_NUM = re.compile(r'VOLTA_(\d+)')
_RE_INLINE_FIELD = re.compile(r'([A-Za-z]):(.*)')
_RE_EMBEDDED_CTRL = re.compile(r'__MIDI_CTRL:(\d+):(\d+)__')
_RE_EMBEDDED_TEMPO = re.compile(r'__MIDI_TEMPO:(\d+)__')
_RE_VOICE_NAME = re.compile(r'name="([^"]*)"')
_RE_VOICE_CLEF = re.compile(r'clef=(\w+)')

DYNAMICS_MAP = {
    'pp': 48,
    'p': 64,
    'mp': 80,
    'mf': 96,
    'f': 112,
    'ff': 127,
}

# ABC 2.1 standard pitch mapping: uppercase = C4 octave, lowercase = C5 octave
# C = C4 = MIDI 60 (middle C), c = C5 = MIDI 72
NOTE_PITCH = {
    'C': 60, 'D': 62, 'E': 64, 'F': 65, 'G': 67, 'A': 69, 'B': 71,
    'c': 72, 'd': 74, 'e': 76, 'f': 77, 'g': 79, 'a': 81, 'b': 83,
}

# Drum mapping for percussion channel (note name -> GM percussion number)
DRUM_MAP = {
    'B,,': 36,  # Kick
    'D,': 38,   # Snare
    'F,': 42,   # Closed Hi-Hat
    'G,': 46,   # Open Hi-Hat
    'A,': 49,   # Crash
    'c': 51,    # Ride
    'd': 50,    # High Tom
    'e': 47,    # Mid Tom
    'f': 45,    # Low Tom
}


# ── Key Signature ────────────────────────────────────────────────────────

# Circle of fifths: order in which sharps/flats are added
SHARPS_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
FLATS_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']

# Root name → number of sharps (negative = flats)
_KEY_SHARPS = {
    # Major
    'C': 0, 'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5,
    'F#': 6, 'C#': 7, 'F': -1, 'Bb': -2, 'Eb': -3,
    'Ab': -4, 'Db': -5, 'Gb': -6, 'Cb': -7,
    # Minor (relative minor is 3 semitones below major)
    'Am': 0, 'Em': 1, 'Bm': 2, 'F#m': 3, 'C#m': 4, 'G#m': 5,
    'Dm': -1, 'Gm': -2, 'Cm': -3, 'Fm': -4, 'Bbm': -5, 'Ebm': -6, 'Abm': -7,
}

# Reverse mapping: sharps count -> (major key name, minor key name)
_SHARPS_TO_KEY = {
    0: ('C', 'A'), 1: ('G', 'E'), 2: ('D', 'B'), 3: ('A', 'F#'),
    4: ('E', 'C#'), 5: ('B', 'G#'), 6: ('F#', 'D#'), 7: ('C#', 'A#'),
    -1: ('F', 'D'), -2: ('Bb', 'G'), -3: ('Eb', 'C'), -4: ('Ab', 'F'),
    -5: ('Db', 'Bb'), -6: ('Gb', 'Eb'), -7: ('Cb', 'Ab'),
}


def _parse_key_signature(key_str: str) -> tuple[dict[str, int], int]:
    """Parse K: field into key accidentals and sharps count.

    Returns (accidental_map, sharps_count).
    accidental_map: {'F': 1, 'C': 1, ...}  letter → semitone offset
    sharps_count: positive = sharps, negative = flats
    """
    key = key_str.strip().split()[0] if key_str.strip() else 'C'
    # Normalize: lowercase root, keep trailing 'm' for minor
    # Handle "major"/"minor" suffixes
    key_lower = key.lower()
    if key_lower.endswith('major'):
        key = key[:-(len('major'))].strip()
    elif key_lower.endswith('minor'):
        root = key[:-(len('minor'))].strip()
        key = root + 'm'

    sharps = _KEY_SHARPS.get(key, 0)

    # Build accidental map from sharps count
    accidentals: dict[str, int] = {}
    if sharps > 0:
        for i in range(min(sharps, 7)):
            accidentals[SHARPS_ORDER[i]] = 1
    elif sharps < 0:
        for i in range(min(-sharps, 7)):
            accidentals[FLATS_ORDER[i]] = -1

    return accidentals, sharps


# ── Header Parsing ──────────────────────────────────────────────────────

def parse_header(abc_text: str) -> dict:
    """Parse ABC header fields and return as a dictionary."""
    result = {
        'abc_version': None,
        'reference': None,
        'title': '',
        'time_signature': '4/4',
        'unit_length': '1/8',
        'bpm': 120,
        'key': 'C',
    }

    for line in abc_text.splitlines():
        line = line.strip()
        if line.startswith('%%abc-version'):
            result['abc_version'] = line.split(None, 1)[1] if len(line.split()) > 1 else None
        elif line.startswith('X:'):
            result['reference'] = line[2:].strip()
        elif line.startswith('T:'):
            result['title'] = line[2:].strip()
        elif line.startswith('M:'):
            result['time_signature'] = line[2:].strip()
        elif line.startswith('L:'):
            result['unit_length'] = line[2:].strip()
        elif line.startswith('Q:'):
            bpm_match = _RE_BPM.search(line)
            if bpm_match:
                result['bpm'] = int(bpm_match.group(2))
        elif line.startswith('K:'):
            result['key'] = line[2:].strip()
        elif line.startswith('%%MIDI') or line.startswith('V:'):
            # Stop at voice/MIDI directives
            break

    return result


# ── Internal Parsing Helpers ────────────────────────────────────────────

def _parse_unit_length_ticks(unit_length: str) -> int:
    """Convert unit length fraction (e.g. '1/8') to ticks.

    L:1/8 means the default note is an eighth note.
    Eighth note = half a beat = TICKS_PER_BEAT / 2 = 240 ticks.
    """
    try:
        parts = unit_length.split('/')
        if len(parts) != 2:
            return TICKS_PER_BEAT // 2
        denominator = int(parts[1])
        return (TICKS_PER_BEAT * 4) // denominator
    except (ValueError, IndexError, ZeroDivisionError):
        return TICKS_PER_BEAT // 2


def _parse_duration(token: str) -> tuple[int, int, int]:
    """Extract duration from a note or chord token.

    Returns (numerator, denominator, dot_count).
    Handles: A, A2, A/2, A3/4, A., A2., [CEG]2.
    """
    # For chord tokens, extract part after ]
    if token.startswith('[') and ']' in token:
        dur_part = token[token.index(']') + 1:]
    else:
        match = _RE_DURATION_SUFFIX.search(token)
        dur_part = match.group(0) if match else ''

    return _parse_dur_str(dur_part)


def _parse_dur_str(s: str) -> tuple[int, int, int]:
    """Parse a duration string. Returns (num, den, dots).

    '' -> (1,1,0)  '2' -> (2,1,0)  '/2' -> (1,2,0)
    '3/4' -> (3,4,0)  '.' -> (1,1,1)  '2.' -> (2,1,1)
    """
    dots = 0
    i = len(s)
    while i > 0 and s[i - 1] == '.':
        dots += 1
        i -= 1
    s = s[:i]

    if not s:
        return (1, 1, dots)

    if '/' in s:
        parts = s.split('/')
        num = int(parts[0]) if parts[0] else 1
        den = int(parts[1]) if len(parts) > 1 and parts[1] else 2
        return (num, den, dots)

    return (int(s), 1, dots)


def _calc_ticks(unit_ticks: int, num: int, den: int, dots: int) -> int:
    """Calculate MIDI ticks from unit length, duration fraction, and dots."""
    ticks = unit_ticks * num // den
    if dots > 0:
        # Each dot extends by half: 1 dot = ×3/2, 2 dots = ×7/4, etc.
        # Formula: (2^(dots+1) - 1) / 2^dots
        multiplier = (1 << (dots + 1)) - 1
        divisor = 1 << dots
        ticks = ticks * multiplier // divisor
    return ticks


def _count_octave_marks(token: str) -> tuple[int, int]:
    """Count combining dot above (U+0307) and dot below (U+0323) in a token.

    Returns (octaves_up, octaves_down).
    """
    up = token.count('\u0307')
    down = token.count('\u0323')
    return (up, down)


def _parse_note_pitch(
    token: str,
    is_drum: bool = False,
    key_accidentals: Optional[dict[str, int]] = None,
    bar_accidentals: Optional[dict[str, int]] = None,
) -> Optional[int]:
    """Parse a single note token to its MIDI pitch.

    Strips octave marks (Unicode combining chars and standard ,/') and duration suffix.
    For drum channel, uses DRUM_MAP instead of pitch calculation.
    Applies key signature accidentals unless overridden by explicit accidental.
    Tracks measure-local accidentals via bar_accidentals dict (cleared on bar lines).
    """
    # Strip duration suffix (digits, /fraction, dots)
    base = _RE_DURATION_SUFFIX.sub('', token)
    # Strip Unicode combining octave marks
    base = base.replace('\u0307', '').replace('\u0323', '')

    # Count standard ABC octave marks: , = down, ' = up
    commas = base.count(',')
    primes = base.count("'")
    base = base.replace(',', '').replace("'", '')

    if is_drum:
        raw = _RE_DURATION_SUFFIX.sub('', token)
        raw = raw.replace('\u0307', '').replace('\u0323', '')
        return DRUM_MAP.get(raw)

    # Handle accidental prefix: ^^ = double sharp, __ = double flat,
    # ^ = sharp, _ = flat, = = explicit natural
    accidental = None
    if base.startswith('^^'):
        accidental = 2
        base = base[2:]
    elif base.startswith('__'):
        accidental = -2
        base = base[2:]
    elif base.startswith('^'):
        accidental = 1
        base = base[1:]
    elif base.startswith('_'):
        accidental = -1
        base = base[1:]
    elif base.startswith('='):
        accidental = 0  # explicit natural
        base = base[1:]

    if base in NOTE_PITCH:
        pitch = NOTE_PITCH[base]
        octaves_up, octaves_down = _count_octave_marks(token)
        pitch += (octaves_up + primes) * 12
        pitch -= (octaves_down + commas) * 12

        # Apply accidental: explicit > bar local > key signature
        letter = base.upper()
        if accidental is not None:
            pitch += accidental
            # Record explicit accidental in bar state for same-letter notes
            if bar_accidentals is not None:
                bar_accidentals[letter] = accidental
        elif bar_accidentals and letter in bar_accidentals:
            # Bar-local accidental takes precedence (e.g. second F after ^F)
            pitch += bar_accidentals[letter]
        elif key_accidentals:
            pitch += key_accidentals.get(letter, 0)

        return pitch

    return None


def _tokenize_music_line(line: str) -> list[str]:
    """Tokenize a music line into individual elements.

    Handles: notes, rests, chords [...], bar lines, dynamics !...!,
    and skips chord symbol annotations "...".
    """
    tokens: list[str] = []
    i = 0
    length = len(line)

    while i < length:
        ch = line[i]

        # Embedded MIDI directives from _parse_voice_section
        if line[i:].startswith('__MIDI_CTRL:'):
            end = line.index('__', i + 12) if '__' in line[i + 12:] else length
            tokens.append(line[i:end + 2])
            i = end + 2
            continue
        if line[i:].startswith('__MIDI_TEMPO:'):
            end = line.index('__', i + 13) if '__' in line[i + 13:] else length
            tokens.append(line[i:end + 2])
            i = end + 2
            continue

        # Skip whitespace
        if ch in ' \t':
            i += 1
            continue

        # Chord symbol annotation - skip entire "..." string
        if ch == '"':
            j = line.index('"', i + 1) if '"' in line[i + 1:] else length
            i = j + 1
            continue

        # Dynamics !...!
        if ch == '!':
            j = line.index('!', i + 1) if '!' in line[i + 1:] else length
            tokens.append(line[i:j + 1])
            i = j + 1
            continue

        # Volta bracket: [1, [2, etc.
        if ch == '[' and i + 1 < length and line[i + 1].isdigit():
            tokens.append(f'VOLTA_{line[i + 1]}')
            i += 2
            continue

        # Inline field: [K:G], [M:3/4], etc.
        if ch == '[' and i + 2 < length and line[i + 1].isalpha() and line[i + 2] == ':':
            j = line.index(']', i + 1) if ']' in line[i + 1:] else length
            tokens.append(line[i:j + 1])
            i = j + 1
            continue

        # Grace notes: {notes}
        if ch == '{':
            j = line.index('}', i + 1) if '}' in line[i + 1:] else length
            tokens.append(line[i:j + 1])
            i = j + 1
            continue

        # Chord [notes] with optional duration
        if ch == '[':
            j = line.index(']', i + 1) if ']' in line[i + 1:] else length
            end = j + 1
            # Collect duration after ]: digits, optional /digits, optional dots
            while end < length and line[end].isdigit():
                end += 1
            if end < length and line[end] == '/':
                end += 1
                while end < length and line[end].isdigit():
                    end += 1
            while end < length and line[end] == '.':
                end += 1
            tokens.append(line[i:end])
            i = end
            continue

        # Bar lines and repeats
        if ch == '|':
            if i + 1 < length and line[i + 1] == '|':
                tokens.append('||')
                i += 2
            elif i + 1 < length and line[i + 1] == ':':
                tokens.append('|:')
                i += 2
            elif i + 1 < length and line[i + 1] == ']':
                tokens.append('|]')
                i += 2
            elif i + 1 < length and line[i + 1].isdigit():
                # Volta ending: |1, |2, etc.
                tokens.append('|')
                tokens.append(f'VOLTA_{line[i + 1]}')
                i += 2
            else:
                tokens.append('|')
                i += 1
            continue

        if ch == ':':
            if i + 1 < length and line[i + 1] == '|':
                tokens.append(':|')
                i += 2
            elif i + 1 < length and line[i + 1] == ':':
                tokens.append('::')
                i += 2
            else:
                i += 1
            continue

        # Broken rhythm: < > << >> <<< >>>
        if ch in ('<', '>'):
            count = 0
            while i < length and line[i] == ch:
                count += 1
                i += 1
            tag = 'GT' if ch == '>' else 'LT'
            tokens.append(f'BRK_{tag}_{count}')
            continue

        # Tie
        if ch == '-':
            tokens.append('TIE')
            i += 1
            continue

        # Tuplet or slur
        if ch == '(':
            if i + 1 < length and line[i + 1].isdigit():
                j = i + 1
                n_str = ''
                while j < length and line[j].isdigit():
                    n_str += line[j]
                    j += 1
                q_str = ''
                r_str = ''
                if j < length and line[j] == ':':
                    j += 1
                    while j < length and line[j].isdigit():
                        q_str += line[j]
                        j += 1
                    if j < length and line[j] == ':':
                        j += 1
                        while j < length and line[j].isdigit():
                            r_str += line[j]
                            j += 1
                n = int(n_str)
                q = int(q_str) if q_str else 2
                r = int(r_str) if r_str else q
                tokens.append(f'TUPLET_{n}_{q}_{r}')
                i = j
            else:
                tokens.append('SLUR_ON')
                i += 1
            continue

        if ch == ')':
            tokens.append('SLUR_OFF')
            i += 1
            continue

        # Decoration symbols (prefix before note)
        if ch in ('.', 'M', 'T', 'H') and i + 1 < length and (
            line[i + 1] in NOTE_PITCH or line[i + 1] in ('z', 'x', '[', '^', '_', '=', '\u0307', '\u0323')
        ):
            deco_map = {'.': 'STACCATO', 'M': 'TENUTO', 'T': 'TRILL', 'H': 'FERMATA'}
            tokens.append(f'DECOR_{deco_map[ch]}')
            i += 1
            continue

        # Note or rest
        token = ch
        i += 1
        # Collect octave marks (combining characters)
        while i < length and line[i] in ('\u0307', '\u0323'):
            token += line[i]
            i += 1
        # Collect octave marks: , = down, ' = up
        while i < length and line[i] == ',':
            token += line[i]
            i += 1
        while i < length and line[i] == "'":
            token += line[i]
            i += 1
        # Collect duration: digits, optional /digits
        while i < length and line[i].isdigit():
            token += line[i]
            i += 1
        if i < length and line[i] == '/':
            token += line[i]
            i += 1
            while i < length and line[i].isdigit():
                token += line[i]
                i += 1
        # Collect dots (dotted rhythm)
        while i < length and line[i] == '.':
            token += line[i]
            i += 1
        tokens.append(token)

    return tokens


# ── Repeat Expansion ─────────────────────────────────────────────────────

def _expand_repeats(tokens: list[str], _depth: int = 0) -> list[str]:
    """Expand repeat markers (|: :| ::) and volta endings in a token list.

    Returns a flat token list with all repeats expanded.
    Handles nested repeats recursively up to _MAX_REPEAT_DEPTH levels.
    """
    if _depth >= 8:
        return tokens  # Safety: stop expanding deeply nested repeats
    result = []
    i = 0
    n = len(tokens)

    while i < n:
        t = tokens[i]

        if t == '|:':
            i = _expand_one_repeat(tokens, i, result, _depth)
        elif t == '::':
            # :: = double repeat (equivalent to :| |:)
            # Close current repeat section, then start a new one
            result.append(':|')
            result.append('|:')
            i += 1
        elif t == ':|':
            # Orphan :| without matching |: — treat as bar line
            result.append('|')
            i += 1
        else:
            result.append(t)
            i += 1

    return result


def _expand_one_repeat(tokens: list[str], start: int, result: list, depth: int = 0) -> int:
    """Process one |: ... :| section and append expanded tokens to result.

    Returns the index after the processed section.
    Handles volta endings both inside and after the :| marker.
    """
    i = start + 1  # Skip |:
    n = len(tokens)
    nesting = 0

    # Find matching :|
    end = n
    for j in range(i, n):
        if tokens[j] == '|:':
            nesting += 1
        elif tokens[j] == ':|':
            if nesting == 0:
                end = j
                break
            nesting -= 1

    # Extract section tokens (between |: and :|)
    section = tokens[i:end]
    next_i = end + 1 if end < n else end

    # Split into body and internal volta endings
    body = []
    voltas: dict[int, list[str]] = {}
    current = body

    for t in section:
        if t.startswith('VOLTA_'):
            num = int(t.split('_')[1])
            voltas[num] = []
            current = voltas[num]
        else:
            current.append(t)

    # Check for volta endings AFTER :| (skip leading bar lines)
    j = next_i
    while j < n and tokens[j] in ('|', '||', '|]'):
        j += 1
    while j < n and tokens[j].startswith('VOLTA_'):
        num = int(tokens[j].split('_')[1])
        voltas[num] = []
        j += 1
        while j < n and not tokens[j].startswith('VOLTA_') and tokens[j] not in ('|:', ':|', '::'):
            if tokens[j] in ('|', '||', '|]'):
                j += 1
                break
            voltas[num].append(tokens[j])
            j += 1
    next_i = j

    # Expand recursively for nested repeats
    body = _expand_repeats(body, _depth=depth + 1)
    for k in voltas:
        voltas[k] = _expand_repeats(voltas[k], _depth=depth + 1)

    # Generate expanded output
    if voltas:
        max_ending = max(voltas.keys())
        for pass_num in range(1, max_ending + 1):
            result.append('|')
            result.extend(body)
            if pass_num in voltas:
                result.extend(voltas[pass_num])
            result.append('|')
    else:
        # Simple repeat: play twice
        result.append('|')
        result.extend(body)
        result.append('|')
        result.extend(body)
        result.append('|')

    return next_i


def _parse_voice_section(abc_text: str) -> list[dict]:
    """Split ABC text into voice sections.

    Each section has: channel, program, name, clef, music_lines.
    """
    lines = abc_text.splitlines()
    voices: list[dict] = []
    current_midi_channel = 0
    current_midi_program = 0
    current_midi_transpose = 0
    current_voice: Optional[dict] = None
    header_done = False

    for line in lines:
        stripped = line.strip()

        if not header_done:
            if stripped.startswith('V:'):
                header_done = True
            elif stripped.startswith('%%MIDI'):
                # Process MIDI directives in header (before first V:) to capture
                # channel/program/transpose settings for the first voice
                if stripped.startswith('%%MIDI channel'):
                    match = _RE_MIDI_CHANNEL.search(stripped)
                    if match:
                        current_midi_channel = int(match.group(1))
                elif stripped.startswith('%%MIDI program'):
                    match = _RE_MIDI_PROGRAM.search(stripped)
                    if match:
                        current_midi_program = int(match.group(1))
                elif stripped.startswith('%%MIDI transpose'):
                    match = _RE_MIDI_TRANSPOSE.search(stripped)
                    if match:
                        current_midi_transpose = int(match.group(1))
                continue
            else:
                continue

        # MIDI directives between voices apply to the NEXT voice, not the current one.
        # Only update the current voice if it hasn't received music lines yet
        # (i.e., the directive appears right after V: but before any notes).
        if stripped.startswith('%%MIDI channel'):
            match = _RE_MIDI_CHANNEL.search(stripped)
            if match:
                ch = int(match.group(1))
                current_midi_channel = ch
                if current_voice is not None and not current_voice['music_lines']:
                    current_voice['channel'] = ch
            continue

        if stripped.startswith('%%MIDI program'):
            match = _RE_MIDI_PROGRAM.search(stripped)
            if match:
                prog = int(match.group(1))
                current_midi_program = prog
                if current_voice is not None and not current_voice['music_lines']:
                    current_voice['program'] = prog
            continue

        if stripped.startswith('%%MIDI transpose'):
            match = _RE_MIDI_TRANSPOSE.search(stripped)
            if match:
                current_midi_transpose = int(match.group(1))
                if current_voice is not None and not current_voice['music_lines']:
                    current_voice['transpose'] = current_midi_transpose
            continue

        if stripped.startswith('%%MIDI control'):
            match = _RE_MIDI_CONTROL.search(stripped)
            if match and current_voice is not None:
                current_voice['music_lines'].append(
                    f'__MIDI_CTRL:{match.group(1)}:{match.group(2)}__')
            continue

        if stripped.startswith('%%MIDI tempo'):
            match = _RE_MIDI_TEMPO.search(stripped)
            if match and current_voice is not None:
                current_voice['music_lines'].append(
                    f'__MIDI_TEMPO:{match.group(1)}__')
            continue

        # Voice declaration
        if stripped.startswith('V:'):
            if current_voice is not None:
                voices.append(current_voice)
            name_match = _RE_VOICE_NAME.search(stripped)
            clef_match = _RE_VOICE_CLEF.search(stripped)
            current_voice = {
                'channel': current_midi_channel,
                'program': current_midi_program,
                'name': name_match.group(1) if name_match else '',
                'clef': clef_match.group(1) if clef_match else 'treble',
                'music_lines': [],
                'transpose': current_midi_transpose,
            }
            continue

        # Music line (contains notes, bar lines, etc.)
        if current_voice is not None and stripped and not stripped.startswith('%'):
            current_voice['music_lines'].append(stripped)

    if current_voice is not None:
        voices.append(current_voice)

    return voices


def _parse_bar_duration(time_sig: str, unit_ticks: int) -> int:
    """Calculate total ticks for one bar based on time signature and unit length.

    E.g. 4/4 with L:1/8: 4 beats * 480 ticks = 1920 ticks per bar.
    """
    try:
        parts = time_sig.split('/')
        beats_per_bar = int(parts[0])
        beat_unit = int(parts[1])
    except (ValueError, IndexError, ZeroDivisionError):
        beats_per_bar, beat_unit = 4, 4
    # Total ticks: beats_per_bar * quarter_note_ticks
    # quarter_note_ticks = TICKS_PER_BEAT * 4 / beat_unit
    return beats_per_bar * TICKS_PER_BEAT * 4 // beat_unit


class _VoiceTrackBuilder:
    """Encapsulates state for building a single MIDI voice track.

    Converts a stream of ABC tokens into MIDI events using absolute-time
    tracking, then converts to delta times at the end.
    """

    def __init__(self, voice: dict, header: dict, unit_ticks: int,
                 key_accidentals: Optional[dict[str, int]] = None,
                 auto_legato: bool = False,
                 legato_overlap_ratio: float = 0.85) -> None:
        self.voice = voice
        self.header = header
        self.unit_ticks = unit_ticks
        self.key_accidentals = key_accidentals or {}
        self.channel = voice['channel']
        self.is_perc = voice['clef'] == 'perc'
        self.transpose = voice.get('transpose', 0)

        # Auto-legato: extend note-off for sustained instruments to create
        # smooth overlap. Only applies within bars (not across bar lines),
        # not before rests, not on staccato notes.
        self.auto_legato = auto_legato and not self.is_perc
        self.legato_overlap_ratio = legato_overlap_ratio

        # Timing state
        self.abs_time = 0
        self.bar_ticks = _parse_bar_duration(header['time_signature'], unit_ticks)
        self.bar_start_tick = 0

        # Event accumulator: (abs_time, Message)
        self.events: list[tuple[int, mido.Message]] = []

        # Pending note state (for tie support)
        self.pending_pitch: Optional[int] = None
        self.pending_start = 0
        self.pending_duration = 0
        self.pending_velocity = 0
        self.pending_was_staccato = False

        # Broken rhythm: multiplier (num, den) to apply to the next note
        self.next_broken_mult: Optional[tuple[int, int]] = None

        # Tie/slur state
        self.tie_active = False
        self.slur_active = False

        # Grace note state
        self.pending_grace_notes: list[tuple[int, int]] = []

        # Crescendo/decrescendo state
        self.current_velocity = DEFAULT_VELOCITY
        self.crescendo_start_velocity: Optional[int] = None
        self.crescendo_target_velocity: Optional[int] = None
        self.crescendo_active = False
        self.crescendo_note_count = 0

        # Tuplet state
        self.tuplet_remaining = 0
        self.tuplet_mult = (1, 1)

        # Decoration state
        self.pending_decor: Optional[str] = None

        # Bar-local accidentals
        self.bar_accidentals: dict[str, int] = {}

        # Track whether next note starts in the same bar as the pending note
        # (auto-legato must NOT extend across bar lines)
        self._pending_bar_end = 0

    # ── Helpers ──────────────────────────────────────────────────────────

    def _close_pending(self, followed_by_rest: bool = False) -> None:
        if self.pending_pitch is None:
            return
        off_time = self.pending_start + self.pending_duration
        if self.slur_active:
            off_time = max(off_time, self.abs_time)
        # Auto-legato: extend note-off to overlap with the next note,
        # but NOT across bar lines, NOT before rests, NOT on staccato.
        if (self.auto_legato and not self.pending_was_staccato
                and not followed_by_rest
                and not self.slur_active):
            # Only extend if the next note is in the same bar
            if self.abs_time < self._pending_bar_end:
                gap = self.abs_time - off_time
                if gap > 0:
                    # Fill most of the gap between notes
                    extend = int(gap * self.legato_overlap_ratio)
                    off_time = off_time + extend
                else:
                    # Back-to-back notes: extend past next note-on for overlap
                    # Use ~10% of note duration as overlap
                    overlap = max(int(self.pending_duration * 0.10), 10)
                    off_time = off_time + overlap
                # Never extend past the bar line
                off_time = min(off_time, self._pending_bar_end)
        self.events.append((self.pending_start, mido.Message(
            'note_on', note=self.pending_pitch, velocity=self.pending_velocity,
            time=0, channel=self.channel)))
        self.events.append((off_time, mido.Message(
            'note_off', note=self.pending_pitch, velocity=0,
            time=0, channel=self.channel)))
        self.abs_time = max(self.abs_time, off_time)
        self.pending_pitch = None

    def _calc_note_duration(self, token: str) -> int:
        num, den, dots = _parse_duration(token)
        dur = _calc_ticks(self.unit_ticks, num, den, dots)
        if self.tuplet_remaining > 0:
            dur = dur * self.tuplet_mult[0] // self.tuplet_mult[1]
            self.tuplet_remaining -= 1
        if self.next_broken_mult is not None:
            dur = dur * self.next_broken_mult[0] // self.next_broken_mult[1]
            self.next_broken_mult = None
        return dur

    def _emit_grace_and_steal(self, main_duration: int) -> int:
        if not self.pending_grace_notes:
            return main_duration
        stolen = main_duration // 2
        remaining = main_duration - stolen
        n = len(self.pending_grace_notes)
        gdur = stolen // n if n > 0 else 0
        gs = self.abs_time
        for gp, gv in self.pending_grace_notes:
            self.events.append((gs, mido.Message(
                'note_on', note=gp, velocity=min(gv, 100),
                time=0, channel=self.channel)))
            self.events.append((gs + gdur, mido.Message(
                'note_off', note=gp, velocity=0,
                time=0, channel=self.channel)))
            gs += gdur
        self.pending_grace_notes = []
        self.abs_time += stolen
        return remaining

    def _interpolate_velocity(self) -> int:
        vel = self.current_velocity
        if self.crescendo_active and self.crescendo_start_velocity is not None:
            self.crescendo_note_count += 1
            progress = min(self.crescendo_note_count / 8.0, 1.0)
            target = (self.crescendo_target_velocity
                      if self.crescendo_target_velocity
                      else min(self.current_velocity + 30, 127))
            vel = int(self.crescendo_start_velocity + (target - self.crescendo_start_velocity) * progress)
            vel = max(1, min(127, vel))
        beat_pos = (self.abs_time - self.bar_start_tick) / self.bar_ticks if self.bar_ticks > 0 else 0
        if beat_pos < 0.01:
            vel = min(127, int(vel * 1.15))
        elif 0.49 < beat_pos < 0.51:
            vel = min(127, int(vel * 1.05))
        return max(1, min(127, vel))

    # ── Token Handlers ───────────────────────────────────────────────────

    def _handle_dynamics(self, token: str) -> bool:
        if not (token.startswith('!') and token.endswith('!')):
            return False
        dyn = token[1:-1]
        if dyn in DYNAMICS_MAP:
            self.current_velocity = DYNAMICS_MAP[dyn]
        elif dyn in ('crescendo(', '<('):
            self.crescendo_start_velocity = self.current_velocity
            self.crescendo_active = True
        elif dyn in ('crescendo)', '<)', 'diminuendo(', '>('):
            if self.crescendo_active and self.crescendo_target_velocity is None:
                self.crescendo_target_velocity = self.current_velocity
            self.crescendo_active = False
        elif dyn in ('diminuendo)', '>)'):
            self.crescendo_target_velocity = None
            self.crescendo_active = False
        return True

    def _handle_inline_field(self, token: str) -> bool:
        if not (token.startswith('[') and ':' in token and ']' in token):
            return False
        inner = token[1:token.index(']')]
        m = _RE_INLINE_FIELD.match(inner)
        if m:
            name, value = m.group(1), m.group(2).strip()
            if name == 'K':
                self.key_accidentals, _ = _parse_key_signature(value)
            elif name == 'M':
                self.header = {**self.header, 'time_signature': value}
                self.bar_ticks = _parse_bar_duration(value, self.unit_ticks)
        return True

    def _handle_grace_notes(self, token: str) -> bool:
        if not (token.startswith('{') and token.endswith('}')):
            return False
        inner = token[1:-1]
        gnotes: list[tuple[int, int]] = []
        gn, gn_len = 0, len(inner)
        while gn < gn_len:
            gc = inner[gn]
            if gc in ' \t':
                gn += 1
                continue
            # Collect accidental prefix (^, _, =, ^^, __)
            gt = ''
            while gn < gn_len and inner[gn] in ('^', '_', '='):
                gt += inner[gn]
                gn += 1
            # Collect base note character
            if gn < gn_len and inner[gn] in 'abcdefgABCDEFG':
                gt += inner[gn]
                gn += 1
            else:
                gn += 1
                continue
            while gn < gn_len and inner[gn] in ('\u0307', '\u0323'):
                gt += inner[gn]
                gn += 1
            while gn < gn_len and inner[gn] == ',':
                gt += inner[gn]
                gn += 1
            gp = _parse_note_pitch(gt, is_drum=self.is_perc,
                                   key_accidentals=self.key_accidentals,
                                   bar_accidentals=self.bar_accidentals)
            if gp is not None:
                gnotes.append((gp, self.current_velocity))
        self.pending_grace_notes = gnotes
        return True

    def _handle_barline(self, token: str) -> bool:
        if token not in ('|', '|:', ':|', '||', '|]', '::'):
            return False
        if not self.tie_active:
            # Bar line = phrase boundary, no legato extension
            self._close_pending(followed_by_rest=True)
        bar_end = self.bar_start_tick + self.bar_ticks
        self.abs_time = max(self.abs_time, bar_end)
        self.bar_start_tick = self.abs_time
        self.bar_accidentals.clear()
        return True

    def _handle_broken_rhythm(self, token: str) -> bool:
        if not token.startswith('BRK_'):
            return False
        parts = token.split('_')
        direction, count = parts[1], int(parts[2])
        prev_num = (1 << (count + 1)) - 1
        prev_den = 1 << count
        next_num, next_den = 1, 1 << count
        if direction == 'LT':
            prev_num, next_num = next_num, prev_num
            prev_den, next_den = next_den, prev_den
        if self.pending_pitch is not None:
            self.pending_duration = self.pending_duration * prev_num // prev_den
        self.next_broken_mult = (next_num, next_den)
        return True

    def _handle_rest(self, token: str) -> bool:
        if token[0] not in ('z', 'x'):
            return False
        self._close_pending(followed_by_rest=True)
        self.abs_time += self._calc_note_duration(token)
        return True

    def _handle_chord(self, token: str) -> bool:
        if not (token.startswith('[') and ']' in token):
            return False
        self._close_pending()
        bracket_end = token.index(']')
        inner = token[1:bracket_end]
        duration = self._calc_note_duration(token)
        # Apply decoration (staccato/fermata) to chord
        decor = self.pending_decor
        self.pending_decor = None
        if decor == 'STACCATO':
            duration = duration // 2
        elif decor == 'FERMATA':
            duration = duration * 2
        duration = self._emit_grace_and_steal(duration)
        vel = self._interpolate_velocity()
        pitches: list[int] = []
        j, ilen = 0, len(inner)
        while j < ilen:
            # Collect accidental prefix (^, _, =, ^^, __)
            nt = ''
            while j < ilen and inner[j] in ('^', '_', '='):
                nt += inner[j]
                j += 1
            # Collect base note character
            if j < ilen and inner[j] in 'abcdefgABCDEFG':
                nt += inner[j]
                j += 1
            else:
                j += 1
                continue
            while j < ilen and inner[j] in ('\u0307', '\u0323'):
                nt += inner[j]
                j += 1
            while j < ilen and inner[j] == ',':
                nt += inner[j]
                j += 1
            p = _parse_note_pitch(nt, is_drum=self.is_perc,
                                  key_accidentals=self.key_accidentals,
                                  bar_accidentals=self.bar_accidentals)
            if p is not None:
                pitches.append(p + self.transpose)
        for p in pitches:
            self.events.append((self.abs_time, mido.Message(
                'note_on', note=p, velocity=vel, time=0, channel=self.channel)))
            self.events.append((self.abs_time + duration, mido.Message(
                'note_off', note=p, velocity=0, time=0, channel=self.channel)))
        self.abs_time += duration
        return True

    def _handle_note(self, token: str) -> None:
        pitch = _parse_note_pitch(token, is_drum=self.is_perc,
                                  key_accidentals=self.key_accidentals,
                                  bar_accidentals=self.bar_accidentals)
        if pitch is None:
            return
        pitch += self.transpose
        duration = self._calc_note_duration(token)
        decor = self.pending_decor
        self.pending_decor = None

        is_staccato = decor == 'STACCATO'
        if is_staccato:
            duration = duration // 2
        elif decor == 'TENUTO':
            duration = int(duration * 1.1)
        elif decor == 'FERMATA':
            duration = duration * 2
        elif decor == 'TRILL':
            self._close_pending()
            self.tie_active = False
            duration = self._emit_grace_and_steal(duration)
            vel = self._interpolate_velocity()
            count = max(2, duration // max(self.unit_ticks, 1))
            td = duration // count
            for ti in range(count):
                tp = pitch if ti % 2 == 0 else pitch + 1
                self.events.append((self.abs_time + ti * td, mido.Message(
                    'note_on', note=tp, velocity=vel, time=0, channel=self.channel)))
                self.events.append((self.abs_time + (ti + 1) * td, mido.Message(
                    'note_off', note=tp, velocity=0, time=0, channel=self.channel)))
            self.abs_time += duration
            return

        if self.tie_active and self.pending_pitch is not None and pitch == self.pending_pitch:
            self.tie_active = False
            self.pending_duration += duration
            return

        self._close_pending()
        self.tie_active = False
        duration = self._emit_grace_and_steal(duration)
        vel = self._interpolate_velocity()
        self.pending_pitch = pitch
        self.pending_start = self.abs_time
        self.pending_duration = duration
        self.pending_velocity = vel
        self.pending_was_staccato = is_staccato
        # Record bar boundary for auto-legato — don't extend past this
        self._pending_bar_end = self.bar_start_tick + self.bar_ticks

    # ── Main Build ───────────────────────────────────────────────────────

    def build(self) -> mido.MidiTrack:
        track = mido.MidiTrack()
        if not self.is_perc:
            track.append(mido.Message('program_change', program=self.voice['program'], channel=self.channel))

        all_tokens: list[str] = []
        for ml in self.voice['music_lines']:
            all_tokens.extend(_tokenize_music_line(ml))
        all_tokens = _expand_repeats(all_tokens)

        for token in all_tokens:
            if self._handle_dynamics(token):
                continue
            if self._handle_inline_field(token):
                continue
            if self._handle_grace_notes(token):
                continue
            if self._handle_barline(token):
                continue
            if self._handle_broken_rhythm(token):
                continue
            if token == 'TIE':
                self.tie_active = True
                continue
            if token.startswith('TUPLET_'):
                parts = token.split('_')
                self.tuplet_remaining = int(parts[1])
                self.tuplet_mult = (int(parts[2]), int(parts[1]))
                continue
            if token == 'SLUR_ON':
                self.slur_active = True
                continue
            if token == 'SLUR_OFF':
                self.slur_active = False
                continue
            if token.startswith('__MIDI_CTRL:'):
                m = _RE_EMBEDDED_CTRL.match(token)
                if m:
                    self.events.append((self.abs_time, mido.Message(
                        'control_change', control=int(m.group(1)),
                        value=int(m.group(2)), time=0, channel=self.channel)))
                continue
            if token.startswith('__MIDI_TEMPO:'):
                m = _RE_EMBEDDED_TEMPO.match(token)
                if m:
                    self.events.append((self.abs_time, mido.MetaMessage(
                        'set_tempo', tempo=mido.bpm2tempo(int(m.group(1))), time=0)))
                continue
            if token.startswith('DECOR_'):
                self.pending_decor = token[6:]
                continue
            if self._handle_rest(token):
                continue
            if self._handle_chord(token):
                continue
            self._handle_note(token)

        self._close_pending()

        # Sort: note_off before note_on at same tick
        self.events.sort(key=lambda e: (e[0], 1 if e[1].type == 'note_on' else 0))
        prev = 0
        for t, msg in self.events:
            msg.time = t - prev
            prev = t
            track.append(msg)
        return track


def _build_voice_track(
    voice: dict,
    header: dict,
    unit_ticks: int,
    key_accidentals: Optional[dict[str, int]] = None,
    auto_legato: bool = False,
    legato_overlap_ratio: float = 0.85,
) -> mido.MidiTrack:
    """Build a MIDI track from a parsed voice section."""
    return _VoiceTrackBuilder(
        voice, header, unit_ticks, key_accidentals,
        auto_legato=auto_legato, legato_overlap_ratio=legato_overlap_ratio,
    ).build()


# ── Main Converter ──────────────────────────────────────────────────────

def abc_to_midi(abc_text: str, auto_legato: bool = False) -> mido.MidiFile:
    """Convert ABC notation text to a MIDI file.

    Args:
        abc_text: Full ABC notation string including headers and voice sections.
        auto_legato: If True, extend note-off times for sustained instruments
            to create smooth overlap (85% ratio). Respects bar lines, rests,
            and staccato markers.

    Returns:
        A mido.MidiFile object with one tempo track plus one track per voice.
    """
    header = parse_header(abc_text)
    voices = _parse_voice_section(abc_text)
    unit_ticks = _parse_unit_length_ticks(header['unit_length'])

    # Parse key signature
    key_accidentals, key_sharps = _parse_key_signature(header['key'])

    mid = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)

    # Track 0: Tempo track
    tempo_track = mido.MidiTrack()
    tempo_track.name = 'Tempo'
    tempo_track.append(mido.MetaMessage(
        'set_tempo', tempo=mido.bpm2tempo(header['bpm']), time=0,
    ))
    try:
        ts_num = int(header['time_signature'].split('/')[0])
        ts_den = int(header['time_signature'].split('/')[1])
    except (ValueError, IndexError, ZeroDivisionError):
        ts_num, ts_den = 4, 4
    tempo_track.append(mido.MetaMessage(
        'time_signature',
        numerator=ts_num,
        denominator=ts_den,
        time=0,
    ))
    # Key signature meta event
    is_minor = header['key'].strip().lower().endswith(('m', 'minor'))
    ks_entry = _SHARPS_TO_KEY.get(key_sharps)
    if ks_entry:
        key_name = ks_entry[1] if is_minor else ks_entry[0]
        if is_minor and not key_name.endswith('m'):
            key_name += 'm'
        try:
            tempo_track.append(mido.MetaMessage(
                'key_signature', key=key_name, time=0,
            ))
        except (ValueError, AttributeError):
            pass  # older mido versions may not support this
    mid.tracks.append(tempo_track)

    # Voice tracks
    for voice in voices:
        track = _build_voice_track(
            voice, header, unit_ticks, key_accidentals=key_accidentals,
            auto_legato=auto_legato,
        )
        track.name = voice.get('name', f'Voice {voice["channel"]}')
        mid.tracks.append(track)

    return mid


if __name__ == "__main__":
    # Fix Windows GBK encoding
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    import argparse
    parser = argparse.ArgumentParser(
        prog='abc_to_midi',
        description='ABC notation to MIDI converter',
    )
    parser.add_argument('input', nargs='?', help='Input ABC file path')
    parser.add_argument('output', nargs='?', default=None,
                        help='Output MIDI file path (default: same name .mid)')
    parser.add_argument('--input', '-i', dest='input_named',
                        help='Input ABC file (alias for positional)')
    parser.add_argument('--output', '-o', dest='output_named',
                        help='Output MIDI file (alias for positional)')
    parser.add_argument('--auto-legato', action='store_true',
                        help='Enable auto-legato for sustained instruments')

    args = parser.parse_args()

    abc_path = args.input_named or args.input
    if args.input_named and args.input:
        parser.error("provide input as positional arg OR --input/-i, not both")
    if not abc_path:
        parser.error("input ABC file is required (use positional arg or --input/-i)")
    out_path = args.output_named or args.output
    if out_path is None:
        out_path = str(Path(abc_path).with_suffix('.mid'))

    abc_text = Path(abc_path).read_text(encoding='utf-8')
    mid = abc_to_midi(abc_text, auto_legato=args.auto_legato)
    mid.save(out_path)
    print(f"MIDI saved to {out_path}")
