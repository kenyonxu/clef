# Server 输出质量加固：逐声部截断、验证闭环、迭代早停

> 日期：2026-04-14 ~ 2026-04-16
> 分支：`feature/clef-server-v2`
> 前序文档：`server/docs/2026-04-14-server-scheduling-recovery-report.md`

本文档记录前序报告（截至 commit `8d385a1`）之后，针对 **输出质量** 和 **迭代效率** 的 3 个 commit。核心问题：多声部合并后全局截断会毁灭 V:3/V:4；Reviewer 对自动化验证失败无感知；迭代无法在无效修复时提前终止。

---

## 1. 三个 Commit 总览

| Commit | 日期 | 描述 |
|--------|------|------|
| `a3e2904` | 2026-04-14 | 修复逐声部 L: 指令保留 + generation_order 加入 rhythm |
| `3855b6e` | 2026-04-15 | 逐声部截断、express plan 校验、Reviewer FAIL 感知、迭代早停 |
| `0a8e282` | 2026-04-16 | 停止跟踪含 API Key 的 bat 文件，修复 stop.bat 安全性 |

---

## 2. 修复 1：generation_order 加入 rhythm（`a3e2904`）

### 问题

`generation_order` 默认值为 `["harmony", "melody"]`，缺少 `rhythm`。这导致：

- `_PlanSchema` 的 Pydantic 验证接受不含 rhythm 的 plan
- `_phase_create` 硬编码 fallback 和 Leader 预规划均不生成 rhythm 声部
- 4 声部作曲（旋律 + 和声 + 低音 + 鼓）实际只生成 2 个声部

### 修复

在 4 处同步更新默认值 `["harmony", "melody"]` → `["harmony", "melody", "rhythm"]`：

| 位置 | 用途 |
|------|------|
| `_PlanSchema.generation_order` | Pydantic schema 默认值 |
| `_phase_parse` 的 plan prompt | 指导 LLM 输出格式 |
| `_phase_create` 硬编码 fallback | 无 Leader 时的降级路径 |
| `_phase_create` Leader 预规划 | 有 Leader 时的任务生成 |

---

## 3. 修复 2：逐声部截断（`3855b6e`，修复 1/4）

### 问题

迭代阶段强制小节计数时，使用 `_truncate_to_bars()` 对合并后的 4 声部 score.abc 做 **全局线性截断**。

4 声部 32 小节 = 总计约 128 个 `|` 符号。`_truncate_to_bars(abc, 32)` 按行数从上到下切到第 32 个 `|`，结果只保留了 V:1 和 V:2 的部分，**V:3（低音）和 V:4（鼓）被完全删除**。

### 修复

新增两个静态方法替代全局截断：

- `_truncate_score_per_voice(abc_text, target_bars)` — 解析所有 V: 块，对每个声部独立截断
- `_truncate_voice_lines(lines, target_bars)` — 对单个声部的行列表按小节数截断

流程：
```
score.abc (V:1 + V:2 + V:3 + V:4)
    │
    ├── parse voice blocks → {V:1: ..., V:2: ..., V:3: ..., V:4: ...}
    │
    ├── truncate each block independently to target_bars
    │
    └── reassemble header + truncated voice blocks
```

测试中新增回归测试 `test_old_global_truncate_destroys_voices` 证明旧方法确实会摧毁 V:3/V:4。

---

## 4. 修复 3：Express Plan 格式校验（`3855b6e`，修复 2/4）

### 问题

`_phase_express` 调用 `clef-orchestrator` agent 生成 expression_plan.json，但不校验返回内容是否包含有效字段（如 `cc7_volume`、`cc10_breath`、`pitch_bend` 等）。如果 agent 返回无效 JSON（如 `{"verdict": "revise"}`），仍然写入 `expression_plan.json` 并传递给 `inject_expression.py`。

### 修复

在 `_phase_express` 中新增格式校验：

- 提取 JSON 后检查是否包含至少一个已知 CC 字段（`cc7_volume`, `cc10_breath`, `cc91_reverb`, `pitch_bend` 等）
- 无有效字段 → 跳过 `inject_expression`，直接标记 session 为 `done`
- 有有效字段 → 正常保存并注入

---

## 5. 修复 4：Reviewer FAIL 感知（`3855b6e`，修复 3/4）

### 问题

迭代阶段 `_run_validation()` 返回的自动化验证失败（measure_duration、voice_alignment 等）只记录到 `_validation_failures`，但不传递给 Reviewer agent。Reviewer 在不知道有技术缺陷的情况下打分，经常给存在 FAIL 问题的乐谱 8-9 分 + `verdict: "pass"`。

### 修复

**a) `_call_reviewer` 新增 `validation_failures` 参数**

将自动化验证结果格式化后注入 Reviewer prompt：

```
VALIDATION REPORT (automated checks):
- [FAIL] measure_duration (V:1): bar 3 has 5 beats
- [FAIL] voice_alignment (global): voices misaligned

The above validation failures indicate TECHNICAL problems in the score.
You MUST factor these into your scoring: each FAIL-level issue should
reduce the relevant dimension score by at least 2 points.
```

**b) SCORING RULES 约束**

在 Reviewer prompt 中新增 3 条硬规则：

