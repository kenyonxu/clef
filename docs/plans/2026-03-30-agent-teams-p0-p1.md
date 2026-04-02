# Agent Teams 集成 + Hooks 成本监控

## Context

clef-compose 工作流当前所有 Agent 调用均为串行执行（主会话通过 `Agent(subagent_type=...)` 逐个派发）。在 Step 2b Leader 迭代阶段，`tasks.json` 中可能包含多个无依赖关系的独立任务（如"修改旋律 5-8 小节"和"改进鼓组 9-16 小节"），这些任务目前串行执行，浪费时间。

本计划将 Agent Teams 引入迭代阶段实现并行执行（P0），并添加 Hooks 监控 Agent 调用成本（P1）。

## 当前状态

- Claude Code 2.1.7，`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 已启用
- `teammateMode: in-process` 已配置
- Teams 目录 `~/.claude/teams/` 存在但为空
- 项目级 `settings.json` 不存在（仅有 `settings.local.json`）
- 无项目级 Hooks 配置

## P0：Agent Teams 集成

### 范围

**改什么：**
- SKILL.md 中 Step 2b 迭代阶段的调度逻辑 → 支持 TeamCreate 并行派发
- 可能的 Step 2a 优化：首个创作 Agent 完成后，Rhythmist 与第二个创作 Agent 并行

**不改什么：**
- Step 0/1/3 保持原有逻辑
- 7 个 Agent .md 定义文件不修改（Agent 定义与 Teams 机制兼容）
- generation_order 机制保持不变（旋律/和声的依赖关系是音乐约束，不是技术约束）

### 设计决策

#### Q1: TeamCreate 何时调用？

**方案：在 Step 2a 开始时创建 Team，Step 2c 结束后销毁。**

理由：
- 避免每轮迭代反复创建/销毁的开销
- Step 2a 可能也受益于并行（见下）
- Step 2b 是主要受益阶段

#### Q2: Teammate 如何回传结果？

**方案：Teammate 将 ABC 片段写入指定文件，通过 SendMessage 通知 Lead 完成。**

```
Teammate (composer) 写入 .clef-work/teammate_composer_v3.abc
Teammate → Lead: "V:1 完成 → .clef-work/teammate_composer_v3.abc"
Lead 读取文件 → merge_abc.py
```

理由：
- ABC 片段可能很长（数十行），不适合放在 SendMessage 正文中
- 文件写入与当前 Agent 的工作方式一致（Agent 已有 Write 工具权限）
- Lead 读取文件后可以保留用于版本对比

#### Q3: 并行任务完成后的 merge→validate 循环？

**方案：所有并行任务全部完成后，Lead 统一执行 merge → analyze → validate。**

```
并行任务 A (Composer) ──→ 完成 ──┐
并行任务 B (Rhythmist) ─→ 完成 ──┼──→ Lead merge → analyze → validate → review → Leader
                                  │
依赖任务 C (depends_on A) ───────┘ (A 完成后才派发)
```

理由：
- 如果部分完成就 merge，另一个任务还在修改声部，会导致 merge 结果不一致
- 全部完成后统一 merge 是最安全的方式

#### Q4: depends_on 任务如何处理？

**方案：两阶段执行。**

1. 第一批：所有 `depends_on: null` 的任务并行派发
2. 等待全部完成 → merge → analyze → validate
3. 第二批：`depends_on` 指向已完成任务的任务并行派发
4. 等待全部完成 → merge → analyze → validate → review → Leader

由于 Leader 限制每轮最多 3 个任务，且 depends_on 链通常只有 1 层（旋律改→和声同步），两阶段足够。

#### Q5: Step 2a 是否有并行机会？

**方案：有条件并行。** 首个创作 Agent（Harmonist 或 Composer）完成后 merge，然后**第二个创作 Agent 和 Rhythmist 并行执行**。

```
generation_order: ["harmony", "melody"]

当前串行：
  Harmonist → merge → Composer → merge → Rhythmist → merge → validate

优化并行：
  Harmonist → merge → Composer ──────────→ merge ──→ validate
                      └→ Rhythmist (并行) ─┘
```

风险：Rhythmist 只看到 V:2 和弦（没有 V:1 旋律），低音线可能不够贴合旋律。但：
1. Rhythmist 主要跟随 V:2 和弦根音
2. 任何问题会被 Step 2b 迭代修复
3. 节省时间约 30-60 秒

**需要用户确认是否启用此优化。** 如果追求质量优先，可以只做 Step 2b 并行。

#### Q6: 文件冲突避免？

每个 Teammate 只写入自己的输出文件：
- Composer → `.clef-work/teammate_composer.abc`
- Harmonist → `.clef-work/teammate_harmonist.abc`
- Rhythmist → `.clef-work/teammate_rhythmist_bass.abc` + `.clef-work/teammate_rhythmist_drums.abc`

`score.abc` 和 `tasks.json` 只由 Lead（主会话）读写。Teammate 不直接修改 `score.abc`。

### 文件变更

#### 1. `SKILL.md` — Step 2 改造

**Step 2a 新增并行逻辑（可选）：**
```markdown
2a. 首轮完整创作

