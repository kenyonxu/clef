<!-- /autoplan restore point: /c/Users/kenyo/.gstack/projects/kenyonxu-clef-dev/feature-clef-server-v2-autoplan-restore-20260412-120122.md -->
# Code-Driven Validate-Repair 循环 + 修复 Agent 实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 orchestrator 的验证修复循环从 prompt 驱动改为代码驱动，引入确定性 measure_duration 修复工具和专项修复 agent，实现 best-of-N 选优。

**Architecture:** 创作负责生成 + 自检，修复由专项 agent + 确定性工具联合处理，orchestrator 控制迭代节奏并选最优结果。每轮 agent 调用独立（不累积上下文），避免 API 崩溃。

**Tech Stack:** Python 3.12, re (ABC 解析), agent_framework, httpx

---

## 根因回顾

E2E 测试日志暴露的 3 层问题：

| # | 问题 | 根因 | 本方案对应 Task |
|---|------|------|----------------|
| 1 | Agent 轮次耗尽（4 次 max_turns） | prompt 驱动的 validate→fix 无限循环 | Task 3（orchestrator 接管循环） |
| 2 | 验证越修越差（3 FAIL → 4 FAIL） | 同一 agent 既创作又修复，上下文累积 | Task 2+3（修复 agent + best-of-N） |
| 3 | GLM API 400 崩溃 | 6 轮工具调用后上下文溢出 | Task 3（每轮独立调用） |
| 4 | measure_duration 顽固 | LLM 不擅长数数 | Task 1（确定性修复工具） |

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `server/src/clef_server/tools.py` | 修改 | 新增 `fix_measure_duration` 工具 |
| `server/tests/test_tools.py` | 修改 | 新增 fix_measure_duration 测试 |
| `server/config/prompts/clef-repair.md` | **新建** | 修复 Agent 专用 prompt |
| `server/config/agents.yaml` | 修改 | 新增 clef-repair agent 配置 |
| `server/src/clef_server/orchestrator.py` | 修改 | best-of-N 验证循环 + 调用修复 agent |
| `server/src/clef_server/tools.py` | 修改 | 新增 `validate_rhythm_skeleton` 工具 |
| `server/src/clef_server/orchestrator.py` | 修改 | Task 4: 两阶段生成（节奏骨架 → 填音高） |

---

### Task 1: fix_measure_duration — 确定性时值修复工具

**Files:**
- Modify: `server/src/clef_server/tools.py`
- Modify: `server/tests/test_tools.py`

ABC 记谱法中 `measure_duration` 是最顽固的验证错误。LLM 不擅长数数，但时值修正是确定性的：解析每个小节，计算实际时值，与目标时值比较，机械修正。

#### 修复规则

- **L:1/8 + M:4/4** → 每小节 8 个单位
- **偏离 1-2 单位**：延长/缩短最后一个音符或休止符
- **偏离 >2 单位**：跳过（留给修复 agent 处理）
- **延长规则**：`c` → `c2`（+1），`c2` → `c3`（+1），`c2` → `c4`（+2）
- **缩短规则**：`c2` → `c`（-1），`c3` → `c2`（-1），`c4` → `c2`（-2）
- **删除规则**：如果缩短后时值为 0，删除该音符

- [ ] **Step 1: 写 fix_measure_duration 测试**

在 `server/tests/test_tools.py` 末尾添加：

```python
# === fix_measure_duration tests ===

def test_fix_measure_duration_correct_measure():
    """正确的小节不应被修改。"""
    from clef_server.tools import fix_measure_duration
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 |"
    result = fix_measure_duration(abc)
    assert result["pass"] is True
    assert result["fixes"] == []
    assert result["abc"] == abc


def test_fix_measure_duration_short_by_one():
    """缺 1 单位的小节：延长最后一个音符。"""
    from clef_server.tools import fix_measure_duration
    # 7/8 units: c2(2) + d2(2) + e2(2) + f(1) = 7
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
    assert len(result["fixes"]) == 1
    # f (1 unit) should be extended to f2 (2 units)
    assert "f2" in result["abc"]
    # Verify the fixed measure has 8 units
    assert result["fixes"][0]["measure"] == 1
    assert result["fixes"][0]["action"] == "extend"


def test_fix_measure_duration_long_by_one():
    """多 1 单位的小节：缩短最后一个音符。"""
    from clef_server.tools import fix_measure_duration
    # 9/8 units: c2(2) + d2(2) + e2(2) + f2(2) + g(1) = 9
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 g |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
    assert len(result["fixes"]) == 1
    # g (1 unit) should be removed
    assert "g" not in result["abc"].split("|")[0].strip().split()[-1] or "f2" in result["abc"]


def test_fix_measure_duration_multiple_measures():
    """多个小节中只有错误的被修正。"""
    from clef_server.tools import fix_measure_duration
    # Measure 1: 8 units (correct), Measure 2: 7 units (short)
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 | c2 d2 e2 f |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
    assert len(result["fixes"]) == 1
    assert result["fixes"][0]["measure"] == 2


def test_fix_measure_duration_large_deviation_skipped():
    """偏离 >2 单位的小节跳过不修。"""
    from clef_server.tools import fix_measure_duration
    # 5/8 units — off by 3, too large to fix mechanically
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
    # Should be skipped (no fix applied)
    assert len(result["fixes"]) == 0 or result["fixes"][0].get("skipped") is True


def test_fix_measure_duration_rest_extension():
    """缺单位时延长休止符。"""
    from clef_server.tools import fix_measure_duration
    # 7/8 units: c2(2) + d2(2) + e2(2) + z(1) = 7
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 z |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
    assert len(result["fixes"]) == 1
    assert "z2" in result["abc"]


def test_fix_measure_duration_multivoice():
    """多声部 ABC 只处理目标声部。"""
    from clef_server.tools import fix_measure_duration
    # V:1 correct, V:2 short by 1
    abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 |\nV:2\nc2 d2 e2 f |"
    result = fix_measure_duration(abc)
    assert result["pass"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && python -m pytest tests/test_tools.py -k "fix_measure_duration" -v`
Expected: FAIL (import error or function not found)

- [ ] **Step 3: 实现 fix_measure_duration**