1. FAIL 级问题 → 对应维度分数至少 -2
2. 有未解决 FAIL 时，任何维度分数不得 > 7
3. `overall_score > 7` 但有 3+ 个 FAIL → 强制 `verdict: "revise"`

**c) 新增 `_format_validation_feedback` 方法**

将 `_validation_failures` 列表格式化为可读文本，包含 category、voice、message。

---

## 6. 修复 5：迭代早停（`3855b6e`，修复 4/4）

### 问题

迭代最多跑 N 轮（默认 3），即使验证失败数连续多轮不改善也继续消耗 API 调用。常见场景：LLM 无法修复某个结构性问题，3 轮迭代每轮都是相同的 FAIL，但系统仍然完整跑完。

### 修复

新增停滞检测机制：

```python
self._stagnation_count = 0
self._prev_iteration_fail_count = None

# 每轮迭代结束后：
current_fail_count = len(failures) if failures else 0
if prev_fails is not None and current_fail_count >= prev_fails:
    self._stagnation_count += 1
else:
    self._stagnation_count = 0

if self._stagnation_count >= 2:
    logger.warning("Session %s: fail_count stagnated for 2 rounds, early-stopping", ...)
    break
```

逻辑：连续 2 轮 fail_count 未改善（或恶化）→ 提前终止迭代。

---

## 7. 修复 6：stop.bat 安全性（`0a8e282`）

### 问题

1. `start-server.bat` 和 `start.bat` 包含硬编码 API Key（`DEEPSEEK_API_KEY`、`GLM_API_KEY`），已被 git 跟踪
2. `stop.bat` 使用 `taskkill /F /IM python.exe` 和 `taskkill /F /IM node.exe`，会杀死系统上所有 Python/Node 进程

### 修复

- **删除** `start-server.bat` 和 `start.bat`（API Key 已泄露，需轮换）
- **重写** `stop.bat`：改用窗口标题匹配（`WINDOWTITLE eq Clef Server*`）+ 端口匹配（`netstat :8900/:5173`），不再杀死无关进程

---

## 8. 文件变更总览

| 操作 | 文件 | 变更 | 职责 |
|------|------|------|------|
| 修改 | `server/src/clef_server/orchestrator.py` | +151 / -4 | 逐声部截断 + express 校验 + Reviewer FAIL 感知 + 迭代早停 + rhythm generation_order |
| 修改 | `server/tests/test_orchestrator.py` | +374 / -1 | 新增 5 个测试类 10 个测试 |
| 删除 | `server/start-server.bat` | -7 | 含 API Key，停止跟踪 |
| 删除 | `server/start.bat` | -27 | 含 API Key，停止跟踪 |
| 修改 | `server/stop.bat` | +14 / -4 | 窗口标题 + 端口匹配替代全局 taskkill |

---

## 9. 测试结果

| 测试文件 | 用例数 | 说明 |
|----------|--------|------|
| `test_orchestrator.py` | 79 | 从 69 增长到 79（+10） |
| `test_concurrency.py` | 8 | 无变化 |
| `test_sessions.py` | 26 | 无变化 |
| **总计** | **113** | **113** |

### 新增测试类

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|----------|
| `TestPerVoiceTruncation` | 3 | 4 声部独立截断、不过度截断、旧方法 bug 回归 |
| `TestExpressPlanValidation` | 2 | 无效 plan 跳过、有效 plan 保存 |
| `TestReviewerValidationContext` | 2 | 验证失败注入 prompt、无失败时不注入 |
| `TestReviewerScoringConstraints` | 1 | SCORING RULES 文本存在于 prompt |
| `TestIterateEarlyStop` | 2 | 停滞 2 轮触发早停、改善则重置计数 |

---

## 10. Commit 清单

```
a3e2904 fix(server): preserve per-voice L: directive in merge and add rhythm to generation_order
3855b6e fix(server): per-voice truncation, express plan validation, reviewer FAIL-awareness, iterate early-stop
0a8e282 chore: stop tracking start-server.bat/start.bat (API keys), fix stop.bat safety
```

---

## 11. 经验总结

1. **多声部截断必须逐声部**：全局线性截断对多声部合并文本是灾难性的。每个 V: 块有独立的小节计数，截断也必须独立进行。这是从 "检查 status=done" 转向 "验证输出完整性" 思路的延续（前序报告经验 12）。

2. **自动化验证结果必须流入 Reviewer**：验证和审查是两个独立环节，如果结果不传递，审查就变成了盲审。将 `_validation_failures` 注入 Reviewer prompt，让 LLM 在打分时知道有哪些技术缺陷，显著提升了审查的准确性。

3. **迭代早停是成本控制的基础**：当 LLM 连续 2 轮无法改善验证失败数时，继续迭代只是浪费 API 调用。停滞检测的代价是几乎为零（一个计数器），收益是节省 1-2 轮的完整迭代成本。

4. **API Key 绝不能进 git**：即使是本地开发用的 bat 文件。`git rm` 只能删除后续跟踪，已泄露的 Key 必须轮换。`stop.bat` 的 `taskkill /IM` 则是另一个教训——杀死进程必须精确匹配，不能使用通配符。
