# 工具链参考

所有脚本位于 `.claude/skills/clef-compose/scripts/`。

## 工具列表

| 工具 | 用途 | 调用方式 |
|------|------|----------|
| `abc_to_midi.py` | ABC → MIDI 转换 | `python scripts/abc_to_midi.py` (通过函数调用) |
| `validate_abc.py` | music21 技术验证（6 项检查，见下） | `python scripts/validate_abc.py <abc> <plan>` |
| `abc_lint.py` | 确定性 ABC 扫描（5 项：升降号/%%V:/||/时值/音域） | `python scripts/abc_lint.py <abc> [--fix] [--plan plan.json]` |
| `merge_abc.py` | 合并多声部 ABC（自动 sanitize） | 通过 `clef_tools.py merge` 调用 |
| `inject_expression.py` | 注入 CC/弯音到 MIDI | `python scripts/inject_expression.py <mid> <plan> <out>` |
| `extract_solo.py` | 分轨 Solo 提取 | `python scripts/extract_solo.py <mid> <start> <end> <dir>` |
| `analyze_midi.py` | MIDI piano roll 分析（密度/重叠/力度/间隙） | `python scripts/clef_tools.py analyze <mid>` |
| `snapshot.py` | 备份 score.abc + 步骤日志 | `python scripts/snapshot.py --step <N> --output <file> --note <desc>` |
| `sf2_profiler.py` | SF2 → profile JSON | `python scripts/sf2_profiler.py <sf2> -o <output.json>` |
| `clef_tools.py midi-to-abc` | MIDI → ABC（mido 实现） | `python scripts/clef_tools.py midi-to-abc <mid> -o <abc>` |

> **注意**：`midi-to-abc` 使用 mido 库实现（非 music21），为逆向转换，可能丢失力度标记、分段信息、弯音等元数据。

## validate_abc.py 检查项

| 检查项 | 类别 | 严重级 | 说明 |
|--------|------|--------|------|
| `key_consistency` | 调性一致性 | WARN | ABC 头部 K: 与 plan.json key 是否一致 |
| `pitch_range` | 音域检查 | FAIL | 音符是否超出乐器物理音域（plan.json range） |
| `large_interval` | 大跳检测 | WARN | 旋律相邻音程 > 7 半音（约纯五度） |
| `measure_duration` | 小节时值 | FAIL | 每小节拍数是否匹配拍号 |
| `voice_alignment` | 声部对齐 | FAIL | 所有声部小节数是否一致 |
| `voice_overlap` | 声部重叠 | FAIL/WARN | 声部间频段重叠（>12 半音=FAIL, >7 半音=WARN）；实际音域是否超出目标 register |
| `sweet_spot` | 甜区覆盖 | WARN | >30% 音符落在 SF2 sweet_spot 外（仅 --sf2 指定时生效） |