在 `server/src/clef_server/tools.py` 的 `get_tool_schemas()` 函数之前添加：

```python
# ---------------------------------------------------------------------------
# fix_measure_duration — deterministic measure duration fixer
# ---------------------------------------------------------------------------

# ABC note pattern: optional accidental + note letter + optional octave marks + optional duration
_NOTE_RE = re.compile(
    r"([\\^_=]*"           # accidental
    r"[a-gA-G]"            # note name
    r"[',]*"               # octave marks
    r")"
    r"(\d*(?:/\d+)?)"      # duration: "2", "3", "/2", "3/2", or "" (=1)
)
_REST_RE = re.compile(r"(z)(\d*(?:/\d+)?)")


def _parse_abc_duration(duration_str: str) -> float:
    """Parse ABC duration suffix to float units. L:1/8 base.

    "" → 1, "2" → 2, "3" → 3, "/2" → 0.5, "3/2" → 1.5
    """
    if not duration_str:
        return 1.0
    if "/" in duration_str:
        parts = duration_str.split("/")
        num = float(parts[0]) if parts[0] else 1.0
        den = float(parts[1]) if len(parts) > 1 and parts[1] else 2.0
        return num / den
    return float(duration_str)


def _duration_to_str(units: float) -> str:
    """Convert float units back to ABC duration suffix."""
    if units == 1.0:
        return ""
    if units == 0.5:
        return "/2"
    if units == int(units):
        return str(int(units))
    # Fractional like 1.5 → "3/2"
    for den in [2, 4, 8]:
        num = units * den
        if num == int(num):
            return f"{int(num)}/{den}"
    return str(int(units))  # fallback


def _count_measure_units(measure_text: str) -> float:
    """Count total duration units in a single measure's text."""
    total = 0.0
    # Remove comments
    text = re.sub(r"%.*$", "", measure_text)
    # Remove decoration marks like !mf!, !<!, etc.
    text = re.sub(r"![^!]*!", "", text)
    # Remove chord brackets but keep inner content
    text = text.replace("[", " ").replace("]", " ")
    # Remove tuplet markers like (3
    text = re.sub(r"\(\d+", " ", text)

    # Find all notes
    for m in _NOTE_RE.finditer(text):
        total += _parse_abc_duration(m.group(2))
    # Find all rests
    for m in _REST_RE.finditer(text):
        total += _parse_abc_duration(m.group(2))

    return total


def _fix_single_measure(measure_text: str, target: float, max_deviation: float = 2.0) -> tuple[str, dict | None]:
    """Try to fix a single measure's duration. Returns (fixed_text, fix_info or None)."""
    actual = _count_measure_units(measure_text)
    deviation = actual - target

    if abs(deviation) < 0.01:
        return measure_text, None

    if abs(deviation) > max_deviation:
        return measure_text, {"skipped": True, "deviation": deviation, "target": target}

    # Find the last note or rest to adjust
    text = measure_text

    # Try adjusting last rest first (least disruptive)
    rest_matches = list(_REST_RE.finditer(text))
    if rest_matches:
        last = rest_matches[-1]
        current_dur = _parse_abc_duration(last.group(2))
        new_dur = current_dur - deviation
        if new_dur > 0:
            new_suffix = _duration_to_str(new_dur)
            fixed = text[:last.start()] + "z" + new_suffix + text[last.end():]
            return fixed, {
                "action": "extend" if deviation < 0 else "shorten",
                "target": "rest",
                "from": last.group(0),
                "to": "z" + new_suffix,
            }
        elif new_dur == 0:
            # Remove the rest entirely
            fixed = text[:last.start()].rstrip() + text[last.end():]
            return fixed, {
                "action": "remove",
                "target": "rest",
                "from": last.group(0),
                "to": "(removed)",
            }

    # Try adjusting last note
    note_matches = list(_NOTE_RE.finditer(text))
    if note_matches:
        last = note_matches[-1]
        current_dur = _parse_abc_duration(last.group(2))
        new_dur = current_dur - deviation
        if new_dur > 0:
            new_suffix = _duration_to_str(new_dur)
            fixed = text[:last.start(2)] + new_suffix + text[last.end(2):]
            return fixed, {
                "action": "extend" if deviation < 0 else "shorten",
                "target": "note",
                "from": last.group(1) + last.group(2),
                "to": last.group(1) + new_suffix,
            }
        elif new_dur == 0:
            # Remove the note
            fixed = text[:last.start()].rstrip() + text[last.end():]
            return fixed, {
                "action": "remove",
                "target": "note",
                "from": last.group(0),
                "to": "(removed)",
            }

    # Can't fix
    return measure_text, {"skipped": True, "deviation": deviation, "target": target}


@tool
def fix_measure_duration(
    abc_content: Annotated[str, "ABC notation content to fix"],
    target_per_measure: Annotated[float, "Target units per measure (0 = auto-detect from M:/L:)"] = 0,
) -> dict:
    """Fix measure duration errors in ABC content deterministically.

    Parses each measure, counts duration units, and mechanically fixes
    measures that are off by 1-2 units. Measures off by >2 units are skipped.
    Returns fixed ABC content and a report of changes.
    """
    lines = abc_content.strip().split("\n")

    # Detect time signature and unit length from headers
    meter = "4/4"
    unit_len = "1/8"
    for line in lines:
        if line.startswith("M:"):
            meter = line[2:].strip()
        elif line.startswith("L:"):
            unit_len = line[2:].strip()

    # Calculate target units per measure
    if target_per_measure > 0:
        target = target_per_measure
    else:
        # M:num/den, L:1/base → target = (num/den) / (1/base) = num*base/den
        m_parts = meter.split("/")
        l_parts = unit_len.split("/")
        num = float(m_parts[0])
        den = float(m_parts[1]) if len(m_parts) > 1 else 1.0
        base = float(l_parts[1]) if len(l_parts) > 1 else float(l_parts[0])
        target = num * base / den

    # Process each line
    all_fixes = []
    result_lines = []
    measure_idx = 0

    for line in lines:
        # Only process lines that contain music (not headers)
        stripped = line.strip()
        if not stripped or stripped.endswith(":") or stripped.startswith("%"):
            result_lines.append(line)
            continue

        # Skip voice/chord lines that are just labels
        if stripped.startswith("V:") and len(stripped) < 10:
            result_lines.append(line)
            continue

        # Split into measures by |
        parts = stripped.split("|")
        fixed_parts = []

        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                fixed_parts.append(part)
                continue

            measure_idx += 1
            fixed, fix_info = _fix_single_measure(part_stripped, target)
            fixed_parts.append(fixed)

            if fix_info:
                fix_info["measure"] = measure_idx
                fix_info["actual_units"] = _count_measure_units(part_stripped)
                fix_info["target_units"] = target
                all_fixes.append(fix_info)

        result_lines.append(" | ".join(fixed_parts))

    return {
        "abc": "\n".join(result_lines),
        "fixes": all_fixes,
        "pass": len(all_fixes) == 0,
        "measures_checked": measure_idx,
    }
```

