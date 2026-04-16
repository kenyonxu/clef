"""Clef Compose v2 — 统一工具链入口。"""
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger("clef_tools")

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def cmd_check_deps(args):
    from check_dependencies import check
    return 0 if check() else 1


def cmd_abc_to_midi(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    from abc_to_midi import abc_to_midi
    with open(args.input, 'r', encoding='utf-8') as f:
        abc_text = f.read()
    mid = abc_to_midi(abc_text)
    mid.save(args.output)
    print(f"OK: {args.input} -> {args.output}")
    return 0


def cmd_validate(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    if not os.path.isfile(args.plan):
        print(f"Error: file not found: {args.plan}")
        return 1
    from validate_abc import validate
    report = validate(args.input, args.plan)
    if args.output:
        report.to_json(args.output)
    if report.fails:
        print(f"FAIL: {len(report.fails)} issue(s)")
        for issue in report.fails:
            print(f"  [{issue.severity}] {issue.category}: {issue.message}")
    else:
        print("PASS: no issues")
    if report.warns:
        print(f"WARN: {len(report.warns)} warning(s)")
        for issue in report.warns:
            print(f"  [{issue.severity}] {issue.category}: {issue.message}")
    return 1 if report.fails else 0


# --- Merge helpers ---

_EXCLUDE_NAMES = {"score", "score.abc", "validation_report", "history"}

_FILENAME_VOICE_MAP = {
    "melody": "V:1",
    "harmony": "V:2",
    "bass": "V:3",
    "drums": "V:4",
    "rhythm": "V:3",
    "v1_melody": "V:1",
    "v2_harmony": "V:2",
    "v3_bass": "V:3",
    "v4_drums": "V:4",
    "v5_harp": "V:5",
    "v1": "V:1",
    "v2": "V:2",
    "v3": "V:3",
    "v4": "V:4",
    "v5": "V:5",
}


def _is_fragment_file(fname: str) -> bool:
    """判断文件是否为声部片段（非合并产物）。"""
    stem = fname.removesuffix('.abc')
    if stem in _EXCLUDE_NAMES:
        return False
    if stem.startswith('score_') or stem.startswith('_v') or stem.startswith('layer_'):
        return False
    return True


def _extract_voice_id(fname: str, content: str) -> str | None:
    """从文件名或内容中提取声部 ID (e.g. "V:1")。

    三级回退策略：
    1. 扫描内容中的 V:N 行
    2. 匹配文件名约定（melody.abc -> V:1）
    3. 匹配文件名中的 V:N 模式（V1_fragment.abc -> V:1）
    """
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('V:'):
            parts = stripped[2:].split()
            if parts and parts[0].isdigit():
                return f"V:{parts[0]}"
    stem = fname.removesuffix('.abc').lower().replace('-', '_')
    if stem in _FILENAME_VOICE_MAP:
        return _FILENAME_VOICE_MAP[stem]
    m = re.search(r'V(\d+)', fname, re.IGNORECASE)
    if m:
        return f"V:{m.group(1)}"
    return None


def cmd_merge(args):
    if not os.path.isfile(args.plan):
        print(f"Error: file not found: {args.plan}")
        return 1
    from merge_abc import merge
    with open(args.plan, 'r', encoding='utf-8') as f:
        plan = json.load(f)
    fragments = {}
    # --files takes priority over --dir
    if args.files:
        for fpath in args.files:
            if not os.path.isfile(fpath):
                print(f"WARN: file not found: {fpath}, skipping", file=sys.stderr)
                continue
            fname = os.path.basename(fpath)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            voice_id = _extract_voice_id(fname, content)
            if voice_id is None:
                print(f"WARN: cannot identify voice in {fname}, skipping", file=sys.stderr)
                continue
            fragments[voice_id] = content
    elif args.dir and os.path.isdir(args.dir):
        for fname in sorted(os.listdir(args.dir)):
            if not fname.endswith('.abc'):
                continue
            if not _is_fragment_file(fname):
                continue
            with open(os.path.join(args.dir, fname), 'r', encoding='utf-8') as f:
                content = f.read()
            voice_id = _extract_voice_id(fname, content)
            if voice_id is None:
                print(f"WARN: cannot identify voice in {fname}, skipping", file=sys.stderr)
                continue
            fragments[voice_id] = content
    else:
        print("Error: provide --files or --dir", file=sys.stderr)
        return 1
    if not fragments:
        print("Error: no fragment files found", file=sys.stderr)
        return 1
    score = merge(plan, fragments, mode=args.mode)
    output_path = args.output
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(score)
        print(f"OK: merged -> {output_path}")
    else:
        sys.stdout.write(score)
    return 0


def cmd_inject(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    if not os.path.isfile(args.plan):
        print(f"Error: file not found: {args.plan}")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    from inject_expression import inject
    inject(args.input, args.plan, args.output)
    print(f"OK: {args.input} + {args.plan} -> {args.output}")
    return 0


def cmd_extract_solo(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    os.makedirs(args.output_dir, exist_ok=True)
    from extract_solo import extract_solo
    files = extract_solo(args.input, args.start, args.end, args.output_dir)
    print(f"OK: extracted {len(files)} solo tracks to {args.output_dir}")
    for f in files:
        print(f"  {os.path.basename(f)}")
    return 0


def cmd_analyze(args):
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}")
        return 1
    if args.segment <= 0:
        print("Error: --segment must be positive", file=sys.stderr)
        return 1
    from analyze_midi import analyze
    report = analyze(args.input, segment_sec=args.segment)
    sys.stdout.write(report)
    sys.stdout.write("\n")
    return 0


def cmd_archive(args):
    if not os.path.isdir(args.workdir):
        print(f"Error: workdir not found: {args.workdir}", file=sys.stderr)
        return 1
    from archive import archive
    dest = archive(args.workdir)
    print(f"Archived to: {dest}")
    return 0


def cmd_midi_to_audio(args):
    """用 FluidSynth 将 MIDI 转为音频文件（WAV/OGG）。"""


def cmd_fix_measure_duration(args):
    """Deterministic fix for ABC measure duration errors (off by ≤2 units)."""
    from fix_measure_duration import fix_abc_content

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    abc_content = input_path.read_text(encoding="utf-8")
    result = fix_abc_content(abc_content, args.max_deviation)

    output_path = Path(args.output) if args.output else input_path
    output_path.write_text(result["abc"], encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        fixes = result["fixes"]
        measures_checked = result["measures_checked"]
        if not fixes:
            print(f"All {measures_checked} measures OK, no fixes needed.")
        else:
            fixed_count = sum(1 for f in fixes if not f.get("skipped"))
            skipped_count = sum(1 for f in fixes if f.get("skipped"))
            print(f"Checked {measures_checked} measures: {fixed_count} fixed, {skipped_count} skipped")
            for f in fixes:
                if f.get("skipped"):
                    print(f"  Measure {f['measure']}: SKIPPED (off by {abs(f['actual_units'] - f['target_units']):.1f} units)")
                else:
                    print(f"  Measure {f['measure']}: {f['action']} {f['target']} {f['from']} -> {f['to']}")
        if result["passed"]:
            print("PASS")
        else:
            print("FAIL: some measures need Revision agent")
    return 0


def cmd_midi_to_abc(args):
    """Convert MIDI file to ABC notation using mido."""
    import mido

    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    def midi_to_abc_pitch(midi_pitch, key_sig):
        """Convert MIDI note number to ABC pitch string with octave marks."""
        name = NOTE_NAMES[midi_pitch % 12]
        # Adjust sharps/flats for key signature
        if key_sig < 0:  # flats
            flat_map = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab', 'D': 'Db', 'G': 'Gb', 'C': 'Cb'}
            if name in flat_map:
                name = flat_map[name]
        elif key_sig > 0:  # sharps
            sharp_map = {'F': 'F#', 'C': 'C#', 'G': 'G#', 'D': 'D#', 'A': 'A#', 'E': 'E#'}
            if name in sharp_map:
                name = sharp_map[name]
        # ABC octave: C4 = c', C5 = c'', etc. MIDI 60 = C4
        octave = (midi_pitch // 12) - 5  # -1 for C3, 0 for C4, 1 for C5...
        if octave >= 0:
            abc_name = name.lower() + "'" * octave
        else:
            abc_name = name.lower() + "," * (-octave)
        return abc_name

    def duration_to_abc(ticks, ticks_per_beat, unit_len):
        """Convert tick duration to ABC duration string.

        For L:1/8 (unit_len=0.125), the unit is an eighth note:
        - 1 unit (eighth note)  -> '' (no suffix)
        - 2 units (quarter)     -> '2'
        - 4 units (half)        -> '4'
        - 0.5 units (16th)      -> '/2'
        """
        beats = ticks / ticks_per_beat
        # How many L units this note spans
        # unit_len is fraction of whole note (e.g. 1/8), but beats is in quarter notes
        # So: abc_units = (beats / 4) / unit_len = beats_in_whole_notes / unit_len
        abc_units = (beats / 4) / unit_len
        abc_units = round(abc_units)
        if abc_units <= 0:
            return None
        if abc_units == 1:
            return ''
        if abc_units in (2, 3, 4, 6, 8):
            return str(abc_units)
        # Fractional: /2 = half unit, /4 = quarter unit
        inv = round(1 / (abc_units)) if abc_units > 0 else 0
        if inv >= 2:
            return f'/{inv}'
        return str(abc_units)

    mid = mido.MidiFile(args.input)
    tpb = mid.ticks_per_beat

    # Detect key signature and tempo from track 0
    key_sig = 0  # C major / A minor
    bpm = 120
    key_str = 'C'
    for msg in mid.tracks[0]:
        if msg.type == 'key_signature':
            key_str_raw = str(msg.key)
            # mido returns 'Em', 'Cm', 'F#m', 'Bbm' for minor; 'E', 'C', 'F#' for major
            is_minor = key_str_raw.endswith('m') and key_str_raw[-2:].isalpha()
            root = key_str_raw.rstrip('m')
            key_str = root + ('m' if is_minor else '')
        elif msg.type == 'set_tempo':
            bpm = round(60000000 / msg.tempo)

    lines = [
        'X:1',
        'T:midi_import',
        f'M:{mid.time_signature if hasattr(mid, "time_signature") else "4/4"}',
        'L:1/8',
        f'Q:1/4={bpm}',
        f'K:{key_str}',
    ]

    # Collect note events per track
    voice_counter = 0
    for ti, track in enumerate(mid.tracks):
        if ti == 0:
            continue  # skip meta track
        # Skip drum tracks (channel 9)
        is_drum = False
        for msg in track:
            if msg.type == 'program_change' and msg.channel == 9:
                is_drum = True
                break
        if is_drum:
            continue

        voice_counter += 1
        vid = voice_counter

        # Extract program and channel
        channel = None
        program = 0
        for msg in track:
            if msg.type == 'program_change':
                channel = msg.channel
                program = msg.program
                break

        # Collect active notes with delta times
        active = {}  # {note: (start_tick, velocity)}
        events = []  # [(abs_tick, type, note, velocity)]

        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                active[msg.note] = (abs_tick, msg.velocity)
            elif msg.type in ('note_off',) or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in active:
                    start, vel = active.pop(msg.note)
                    events.append((start, abs_tick - start, msg.note, vel))

        if not events:
            continue

        # Add MIDI directives
        lines.append(f'%%MIDI channel {channel if channel is not None else vid}')
        lines.append(f'%%MIDI program {program}')
        voice_name = f'Track{vid}'
        lines.append(f'V:{vid} clef=treble name="{voice_name}"')

        # Sort events by start time, group into bars
        events.sort(key=lambda e: e[0])
        unit_len = 1 / 8  # L:1/8
        bar_ticks = tpb * 4  # assuming 4/4

        # Build ABC notation per bar
        current_bar_tick = 0
        bar_notes = []
        for start, dur, note, vel in events:
            bar_idx = start // bar_ticks
            abc_pitch = midi_to_abc_pitch(note, key_sig)
            abc_dur = duration_to_abc(dur, tpb, unit_len)
            if abc_dur is None:
                continue
            note_str = abc_pitch + abc_dur
            # Add rest gap if needed (simplified: just place notes)
            bar_notes.append((bar_idx, note_str))

        # Group by bar
        bars = {}
        for bar_idx, note_str in bar_notes:
            bars.setdefault(bar_idx, []).append(note_str)

        max_bar = max(bars.keys()) if bars else 0
        for i in range(max_bar + 1):
            notes = bars.get(i, [])
            bar_str = ' '.join(notes) if notes else 'z4'
            lines.append(bar_str + ' |')
    else:
        max_bar = 0

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"OK: {args.input} -> {args.output}")
    return 0


def cmd_snapshot(args):
    from snapshot import snapshot
    return snapshot(args.step, args.status, args.output, args.note, args.workdir)


def _compat_normalize(args):
    """Backward compat: fill named attrs from deprecated positional args.

    Each subcommand defines _pos_* positional fallbacks. If a named attr
    (e.g. args.input) is None but its _pos_* fallback has a value, copy
    the fallback. This lets old positional usage coexist with new --flags.
    """
    cmd = args.command
    pos_to_named = {
        'abc-to-midi': {'_pos_input': 'input', '_pos_output': 'output'},
        'validate': {'_pos_abc': 'input', '_pos_plan': 'plan'},
        'merge': {'_pos_plan': 'plan', '_pos_dir': 'dir'},
        'inject': {'_pos_input': 'input', '_pos_plan': 'plan', '_pos_output': 'output'},
        'extract-solo': {'_pos_input': 'input', '_pos_start': 'start', '_pos_end': 'end', '_pos_output_dir': 'output_dir'},
        'analyze': {'_pos_input': 'input'},
        'midi-to-audio': {'_pos_input': 'input'},
        'midi-to-abc': {'_pos_input': 'input'},
    }
    mapping = pos_to_named.get(cmd, {})
    for pos_attr, named_attr in mapping.items():
        named_val = getattr(args, named_attr, None)
        pos_val = getattr(args, pos_attr, None)
        if named_val is None and pos_val is not None:
            setattr(args, named_attr, pos_val)


def main():
    parser = argparse.ArgumentParser(
        prog='clef_tools',
        description='Clef Compose v2 工具链',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # check-deps
    sub.add_parser('check-deps', help='检查 Python 依赖')

    # abc-to-midi
    p = sub.add_parser('abc-to-midi', help='ABC 转 MIDI')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) 输入 ABC 文件')
    p.add_argument('_pos_output', nargs='?', help='(deprecated) 输出 MIDI 文件')
    p.add_argument('--input', '-i', dest='input', help='输入 ABC 文件')
    p.add_argument('--output', '-o', dest='output', help='输出 MIDI 文件')

    # validate
    p = sub.add_parser('validate', help='music21 验证 ABC')
    p.add_argument('_pos_abc', nargs='?', help='(deprecated) ABC 文件路径')
    p.add_argument('_pos_plan', nargs='?', help='(deprecated) plan.json 路径')
    p.add_argument('--input', '-i', dest='input', help='ABC 文件路径')
    p.add_argument('--plan', help='plan.json 路径')
    p.add_argument('--output', '-o', default=None, help='输出报告路径')

    # merge
    p = sub.add_parser('merge', help='合并声部 ABC 片段')
    p.add_argument('_pos_plan', nargs='?', help='(deprecated) plan.json 路径')
    p.add_argument('_pos_dir', nargs='?', help='(deprecated) 片段目录路径')
    p.add_argument('--plan', help='plan.json 路径')
    p.add_argument('--dir', help='片段目录路径（扫描所有 .abc 文件）')
    p.add_argument('--files', nargs='+', help='显式指定片段文件列表（优先于 --dir）')
    p.add_argument('--mode', choices=['full', 'solo'], default='full')
    p.add_argument('--output', '-o', default=None, help='输出 score.abc 路径')

    # inject
    p = sub.add_parser('inject', help='注入 CC/弯音到 MIDI')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) 基础 MIDI 文件')
    p.add_argument('_pos_plan', nargs='?', help='(deprecated) expression_plan.json 路径')
    p.add_argument('_pos_output', nargs='?', help='(deprecated) 输出 MIDI 文件')
    p.add_argument('--input', '-i', dest='input', help='基础 MIDI 文件')
    p.add_argument('--plan', required=True, help='expression_plan.json 路径')
    p.add_argument('--output', '-o', dest='output', help='输出 MIDI 文件')

    # extract-solo
    p = sub.add_parser('extract-solo', help='分轨 Solo 提取')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) MIDI 文件')
    p.add_argument('_pos_start', nargs='?', type=float, help='(deprecated) 起始时间（秒）')
    p.add_argument('_pos_end', nargs='?', type=float, help='(deprecated) 结束时间（秒）')
    p.add_argument('_pos_output_dir', nargs='?', help='(deprecated) 输出目录')
    p.add_argument('--input', '-i', dest='input', help='MIDI 文件')
    p.add_argument('--start', type=float, required=True, help='起始时间（秒）')
    p.add_argument('--end', type=float, required=True, help='结束时间（秒）')
    p.add_argument('--output-dir', '-o', dest='output_dir', help='输出目录')

    # analyze
    p = sub.add_parser('analyze', help='MIDI piano roll analysis report')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) MIDI 文件')
    p.add_argument('--input', '-i', dest='input', help='MIDI 文件')
    p.add_argument('--segment', type=float, default=2.0, help='密度条时间分段（秒，最小 0.1）')

    # snapshot
    p = sub.add_parser('snapshot', help='备份 score.abc + 写入步骤日志')
    p.add_argument('--step', required=True, help='步骤编号 (如 2a)')
    p.add_argument('--status', default='成功', choices=['成功', '有警告', '失败'])
    p.add_argument('--output', default='', help='输出文件名')
    p.add_argument('--note', default='', help='补充说明')
    p.add_argument('--workdir', default='.clef-work', help='工作目录')

    # fix-measure-duration
    p = sub.add_parser('fix-measure-duration', help='确定性修复小节时值偏差（偏离 ≤2 单位）')
    p.add_argument('input', help='输入 ABC 文件')
    p.add_argument('--output', '-o', default=None, help='输出 ABC 文件（默认覆盖输入）')
    p.add_argument('--max-deviation', type=float, default=2.0, help='最大修复偏差（默认 2.0）')
    p.add_argument('--json', action='store_true', help='JSON 格式输出')

    # archive
    p = sub.add_parser('archive', help='归档最终产出到 output/{title}/ 目录')
    p.add_argument('--workdir', default='.clef-work', help='工作目录')

    # midi-to-audio
    p = sub.add_parser('midi-to-audio', help='用 FluidSynth 将 MIDI 转为音频（WAV/OGG）')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) MIDI 文件或目录')
    p.add_argument('--input', '-i', dest='input', help='MIDI 文件或目录（配合 --batch）')
    p.add_argument('--sf2', required=True, help='SoundFont (.sf2) 文件路径')
    p.add_argument('--output-dir', '-o', default='', help='输出目录（默认和输入同目录）')
    p.add_argument('--format', '-f', choices=['wav', 'ogg', 'mp3'], default='wav', help='输出格式')
    p.add_argument('--sample-rate', '-r', type=int, default=44100, help='采样率（默认 44100）')
    p.add_argument('--gain', '-g', type=float, default=1.0, help='音量增益（默认 1.0，FluidSynth 原始默认 0.2）')
    p.add_argument('--batch', action='store_true', help='批量模式：input 为目录，转换其中所有 .mid 文件')

    # midi-to-abc
    p = sub.add_parser('midi-to-abc', help='将 MIDI 文件转换为 ABC 记谱法')
    p.add_argument('_pos_input', nargs='?', help='(deprecated) 输入 MIDI 文件')
    p.add_argument('--input', '-i', dest='input', help='输入 MIDI 文件')
    p.add_argument('--output', '-o', required=True, help='输出 ABC 文件')

    args = parser.parse_args()
    _compat_normalize(args)

    commands = {
        'check-deps': cmd_check_deps,
        'abc-to-midi': cmd_abc_to_midi,
        'validate': cmd_validate,
        'merge': cmd_merge,
        'inject': cmd_inject,
        'extract-solo': cmd_extract_solo,
        'analyze': cmd_analyze,
        'snapshot': cmd_snapshot,
        'archive': cmd_archive,
        'midi-to-audio': cmd_midi_to_audio,
        'midi-to-abc': cmd_midi_to_abc,
        'fix-measure-duration': cmd_fix_measure_duration,
    }

    func = commands.get(args.command)
    if func:
        try:
            sys.exit(func(args))
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            sys.exit(130)
        except BrokenPipeError:
            sys.exit(0)
        except Exception as exc:
            logger.debug("Full traceback", exc_info=True)
            print(f"Error ({args.command}): {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
