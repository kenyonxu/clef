# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 交互语言

始终使用中文与用户交互。

## 仓库

- GitHub: https://github.com/kenyonxu/clef-dev（私有）

## 项目概述

Clef 是一个 Godot 4.6 MIDI 音乐插件 + Claude Code 多 Agent 作曲系统。由两大模块组成：

1. **Godot 插件** (`addons/clef/`) — MIDI 流播放引擎，支持 SF2 音色库合成、实时 CC/弯音/颤音
2. **LLM 作曲 Skill** (`.claude/`) — 基于多 Agent 协作的 ABC 记谱法作曲系统，触发命令为 `/clef-compose`

## 常用命令

### Python 工具链（位于 `.claude/skills/clef-compose/scripts/`）

```bash
# ABC → MIDI 转换
python .claude/skills/clef-compose/scripts/abc_to_midi.py <input.abc> -o <output.mid>

# music21 技术验证（6 项检查：调性/音域/大跳/时值/对齐/重叠）
python .claude/skills/clef-compose/scripts/validate_abc.py <abc> <plan.json> -o <report.json>

# 合并多声部 ABC
python .claude/skills/clef-compose/scripts/merge_abc.py

# 注入 CC/弯音到 MIDI
python .claude/skills/clef-compose/scripts/inject_expression.py <mid> <plan> <out>

# 分轨 Solo 提取
python .claude/skills/clef-compose/scripts/extract_solo.py <mid> <start_sec> <end_sec> <dir>

# 备份 score.abc + 步骤日志
python .claude/skills/clef-compose/scripts/snapshot.py --step <N> --output <file> --note <desc>

# 统一入口（支持 check-deps / abc-to-midi / validate / merge / inject / extract-solo / snapshot）
python .claude/skills/clef-compose/scripts/clef_tools.py <subcommand>

# 依赖检查
python .claude/skills/clef-compose/scripts/check_dependencies.py

# Python 测试
cd .claude/skills/clef-compose && python -m pytest tests/ -v
```

### Godot 测试

```bash
godot --headless --script addons/clef/tests/test_midi_composer.gd
godot --headless --script addons/clef/tests/test_midi_reader_quick.gd
godot --headless --script addons/clef/tests/test_cc_pitchbend_roundtrip.gd
```

## 架构

### Godot 插件 (`addons/clef/`)

```
player/
  midi_stream_player.gd    # 核心：MIDI 流播放器（AudioStreamPlayer 池 + 音序器）
  sf2_reader.gd            # SF2 文件解析
  sf2_bank.gd              # SF2 音色库管理
  sf2_data.gd              # SF2 采样数据
  clef_voice.gd            # 单音发声单元
  clef_voice_pool.gd       # 复音池管理
  clef_bank.gd             # 音色库抽象层
  channel_state.gd         # MIDI 通道状态（CC/弯音/Pitch）
converter.gd               # JSON → MidiData 转换（v2.0 拍单位）
midi_reader.gd             # MIDI 二进制解析
midi_writer.gd             # MidiData → MIDI 二进制输出
midi_resource.gd           # Resource 子类，序列化 MIDI 数据
midi_import_plugin.gd      # .mid 文件导入插件
midi_inspector_plugin.gd   # MidiResource Inspector 插件
editor/clef_file_context_menu.gd  # 文件右键菜单
ui/midi_player_ui.gd       # 播放器 UI
```

MIDI 播放链路：`MidiResource` → `Converter` → `MidiData` → `MidiStreamPlayer`（音序器调度 `ClefVoicePool`，每个音符独立 `AudioStreamPlayer`，音高通过 `pitch_scale`，ADSR 通过 `volume_db`）

### 多 Agent 作曲系统 (`.claude/`)

| Agent | 文件 | 职责 | 输出 |
|-------|------|------|------|
| Composer | `agents/clef-composer.md` | 旋律创作 V:1 | ABC 片段 |
| Harmonist | `agents/clef-harmonist.md` | 和声编配 V:2 | ABC 片段 |
| Rhythmist | `agents/clef-rhythmist.md` | 低音 V:3 + 鼓 V:4 | ABC 片段 |
| Orchestrator | `agents/clef-orchestrator.md` | 表现力（CC7/CC10/CC91/弯音） | expression_plan.json |
| Reviewer | `agents/clef-reviewer.md` | 音乐质量评审（6 维度打分） | review_report.json |
| Revision | `agents/clef-revision.md` | 最小干预格式修正 | 修正后 score.abc |
| Leader | `agents/clef-leader.md` | 迭代调度（依赖/合并/终止） | tasks.json |

Skill 定义在 `.claude/skills/clef-compose/SKILL.md`，核心乐理已拆分为 6 个子技能（theory-abc / theory-melody / theory-harmony / theory-rhythm / theory-orchestration / theory-structure），由各 Agent 通过 `skills:` frontmatter 预加载。

**工作流**：Step 0 需求解析 → Step 1a plan.json → Step 1b 方向小样（用户确认） → Step 2a 完整创作 → Step 2b Leader 迭代（最多 3 轮） → Step 3 表现力注入

**工作目录**：`.clef-work/` 存放 plan.json、score.abc、各类 report、版本历史；`addons/clef/output/` 存放最终 MIDI 输出。

## 关键约定

- ABC 声部编号：V:1 旋律、V:2 和声、V:3 低音、V:4 鼓（channel 9）
- `validate_abc.py` 检查项中 severity=FAIL 必须修正才能继续
- `plan.json` 中 `range` 为乐器物理极限，`register` 为本次编曲目标频段（range 子集）
- `generation_order` 控制旋律/和声的生成先后顺序（默认先和声后旋律）
- Revision Agent 只修正格式，绝不修改创作内容
- Leader 迭代中依赖任务（`depends_on`）完成后必须 merge → validate 通过才派发下一个
- Godot 项目使用 Jolt Physics、D3D12、Forward Plus 渲染器
