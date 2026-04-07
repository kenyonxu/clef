# Clef Server Workflow Alignment Design

## Goal

将 Clef Server 的工作流与 clef-compose SKILL.md 完全对齐，实现分阶段执行、用户确认点、Leader 迭代循环，并通过 Web 前端展示确认 UI。

## Scope

核心流程（6 阶段，3 确认点），不含 Step 2.5 编曲扩展（Arranger）。

## Architecture

Phase Orchestrator 模式。新建 `ComposeOrchestrator` 类，每个阶段是独立方法。阶段完成时更新 session 状态，如需确认则设为 `awaiting_confirm`。前端通过 3 秒轮询 `GET /status` 发现确认点，通过 `POST /confirm` 恢复下一阶段。

**通信机制**: 轮询 + REST（前端已有骨架）。

**确认交互**: 继续/取消 + 文字反馈。方向小样确认点支持最多 10 轮反馈回路。

## Tech Stack

- Python: FastAPI, asyncio, httpx (ChatCompletionsClient)
- Agent Framework: AgentExecutor, WorkflowBuilder (子图)
- React 19 + TypeScript + Zustand + TailwindCSS (前端)

---

## Workflow Phases

```
POST /compose (用户输入 prompt)
       │
       ▼
┌──────────────────────────────┐
│  Phase 0: parse              │  LLM 解析需求 → 生成 plan.json
│  (需求解析 + 规划)            │
└──────────────┬───────────────┘
               ▼
         ⛔ 确认点 1 ─── POST /confirm {action, feedback?}
         展示: plan.json 关键参数
         用户: 确认 / 取消
               │ (确认)
               ▼
┌──────────────────────────────┐
│  Phase 1: sample             │  harmony → melody → 旋律门控 → merge → review
│  (方向小样, ≤10轮反馈)        │
└──────────────┬───────────────┘
               ▼
         ⛔ 确认点 2 ─── POST /confirm {action, feedback?}
         展示: sample.mid + 审核报告
         用户: 继续/反馈/取消
         反馈 → 重新执行 Phase 1
               │ (继续)
               ▼
┌──────────────────────────────┐
│  Phase 2: create             │  harmony → melody → rhythm → merge → validate
│  (完整创作)                  │  → analyze
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  Phase 3: iterate            │  review → leader → 派任务 → merge → validate
│  (Leader 迭代, ≤3轮)         │  循环直到 iteration_complete
└──────────────┬───────────────┘
               ▼
         ⛔ 确认点 3 ─── POST /confirm {action, feedback?}
         展示: final.mid + 审核报告 + 迭代摘要
         用户: 继续/反馈(回Phase3)/取消
               │ (继续)
               ▼
┌──────────────────────────────┐
│  Phase 4: express            │  orchestrator → expression_plan.json
│  (表现力注入)                │  → inject_expression → final.mid
└──────────────┬───────────────┘
               ▼
           ✓ done (输出 final.mid)
```

## Session State Machine

```
created → running ⇄ awaiting_confirm → done
                    ↓
                cancelled / failed
```

`running` 细分为 `current_phase` 字段。`awaiting_confirm` 附带 `confirmation_data`。

### Phase 常量

```python
PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True},
    {"id": "sample",  "label": "方向小样",         "confirm": True},
    {"id": "create",  "label": "完整创作",         "confirm": False},
    {"id": "iterate", "label": "质量迭代",         "confirm": False},
    {"id": "review",  "label": "试听审核",         "confirm": True},
    {"id": "express", "label": "表现力注入",       "confirm": False},
]
```

### ComposeSession 新增字段

```python
current_phase: str = "parse"
phase_history: list[dict]           # 每阶段执行记录
confirmation_data: dict | None      # 确认点展示数据
sample_round: int = 0               # 方向小样反馈轮次
```

### confirmation_data 结构