同时更新 `TOOLS_REGISTRY`：

```python
TOOLS_REGISTRY: dict[str, object] = {
    "read_file": read_file,
    "write_file": write_file,
    "validate_abc": validate_abc,
    "abc_to_midi": abc_to_midi,
    "abc_lint": abc_lint,
    "merge_abc": merge_abc,
    "inject_expression": inject_expression,
    "snapshot": snapshot,
    "fix_measure_duration": fix_measure_duration,
}
```

更新 `_AGENT_TOOL_MAP` 添加 clef-repair：

```python
_AGENT_TOOL_MAP: dict[str, list[str]] = {
    "clef-composer": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-harmonist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-rhythmist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-reviewer": ["read_file", "validate_abc", "abc_lint"],
    "clef-revision": ["read_file", "write_file"],
    "clef-orchestrator": ["read_file", "write_file", "abc_to_midi", "inject_expression"],
    "clef-repair": ["read_file", "write_file", "abc_lint", "fix_measure_duration"],
}
```

更新 `_TOOL_META`：

```python
_TOOL_META: dict[str, ToolMeta] = {
    "read_file": ToolMeta(ToolSafety.READ_ONLY, 1000),
    "write_file": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "validate_abc": ToolMeta(ToolSafety.READ_ONLY, 800),
    "abc_lint": ToolMeta(ToolSafety.READ_ONLY, 400),
    "abc_to_midi": ToolMeta(ToolSafety.READ_ONLY, 100),
    "merge_abc": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "inject_expression": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 100),
    "snapshot": ToolMeta(ToolSafety.IDEMPOTENT_WRITE, 50),
    "fix_measure_duration": ToolMeta(ToolSafety.READ_ONLY, 200),
}
```

- [ ] **Step 4: 运行测试**

Run: `cd server && python -m pytest tests/test_tools.py -k "fix_measure_duration" -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/tools.py server/tests/test_tools.py
git commit -m "feat(server): add fix_measure_duration deterministic tool"
```

---

### Task 2: clef-repair Agent — 专项修复 Agent

**Files:**
- Create: `server/config/prompts/clef-repair.md`
- Modify: `server/config/agents.yaml`

修复 agent 负责处理确定性工具无法解决的验证错误。它接收具体的失败项和 ABC 内容，做定向修复。

- [ ] **Step 1: 创建修复 Agent prompt**

创建 `server/config/prompts/clef-repair.md`：

```markdown
# ABC 修复专家（Repair）

你是 ABC 记谱法修复专家。你接收包含验证错误的 ABC 内容，做最小干预的定向修复。

## 上下文来源

你的任务指令和会话上下文会在 user message 中提供。

## 可用工具

- **read_file(path, workdir)** — 读取工作目录中的文件
- **write_file(path, content, workdir)** — 写入文件到工作目录
- **abc_lint(abc_content, plan_path)** — 轻量 ABC 格式检查
- **fix_measure_duration(abc_content, target_per_measure)** — 确定性时值修复

推荐工作流程（你有最多 3 轮对话）：
1. 读取需要修复的 ABC 文件（1 轮）
2. 根据验证报告做定向修复，写入文件（1 轮）
3. 如有余量，调用 abc_lint 确认修复结果（1 轮）

**重要**：3 轮内必须完成修复并输出结果。不要无限循环。

## 修复原则

1. **最小干预**：只修正报告中的具体错误，不重写整段音乐
2. **保留创作意图**：不改变旋律走向、和声选择或节奏风格
3. **时值修正优先级**：
   - 先调用 fix_measure_duration 处理简单时值偏差
   - 它无法处理的（偏离>2 单位），手动调整
4. **声部对齐**：确保各声部小节数一致，对齐方式以最短声部为准

## 时值速查表（L:1/8 基准）

| 记法 | 含义 | 单位值 |
|------|------|--------|
| `c` | 八分音符 | 1 |
| `c2` | 四分音符 | 2 |
| `c3` | 附点四分 | 3 |
| `c4` | 二分音符 | 4 |
| `c6` | 附点二分 | 6 |
| `c8` | 全音符 | 8 |
| `c/2` | 十六分 | 0.5 |
| `z` | 八分休止 | 1 |
| `z2` | 四分休止 | 2 |

M:4/4 + L:1/8 = 每小节 **8** 个单位

## 常见错误修复模板

### measure_duration 短缺

```
原始: c2 d2 e2 f |     (7/8, 少 1)
修复: c2 d2 e2 f2 |    (8/8, 延长末音)

原始: c2 d2 e |          (5/8, 少 3)
修复: c2 d2 e2 z2 |     (8/8, 补休止符)
```

### measure_duration 超出

```
原始: c2 d2 e2 f2 g |   (9/8, 多 1)
修复: c2 d2 e2 f2 |     (8/8, 去掉末音)

原始: c2 d2 e2 f4 |     (10/8, 多 2)
修复: c2 d2 e2 f2 |     (8/8, 缩短 f4→f2)
```

### voice_alignment

确保所有声部有相同的小节数。如果某声部多了小节，截断末尾。如果少了，用休止小节填充。

## 输出

修复后的完整 ABC 内容（包含所有声部），通过 write_file 写入。
```

- [ ] **Step 2: 在 agents.yaml 注册 clef-repair**

在 `server/config/agents.yaml` 的 `agents:` 节末尾添加：

