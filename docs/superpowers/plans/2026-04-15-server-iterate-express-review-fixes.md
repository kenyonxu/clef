# Server Iterate/Express/Review 系统性修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 clef-server E2E 流程中三个关键 Bug：iterate 阶段多声部截断毁谱、express 阶段无效 JSON 被保存、review 阶段过于宽松导致质量问题不暴露。

**Architecture:** 在 `orchestrator.py` 中修复 5 个问题点。核心思路：per-voice 截断替代全局截断、express 输出格式校验、reviewer 注入 validation 上下文 + FAIL 惩罚、迭代轮次早停。

**Tech Stack:** Python 3.11+, pytest, asyncio, FastAPI

---

## File Structure

| File | Responsibility |
|------|---------------|
| `server/src/clef_server/orchestrator.py` | 主要修改文件，所有 5 个 Task 均涉及 |
| `server/tests/test_orchestrator.py` | 新增测试用例 |

---

### Task 1: 修复 iterate 阶段多声部截断 Bug（CRITICAL）

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:2413-2424`
- Test: `server/tests/test_orchestrator.py`

**根因分析：** `_count_bars` 统计合并后 ABC 中所有声部的小节线总和（4 声部 × 10 小节 = 40 条），然后与 `target_bars`（10）比较。40 > 11 恒为真，导致每次迭代都触发 `_truncate_to_bars`，线性截断会切掉后面的声部（V:3/V:4 完全丢失，V:2 被截短）。

**修复方案：** 将截断逻辑改为 per-voice：解析各声部 → 逐声部截断到 target_bars → 重新合并。

- [ ] **Step 1: 在 `_count_bars` 下方新增 `_truncate_score_per_voice` 方法**

在 `orchestrator.py` 的 `_truncate_to_bars` 方法后面（约 line 1207 后）添加：

```python
@staticmethod
def _truncate_score_per_voice(abc_text: str, target_bars: int) -> str:
    """Truncate each voice independently to target_bars measures.

    Unlike _truncate_to_bars which linearly cuts across all lines,
    this method parses voice blocks (V:1, V:2, ...) and truncates
    each one independently, preserving the multi-voice structure.
    """
    lines = abc_text.strip().split("\n")
    header_lines: list[str] = []
    voice_blocks: dict[str, list[str]] = {}
    current_voice: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            if current_voice is not None:
                voice_blocks.setdefault(current_voice, []).append(line)
            else:
                header_lines.append(line)
            continue

        # Detect voice directive
        voice_match = re.match(r"^V:\s*(\d+)", stripped)
        if voice_match:
            current_voice = f"V:{voice_match.group(1)}"
            voice_blocks.setdefault(current_voice, []).append(line)
            continue

        # Header lines (before any V: directive)
        if current_voice is None:
            header_lines.append(line)
        else:
            voice_blocks.setdefault(current_voice, []).append(line)

    # Truncate each voice block independently
    truncated_blocks: dict[str, list[str]] = {}
    for voice_label, voice_lines in voice_blocks.items():
        truncated_blocks[voice_label] = ComposeOrchestrator._truncate_voice_lines(
            voice_lines, target_bars
        )

    # Reassemble: header + each voice block
    result_parts = list(header_lines)
    for voice_label, voice_lines in truncated_blocks.items():
        result_parts.extend(voice_lines)

    return "\n".join(result_parts)

@staticmethod
def _truncate_voice_lines(lines: list[str], target_bars: int) -> list[str]:
    """Truncate a single voice's lines to target_bars measures."""
    bars_found = 0
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%") or stripped.startswith("V:"):
            result.append(line)
            continue
        bar_positions = [m.start() for m in ComposeOrchestrator._BAR_RE.finditer(line)]
        if not bar_positions:
            result.append(line)
            continue
        new_bars = bars_found + len(bar_positions)
        if new_bars <= target_bars:
            result.append(line)
            bars_found = new_bars
        else:
            remaining = target_bars - bars_found
            if remaining > 0 and bar_positions:
                end_pos = bar_positions[remaining - 1] + 1
                result.append(line[:end_pos])
            break
    return result
