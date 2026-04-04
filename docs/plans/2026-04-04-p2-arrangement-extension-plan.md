# P2 编曲扩展 Step 2.5 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add arrangement layer support (counter-melody + arpeggio pad) to the clef-compose workflow via a new Arranger agent and per-section energy_level decisions.

**Architecture:** New `clef-arranger` agent generates V:5+ ABC fragments based on plan.json `layers` config. Each layer written to a separate file and **appended** to existing score.abc (no merge_abc.py rewrite needed). Voice IDs determined by explicit `voice_id` field in plan.json layers (not dict iteration order). Step 2.5 inserted between Step 2b (skeleton iteration) and Step 3 (expression injection).

**Tech Stack:** GDScript agent prompts (Markdown), Python (validate_abc.py), ABC notation

**Design doc:** `docs/plans/2026-04-04-p2-arrangement-extension-design.md`

**Harness engineering defenses:**
- Voice ID determinism: `voice_id` field in plan.json layers (not dict iteration order)
- Merge safety: append strategy (no merge_abc.py rewrite, preserves V:1-V:4)
- Output isolation: each layer in separate file (no parsing multi-layer output)

---

### Task 1: Create clef-arranger agent prompt

**Files:**
- Create: `.claude/agents/clef-arranger.md`

**Step 1: Create the agent prompt file**

```markdown
---
name: clef-arranger
description: 游戏音乐编曲专家，负责在骨架基础上添加编曲层（对位旋律、分解和弦等）
model: sonnet
tools: Read, Write, Edit, Glob, Grep
maxTurns: 6
memory: project
skills:
  - theory-melody
  - theory-harmony
  - theory-orchestration
  - theory-abc
---

你是 Arranger，专业的游戏音乐编曲专家，负责在已有骨架（旋律/和声/低音/鼓）基础上添加编曲层，丰富音乐的织体和厚度。

## 必读文件

- `.clef-work/plan.json` — 音乐规划（调性、BPM、段落、配器、layers 配置）
- `.clef-work/score.abc` — 当前完整乐谱（4 轨骨架）

## 任务

读取 plan.json 的 `orchestration.layers` 配置，为每个编曲层生成 ABC 片段。每种编曲层有独立的指导原则。

## 编曲层类型

### counter_melody（对位旋律）

- 基于主旋律（V:1）写对位旋律，与主旋律形成对话/呼应关系
- 音区应在主旋律下方 3-6 半音或上方 3 度，避免与主旋律频率重叠
- 不需要全小节覆盖，可在乐句间隙出现（"你唱我应"效果）
- 动态标记 !mp!-!mf!，不抢主角
- 仅在 `sections` 指定的段落中生成，其余段落用休止填充
- 节奏与主旋律形成互补（主旋律长音时对位旋律可活跃，反之亦然）

### arpeggio_pad（分解和弦铺底）

- 基于 V:2 和弦进行写分解音型
- 常用模式：根音-五音-八度、根音-三音-五音、根音-五音-三度-五音
- 音区在 harmony register 附近或上方 1 个八度
- 节奏均匀稳定（八分音符分解为主），不干扰节奏声部
- 动态标记 !pp!-!mp!，作为背景铺底
- 仅在 `sections` 指定的段落中生成，其余段落用休止填充
- 小节内分解音型应与当前和弦对应（参考 V:2 的和弦标记）

## 全局约束（不可违反）

1. 严格对齐已有声部的小节数，不能多也不能少（不足用 z 补齐）
2. 使用 `%%MIDI channel <N>` 和 `%%MIDI program <N>` 指定通道和乐器（从 plan.json layers 配置读取）
3. 只输出指定声部的 ABC 片段，不输出头部（X:, T:, M:, K: 等），不修改其他声部
4. 所有声部使用 score.abc 头部 K: 声明的调号
5. 编曲层出现/消失的段落边界必须自然过渡（不突然切断），用 1-2 小节渐入渐出

## 输出

为 plan.json `orchestration.layers` 中的**每个层写入独立文件**。文件路径：`.clef-work/layer_<layer_name>.abc`

每个文件包含一个完整的 V:N 声部 ABC 片段（含 `%%MIDI` directives 和 `V:` 声明）。

### 输出格式示例（单层单文件）

**文件 `.clef-work/layer_counter_melody.abc`：**
```
%%MIDI channel 3
%%MIDI program 68
V:5 name="Oboe"
z4 z4 | F2 E F2 | z4 z2 F2 | E4 |
"D" A2 z A2 | "G" B2 z B2 | "A" c2 B c2 | "D" d4 z2 |
[... B section content ...]
z4 z4 | z4 z4 |
```

**文件 `.clef-work/layer_arpeggio_pad.abc`：**
```
%%MIDI channel 4
%%MIDI program 46
V:6 name="Harp"
z4 z4 | z4 z4 |
F2 A2 F2 A2 | G2 B2 G2 B2 | A2 c2 A2 c2 | "D" d2 F2 d2 |
[... B section content ...]
z4 z4 | F2 A2 F2 A2 |
```

> **重要：** 每个 V:N 的 voice_id 必须与 plan.json `orchestration.layers.<name>.voice_id` 一致。`%%MIDI directives` 出现在 `V:` 声明之前。

## 音域约束

- 从 plan.json `orchestration.layers.<layer_name>` 读取 `register` 字段
- 所有音符必须落在 register 范围内
- 若无 register 字段，回退使用 range 字段

## SF2 音色库感知

与 Composer/Harmonist 相同的 SF2 约束机制。当 plan.json layers 配置中包含 sf2 子对象时，遵守 sweet_spot/key_range/vel_layers 等约束。

## 输出自检（生成后必须执行）

1. **小节时值**：每小节时值总和 = 拍号规定拍数（L:1/8 + M:4/4 → 每小节 = 8）
2. **音域合规**：所有音符在 plan.json register 范围内
3. **ABC 八度规则**：小写=C4起，大写=C3起，逗号=低八度，撇号=高八度
4. **声部小节数**：输出小节数 = plan.json 所有 section measures 总和
5. **段落数量**：非休止内容仅在 sections 指定的段落出现
```