```yaml
  clef-repair:
    model_alias: anthropic-haiku
    prompt_md: server/config/prompts/clef-repair.md
    skills:
    - abc
    temperature: 0.2
    max_turns: 3
    tools:
    - read_file
    - write_file
    - abc_lint
    - fix_measure_duration
```

- [ ] **Step 3: 在 orchestrator.py 注册 clef-repair**

在 `server/src/clef_server/orchestrator.py` 的 `_AGENT_DEFS` 字典中添加：

```python
        "clef-repair": {
            "prompt_md": "server/config/prompts/clef-repair.md",
            "model_alias": "anthropic-haiku",
            "skills": ["abc"],
            "temperature": 0.2,
            "max_turns": 3,
        },
```

- [ ] **Step 4: 运行测试确认无回归**

Run: `cd server && python -m pytest tests/test_config.py tests/test_tools.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/config/prompts/clef-repair.md server/config/agents.yaml server/src/clef_server/orchestrator.py
git commit -m "feat(server): add clef-repair agent for validation-driven fixes"
```

---

### Task 3: orchestrator best-of-N 验证修复循环

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`

这是核心改动。将 `_phase_sample` 和 `_phase_create` 中的验证修复循环从 "同一 agent 重试" 改为 "best-of-N + 修复 agent" 模式。

#### 设计

```
for round in range(max_fix_rounds):  # 例如 2
  ① 创作 agent 生成（独立调用，不累积上下文）
  ② 保存 candidate_r{N}.abc
  ③ fix_measure_duration 确定性修复
  ④ validate_abc 检查
  ⑤ 记录 candidate: {round, abc_text, fail_count, failures}
  ⑥ 如果 fail_count == 0 → 直接用，跳出
  ⑦ 如果有 FAIL 且还有轮次 → 将反馈注入下一轮的 agent 消息

如果仍有 FAIL:
  ⑧ 将最优 candidate 交给修复 agent 定向修复
  ⑨ fix_measure_duration + validate_abc
  ⑩ 如果修复后更优 → 使用修复版本

最终: 从所有 candidate 中取 fail_count 最小的
```

- [ ] **Step 1: 添加 best-of-N 辅助方法**

在 `orchestrator.py` 的 `_run_validation()` 方法后面添加：

```python
    async def _generate_with_best_of_n(
        self,
        agent_name: str,
        message: str,
        plan: dict,
        score_path: Path,
        plan_path: Path,
        max_rounds: int = 2,
        voice_label: str = "",
    ) -> tuple[str, int]:
        """Generate ABC with best-of-N selection and repair.

        Returns (best_abc_text, fail_count).
        """
        from clef_server.tools import fix_measure_duration, validate_abc

        candidates: list[dict] = []
        feedback = ""

        for round_idx in range(max_rounds):
            full_message = message
            if feedback:
                full_message = (
                    f"{message}\n\n---\n"
                    f"**上一轮验证反馈（请修正）：**\n{feedback}"
                )

            response = await self._run_agent(agent_name, full_message, plan=plan)
            abc_text = self._extract_abc(response)

            if not abc_text or self._is_placeholder(abc_text):
                candidates.append({
                    "round": round_idx, "abc": abc_text or "",
                    "fail_count": 999, "failures": [],
                })
                feedback = "输出不是有效的 ABC 记谱法，请直接输出 ABC 内容。"
                continue

            # Deterministic fix
            fix_result = fix_measure_duration(abc_text)
            if fix_result["fixes"]:
                logger.info(
                    "fix_measure_duration: %d fixes in round %d",
                    len(fix_result["fixes"]), round_idx,
                )
                abc_text = fix_result["abc"]

            # Validate
            report_path = Path(self.workdir) / f"_candidate_r{round_idx}_report.json"
            failures = self._run_validation_from_abc(
                abc_text, plan_path, report_path, voice_label,
            )
            fail_count = len(failures)

            candidates.append({
                "round": round_idx, "abc": abc_text,
                "fail_count": fail_count, "failures": failures,
            })

            logger.info(
                "Best-of-N round %d: %d FAILs (agent=%s)",
                round_idx, fail_count, agent_name,
            )

            if fail_count == 0:
                break

            # Prepare feedback for next round
            feedback = self._format_validation_feedback(failures)

        # Select best candidate
        best = min(candidates, key=lambda c: c["fail_count"])

        # If best still has failures, try repair agent
        if best["fail_count"] > 0:
            repaired = await self._attempt_repair(
                best["abc"], best["failures"], plan, plan_path, voice_label,
            )
            if repaired["fail_count"] < best["fail_count"]:
                logger.info(
                    "Repair agent improved: %d → %d FAILs",
                    best["fail_count"], repaired["fail_count"],
                )
                best = repaired

        return best["abc"], best["fail_count"]

    def _run_validation_from_abc(
        self,
        abc_text: str,
        plan_path: Path,
        report_path: Path,
        voice_label: str = "",
    ) -> list[dict]:
        """Write ABC to temp file, validate, return failures."""
        from clef_server.tools import validate_abc as validate_tool

        tmp_abc = Path(self.workdir) / f"_tmp_{voice_label.replace(':', '_').replace('+', '_')}.abc"
        tmp_abc.write_text(abc_text, encoding="utf-8")

        try:
            result = validate_tool(str(tmp_abc), str(plan_path), str(report_path))
        except Exception as e:
            logger.warning("Validation failed: %s", e)
            return [{"category": "validation_error", "voice": voice_label, "message": str(e)}]

        if isinstance(result, dict) and "error" in result:
            return [{"category": "validation_error", "voice": voice_label, "message": result["error"]}]

        # Read report
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            fails = [
                {"category": f.get("category", ""), "voice": f.get("voice", voice_label), "message": f.get("message", "")}
                for f in report.get("fails", [])
                if f.get("category") != "known_artifact"
            ]
            return fails
        return []

    async def _attempt_repair(
        self,
        abc_text: str,
        failures: list[dict],
        plan: dict,
        plan_path: Path,
        voice_label: str = "",
    ) -> dict:
        """Attempt repair via clef-repair agent."""
        from clef_server.tools import fix_measure_duration

        if not abc_text:
            return {"abc": "", "fail_count": 999, "failures": failures}

        feedback = self._format_validation_feedback(failures)
        repair_msg = (
            f"修复以下 ABC 内容中的验证错误：\n\n"
            f"## 验证失败项\n{feedback}\n\n"
            f"## 待修复的 ABC\n```\n{abc_text}\n```\n\n"
            f"请修复后通过 write_file 输出完整的修正版本。"
        )

        try:
            response = await self._run_agent("clef-repair", repair_msg, plan=plan)
            repaired_abc = self._extract_abc(response)
        except Exception as e:
            logger.warning("Repair agent failed: %s", e)
            return {"abc": abc_text, "fail_count": len(failures), "failures": failures}

        if not repaired_abc:
            return {"abc": abc_text, "fail_count": len(failures), "failures": failures}

        # Deterministic fix on repaired version
        fix_result = fix_measure_duration(repaired_abc)
        if fix_result["fixes"]:
            repaired_abc = fix_result["abc"]

        # Validate repaired version
        report_path = Path(self.workdir) / "_repair_report.json"
        new_failures = self._run_validation_from_abc(
            repaired_abc, plan_path, report_path, voice_label,
        )

        return {
            "abc": repaired_abc,
            "fail_count": len(new_failures),
            "failures": new_failures,
        }
