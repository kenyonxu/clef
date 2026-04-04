"""Clef Compose v2 — 统一工具链入口。"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading

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
    if not os.path.isfile(args.abc):
        print(f"Error: file not found: {args.abc}")
        return 1
    if not os.path.isfile(args.plan):
        print(f"Error: file not found: {args.plan}")
        return 1
    from validate_abc import validate
    report = validate(args.abc, args.plan)
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


def cmd_merge(args):
    if not os.path.isfile(args.plan):
        print(f"Error: file not found: {args.plan}")
        return 1
    if not os.path.isdir(args.fragments_dir):
        print(f"Error: directory not found: {args.fragments_dir}")
        return 1
    from merge_abc import merge
    with open(args.plan, 'r', encoding='utf-8') as f:
        plan = json.load(f)
    # Read fragments from directory
    fragments = {}
    if os.path.isdir(args.fragments_dir):
        for fname in sorted(os.listdir(args.fragments_dir)):
            if not fname.endswith('.abc'):
                continue
            with open(os.path.join(args.fragments_dir, fname), 'r', encoding='utf-8') as f:
                content = f.read()
            # Extract voice ID from content (V: header line)
            voice_id = fname.replace('.abc', '')
            for line in content.split('\n'):
                if line.startswith('V:'):
                    voice_id = line.split()[0]  # e.g. "V:1"
                    break
            fragments[voice_id] = content
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


def cmd_midi_to_abc(args):
    """Convert MIDI file to ABC notation using music21."""
    from music21 import converter, midi as m21midi
    mf = m21midi.MidiFile()
    mf.open(args.input)
    mf.read()
    mf.close()
    score = m21midi.translate.midiFileToStream(mf)
    abc_str = converter.freezeStr(score, fmt='abc')
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(abc_str)
    print(f"OK: {args.input} -> {args.output}")
    return 0


def cmd_snapshot(args):
    from snapshot import snapshot
    return snapshot(args.step, args.status, args.output, args.note, args.workdir)


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
    p.add_argument('input', help='输入 ABC 文件')
    p.add_argument('output', help='输出 MIDI 文件')

    # validate
    p = sub.add_parser('validate', help='music21 验证 ABC')
    p.add_argument('abc', help='ABC 文件路径')
    p.add_argument('plan', help='plan.json 路径')
    p.add_argument('--output', '-o', default=None, help='输出报告路径')

    # merge
    p = sub.add_parser('merge', help='合并声部 ABC 片段')
    p.add_argument('plan', help='plan.json 路径')
    p.add_argument('fragments_dir', help='片段目录路径')
    p.add_argument('--mode', choices=['full', 'solo'], default='full')
    p.add_argument('--output', '-o', default=None, help='输出 score.abc 路径')

    # inject
    p = sub.add_parser('inject', help='注入 CC/弯音到 MIDI')
    p.add_argument('input', help='基础 MIDI 文件')
    p.add_argument('plan', help='expression_plan.json 路径')
    p.add_argument('output', help='输出 MIDI 文件')

    # extract-solo
    p = sub.add_parser('extract-solo', help='分轨 Solo 提取')
    p.add_argument('input', help='MIDI 文件')
    p.add_argument('start', type=float, help='起始时间（秒）')
    p.add_argument('end', type=float, help='结束时间（秒）')
    p.add_argument('output_dir', help='输出目录')

    # analyze
    p = sub.add_parser('analyze', help='MIDI piano roll analysis report')
    p.add_argument('input', help='MIDI 文件')
    p.add_argument('--segment', type=float, default=2.0, help='密度条时间分段（秒，最小 0.1）')

    # snapshot
    p = sub.add_parser('snapshot', help='备份 score.abc + 写入步骤日志')
    p.add_argument('--step', required=True, help='步骤编号 (如 2a)')
    p.add_argument('--status', default='成功', choices=['成功', '有警告', '失败'])
    p.add_argument('--output', default='', help='输出文件名')
    p.add_argument('--note', default='', help='补充说明')
    p.add_argument('--workdir', default='.clef-work', help='工作目录')

    # archive
    p = sub.add_parser('archive', help='归档最终产出到 output/{title}/ 目录')
    p.add_argument('--workdir', default='.clef-work', help='工作目录')

    # midi-to-audio
    p = sub.add_parser('midi-to-audio', help='用 FluidSynth 将 MIDI 转为音频（WAV/OGG）')
    p.add_argument('input', help='MIDI 文件或目录（配合 --batch）')
    p.add_argument('--sf2', required=True, help='SoundFont (.sf2) 文件路径')
    p.add_argument('--output-dir', '-o', default='', help='输出目录（默认和输入同目录）')
    p.add_argument('--format', '-f', choices=['wav', 'ogg', 'mp3'], default='wav', help='输出格式')
    p.add_argument('--sample-rate', '-r', type=int, default=44100, help='采样率（默认 44100）')
    p.add_argument('--gain', '-g', type=float, default=1.0, help='音量增益（默认 1.0，FluidSynth 原始默认 0.2）')
    p.add_argument('--batch', action='store_true', help='批量模式：input 为目录，转换其中所有 .mid 文件')

    # midi-to-abc
    p = sub.add_parser('midi-to-abc', help='将 MIDI 文件转换为 ABC 记谱法')
    p.add_argument('input', help='输入 MIDI 文件')
    p.add_argument('--output', '-o', required=True, help='输出 ABC 文件')

    args = parser.parse_args()

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
