# Code-Driven Validate-Repair 循环：从计划到端到端验证

> 日期：2026-04-12
> 分支：`feature/clef-server-v2`
> 计划文档：`docs/superpowers/plans/2026-04-11-code-driven-repair-loop.md`

本文档记录 Clef Server 将验证修复循环从 prompt 驱动改为代码驱动的完整过程：4 个根因、4 个实施任务（确定性修复工具 + 专项修复 agent + best-of-N 选优 + 两阶段生成）、review 中发现的 8 个问题、E2E 验证中发现的 1 个运行时 bug，以及最终成果。

---

## 1. 起因：验证修复循环的 4 个根因

上一轮 agentic tool-use loop 升级（`2026-04-11-e2e-fix-report.md`）解决了 agent prompt 遵循度问题，将 validation FAIL 从 17 降到 0。但 E2E 日志暴露了验证修复循环本身的新问题：

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| 1 | Agent 轮次耗尽（4 次 max_turns） | prompt 驱动的 validate→fix 无限循环，agent 在 loop 内反复修同一个错误 | 创作阶段卡死 |
| 2 | 验证越修越差（3 FAIL → 4 FAIL） | 同一个 agent 既创作又修复，上下文累积导致退化 | 质量不升反降 |
| 3 | GLM API 400 崩溃 | 6 轮工具调用后上下文溢出，LLM API 拒绝请求 | 整个 session 失败 |
| 4 | measure_duration 顽固 | LLM 不擅长数数，时值计算是确定性问题却交给概率模型处理 | 最常见的 FAIL 类型 |

### 根因 1：Prompt 驱动的无限循环

原有的修复流程让 agent 自己在 agentic loop 内调用 `validate_abc` → 修复 → 再验证。如果 agent 无法修好某个错误，它会一直重试直到 `max_turns` 耗尽。orchestrator 没有退出机制。

### 根因 4：measure_duration 的本质

ABC 记谱法中 `measure_duration` 错误是纯粹的算术问题。以 `M:4/4` + `L:1/8` 为例，每个小节必须恰好 8 个单位。`c2 d2 e2 f` = 7/8（缺 1），`c2 d2 e2 f2 g` = 9/8（多 1）。这类问题有确定性答案，不需要 LLM 的创造力。

---

## 2. 实施方案：4 个任务

### 整体架构

```
生成阶段（创作 agent）
  ↓
确定性修复（fix_measure_duration）
  ↓
技术验证（validate_abc）
  ↓ 仍有 FAIL?
专项修复（clef-repair agent）
  ↓
选最优（best-of-N）
```

**核心原则**：创作负责生成 + 自检，修复由专项 agent + 确定性工具联合处理，orchestrator 控制迭代节奏并选最优结果。每轮 agent 调用独立（不累积上下文），避免 API 崩溃。

### Task 1：fix_measure_duration — 确定性时值修复工具

**文件**：`server/src/clef_server/tools.py`、`server/tests/test_tools.py`

创建 `fix_measure_duration()` 工具，用正则表达式解析 ABC 小节，计算实际时值，机械修正偏差在 ±2 单位内的小节。

修复规则：

- **L:1/8 + M:4/4** → 每小节 8 个单位
- **偏离 1-2 单位**：延长或缩短最后一个音符/休止符
- **偏离 >2 单位**：跳过（留给修复 agent 处理）
- **自动检测拍号**：从 `M:` 和 `L:` 头部解析

关键实现细节：

1. **和弦计数**：`[CEG]2` 是一个事件（时值 2），不是三个音符。用 `_CHORD_RE` 先匹配和弦，再排除和弦内部的音符匹配。

2. **三连音计数**：`(3e f g` 三个音符在 2 单位时间内。用 `tuplet_factor = (ratio - 1) / ratio` 缩放受影响的音符时值。例如 `(3` 的 factor = 2/3，三个各 1 单位的音符总计 3 × 2/3 = 2 单位。

3. **L: 默认值**：ABC 标准默认 `L:1/4`（不是 `1/8`）。自动检测时 `l_base = 4`。

### Task 2：clef-repair Agent — 专项修复 Agent

**文件**：`server/config/prompts/clef-repair.md`（新建）、`server/config/agents.yaml`

创建专门处理验证失败的 agent。它接收具体的失败项和 ABC 内容，做最小干预的定向修复。

配置：

| 参数 | 值 | 说明 |
|------|-----|------|
| model_alias | anthropic-haiku | 快速、低成本 |
| temperature | 0.2 | 确定性输出 |
| max_turns | 3 | 读 → 修复 → 验证 |
| tools | read_file, write_file, abc_lint, fix_measure_duration | 修复专用工具集 |