```

- [ ] **Step 2: 替换 `_phase_iterate` 中的截断逻辑**

将 `orchestrator.py` lines 2413-2424 从：

```python
                # Enforce bar count — truncate if agent added extra bars
                target_bars = plan.get("total_bars", 0)
                if target_bars > 0:
                    current_score = score_path.read_text(encoding="utf-8")
                    actual = self._count_bars(current_score)
                    if actual > target_bars + 1:
                        logger.warning(
                            "Session %s: After %s revision, score has %d bars (target %d), truncating",
                            self.session_id, agent_name, actual, target_bars,
                        )
                        truncated = self._truncate_to_bars(current_score, target_bars)
                        score_path.write_text(truncated, encoding="utf-8")
```

替换为：

```python
                # Enforce bar count — truncate per-voice if agent added extra bars
                target_bars = plan.get("total_bars", 0)
                if target_bars > 0:
                    current_score = score_path.read_text(encoding="utf-8")
                    voice_blocks = self._parse_voice_blocks(current_score)
                    needs_truncate = False
                    for vl in voice_blocks:
                        voice_bars = self._count_bars(voice_blocks[vl])
                        if voice_bars > target_bars + 1:
                            needs_truncate = True
                            logger.warning(
                                "Session %s: After %s revision, %s has %d bars (target %d)",
                                self.session_id, agent_name, vl, voice_bars, target_bars,
                            )
                    if needs_truncate:
                        truncated = self._truncate_score_per_voice(current_score, target_bars)
                        score_path.write_text(truncated, encoding="utf-8")