```python
# Phase 0 (parse)
{"phase": "parse", "title": "确认音乐规划", "plan": {...}}

# Phase 1 (sample)
{"phase": "sample", "title": "试听方向小样",
 "sample_file": "path", "review": {...}}

# Phase 3→4 (review)
{"phase": "review", "title": "审核最终作品",
 "output_file": "path", "review": {...}, "iterations": 2}
```

## ComposeOrchestrator

文件: `server/src/clef_server/orchestrator.py`

```python
class ComposeOrchestrator:
    def __init__(self, session_id: str, providers: dict, workdir: str): ...

    async def start(self, prompt: str):
        """Entry point — runs Phase 0 (parse + plan)."""

    async def resume(self, user_feedback: str | None = None):
        """Resume from awaiting_confirm — runs next phase based on session.current_phase."""

    async def _phase_parse(self, prompt: str) -> dict:
        """Phase 0: LLM parses requirements, generates plan.json."""

    async def _phase_sample(self, feedback: str | None = None) -> None:
        """Phase 1: Direction sample with melody gate (≤3 rounds) + review."""

    async def _phase_create(self) -> None:
        """Phase 2: Full creation (harmony → melody → rhythm → merge → validate → analyze)."""

    async def _phase_iterate(self) -> int:
        """Phase 3: Leader iteration loop (≤3 rounds). Returns iterations count."""

    async def _phase_express(self) -> str:
        """Phase 4: Orchestrator + inject_expression → final.mid."""
```

每个 phase 方法是自包含的：读 workdir 文件作为输入，输出写回 workdir。无长阻塞协程。

### Phase 内部实现

**Phase 0 (parse)** — 单次 LLM 调用
- 用 ChatCompletionsClient 解析用户需求，输出结构化 plan.json
- 保存 plan.json 到 workdir
- 设置 `session.awaiting_confirm` + confirmation_data

**Phase 1 (sample)** — 顺序派 Agent
- 按 `generation_order` 顺序派 2 个 AgentExecutor（harmony → melody）
- 旋律门控：Composer 后调 Reviewer 审旋律（M1/M3/M4/M5），不通过则反馈重写（≤3 轮）
- merge_abc → abc_to_midi → Reviewer 7 维审核
- 用户反馈时：附加 feedback 到 Agent prompt，重新执行，`sample_round++`（≤10 轮）

**Phase 2 (create)** — 顺序派 Agent
- 按 `generation_order` 派 harmony → melody，然后 Rhythmist（V:3+V:4）
- merge_abc → validate_abc → abc_to_midi → analyze
- 无确认，自动进入 Phase 3

**Phase 3 (iterate)** — Python 循环
- 每轮：调 Reviewer → 调 Leader → 按 tasks.json 派 Agent → merge → validate
- 失败时 Revision（≤2 次/轮）
- 最多 3 轮，或 `iteration_complete` 终止
- 设置 `session.awaiting_confirm` + confirmation_data

**Phase 4 (express)** — LLM + 脚本
- 调 Orchestrator LLM → expression_plan.json
- 运行 inject_expression.py → final.mid
- 设置 `session.set_done(output_files=[final.mid])`

## API 变更

| 端点 | 变更 | 说明 |
|------|------|------|
| `POST /compose` | 无变化 | 启动 Phase 0 |
| `GET /status/{id}` | response 增加 `current_phase`, `confirmation_data`, `phase_history`, `sample_round` | 前端轮询 |
| `POST /confirm/{id}` | body: `{action: "continue"\|"cancel", feedback?: string}` | 恢复/取消 |

`POST /confirm` 行为：
- `action: "continue"` — resume 下一阶段（feedback 可选）
- `action: "cancel"` — 取消工作流

Phase 1 反馈回路：`action: "continue"` + `feedback` 非空 → 重新执行 Phase 1（不推进）。
Phase 3 反馈回路：`action: "continue"` + `feedback` 非空 → 重新执行 Phase 3（不推进）。