修复原则：只修正报告中的具体错误，不重写整段音乐，不改变旋律走向和和声选择。

### Task 3：best-of-N 验证修复循环

**文件**：`server/src/clef_server/orchestrator.py`

这是核心改动。将 `_phase_sample` 和 `_phase_create` 中的验证修复循环从"同一 agent 重试"改为"best-of-N + 修复 agent"模式。

流程：

```
for round in range(max_rounds):   # 默认 2 轮
  ① 创作 agent 生成（独立调用，不累积上下文）
  ② fix_measure_duration 确定性修复
  ③ abc_lint 轻量检查
  ④ validate_abc 技术验证
  ⑤ 记录 candidate: {round, abc_text, fail_count, failures}
  ⑥ 如果 fail_count == 0 → 直接用，跳出
  ⑦ 如果有 FAIL → 将反馈注入下一轮的 agent 消息

如果仍有 FAIL:
  ⑧ 将最优 candidate 交给 clef-repair agent 定向修复
  ⑨ fix_measure_duration + validate_abc
  ⑩ 如果修复后更优 → 使用修复版本

最终: 从所有 candidate 中取 fail_count 最小的
```

关键方法：

- `_generate_with_best_of_n()`：编排多轮生成 + 选优
- `_run_validation_from_abc()`：写入临时文件后验证
- `_attempt_repair()`：调用 clef-repair agent，修复后再验证

### Task 4：两阶段生成 — 节奏骨架优先

**文件**：`server/src/clef_server/tools.py`、`server/src/clef_server/orchestrator.py`

PoC 实验证明两阶段生成将 measure_duration 错误率从 75% 降到 12.5%。原理：LLM 处理纯数字求和比处理 ABC 音符 + 时值 + 八度 + 变音记号准确得多。

Pass 1 — 生成节奏骨架（只有数字）：

```
2 2 2 2 | 4 4 | 2 2 1 1 2 |
```

用 `validate_rhythm_skeleton()` 验证每个小节的数字之和。如果验证失败，带具体错误信息重试一次。

Pass 2 — 填入音高：

```
c2 d2 e2 f2 | g4 a4 | b2 c'2 d e f2 |
```

agent 只需在数字前加音名字母，不改时值。

集成到 best-of-N：首轮自动尝试 two-pass，失败回退到单次生成。

---

## 3. Review 中发现并修复的 8 个问题

采用 Subagent-Driven Development 工作流，每个任务经过独立 implementer → spec reviewer → quality reviewer 三阶段审查。共发现 8 个问题。

### Eng Review 识别的关键 Bug（3 个）

| Bug | 根因 | 修复 |
|-----|------|------|
| **三连音计数错误** | `_count_measure_units` 直接将 tuplet 内音符时值相加，没有除以 tuplet ratio。`(3c2 d2 e2` 计为 6 而非 4 | 用 `(ratio-1)/ratio` 因子缩放，替换为 `_count_measure_units_clean` |
| **和弦双计数** | `[CEG]4` 去掉方括号后变成三个独立音符，各计 4 单位 = 12 | 先匹配 `_CHORD_RE` 提取和弦为单个事件，再排除和弦内部的音符匹配 |
| **L: 默认值错误** | 代码默认 `L:1/8`，但 ABC 标准默认是 `L:1/4` | `l_base = 4`，auto-detect 从 `L:` 头部读取 |

### Code Quality Review 发现的问题（3 个）

| 问题 | 修复 |
|------|------|
| 3 个未使用变量（`text_pos`, `event_idx`, `tuplet_ranges`） | 删除 |
| `test_large_deviation_skipped` 断言用 `or` 允许两种结果 | 收紧为只断言 `skipped=True` |
| `%%MIDI` 指令行含 `|` 字符时被误当作音乐行处理 | 在音乐行循环中跳过 `%%` 开头的行 |

### Final Review 发现的问题（2 个）

| 问题 | 修复 |
|------|------|
| `stripped` 变量作用域 bug — `fix_measure_duration` 中音乐行循环引用了 header 循环的旧 `stripped` 值 | 改为 `line.strip()` |
| `agents.yaml` 与 `_AGENT_TOOL_MAP` 不同步 — 缺少 `validate_rhythm_skeleton` | 同步更新 |

### DX Review 改进（2 项）

| 改进 | 原值 | 新值 |
|------|------|------|
| `pass` 关键字作为 dict key | `result["pass"]` | `result["passed"]` |
| `target_per_measure` 默认值 | `=0`（语义不明） | `=None`（auto-detect） |

---

## 4. E2E 验证中发现的运行时 Bug

E2E 测试暴露了一个计划审查和代码审查都没发现的问题。

### Bug：`KeyError: 'sum'` in `_generate_two_pass`

