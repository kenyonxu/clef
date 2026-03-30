# clef-compose 工作流问题修复计划

> 日期：2026-03-30
> 来源：DungeonExploration 作曲实战中发现的问题

## 问题总览

| ID | 优先级 | 问题 | 根因 | 影响 |
|----|--------|------|------|------|
| P0-1 | **P0** | validate_abc.py 和弦时值误报 4.5 beats | `_calc_abc_duration` 未过滤和弦标注 `"Am"` 中的字母 D | 每次 validate 必 FAIL |
| P0-2 | **P0** | validate_abc.py 八度偏移 +12 | music21 将 `a` 解析为 C5(72)，abc_to_midi 将 `a` 解析为 A4(69) | pitch_range/sweet_spot/voice_overlap 全错 |
| P1-1 | **P1** | Rhythmist 无输出自检 | agent prompt 缺少时值求和+音域验证步骤 | 低音线出现 10/8 小节和 C5 超域 |
| P1-2 | **P1** | Composer/Harmonist 同类风险 | 同上，三个 agent 均无自检机制 | 潜在同类错误 |
| P2 | **P2** | expression_plan.json 手写无校验 | inject_expression.py 无 JSON schema 校验 | 语法错误导致注入失败 |
| P3 | **P3** | clef_tools.py analyze 参数/文档不一致 | SKILL.md 记录 `analyze -o` 但实际不支持 | 用户困惑 |

---

## Phase 1: validate_abc.py 修复（P0-1 + P0-2）

### 1.1 修复和弦标注导致的时值误报（P0-1）

**文件**：`.claude/skills/clef-compose/scripts/validate_abc.py`
**函数**：`_calc_abc_duration`（第 377-440 行）

**根因分析**：
- 第 390 行 `tokens = re.sub(r"![^!]*!", "", tokens)` 只过滤了 ABC 装饰标记 `!xxx!`
- 和弦标注 `"Am"` 中的 `A` 和 `"Dm"` 中的 `D` 未被过滤
- 正则 `pattern = re.compile(r"([^A-Ga-gzZ~]*)([A-Ga-gzZ~])([,']*)(\d*(?:/\d+)?)")` 将 `"D"` 中的 `D` 匹配为音符，贡献 0.5 拍额外时长
- 导致 `"Am" [ACE]8` 被计算为 4.5 拍（正确应为 4.0）

**修复方案**：
在第 390 行（过滤 `!xxx!` 之后）添加一行，过滤引号标注：
```python
# 第 390 行之后添加
tokens = re.sub(r'"[^"]*"', "", tokens)
```

**验证**：
```bash
python -m pytest tests/test_validate_abc.py -v -k "measure_duration"
```
需新增测试用例：包含 `"Am"` 标注的和弦小节应返回 4.0 beats。

### 1.2 修复 music21 八度偏移（P0-2）

**文件**：`.claude/skills/clef-compose/scripts/validate_abc.py`
**影响范围**：6 个 `.midi` 读取点

**根因分析**：
- abc_to_midi.py 的 `NOTE_PITCH` 定义：`'a': 69`（A4），`'A': 57`（A3）
- music21 的 ABC 解析器：`a` → A5(81)，`A` → A4(69)，偏移 +12
- validate_abc.py 使用 music21 解析后直接读 `.midi`，导致所有音高偏高一个八度

**修复方案**：
创建辅助函数统一修正八度偏移：
```python
def _abc_midi(pitch_obj) -> int:
    """Convert music21 pitch to abc_to_midi compatible MIDI number.

    music21 ABC parser maps 'a' to A5(81), but abc_to_midi maps 'a' to A4(69).
    This -12 offset aligns validate_abc.py with the conversion tool.
    """
    return pitch_obj.midi - 12
```

替换所有 7 个 `.midi` 读取点：

| 行号 | 原代码 | 替换为 |
|------|--------|--------|
| L228 | `[p.midi for p in note.pitches]` | `[_abc_midi(p) for p in note.pitches]` |
| L231 | `[note.pitch.midi]` | `[_abc_midi(note.pitch)]` |
| L495 | `music21.pitch.Pitch(parts[0]).midi` | `_abc_midi(music21.pitch.Pitch(parts[0]))` |
| L496 | `music21.pitch.Pitch(parts[1]).midi` | `_abc_midi(music21.pitch.Pitch(parts[1]))` |
| L550 | `midi_notes.extend(p.midi for p in note.pitches)` | `midi_notes.extend(_abc_midi(p) for p in note.pitches)` |
| L552 | `midi_notes.append(note.pitch.midi)` | `midi_notes.append(_abc_midi(note.pitch))` |
| L664 | `if ss_lo <= p.midi <= ss_hi:` | `if ss_lo <= _abc_midi(p) <= ss_hi:` |

**验证**：
```bash
python -m pytest tests/test_validate_abc.py -v -k "pitch_range or sweet_spot or overlap"
```
需更新现有测试用例的预期 MIDI 值（全部 -12）。

### 1.3 Phase 1 依赖与风险

- **依赖**：1.1 和 1.2 互相独立，可并行
- **风险**：`_abc_midi` 函数对所有声部统一 -12，需确认 music21 对不同声部（treble/bass/perc）的八度偏移是否一致。根据 DungeonExploration 实测数据，bass 声部 `C,` = music21 C3(48) → 修正后 36(C2)，与 abc_to_midi 一致
- **复杂度**：Low

---

## Phase 2: Agent Prompt 自检机制（P1-1 + P1-2）

### 2.1 添加通用输出自检节

**文件**：
- `.claude/agents/clef-rhythmist.md`
- `.claude/agents/clef-composer.md`
- `.claude/agents/clef-harmonist.md`