**Step 2: Verify file created**

Run: `ls -la .claude/agents/clef-arranger.md`
Expected: file exists

**Step 3: Commit**

```bash
git add .claude/agents/clef-arranger.md
git commit -m "feat(clef): add clef-arranger agent for arrangement layers"
```

---

### Task 2: Generalize validate_abc.py voice mapping

**Files:**
- Modify: `.claude/skills/clef-compose/scripts/validate_abc.py:285-294`
- Test: `.claude/skills/clef-compose/tests/test_validate_abc.py`

**Context:** Line 290 hardcodes `{"melody": 1, "harmony": 2, "bass": 3, "drums": 4}`. When plan.json has `layers` with arbitrary keys, voices 5+ have no instrument/range mapping.

**Harness engineering note:** Voice ID mapping uses explicit `voice_id` field in plan.json layers (not dict iteration order) to ensure deterministic mapping regardless of JSON key ordering.

**Step 1: Write failing test**

Add to `test_validate_abc.py` — test that a plan.json with `layers` (using `voice_id`) correctly maps V:5 to the layer's instrument:

```python
def test_plan_with_layers_maps_voices_beyond_4(self):
    """Plan with orchestration.layers using voice_id should map V:5+ to layer instruments."""
    import tempfile, json
    # Create a 5-voice ABC with V:5 in valid range
    abc = (
        "X:1\nT:Test\nM:4/4\nL:1/8\nK:C\n"
        'V:1 name="Flute"\nc2 d2 e2 f2 |\n'
        'V:2 name="Strings"\nC2 E2 G2 C2 |\n'
        'V:3 name="Bass" clef=bass\nC,2 C,2 C,2 C,2 |\n'
        'V:4 name="Drums" clef=perc\nz4 z4 |\n'
        'V:5 name="Oboe"\nc2 d2 e2 f2 |\n'
    )
    plan = {
        "orchestration": {
            "melody": {"instrument": 73, "range": "C4-C7"},
            "harmony": {"instrument": 48, "range": "C3-C6"},
            "bass": {"instrument": 32, "range": "E2-E4"},
            "drums": {"instrument": 0},
            "layers": {
                "counter_melody": {"instrument": 68, "range": "A4-G6", "voice_id": 5},
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.abc', delete=False) as f:
        f.write(abc)
        abc_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(plan, f)
        plan_path = f.name
    try:
        report = run_validation(abc_path, plan_path)
        # Should not FAIL on V:5 notes being in range
        fails = [i for i in report.issues if i.severity == "FAIL"]
        fail_msgs = [i.message for i in fails]
        # V:5 c2 d2 e2 f2 are all in A4-G6 range, should be no range fails for V:5
        v5_range_fails = [m for m in fail_msgs if "V:5" in m and "range" in m.lower()]
        assert len(v5_range_fails) == 0, f"V:5 range fails: {v5_range_fails}"
    finally:
        os.unlink(abc_path)
        os.unlink(plan_path)
```