## workdir 文件契约

```
workdir/
├── plan.json              # Phase 0 写, 后续所有阶段读
├── score.abc              # Phase 1/2/3 反复读写, merge 输出
├── sample.mid             # Phase 1 写, 确认点 2 展示
├── base.mid               # Phase 2 写, 表现力注入输入
├── output/
│   └── final.mid          # Phase 4 写, 最终输出
├── review_report.json     # Phase 1/3 写
├── validation_report.json # Phase 2/3 写
├── tasks.json             # Phase 3 写
└── history/               # snapshot 备份 (可选)
```

## Error Handling

| 场景 | 处理 |
|------|------|
| LLM 超时/断连 | 自动重试 1 次，仍失败则 `session.set_failed(error)` |
| Agent 输出失败信号 | 记录原因，不合并该片段，继续其他声部 |
| validate_abc FAIL | 自动 Revision（≤2 次/轮），超过则 CRITICAL |
| Leader 迭代 3 轮未达标 | 终止迭代，带警告进入确认点 3 |
| 方向小样反馈 10 轮 | 停止，建议用户回到 Phase 0 修改 plan |
| 用户取消 | 立即停止当前阶段，保留已有输出 |

## Frontend Confirmation UI

新增 `<ConfirmationPanel>` 组件，根据 `confirmation_data.phase` 渲染：

- `parse` → `<PlanConfirm>` — 参数网格（调性/BPM/曲式/时长）+ 配器列表 + 段落结构
- `sample` → `<SampleConfirm>` — MIDI 文件预览 + 评分条（旋律/和声/节奏/音域）+ verdict badge
- `review` → `<ReviewConfirm>` — MIDI 文件预览 + 评分条 + 迭代轮次摘要

三个确认点共享底部：反馈 textarea + 操作按钮组（取消 / 修改 / 继续）。

当 `session.status === "awaiting_confirm"` 且 `confirmation_data` 存在时，在 Workspace 右栏渲染 ConfirmationPanel，替代默认的 StepCard 列表。

原型文件: `server/web/public/confirm-mockup.html`

## 文件变更清单

### 新建
- `server/src/clef_server/orchestrator.py` — ComposeOrchestrator 类
- `server/web/src/components/ConfirmationPanel.tsx` — 确认面板容器
- `server/web/src/components/PlanConfirm.tsx` — 确认点 1 UI
- `server/web/src/components/SampleConfirm.tsx` — 确认点 2 UI
- `server/web/src/components/ReviewConfirm.tsx` — 确认点 3 UI

### 修改
- `server/src/clef_server/sessions.py` — 新增字段、PHASES 常量、phase 转换逻辑
- `server/src/clef_server/routes.py` — 重写 _run_workflow 为 orchestrator.start()，confirm 端点改为 orchestrator.resume()
- `server/src/clef_server/workflow.py` — 保留子图构建能力，供 orchestrator 的各 phase 调用
- `server/web/src/stores/sessionStore.ts` — 新增 confirmationData, currentPhase, sampleRound 状态
- `server/web/src/pages/Workspace.tsx` — 集成 ConfirmationPanel
- `server/web/src/api/types.ts` — 新增 ConfirmationData, PhaseHistory 类型

### 删除
- `server/src/clef_server/workflow.py` 中的 `build_compose_workflow()` 整图构建（被 orchestrator 替代）

### 不变
- `server/src/clef_server/chat_completions_client.py` — LLM 调用客户端
- `server/src/clef_server/config.py` — 配置加载
- `server/src/clef_server/providers.py` — Provider 工厂
- `server/src/clef_server/agents.py` — Agent 工厂
- `server/src/clef_server/tools.py` — 工具封装（merge_abc, validate 等）
- `server/src/clef_server/middleware.py` — Agent 上下文中间件
- `server/src/clef_server/app.py` — FastAPI app + CORS