1. 按 generation_order 派发第一个创作 Agent（Harmonist 或 Composer）
2. 合并输出到 score.abc
3. [并行优化] 同时派发：
   - 第二个创作 Agent
   - Rhythmist（读当前 score.abc，写 teammate_rhythmist_*.abc）
4. 等待两者完成
5. 合并所有声部 → score.abc
6. 继续原有 merge → snapshot → validate → analyze 流程
```

**Step 2b 新增 Team 并行逻辑：**
```markdown
2b. Leader 迭代

7-9. [不变] Reviewer → Leader → tasks.json 判断
10. 如果需要迭代：
    a. 创建 Team: TeamCreate("clef-iter-{round}")
    b. 解析 tasks.json，按 depends_on 分为两批
    c. 第一批（depends_on: null）并行 spawn teammates
    d. 等待全部完成（通过 SendMessage 通知）
    e. merge → analyze → validate（FAIL 则派 Revision）
    f. 第二批（depends_on）并行 spawn teammates
    g. 等待全部完成 → merge → analyze → validate
    h. Reviewer → Leader → 判断是否继续
    i. TeamDelete
```

#### 2. 不修改的文件

- `.claude/agents/clef-*.md` — 7 个 Agent 定义不需要改动
- `.claude/settings.local.json` — 权限配置不变
- `scripts/*.py` — Python 工具链不变

### 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| Step 2a 并行导致 Rhythmist 低音不贴合旋律 | 中 | 可选功能，用户确认后启用；迭代阶段会修复 |
| Teammate 上下文不共享，需要重复传入 plan.json | 低 | Agent prompt 已设计为独立读取 plan.json |
| 并行 merge 时文件竞争 | 低 | 每个 Teammate 写独立文件，只有 Lead 操作 score.abc |
| Teams 功能仍为实验性 | 低 | 可随时回退到串行模式（不创建 Team 即可） |
| in-process 模式下 Teammate UI 切换 | 低 | Shift+Down 可切换查看，主要关注 Lead 输出 |

### 验证方案

1. 运行 `/clef-compose` 创建一首简单曲目
2. 观察 Step 2a 是否正确执行（串行或并行模式）
3. 在 Step 2b 中人为制造需要多个独立任务的场景
4. 确认并行任务正确完成且 merge 结果正确
5. 确认 depends_on 任务按正确顺序执行
6. 确认 Team 正确创建和销毁

### 回滚方案

- SKILL.md 通过 git 可随时回退
- 不创建 Team 即回退到串行模式
- 无其他配置变更需要回退

---

## P1：Hooks Agent 成本监控

### 范围

在项目级添加 PostToolUse Hook，记录每次 Agent 工具调用的元数据。

### 设计

#### Hook 触发条件

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Agent",
        "command": "python .claude/hooks/log_agent_call.py"
      }
    ]
  }
}
```

仅匹配 `Agent` 工具调用，不记录其他工具。

#### Hook 脚本

文件：`.claude/hooks/log_agent_call.py`

功能：
1. 从 stdin 读取 tool_input（JSON，包含 subagent_type、prompt 等信息）
2. 从 stdin 读取 tool_output（包含 Agent 返回的文本）
3. 提取关键字段：agent_name、timestamp、workflow_step（从 prompt 推断）
4. 追加写入 `.clef-work/agent_cost_log.jsonl`

#### 日志格式

```jsonl
{"ts": "2026-03-30T15:00:00", "agent": "clef-composer", "model": "opus", "step": "2a", "output_chars": 1234}
{"ts": "2026-03-30T15:01:30", "agent": "clef-reviewer", "model": "sonnet", "step": "2b-iter1", "output_chars": 2345}
```

#### workflow_step 推断逻辑

从 Agent tool 的 prompt 参数中提取步骤标识：
- 包含 "Step 2a" 或 "首轮" → `2a`
- 包含 "Step 2b" 或 "iter" → `2b-iter{N}`
- 包含 "Step 1b" 或 "方向小样" → `1b`
- 包含 "Step 3" 或 "表现力" → `3`
- 其他 → `unknown`

### 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `.claude/settings.json` | **新建** | 项目级 settings，包含 hooks 配置 |
| `.claude/hooks/log_agent_call.py` | **新建** | Hook 脚本 |
| `.claude/hooks/__init__.py` | **新建** | 空文件（Python 包） |

### 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| Hook 脚本执行失败阻塞工作流 | 低 | 添加 try/except，失败时静默跳过 |
| 日志文件过大 | 低 | 每次任务开始时清理旧日志（已在 Step 0 清理 .clef-work/） |
| Hook 输入格式变更 | 低 | 脚本添加防御性解析，缺失字段默认为 "unknown" |

### 验证方案

1. 手动触发一次 Agent 调用（如 `/clef-compose` 的任意步骤）
2. 检查 `.clef-work/agent_cost_log.jsonl` 是否正确写入
3. 验证 JSON 格式有效（`python -m json.tool`）
4. 确认 workflow_step 推断正确

---

## 实施顺序

1. **P1 先行**（低风险，独立于 P0）
   - 创建 `.claude/settings.json` + hooks 脚本
   - 验证日志输出
2. **P0 Step 2b 并行**（核心收益）
   - 修改 SKILL.md Step 2b
   - 测试并行迭代
3. **P0 Step 2a 并行**（可选优化）
   - 修改 SKILL.md Step 2a
   - 用户确认后启用