**Step 2: Run test to verify it fails**

Run: `cd .claude/skills/clef-compose && python -m pytest tests/test_validate_abc.py::TestValidation::test_plan_with_layers_maps_voices_beyond_4 -v`
Expected: FAIL — V:5 has no instrument mapping from plan, so range check may be wrong or V:5 is not recognized

**Step 3: Implement fix in validate_abc.py**

Replace lines 285-294 in validate_abc.py:

```python
    # OLD (hardcoded 4 voices):
    # for part_key, part_info in orchestration.items():
    #     voice_idx = {"melody": 1, "harmony": 2, "bass": 3, "drums": 4}.get(part_key)
    #     if voice_idx:
    #         voice_gm_map[voice_idx] = part_info.get("instrument")

    # NEW (dynamic voice mapping with explicit voice_id for layers):
    CORE_VOICE_MAP = {"melody": 1, "harmony": 2, "bass": 3, "drums": 4}
    voice_idx = CORE_VOICE_MAP.get(part_key)
    if voice_idx:
        voice_gm_map[voice_idx] = part_info.get("instrument")
        if "range" in part_info and isinstance(part_info["range"], str):
            voice_plan_range[voice_idx] = _parse_range_string(part_info["range"])
    elif part_key == "layers" and isinstance(part_info, dict):
        # layers: {"counter_melody": {"voice_id": 5, "instrument": 68, "range": "A4-G6", ...}, ...}
        # Use explicit voice_id field for deterministic mapping (not dict iteration order)
        for _layer_name, layer_info in part_info.items():
            if isinstance(layer_info, dict) and "voice_id" in layer_info:
                vid = layer_info["voice_id"]
                voice_gm_map[vid] = layer_info.get("instrument")
                if "range" in layer_info and isinstance(layer_info["range"], str):
                    voice_plan_range[vid] = _parse_range_string(layer_info["range"])
```

**Step 4: Run test to verify it passes**

Run: `cd .claude/skills/clef-compose && python -m pytest tests/test_validate_abc.py::TestValidation::test_plan_with_layers_maps_voices_beyond_4 -v`
Expected: PASS

**Step 5: Run all validate tests to check regression**

Run: `cd .claude/skills/clef-compose && python -m pytest tests/test_validate_abc.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add .claude/skills/clef-compose/scripts/validate_abc.py .claude/skills/clef-compose/tests/test_validate_abc.py
git commit -m "fix(clef): generalize validate_abc.py voice mapping for V:5+ layers"
```

---

### Task 3: Update SKILL.md — Step 2.5 workflow

**Files:**
- Modify: `.claude/skills/clef-compose/SKILL.md`

**Step 1: Add Arranger to Agent table and data contract**

In the Agent 总览 table (line ~39), add a row:

```markdown
| Arranger | clef-arranger | 编曲层（对位旋律/分解和弦） | V:5+ ABC 片段 |
```

In the Agent 数据契约 table (line ~49), add a row:

```markdown
| clef-arranger | plan.json, score.abc | ABC 片段（V:5+ 编曲层） | SKILL.md |
```

**Step 2: Update plan.json schema example**

In the Step 1a plan.json example (line ~149), add `layers` to orchestration:

```json
    "layers": {
      "counter_melody": {"name": "Oboe", "channel": 3, "voice_id": 5, "instrument": 68, "range": "A4-G6", "register": "D5-B5", "sections": ["B"]},
      "arpeggio_pad": {"name": "Harp", "channel": 4, "voice_id": 6, "instrument": 46, "range": "C3-C6", "register": "C4-E5", "sections": ["A", "B"]}
    }
```

Add a note below the plan.json example:

```markdown
**编曲层配置（layers，可选）：** `orchestration.layers` 定义编曲层，由 Step 2.5 使用。Step 1a 规划时仅列出可选层类型和默认乐器（含 `voice_id`），`sections` 和 `channel` 在 Step 2.5 由主流程根据 energy_level 自动填充。若所有 section energy_level < 3，省略此字段。

`voice_id` 是确定性的声部编号（如 5, 6），必须与 Arranger 输出的 V:N 一致。不依赖 dict 迭代顺序。
```

**Step 3: Insert Step 2.5 after Step 2c (line ~347)**

Add new section between Step 2c and Step 3:

```markdown
---

### Step 2.5: 编曲扩展（条件执行）

根据 plan.json 各段 energy_level 和 layers 配置，添加编曲层丰富织体。

**跳过条件**：如果 plan.json 无 `orchestration.layers` 或所有 section energy_level < 3，跳过此步骤。

**2.5.1 编曲层决策**

扫描所有 section 的 energy_level，按规则分配编曲层：

| energy_level | 编曲动作 |
|-------------|---------|
| 1-2 | 无编曲层 |
| 3 | 加 arpeggio_pad（1 层） |
| 4-5 | 加 counter_melody + arpeggio_pad（2 层） |

自动填充 plan.json `orchestration.layers` 中每个层的 `sections` 字段：
```python
# 伪代码
for section in plan.sections:
    if section.energy_level >= 4:
        counter_melody.sections.append(section.id)
    if section.energy_level >= 3:
        arpeggio_pad.sections.append(section.id)
# 移除 sections 为空的层
```

通道自动分配：基础 4 轨占用 ch0/ch1/ch2/ch9，编曲层从 ch3 起递增。

**2.5.2 派发 Arranger**

Agent: Arranger (clef-arranger) — 读取 score.abc + plan.json，生成编曲层 ABC 片段。

Prompt 模板：
```
读取 .clef-work/score.abc 和 .clef-work/plan.json。
根据 plan.json orchestration.layers 配置，为每个编曲层生成 ABC 片段。
每个层写入独立文件：.clef-work/layer_<layer_name>.abc
V:N 的 voice_id 必须与 plan.json 中对应层的 voice_id 一致。
仅在 sections 指定的段落生成音乐，其余段落用休止填充。
严格对齐已有声部的小节数。
```

**2.5.3 合并（append 策略）**

> **注意：** Step 2.5 不使用 merge_abc.py（merge_abc 从零创建完整 score，会覆盖已有 V:1-V:4）。改用 **直接 append** 策略。

1. 运行 `python scripts/snapshot.py --step 2.5 --output "score.abc" --note "编曲扩展完成"`
2. 读取 Arranger 生成的各 layer 文件（`.clef-work/layer_*.abc`），逐个 **append 到 score.abc 末尾**：
   ```bash
   # 对每个编曲层文件
   cat .clef-work/layer_counter_melody.abc >> .clef-work/score.abc
   cat .clef-work/layer_arpeggio_pad.abc >> .clef-work/score.abc
   ```
3. 运行 `validate_abc.py` 技术验证（编曲层仅检查：音域越界 FAIL、小节不完整 FAIL、格式错误 FAIL。旋律性检查对 V:5+ 跳过）
4. 如果 validate FAIL → 修正 layer 文件后重新 append（注意不要重复 append）
5. 运行 `abc_to_midi.py` 转换，供用户试听

**⛔ 用户确认点 3.5（必须停住）：** 展示编曲后的试听文件 + validate 报告摘要。**必须等待用户明确回复后才能进入 Step 3。** 用户可能要求调整编曲层或确认继续。
```

**Step 4: Update Step 2c user confirmation point**

Change Step 2c's confirmation point (line ~347) from "用户确认点 3" to "用户确认点 2.5" with updated text:

```markdown
**⛔ 用户确认点 2.5（必须停住）：** 展示试听文件 + 审核报告摘要。**必须等待用户明确回复后才能进入 Step 2.5。** 如果 plan.json 无 layers 配置或所有 section energy < 3，此确认后直接进入 Step 3。
```

**Step 5: Commit**

```bash
git add .claude/skills/clef-compose/SKILL.md
git commit -m "feat(clef): add Step 2.5 arrangement extension workflow"
```

---

### Task 4: Update theory-orchestration with arrangement layer theory