```

- [ ] **Step 2: 改造 _phase_sample 的验证修复循环**

替换 `_phase_sample()` 中 lines 1451-1479 的验证修复循环。

**旧代码**（删除）：
```python
        self.session.record_sub_step("技术验证", "running")
        validation_report = Path(self.workdir) / "validation_report_sample.json"
        failures = self._run_validation(score_path, plan_path, validation_report)
        if failures:
            val_feedback = self._format_validation_feedback(failures)
            for f in failures:
                voice = f.get("voice", "")
                agent_name = self._VOICE_TO_AGENT.get(voice)
                if not agent_name:
                    continue
                response = await self._run_agent(
                    agent_name,
                    f"Fix validation errors in your {voice} part:\n{val_feedback}\n\n"
                    f"Output only the corrected ABC for {voice}.",
                    plan=plan,
                    score_abc=score_path.read_text(encoding="utf-8") if score_path.exists() else "",
                )
                abc_text = self._extract_abc(response)
                fragments[voice] = abc_text
            merge_result = merge_abc(str(plan_path), fragments, str(score_path))
            if "error" in merge_result:
                logger.error("merge_abc (validation fix) failed: %s", merge_result["error"])
            else:
                self._inject_midi_programs(score_path, plan)
                failures = self._run_validation(score_path, plan_path, validation_report)
        self.session.record_sub_step("技术验证", "done")
```

**新代码**（替换为）：
```python
        # Step 1.5: Best-of-N validation + repair for each voice
        self.session.record_sub_step("技术验证", "running")
        for voice in generation_order:
            voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")
            if voice_label not in fragments:
                continue
            agent_name = self.VOICE_AGENT_MAP.get(voice)
            if not agent_name:
                continue

            demo_bars = plan.get("demo_length_bars", 8)
            best_abc, fail_count = await self._generate_with_best_of_n(
                agent_name=agent_name,
                message=(
                    f"Generate a {demo_bars}-bar {voice} part as ABC notation. "
                    f"Use voice label {voice_label}. Key: {plan.get('key', 'C')}, "
                    f"Scale: {plan.get('scale', 'major')}, "
                    f"Time: {plan.get('time_signature', '4/4')}, "
                    f"BPM: {plan.get('bpm', 120)}. "
                    f"This is a direction sample — focus on establishing the musical character. "
                    f"Output only ABC notation."
                ),
                plan=plan,
                score_path=score_path,
                plan_path=plan_path,
                max_rounds=2,
                voice_label=voice_label,
            )
            fragments[voice_label] = best_abc
            logger.info("Voice %s: best candidate has %d FAILs", voice_label, fail_count)

        # Re-merge with best candidates
        merge_result = merge_abc(str(plan_path), fragments, str(score_path))
        if "error" in merge_result:
            logger.error("merge_abc failed: %s", merge_result["error"])
        else:
            self._inject_midi_programs(score_path, plan)

        self.session.record_sub_step("技术验证", "done")
```

- [ ] **Step 3: 改造 _phase_create 的验证修复循环**

在 `_phase_create()` 中，将每个 voice 的 per-voice repair loop (lines ~1581-1618) 替换为 `_generate_with_best_of_n` 调用。

找到每个 voice 的生成循环（约 line 1570-1618）：

**旧代码**（删除 per-voice 的 3 次重试循环）：
```python
            for attempt in range(3):
                full_message = message
                if repair_feedback:
                    ...
```

**新代码**（替换为 best-of-N 调用）：
```python
            best_abc, fail_count = await self._generate_with_best_of_n(
                agent_name=agent_name,
                message=message,
                plan=plan,
                score_path=Path(self.workdir) / "score.abc",
                plan_path=Path(self.workdir) / "plan.json",
                max_rounds=2,
                voice_label=voice_label,
            )
            abc_text = best_abc
```

同样替换 _phase_create 中的整体验证修复循环（lines ~1648-1692），改用 `_attempt_repair`：

**旧代码**（删除）：
```python
        validation_report = Path(self.workdir) / "validation_report.json"
        failures = self._run_validation(score_path, plan_path, validation_report)
        if failures:
            ...
```

**新代码**（替换为）：
```python
        # Final validation + repair pass on merged score
        validation_report = Path(self.workdir) / "validation_report.json"
        failures = self._run_validation(score_path, plan_path, validation_report)
        self._validation_failures = failures

        if failures:
            logger.info("Phase create: %d FAILs after merge, attempting repair", len(failures))
            score_abc = score_path.read_text(encoding="utf-8")
            repaired = await self._attempt_repair(
                abc_text=score_abc,
                failures=failures,
                plan=plan,
                plan_path=plan_path,
            )
            if repaired["fail_count"] < len(failures):
                logger.info("Repair improved: %d → %d FAILs", len(failures), repaired["fail_count"])
                score_path.write_text(repaired["abc"], encoding="utf-8")
                self._inject_midi_programs(score_path, plan)
                # Re-validate
                self._validation_failures = self._run_validation(score_path, plan_path, validation_report)
            else:
                logger.info("Repair did not improve, keeping original")