**现象**

```
Session clef-9ba1c7b0: resume failed
KeyError: 'sum'
  File "orchestrator.py", line 1635, in _generate_two_pass
    f"M{m['measure']}={m['sum']}(need {m['target']})"
```

Sample 阶段崩溃。parse 阶段正常通过。

**根因**

`validate_rhythm_skeleton()` 对不同类型的错误返回不同的数据结构：

```python
# PARSE_ERROR: 无法解析为数字
{"measure": 3, "error": "PARSE_ERROR", "text": "abc xyz"}

# 时值不匹配: 正常解析但总和不等于目标
{"measure": 3, "sum": 7.0, "target": 8.0, "passed": False}
```

`_generate_two_pass()` 的重试反馈构建器假设所有失败小节都有 `sum` 键，但 PARSE_ERROR 小节没有。LLM 返回的节奏骨架包含无法解析的 token 时触发此 bug。

**修复**

用 `.get()` 替代直接索引，为两种数据结构提供合理的 fallback：

```python
# 修复前
f"M{m['measure']}={m['sum']}(need {m['target']})"

# 修复后
f"M{m['measure']}={m.get('sum', 'PARSE_ERROR')}(need {m.get('target', 8)})"
```

---

## 5. 最终 E2E 验证结果

使用 DeepSeek（deepseek-chat）完成全流程测试。

**Session**: `clef-788135f2`
**Prompt**: "RPG village theme, C major, 4/4, 80BPM, ABA form, ~45s"
**Plan**: 15 bars, key=C, bpm=80, ABA (4+7+4)

### 全流程完成

```
Parse → Sample → Create → Iterate → Review → Express
  6s     345s     240s     1 round    confirm   30s
                   ↓                     ↓
              2 FAIL                auto-continue
              (repaired)                ↓
                                     done
```

**总耗时**: ~10 分钟
**输出**: `final_r1.mid`

### 验证指标

| 指标 | 修复前（E2E 日志） | 修复后 | 状态 |
|------|-------------------|--------|------|
| Agent 轮次耗尽 | 4 次 max_turns 耗尽 | 15 次触发均为正常退出 | ✅ |
| 验证越修越差 | 3 → 4 FAIL | 2 FAIL 被 repair 处理 | ✅ |
| API 400 崩溃 | 6 轮后上下文溢出 | 0 次崩溃 | ✅ |
| measure_duration | 最常见的 FAIL 类型 | 确定性工具 + repair 处理 | ✅ |
| 最终输出 | N/A（session 失败） | valid MIDI 文件 | ✅ |

### Commit 清单

```
c216c0f feat(server): add fix_measure_duration deterministic tool
49cbffb fix(server): remove dead code and add clef-repair agent test
a3a6804 fix(server): clean up unused variables, tighten test, skip %%MIDI lines
b1959e7 feat(server): add clef-repair agent for validation-driven ABC fixes
1a19ab8 feat(server): code-driven best-of-N validate-repair loop with repair agent
58a191c feat(server): two-pass generation (rhythm skeleton first, pitch fill second)
7112542 fix(server): fix stripped scope bug, update tool counts, sync agents.yaml tools
baec555 feat(server): integrate two-pass generation into best-of-N first round
8e7e418 fix(server): handle PARSE_ERROR measures in two-pass rhythm feedback
```

---

## 6. 经验总结

1. **确定性问题用确定性方案**：measure_duration 是算术问题，不应该交给 LLM。`fix_measure_duration` 用正则 + 算术一次性解决，比 agent 重试 3 次更可靠。

2. **职责分离：创作 ≠ 修复**：同一个 agent 既创作又修复会导致上下文累积和验证退化。拆分为创作 agent（生成）和修复 agent（定向修复），各自在独立上下文中工作。

3. **Best-of-N 选优比单次重试更鲁棒**：生成多个 candidate，选 fail_count 最小的。即使某个 candidate 质量差，不影响其他 candidate 的评估。

4. **两阶段生成降低 LLM 认知负担**：LLM 处理 `2 2 2 2 |` 比 `c2 d2 e2 f2 |` 准确得多。先验证骨架再填音高，将 measure_duration 错误率从 75% 降到 12.5%。

5. **Review 流程有效但无法覆盖运行时路径**：8 个代码问题在 review 中被发现，但 `KeyError: 'sum'` 只在 E2E 测试中暴露——因为 PARSE_ERROR 路径只有真实 LLM 输出才会触发。单元测试和 code review 无法替代 E2E 验证。

6. **Subagent-Driven Development 工作流有效**：每个任务由独立 subagent 实现，经过 spec review 和 quality review 两道检查。4 个任务共发现 8 个问题，全部在 commit 前修复。