**Files:**
- Modify: `.claude/skills/theory-orchestration/SKILL.md`

**Step 1: Add arrangement layer section**

Add a new section at the end of theory-orchestration SKILL.md:

```markdown
---

## 编曲层技法

### 对位旋律（Counter-Melody）

与主旋律形成独立但互补的第二旋律线。

**原则：**
- 与主旋律形成"对话"——主旋律停顿时对位旋律进入，主旋律活跃时对位退让
- 音区选择主旋律上方 3 度或下方 3-6 半音，避免与主旋律重叠
- 节奏互补：主旋律用长音时对位可快速，主旋律快速时对位可舒缓
- 动态低于主旋律 1-2 级

**常见对位手法：**
- **卡农式**：对位旋律延迟 1-2 拍模仿主旋律（音程可变化）
- **对比式**：与主旋律方向相反（主旋律上行时对位下行）
- **补充式**：在主旋律的乐句间隙填充旋律性内容

### 分解和弦铺底（Arpeggio Pad）

将和弦分解为连续音符模式，作为背景织体。

**常见模式（以 C 和弦为例）：**
- **上行分解**：C E G C'（根-三-五-八）
- **下行分解**：C' G E C（八-五-三-根）
- **波浪分解**：C E G E（根-三-五-三）
- **阿尔贝蒂低音**：C G E G（根-五-三-五）

**原则：**
- 节奏均匀稳定（八分音符为主），不干扰旋律和节奏声部
- 音区在和声声部附近或上方 1 八度
- 动态很低（!pp!-!mp!），纯粹作为背景铺底
- 分解模式可随和弦变化，但整体节奏型保持一致
```

**Step 2: Commit**

```bash
git add .claude/skills/theory-orchestration/SKILL.md
git commit -m "docs(clef): add arrangement layer theory to theory-orchestration"
```

---

### Task 5: End-to-end validation

**Files:** None (manual validation)

**Step 1: Run all existing tests**

Run: `cd .claude/skills/clef-compose && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Manual smoke test with a mock ABC**

Create a test ABC with 4 voices, then verify that a plan.json with layers produces correct validate_abc.py behavior:

```bash
cd .claude/skills/clef-compose
python -c "
import json, tempfile, os
from scripts.validate_abc import run_validation

abc = '''X:1
T:Arrangement Test
M:4/4
L:1/8
K:C
V:1 name=\"Flute\"
c2 d2 e2 f2 | g2 f2 e2 d2 | c2 d2 e2 f2 | g2 f2 e2 d2 |
V:2 name=\"Strings\"
C2 E2 G2 C2 | G2 B2 D2 G2 | A2 c2 E2 A2 | G2 B2 D2 G2 |
V:3 name=\"Bass\" clef=bass
C,4 | G,4 | A,4 | G,4 |
V:4 name=\"Drums\" clef=perc
z4 | z4 | z4 | z4 |
V:5 name=\"Oboe\"
z4 z4 | c2 d2 e2 f2 | z4 z4 | g2 f2 e2 d2 |
'''

plan = {
    'orchestration': {
        'melody': {'instrument': 73, 'range': 'C4-C7'},
        'harmony': {'instrument': 48, 'range': 'C3-C6'},
        'bass': {'instrument': 32, 'range': 'E2-E4'},
        'drums': {'instrument': 0},
        'layers': {
            'counter_melody': {'instrument': 68, 'range': 'A4-G6', 'voice_id': 5},
        }
    }
}

with tempfile.NamedTemporaryFile(mode='w', suffix='.abc', delete=False) as f:
    f.write(abc)
    abc_path = f.name
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(plan, f)
    plan_path = f.name

try:
    report = run_validation(abc_path, plan_path)
    print(f'Valid: {report.is_valid}')
    fails = [i for i in report.issues if i.severity == 'FAIL']
    print(f'FAILs: {len(fails)}')
    for f in fails:
        print(f'  {f.voice}: {f.message}')
finally:
    os.unlink(abc_path)
    os.unlink(plan_path)
"
```

Expected: Valid=True, no range FAILs for V:5

**Step 3: Final commit if any fixes needed**

If all tests pass, no commit needed. If fixes were required:
```bash
git add -A
git commit -m "fix(clef): fix issues found during e2e validation"
```