**方案**：在每个 agent 的"约束"节末尾，添加统一的"输出自检"子节：

```markdown
## 输出自检（生成后必须执行）

生成 ABC 片段后，必须逐项验证以下内容：

1. **小节时值**：每小节所有音符/休止符的时值总和必须等于拍号规定的拍数。
   - L:1/8 + M:4/4 时，每小节 = 8 个八分音符
   - 计算方法：逐小节累加每个音符的 duration 值，包括 z（休止）

2. **音域合规**：所有音符必须在 plan.json 对应声部的 `sf2.key_range` 范围内。
   - 旋律(V:1)：检查 plan.orchestration.melody.sf2.key_range
   - 和声(V:2)：检查 plan.orchestration.harmony.sf2.key_range
   - 低音(V:3)：检查 plan.orchestration.bass.sf2.key_range

3. **ABC 八度规则**：
   - 小写字母 = C4 起始八度（a=A4=69, c=C4=60）
   - 大写字母 = C3 起始八度（A=A3=57, C=C3=48）
   - 逗号 `,` = 降低八度，撇号 `'` = 升高八度

4. **声部小节数**：输出小节数必须与 plan.json 对应 section 的 measures 一致。

如果自检发现错误，必须在输出中修正后再返回。不要输出未通过自检的 ABC。
```

### 2.2 Rhythmist 附加约束

**文件**：`.claude/agents/clef-rhythmist.md`

在 SF2 约束节中补充低音线音域硬约束：
```markdown
- 低音线所有音符必须落在 plan.orchestration.bass.sf2.key_range 内
- ABC 八度参考：A,=A2(45), C,=C3(48), E,=E3(52), G,=G3(55)
- 禁止使用无逗号的小写字母（c=C5, 超出低音域）
```

### 2.3 Phase 2 依赖与风险

- **依赖**：无，独立于 Phase 1
- **风险**：Low。仅修改 markdown prompt，不影响代码逻辑
- **复杂度**：Low

---

## Phase 3: expression_plan.json 校验（P2）

### 3.1 inject_expression.py 添加 JSON schema 校验

**文件**：`.claude/skills/clef-compose/scripts/inject_expression.py`

**方案**：在 `inject()` 函数的 JSON 加载后、注入前，添加 schema 校验：

```python
def _validate_expression_plan(plan: dict) -> list[str]:
    """Validate expression_plan.json structure. Returns list of error messages."""
    errors = []
    if "tracks" not in plan:
        errors.append("Missing top-level 'tracks' key")
        return errors

    for i, track in enumerate(plan["tracks"]):
        if "channel" not in track:
            errors.append(f"Track {i}: missing 'channel'")
        if "events" not in track:
            errors.append(f"Track {i}: missing 'events'")
            continue
        for j, event in enumerate(track["events"]):
            if "type" not in event:
                errors.append(f"Track {i} event {j}: missing 'type'")
            elif event["type"] not in ("cc", "pitch_bend"):
                errors.append(f"Track {i} event {j}: invalid type '{event['type']}'")
            if "time_beats" not in event:
                errors.append(f"Track {i} event {j}: missing 'time_beats'")
            if event.get("type") == "cc" and "control" not in event:
                errors.append(f"Track {i} event {j}: cc event missing 'control'")
            if event.get("type") == "cc" and "value" not in event:
                errors.append(f"Track {i} event {j}: cc event missing 'value'")
            if event.get("type") == "pitch_bend" and "value" not in event:
                errors.append(f"Track {i} event {j}: pitch_bend event missing 'value'")
    return errors
```

在 `inject()` 中调用，校验失败时打印错误并 exit(1)。

### 3.2 Phase 3 依赖与风险

- **依赖**：无
- **风险**：Low。只添加校验，不修改注入逻辑
- **复杂度**：Low

---

## Phase 4: 文档与参数对齐（P3）

### 4.1 修复 SKILL.md 文档

**文件**：`.claude/skills/clef-compose/SKILL.md`

**修改**：
- 第 37 行附近：移除 `analyze -o <report>` 中的 `-o` 选项描述
- 第 287 行附近：同上
- 添加 `--balance-sections <plan.json>` 的文档说明

### 4.2 Phase 4 依赖与风险

- **依赖**：无
- **风险**：None
- **复杂度**：Trivial

---

## 执行顺序与依赖图

```
Phase 1 (P0) ──┐
                ├── Phase 5: 集成验证
Phase 2 (P1) ──┤
                ├──
Phase 3 (P2) ──┤
                ├──
Phase 4 (P3) ──┘
```

所有 Phase 互相独立，可并行执行。Phase 5 在所有 Phase 完成后执行。

## Phase 5: 集成验证

使用 DungeonExploration 的 score.abc 作为测试输入：

```bash
# 1. 验证 validate_abc.py 修复
python scripts/validate_abc.py .clef-work/score.abc .clef-work/plan.json
# 预期：无 FAIL（P0-1 修复后 measure_duration PASS，P0-2 修复后 sweet_spot 改善）

# 2. 验证 inject schema 校验
python scripts/clef_tools.py inject base.mid invalid_plan.json out.mid
# 预期：报具体 schema 错误并 exit(1)

# 3. 运行现有测试
cd .claude/skills/clef-compose && python -m pytest tests/ -v
# 预期：全部 PASS（需更新预期值）
```

## 复杂度估算

| Phase | 修改文件数 | 新增测试 | 复杂度 |
|-------|-----------|---------|--------|
| Phase 1 | 1 (validate_abc.py) | 2-3 个 | Low |
| Phase 2 | 3 (agent .md) | 0 | Low |
| Phase 3 | 1 (inject_expression.py) | 1 个 | Low |
| Phase 4 | 1 (SKILL.md) | 0 | Trivial |