```

- [ ] **Step 3: 写测试**

在 `test_orchestrator.py` 中添加：

```python
class TestPerVoiceTruncation:
    """Tests for per-voice truncation in iterate phase."""

    def test_truncate_score_per_voice_4_voices(self):
        """Per-voice truncation preserves all 4 voices, truncating each independently."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|F E D C|C D E F|G A B c|\n"
            "V:2\n[C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]|\n"
            "V:3\nC,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|\n"
            "V:4\n^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|\n"
        )
        result = ComposeOrchestrator._truncate_score_per_voice(abc, 3)
        # All 4 voices should still be present
        assert "V:1" in result
        assert "V:2" in result
        assert "V:3" in result
        assert "V:4" in result
        # Each voice should have at most 3 bar lines
        for vl in ["V:1", "V:2", "V:3", "V:4"]:
            blocks = ComposeOrchestrator._parse_voice_blocks(result)
            if vl in blocks:
                bars = ComposeOrchestrator._count_bars(blocks[vl])
                assert bars <= 3, f"{vl} has {bars} bars, expected <= 3"

    def test_truncate_score_per_voice_no_over_truncate(self):
        """Score with correct bar count per voice is not modified."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|\n"
            "V:2\n[C E G]| [D F A]| [E G B]|\n"
        )
        result = ComposeOrchestrator._truncate_score_per_voice(abc, 3)
        assert "V:1" in result
        assert "V:2" in result
        assert ComposeOrchestrator._count_bars(
            ComposeOrchestrator._parse_voice_blocks(result).get("V:1", "")
        ) == 3

    def test_old_global_truncate_destroys_voices(self):
        """Document the OLD bug: _truncate_to_bars on merged 4-voice score destroys later voices."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|F E D C|C D E F|G A B c|c B A G|F E D C|C D E F|G A B c|\n"
            "V:2\n[C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]| [C E G]|\n"
            "V:3\nC,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|\n"
            "V:4\n^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|\n"
        )
        # OLD behavior: global truncation with target=10 cuts across all 40 bars, destroying V:3/V:4
        result_old = ComposeOrchestrator._truncate_to_bars(abc, 10)
        # V:3 and V:4 are gone because old method counts 40 bars total and cuts after 10
        assert "V:3" not in result_old or "V:4" not in result_old
        # NEW behavior: per-voice truncation preserves all voices
        result_new = ComposeOrchestrator._truncate_score_per_voice(abc, 10)
        assert "V:1" in result_new
        assert "V:2" in result_new
        assert "V:3" in result_new
        assert "V:4" in result_new
```

- [ ] **Step 4: 运行测试**

```bash
cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py::TestPerVoiceTruncation -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "fix(server): per-voice truncation in iterate phase preserves all voices"
```

---

### Task 2: 验证 expression_plan 格式后再保存（CRITICAL）

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:2513-2522`
- Test: `server/tests/test_orchestrator.py`

**根因分析：** `_extract_json` 在 JSON 解析失败时返回 `{"verdict": "revise"}`，这个 dict 被 `_phase_express` 直接保存为 `expression_plan.json`。后续 `inject_expression` 期望 `tracks`/`channels`/`sections` 等顶级 key，发现 `verdict` 就报错："Expected top-level key 'tracks'/'channels'/'sections', found: ['verdict']"。

- [ ] **Step 1: 在 `_phase_express` 中添加格式校验**

将 `orchestrator.py` lines 2513-2522 从：

```python
        response = await self._run_agent("clef-orchestrator", message, plan=plan)
        expression_plan = self._extract_json(response)

        self.session.record_sub_step("生成表现力方案", "done", agent="clef-orchestrator")

        # Save expression plan
        expr_plan_path = Path(self.workdir) / "expression_plan.json"
        expr_plan_path.write_text(
            json.dumps(expression_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
```

替换为：

```python
        response = await self._run_agent("clef-orchestrator", message, plan=plan)
        expression_plan = self._extract_json(response)

        self.session.record_sub_step("生成表现力方案", "done", agent="clef-orchestrator")

        # Validate expression plan format before saving
        valid_keys = {"tracks", "channels", "sections", "cc7_volume", "cc10_pan",
                      "cc91_reverb", "pitch_bend", "vibrato"}
        has_valid_key = any(k in expression_plan for k in valid_keys)

        if not has_valid_key:
            logger.warning(
                "Session %s: expression_plan has no valid top-level keys (%s), skipping injection",
                self.session_id,
                list(expression_plan.keys()),
            )
            self.session.record_phase("express", "done", error="invalid expression plan format")
            self.session.set_done()
            return

        # Save expression plan
        expr_plan_path = Path(self.workdir) / "expression_plan.json"
        expr_plan_path.write_text(
            json.dumps(expression_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
```

- [ ] **Step 2: 写测试**

```python
class TestExpressPlanValidation:
    """Tests for expression plan format validation."""

    @pytest.mark.asyncio
    async def test_express_skips_invalid_plan(self, orchestrator, tmp_path):
        """_phase_express should skip when expression_plan has no valid keys."""
        # Setup: plan.json + a base MIDI
        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x60")

        orch = orchestrator
        orch.workdir = str(tmp_path)
        orch.session.iteration_count = 1

        # Mock _run_agent to return invalid JSON (like _extract_json fallback)
        invalid_plan = {"verdict": "revise"}
        orch._run_agent = AsyncMock(return_value=json.dumps(invalid_plan))

        await orch._phase_express()

        # Should NOT have created expression_plan.json
        assert not (tmp_path / "expression_plan.json").exists()
        # Session should be done (early exit)
        assert orch.session.is_done

    @pytest.mark.asyncio
    async def test_express_saves_valid_plan(self, orchestrator, tmp_path):
        """_phase_express should save and inject when plan has valid keys."""
        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x60")

        orch = orchestrator
        orch.workdir = str(tmp_path)
        orch.session.iteration_count = 1

        valid_plan = {"cc7_volume": [{"beat": 0, "value": 80}]}
        orch._run_agent = AsyncMock(return_value=json.dumps(valid_plan))
        # Mock inject_expression to avoid real MIDI processing
        with patch("clef_server.orchestrator.inject_expression", return_value={"ok": True}):
            await orch._phase_express()

        assert (tmp_path / "expression_plan.json").exists()
        saved = json.loads((tmp_path / "expression_plan.json").read_text())
        assert "cc7_volume" in saved
```

- [ ] **Step 3: 运行测试**

```bash
cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py::TestExpressPlanValidation -v
```

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "fix(server): validate expression_plan format before saving, skip if invalid"
```

---

### Task 3: 传递 validation_failures 给 Reviewer（HIGH）

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:1398-1457`
- Test: `server/tests/test_orchestrator.py`

**根因分析：** `_call_reviewer` 只传 score.abc + plan.json 给 reviewer agent，不包含 `_validation_failures`。reviewer 不知道有 12 个 FAIL，给了一个过于宽松的评分（如 7.5/10）。

- [ ] **Step 1: 修改 `_call_reviewer` 签名，注入 validation failures**

在 `orchestrator.py` 的 `_call_reviewer` 方法中（约 line 1398），修改签名和消息构建：

从：

```python
    async def _call_reviewer(
        self,
        plan: dict,
        melody_only: bool = False,
        is_sample: bool = False,
        extra_context: str = "",
    ) -> dict:
```

改为：

```python
    async def _call_reviewer(
        self,
        plan: dict,
        melody_only: bool = False,
        is_sample: bool = False,
        extra_context: str = "",
        validation_failures: list | None = None,
    ) -> dict:
```

然后在 `if extra_context:` 块后面（约 line 1457 后）添加：

```python
        if validation_failures:
            fail_summary = self._format_validation_feedback(validation_failures)
            message += f"\n\nVALIDATION REPORT (automated checks):\n{fail_summary}\n"
            message += (
                "The above validation failures indicate TECHNICAL problems in the score. "
                "You MUST factor these into your scoring: each FAIL-level issue should "
                "reduce the relevant dimension score by at least 2 points.\n"
            )
```

- [ ] **Step 2: 更新 `_phase_iterate` 中的 `_call_reviewer` 调用**

在 `orchestrator.py` line 2321，从：

```python
                review = await self._call_reviewer(plan, melody_only=False)
```

改为：

```python
                review = await self._call_reviewer(plan, melody_only=False, validation_failures=self._validation_failures)
```

同样在 line 2464（final review），从：

```python
            final_review = await self._call_reviewer(plan, melody_only=False)
```

改为：

```python
            final_review = await self._call_reviewer(plan, melody_only=False, validation_failures=self._validation_failures)
```

- [ ] **Step 3: 写测试**

```python
class TestReviewerValidationContext:
    """Tests for passing validation failures to reviewer."""

    @pytest.mark.asyncio
    async def test_call_reviewer_includes_validation_failures(self, orchestrator, tmp_path):
        """_call_reviewer message should include validation failure details."""
        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        score_abc = "X:1\nT:Test\nM:4/4\nV:1\nC D E F|G A B c|\n"
        (tmp_path / "score.abc").write_text(score_abc)

        orch = orchestrator
        orch.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":5,"issues":[]}},"overall_score":5,"verdict":"revise","summary":"test"}'

        orch._run_agent = mock_run_agent

        failures = [
            {"check": "V:1:measure_duration", "severity": "FAIL", "detail": "bar 3 has 5 beats"},
            {"check": "global:voice_alignment", "severity": "FAIL", "detail": "voices misaligned"},
        ]

        await orch._call_reviewer(plan, validation_failures=failures)

        assert captured_message is not None
        assert "VALIDATION REPORT" in captured_message
        assert "FAIL-level issue" in captured_message
        assert "measure_duration" in captured_message

    @pytest.mark.asyncio
    async def test_call_reviewer_no_failures_no_extra_text(self, orchestrator, tmp_path):
        """_call_reviewer without failures should not include validation section."""
        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA"}
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nV:1\nC D E F|\n")

        orch = orchestrator
        orch.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":8,"issues":[]}},"overall_score":8,"verdict":"pass","summary":"ok"}'

        orch._run_agent = mock_run_agent

        await orch._call_reviewer(plan, validation_failures=None)

        assert "VALIDATION REPORT" not in captured_message
```

- [ ] **Step 4: 运行测试**

```bash
cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py::TestReviewerValidationContext -v
```

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "fix(server): pass validation failures to reviewer agent for informed scoring"
```

---

### Task 4: 在 reviewer prompt 中添加 FAIL 惩罚指令（HIGH）

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:1436-1455`（`_call_reviewer` 中的 JSON 格式指令部分）

**根因分析：** 即使传了 validation failures，DeepSeek 等低成本模型可能仍然给出高评分。需要在 prompt 中加入更明确的评分约束，确保 FAIL 级别的技术问题被反映到分数中。

- [ ] **Step 1: 在 `_call_reviewer` 的 prompt 中强化评分约束**

在 `orchestrator.py` 中 `_call_reviewer` 的 `"IMPORTANT: Every dimension MUST have a score"` 行之后（约 line 1454 后），添加：

```python
            "SCORING RULES:\n"
            "- If the VALIDATION REPORT section contains FAIL-level issues, the corresponding "
            "dimension score MUST be reduced by at least 2 points per FAIL.\n"
            "- A score above 7 with any FAIL issue is INVALID. Do not give scores above 7 "
            "if there are unresolved FAIL issues.\n"
            "- If overall_score > 7 but there are 3+ FAIL issues, you MUST set verdict to 'revise'.\n"
```

- [ ] **Step 2: 写测试**

```python
class TestReviewerScoringConstraints:
    """Tests for FAIL-penalty scoring instructions in reviewer prompt."""

    @pytest.mark.asyncio
    async def test_reviewer_prompt_contains_scoring_rules(self, orchestrator, tmp_path):
        """Reviewer prompt should include FAIL-penalty scoring rules."""
        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA"}
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nV:1\nC D E F|\n")

        orch = orchestrator
        orch.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":5,"issues":[]}},"overall_score":5,"verdict":"revise","summary":"test"}'

        orch._run_agent = mock_run_agent
        await orch._call_reviewer(plan)

        assert "SCORING RULES" in captured_message
        assert "FAIL-level issues" in captured_message
        assert "verdict" in captured_message
```

- [ ] **Step 3: 运行测试**

```bash
cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py::TestReviewerScoringConstraints -v
```

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "fix(server): add FAIL-penalty scoring rules to reviewer prompt"
```

---

### Task 5: 迭代早停 — validation fail_count 无改善时停止（MEDIUM）

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:2300-2450`（`_phase_iterate` 轮次循环）

**根因分析：** 当前迭代会跑满 `max_iteration_rounds` 轮（默认 3），即使每轮的 validation fail_count 完全相同（如连续 3 轮都是 11-12 个 FAIL）。浪费 token 且不会改善结果。

- [ ] **Step 1: 在 `_phase_iterate` 轮次循环中添加早停逻辑**

在 `orchestrator.py` 的 `_phase_iterate` 方法中，`for round_num in range(1, ...)` 循环内、validation 执行后（约 line 2439 `self._validation_failures = failures` 之后）添加：

```python
                # Early stop: if fail_count hasn't improved for 2 rounds, stop iterating
                current_fail_count = len(failures) if failures else 0
                prev_fails = getattr(self, "_prev_iteration_fail_count", None)
                if prev_fails is not None and current_fail_count >= prev_fails:
                    self._stagnation_count = getattr(self, "_stagnation_count", 0) + 1
                else:
                    self._stagnation_count = 0
                self._prev_iteration_fail_count = current_fail_count

                if self._stagnation_count >= 2:
                    logger.info(
                        "Session %s: fail_count stagnant at %d for 2+ rounds, stopping iteration",
                        self.session_id, current_fail_count,
                    )
                    break
```

- [ ] **Step 2: 在 `_phase_create` 或 session 初始化时重置早停计数器**

在 `orchestrator.py` 中 `__init__` 或 `_phase_create` 开头添加重置：

```python
        self._stagnation_count = 0
        self._prev_iteration_fail_count = None
```

- [ ] **Step 3: 写测试**

```python
class TestIterateEarlyStop:
    """Tests for early-stop when validation fail_count stagnates."""

    @pytest.mark.asyncio
    async def test_iterate_stops_on_stagnation(self, orchestrator, tmp_path):
        """Iteration should stop after 2 rounds with no fail_count improvement."""
        plan = {
            "key": "C", "scale": "major", "bpm": 120, "form": "ABA",
            "total_bars": 8,
            "sections": [
                {"name": "A", "bars": 4, "energy_level": 5},
                {"name": "B", "bars": 4, "energy_level": 7},
            ],
            "orchestration": [
                {"voice": "V:1", "label": "melody", "instrument": "Piano"},
            ],
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nM:4/4\nV:1\nC D E F|G A B c|c B A G|F E D C|\n")

        orch = orchestrator
        orch.workdir = str(tmp_path)
        orch.max_iteration_rounds = 5  # would run 5 rounds without early stop

        call_count = 0

        async def mock_reviewer(plan, **kwargs):
            nonlocal call_count
            return {
                "verdict": "revise",
                "scores": {"melody": 5},
                "issues": ["bad melody"],
            }

        async def mock_leader(plan, review, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "tasks": [{"agent": "clef-composer", "voice": "melody", "instruction": "fix"}],
                "iteration_complete": False,
            }

        orch._call_reviewer = mock_reviewer
        orch._call_leader = mock_leader
        orch._run_agent = AsyncMock(return_value="C D E F|G A B c|c B A G|F E D C|")
        orch._extract_abc = lambda x: x
        orch._inject_midi_programs = MagicMock()
        orch._run_validation = MagicMock(return_value=[
            {"check": "V:1:measure_duration", "severity": "FAIL"}
        ] * 10)  # Always return 10 failures
        orch.session.record_phase = MagicMock()
        orch.session.record_sub_step = MagicMock()
        orch._iteration_history = []

        with patch("clef_server.orchestrator.merge_abc", return_value={"ok": True}):
            with patch("clef_server.orchestrator.abc_to_midi", return_value={"ok": True}):
                await orch._phase_iterate()

        # Should have stopped before reaching 5 rounds due to stagnation
        assert orch.session.iteration_count < 5
```

- [ ] **Step 4: 运行测试**

```bash
cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py::TestIterateEarlyStop -v
```

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): early-stop iterate when validation fail_count stagnates"
```

---

## Self-Review

### 1. Spec coverage

| Issue | Task | Status |
|-------|------|--------|
| 多声部截断毁谱（V:3/V:4 丢失） | Task 1 | ✅ |
| expression_plan 无效 JSON 被保存 | Task 2 | ✅ |
| Reviewer 不知道 validation failures | Task 3 | ✅ |
| Reviewer 评分过于宽松 | Task 4 | ✅ |
| 迭代无改善时浪费 token | Task 5 | ✅ |

### 2. Placeholder scan

无 TBD/TODO/fill-in-later。所有代码块均包含完整实现。

### 3. Type consistency

- `_truncate_score_per_voice(abc_text: str, target_bars: int) -> str` — 与 `_truncate_to_bars` 签名一致
- `_call_reviewer` 新增 `validation_failures: list | None = None` — 向后兼容
- `_phase_express` 中 `valid_keys` 为 set of str — 与 `expression_plan.keys()` 对比正确
- `_stagnation_count` / `_prev_iteration_fail_count` 为实例属性 — 在 Task 5 中初始化