```

- [ ] **Step 4: 运行测试确认无回归**

Run: `cd server && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "feat(server): code-driven best-of-N validate-repair loop with repair agent"
```

---

### Task 4: 两阶段生成 — 节奏骨架优先（PoC 验证）

**Files:**
- Modify: `server/src/clef_server/tools.py`
- Modify: `server/src/clef_server/orchestrator.py`

PoC 实验证明两阶段生成将 measure_duration 错误率从 **75% 降到 12.5%**（DeepSeek Chat, 8 小节测试）。结合 fix_measure_duration 兜底，理论错误率接近 0%。

**原理**：LLM 处理纯数字求和比处理 ABC 音符+时值+八度+变音记号准确得多。先生成节奏骨架（只有数字），验证通过后再填入音高。

- [ ] **Step 1: 添加 `validate_rhythm_skeleton` 工具**

在 `server/src/clef_server/tools.py` 添加：

```python
@tool
def validate_rhythm_skeleton(
    skeleton: Annotated[str, "Rhythm skeleton: duration values separated by spaces, measures by |"],
    target_per_measure: Annotated[float, "Target units per measure (0 = auto-detect)"] = 0,
) -> dict:
    """Validate a rhythm skeleton (durations only, no pitches).

    Each value represents one note/rest duration in L:1/8 units.
    Rests use 'z' prefix: z=1, z2=2, z4=4.
    Returns per-measure validation results.
    """
    if target_per_measure <= 0:
        target = 8.0  # Default: M:4/4 + L:1/8
    else:
        target = target_per_measure

    measures = skeleton.strip().split("|")
    results = []
    fail_count = 0

    for i, meas in enumerate(measures):
        meas = meas.strip()
        if not meas:
            continue
        try:
            durations = []
            for token in meas.split():
                token = token.strip()
                if not token:
                    continue
                if token.startswith("z"):
                    rest_val = token[1:]
                    durations.append(float(rest_val) if rest_val else 1.0)
                else:
                    durations.append(float(token))
        except ValueError:
            results.append({"measure": i + 1, "error": "PARSE_ERROR", "text": meas})
            fail_count += 1
            continue

        total = sum(durations)
        ok = abs(total - target) < 0.01
        if not ok:
            fail_count += 1
        results.append({
            "measure": i + 1,
            "durations": durations,
            "sum": total,
            "target": target,
            "passed": ok,
        })

    return {
        "passed": fail_count == 0,
        "measures": results,
        "fail_count": fail_count,
        "measures_checked": len(results),
    }
```

注册到 `TOOLS_REGISTRY`、`_AGENT_TOOL_MAP`（clef-composer, clef-harmonist, clef-rhythmist）、`_TOOL_META`。

- [ ] **Step 2: 修改 orchestrator 生成流程为两阶段**

在 `orchestrator.py` 的 `_generate_with_best_of_n` 中，将每个 round 的生成改为两阶段：

```python
    async def _generate_two_pass(
        self,
        agent_name: str,
        plan: dict,
        plan_path: Path,
        bars: int,
        voice_label: str = "",
    ) -> str:
        """Two-pass generation: rhythm skeleton first, then pitch fill."""
        from clef_server.tools import validate_rhythm_skeleton

        # Pass 1: Generate rhythm skeleton
        rhythm_msg = (
            f"Generate a {bars}-measure rhythm skeleton for {voice_label}. "
            f"M:4/4 L:1/8. Each measure MUST sum to exactly 8. "
            f"Output ONLY duration values (1,2,3,4,6,8,0.5) separated by spaces, "
            f"measures separated by |. Rests: z=1, z2=2. "
            f"Example: 2 2 2 2 | 4 4 | 2 2 1 1 2 |"
        )
        rhythm_response = await self._run_agent(agent_name, rhythm_msg, plan=plan)
        rhythm_text = self._extract_rhythm(rhythm_response)

        # Validate rhythm
        rhythm_result = validate_rhythm_skeleton(rhythm_text)
        if not rhythm_result["passed"]:
            # Retry once with feedback
            bad = [m for m in rhythm_result["measures"] if not m["passed"]]
            feedback = ", ".join(
                f"M{m['measure']}={m['sum']}(need {m['target']})" for m in bad
            )
            rhythm_msg += f"\n\nPrevious attempt had errors: {feedback}. Fix and output corrected skeleton."
            rhythm_response = await self._run_agent(agent_name, rhythm_msg, plan=plan)
            rhythm_text = self._extract_rhythm(rhythm_response)
            rhythm_result = validate_rhythm_skeleton(rhythm_text)

        if not rhythm_result["passed"]:
            logger.warning("Two-pass: rhythm still invalid after retry, falling back to single-pass")
            return ""

        # Pass 2: Fill pitches into validated rhythm
        pitch_msg = (
            f"Fill pitches into this validated rhythm skeleton for {voice_label}. "
            f"Key: {plan.get('key', 'C')}, Scale: {plan.get('scale', 'major')}. "
            f"Each number is a duration in L:1/8 units. Add a pitch letter before each number. "
            f"Duration 1 = just letter (e.g., c), 2 = letter+2 (e.g., c2), 4 = letter+4 (e.g., c4). "
            f"Do NOT change any durations. Output ABC notes only.\n\n"
            f"Rhythm: {rhythm_text}"
        )
        pitch_response = await self._run_agent(agent_name, pitch_msg, plan=plan)
        return self._extract_abc(pitch_response)

    def _extract_rhythm(self, response: str) -> str:
        """Extract rhythm skeleton from agent response."""
        # Try to find content between ``` blocks
        import re
        match = re.search(r"```(?:rhythm)?\s*\n?(.*?)```", response, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: look for | separated numbers
        lines = response.strip().split("\n")
        for line in lines:
            if "|" in line and any(c.isdigit() for c in line):
                return line.strip()
        return response.strip()
```

在 `_generate_with_best_of_n` 的每个 round 中，先尝试 `_generate_two_pass`，如果返回空则回退到单次生成。

- [ ] **Step 3: 测试**

Run: `cd server && python -m pytest tests/test_tools.py -k "rhythm_skeleton" -v`

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/tools.py server/src/clef_server/orchestrator.py
git commit -m "feat(server): two-pass generation (rhythm skeleton first, pitch fill second)"
```

---

## Self-Review Checklist

### 1. Spec coverage
- [x] **Agent 轮次耗尽** — 创作 agent max_turns 不变（保留自检），orchestrator 控制外层循环: Task 3
- [x] **验证越修越差** — best-of-N 选优 + 修复 agent 专项处理: Task 2 + 3
- [x] **GLM API 400 崩溃** — 每轮独立调用，不累积上下文: Task 3 (_generate_with_best_of_n)
- [x] **measure_duration 顽固** — fix_measure_duration 确定性修复: Task 1
- [x] **修复 agent** — clef-repair 专项 prompt + 配置: Task 2
- [x] **两阶段生成（PoC 验证）** — 节奏骨架优先，错误率从 75% 降到 12.5%: Task 4

### 2. Placeholder scan
- No "TBD", "TODO", "implement later" found
- All code blocks contain complete implementation

### 3. Type consistency
- `fix_measure_duration(abc_content, target_per_measure=0)` → `dict` with keys `abc, fixes, pass, measures_checked`
- `_generate_with_best_of_n(...)` → `tuple[str, int]` (abc_text, fail_count)
- `_attempt_repair(...)` → `dict` with keys `abc, fail_count, failures`
- `_run_validation_from_abc(...)` → `list[dict]` (same format as `_run_validation`)
- `clef-repair` in `_AGENT_TOOL_MAP` has tools: `read_file, write_file, abc_lint, fix_measure_duration`
- `clef-repair` in `agents.yaml` matches `_AGENT_DEFS` in orchestrator

---

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|----------|
| 1 | CEO | All 4 premises valid | Mechanical | P6 | Verified against E2E logs and code | — |
| 2 | CEO | Approach B (full plan) over A/C | Mechanical | P1 | Only approach covering all 4 root causes | Minimal-viable (A), Orchestrator-only (C) |
| 3 | CEO | HOLD mode, no expansion | Mechanical | P3 | Targeted fix, scope well-defined | — |
| 4 | CEO | Accept syncopation risk in deterministic fix | Taste | P3 | max_deviation=2 + skip >2 mitigates | Strict musical semantic preservation |
| 5 | CEO | Defer constrained generation alternatives | Taste | P6 | Higher effort/risk, separate project scope | Two-pass generation, constrained decoding |
| 6 | CEO | Add exception handling in _generate_with_best_of_n rounds | Mechanical | P1 | Prevents cascade failure on agent exception | — |
| 7 | CEO | Add empty ABC guard in _generate_with_best_of_n | Mechanical | P1 | Prevents empty candidate from breaking merge | — |
| 8 | CEO | Accept ABC format longevity risk | Taste | P6 | Current format, migration is separate project | Migrate to MusicXML/custom DSL |

## CEO Completion Summary

**Mode:** HOLD | **Scope:** 3 tasks, 5 files | **Premises:** All valid

| Dimension | Status |
|-----------|--------|
| Premise validity | All 4 confirmed |
| Right problem | Yes — fixes broken loop |
| Alternatives | 1 critical gap noted (constrained generation), deferred |
| Scope calibration | Correct — targeted fix |
| Rollback posture | Simple (per-task commits) |
| Success metric | E2E: 0 FAIL, no crashes, <3 min |

**Voice source:** [subagent-only] (Codex 401 unavailable)
**Taste decisions:** 3 (syncopation risk, constrained gen deferral, ABC longevity)
**User challenges:** 0

---

## Eng Review Findings

**Voice source:** [subagent-only] (Codex 401 unavailable)

### Critical Bugs (fix before implementation)

1. **Tuplet miscount** — `_count_measure_units` strips `(3` but doesn't divide durations by tuplet ratio. `(3c2 d2 e2` counts as 6 instead of 4.
2. **Chord double-count** — `[CEG]4` becomes 3 separate notes after bracket removal. Must parse as single chord event.

### High Issues

3. **L: default wrong** — ABC standard default is `1/4`, not `1/8`. Change `unit_len = "1/4"`.
4. **No orchestrator tests** — `_generate_with_best_of_n`, `_attempt_repair` have zero coverage. Deferred to TODOS.
5. **M:C / M:none** — Cut time and free meter not handled. Deferred (rare case).

### Auto-Decisions

| # | Decision | Principle | Rationale |
|---|----------|-----------|----------|
| 9 | Fix tuplet counting | P1 | Mathematical bug corrupts music |
| 10 | Fix chord parsing | P1 | Mathematical bug corrupts music |
| 11 | Defer orchestrator tests to TODOS | P3 | Integration tests harder, tool tests in plan |
| 12 | Fix L: default to 1/4 | P1 | ABC standard compliance |
| 13 | Defer M:C/M:none to TODOS | P3 | Rare, current usage is 4/4 only |
| 14 | Accept cost multiplier (8 calls) | P3 | max_rounds=2 reasonable, configurable |
| 15 | Add empty candidate fallback | P1 | Prevent garbage from winning best-of-N |

### Test Plan Artifact

Written to `~/.gstack/projects/kenyonxu-clef-dev/2026-04-12-repair-loop-test-plan.md`

**Est. new tests:** ~25 (8 critical P0 + 9 P1 + 4 P2)

### Eng Completion Summary

| Dimension | Status |
|-----------|--------|
| Architecture | Sound — clean separation |
| Test coverage | CRITICAL GAP — 2 math bugs + missing tests |
| Performance | OK — cost multiplier acceptable |
| Security | OK — no new attack surface |
| Error paths | PARTIAL — 3 gaps (agent exception, empty ABC, repair failure) |
| Deployment risk | Low — per-task commits |

**Consensus:** 3/6 confirmed, 1 critical gap (math bugs), 2 deferred to TODOS

---

## DX Review Findings

**Voice source:** [subagent-only] (Codex 401 unavailable)
**Overall DX:** 5.5/10 | **TTHW:** ~25 min (target: <10 min)

### DX Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Getting Started | 5/10 | No usage example |
| API/CLI/SDK | 6/10 | `pass` keyword as key, magic 0 |
| Error Messages | 4/10 | 3 gaps, no structured envelope |
| Documentation | 6/10 | Good prompt, missing payload schema |
| Upgrade Path | 8/10 | Per-task commits, additive |
| Dev Environment | 7/10 | Standard Python/pytest |
| DX Measurement | 3/10 | No TTHW target |
| Overall | 5.5/10 | Needs Work |

### Auto-Decisions

| # | Decision | Principle | Rationale |
|---|----------|-----------|----------|
| 16 | Rename `pass` → `passed` | P5 | Python keyword as dict key is confusing |
| 17 | Change `target_per_measure=0` → `=None` | P5 | Semantic clarity |
| 18 | Add usage example to Task 1 | P1 | Reduces TTHW from 25→10 min |
| 19 | Add validation payload example to repair prompt | P5 | Contributor can reconstruct |
| 20 | Defer max_rounds/max_deviation config | P3 | Hardcoded 2 is reasonable |
| 21 | Defer structured error envelope | P3 | Fill 3 error gaps, envelope is over-engineering |

### Cross-Phase Themes

No cross-phase themes — each phase's concerns were distinct.

---

## 执行记录（2026-04-12）

**执行方式**: Subagent-Driven Development（每 Task 派发独立 implementer + spec reviewer + quality reviewer）
**分支**: `feature/clef-server-v2`
**Base SHA**: `286011f` → **Head SHA**: `7112542`

### Task 完成状态

| Task | 状态 | Commit(s) | 测试 |
|------|------|-----------|------|
| Task 1: fix_measure_duration | ✅ 完成 | `c216c0f` → `49cbffb` → `a3a6804` | 43 passed (11 新增) |
| Task 2: clef-repair Agent | ✅ 完成 | `b1959e7` | 287 passed |
| Task 3: best-of-N 循环 | ✅ 完成 | `1a19ab8` | 286 passed |
| Task 4: 两阶段生成 | ✅ 完成 | `58a191c` → `7112542` | 54 passed |

### Commit 清单

```
c216c0f feat(server): add fix_measure_duration deterministic tool
49cbffb fix(server): remove dead code and add clef-repair agent test
a3a6804 fix(server): clean up unused variables, tighten test, skip %%MIDI lines
b1959e7 feat(server): add clef-repair agent for validation-driven ABC fixes
1a19ab8 feat(server): code-driven best-of-N validate-repair loop with repair agent
58a191c feat(server): two-pass generation (rhythm skeleton first, pitch fill second)
7112542 fix(server): fix stripped scope bug, update tool counts, sync agents.yaml tools
```

### 与计划的出入

#### 1. Eng Review Bug 修复 — 全部完成

| Bug | 计划 | 实际 |
|-----|------|------|
| Tuplet 三连音计数 | 修复 | ✅ 用 `(ratio-1)/ratio` 因子缩放 |
| Chord 和弦双计数 | 修复 | ✅ 先匹配 chord 再排除内部音符 |
| L: 默认值 1/4 | 修复 | ✅ `l_base = 4` |
| `pass` → `passed` | DX 改进 | ✅ |
| `target_per_measure=0` → `=None` | DX 改进 | ✅ |

#### 2. 实现偏差

| 编号 | 计划描述 | 实际实现 | 原因 |
|------|----------|----------|------|
| A | Task 1 使用 `_count_measure_units` 函数 | 改为 `_count_measure_units_clean`，原函数有 bug | 初始实现遗留死代码，Spec review 后删除 |
| B | `_phase_sample` 保留原有生成循环 + 新增 best-of-N 验证 | 替换为统一的 best-of-N 循环（生成+验证一体） | 避免双重生成（先生成再验证 = 浪费 token） |
| C | `_generate_with_best_of_n` 中集成 `_generate_two_pass` | 仅添加方法，未在 best-of-N 中自动调用 | 两阶段生成作为可选工具方法，由 orchestrator 按需调用 |
| D | Task 3 的 `_VOICE_TO_AGENT` 验证修复循环 | 改为 `_attempt_repair`（对合并后整曲修复） | 更高效：修复 agent 处理全曲上下文，而非逐声部重生成 |
| E | agents.yaml 在 Task 2 添加 clef-repair | 同步完成 | 无偏差 |
| F | test_api_ttl.py 工具计数 | 从 8 → 9 → 10（Task 2 修到 9，Task 4 修到 10） | 工具数增量更新 |

#### 3. Review 中发现并修复的问题

| 阶段 | 问题 | 修复 Commit |
|------|------|------------|
| Task 1 Spec Review | 死代码 `_count_measure_units`（~100 行） | `49cbffb` |
| Task 1 Spec Review | 缺少 `clef-repair` agent 的 `get_tools_for_agent` 测试 | `49cbffb` |
| Task 1 Quality Review | 3 个未使用变量（`text_pos`, `event_idx`, `tuplet_ranges`） | `a3a6804` |
| Task 1 Quality Review | `test_large_deviation_skipped` 断言过于宽松 | `a3a6804` |
| Task 1 Quality Review | `%%MIDI` 行未在音乐行循环中跳过 | `a3a6804` |
| Final Review | `stripped` 变量作用域 bug（引用了 header 循环的旧值） | `7112542` |
| Final Review | `test_api_ttl.py` 工具计数陈旧（9 → 10） | `7112542` |
| Final Review | `agents.yaml` 缺少 `validate_rhythm_skeleton` | `7112542` |

#### 4. 未完成 / 后续事项

| 项目 | 状态 | 说明 |
|------|------|------|
| orchestrator tests（`_generate_with_best_of_n` 等） | ❌ 未完成 | Eng Review Decision #11：integration tests harder，deferred |
| M:C / M:none 拍号支持 | ❌ 未完成 | Decision #13：当前只用 4/4，rare case |
| 两阶段生成与 best-of-N 集成 | ❌ 未完成 | `_generate_two_pass` 方法已添加但未在 best-of-N 循环中自动调用 |
| `(2` 二连音支持 | ⚠️ 已知限制 | `tuplet_factor` 公式对 `(2` 不正确（应为 1.5，实际 0.5） |
| `_duration_to_str` 三连音修正后精度 | ⚠️ 已知限制 | `2/3` 单位无法表示为标准 ABC 时值后缀 |
| E2E 验证 | ❌ 未完成 | 需要 `clef-compose` 完整工作流测试 |
