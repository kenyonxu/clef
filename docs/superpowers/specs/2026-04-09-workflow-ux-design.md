# Workflow 面板可用性改进设计

**日期**: 2026-04-09
**状态**: 已批准
**分支**: feature/clef-server-v2

## 问题

1. **Reviewer 不可见** — `sample` phase 调用 reviewer 两次（melody gate + full review），`iterate` phase 调用 leader 做任务调度，但这些 agent 都没有出现在前端 StepCard 的 agents 列表中
2. **长时间运行无进度** — `create`、`iterate` 等 phase 内部有 5+ 个子步骤（生成声部、合并、验证、修正、转换 MIDI），前端只显示 "running"，用户无法了解进展
3. **运行中步骤无视觉区分** — running 状态的步骤与 pending/done 步骤外观差异不足

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 子步骤展示方式 | 缩进列表（✓/spinner/○） | 信息密度高，可回溯，改动量适中 |
| 数据推送机制 | SSE 实时推送 | endpoint 已存在（stub），动态效果需要实时性 |
| 动态效果 | 蓝色发光边框 + 脉冲动画 | 明确区分运行中步骤，视觉反馈即时 |

## 架构变更

### 1. 后端 — SSE 事件系统

**文件**: `server/src/clef_server/sessions.py`

在 `ComposeSession` 中新增：

- `sub_steps: list[dict]` — 当前 phase 的子步骤列表，每项 `{label, status, agent, timestamp}`
- `record_sub_step(label, status, agent)` — 记录子步骤状态变更
- `get_sub_steps()` — 返回当前 phase 的子步骤列表
- `_sse_queue: asyncio.Queue` — 每个 session 一个事件队列

新增 SSE 事件类型：
- `sub_step_start` — 子步骤开始，payload: `{phase, label, agent}`
- `sub_step_done` — 子步骤完成，payload: `{phase, label, agent, duration_ms}`
- `agent_status` — agent 状态变更，payload: `{phase, agent, status}`

**文件**: `server/src/clef_server/routes.py`

补全 `/status/{session_id}/stream` endpoint：
- 从 session 的 `_sse_queue` 消费事件并 yield
- session 状态变更时也推送 `phase_update` 事件
- 连接断开时清理

### 2. 后端 — Orchestrator 子步骤埋点

**文件**: `server/src/clef_server/orchestrator.py`

在每个 phase 方法的关键点调用 `record_sub_step()`：

**parse phase**:
1. 解析用户需求
2. 生成 plan.json
3. 验证规划参数

**sample phase**:
1. 生成和声 (clef-harmonist)
2. 生成旋律 (clef-composer)
3. 生成节奏 (clef-rhythmist)
4. 合并声部
5. 技术验证
6. 旋律审查 (clef-reviewer) — 可能重复 N 次
7. 转换 MIDI
8. 完整审查 (clef-reviewer)

**create phase**:
1. 生成和声 (clef-harmonist)
2. 生成旋律 (clef-composer)
3. 生成节奏 (clef-rhythmist)
4. 合并声部
5. 技术验证
6. 修正失败声部（条件执行）
7. 转换 MIDI

**iterate phase**（每轮）:
1. 完整审查 (clef-reviewer)
2. 任务调度 (clef-leader)
3. 执行任务 — 动态，按 leader 返回的 tasks 展开
4. 验证 + 导出 MIDI

**express phase**:
1. 生成表现力方案 (clef-orchestrator)
2. 注入表现力数据

### 3. 后端 — PHASES agents 列表修正

**文件**: `server/src/clef_server/sessions.py`

```python
PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True,  "agents": []},
    {"id": "sample",  "label": "方向小样",         "confirm": True,  "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist", "clef-reviewer"]},
    {"id": "create",  "label": "完整创作",         "confirm": False, "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist"]},
    {"id": "iterate", "label": "质量迭代",         "confirm": False, "agents": ["clef-reviewer", "clef-leader", "clef-revision"]},
    {"id": "review",  "label": "试听审核",         "confirm": True,  "agents": ["clef-reviewer"]},
    {"id": "express", "label": "表现力注入",       "confirm": False, "agents": ["clef-orchestrator"]},
]
```

变更点：
- `sample` 新增 `clef-reviewer`
- `iterate` 新增 `clef-leader`

### 4. 前端 — 类型更新

**文件**: `server/web/src/api/types.ts`

```typescript
export interface SubStep {
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
  agent?: string
  timestamp?: number
}

export interface PhaseStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  confirm: boolean
  agents?: AgentProgress[]
  sub_steps?: SubStep[]    // 新增
  error?: string
}
```

### 5. 前端 — SSE 订阅

**文件**: `server/web/src/hooks/useSSE.ts`（新文件）

- 封装 EventSource 连接管理
- 接收 `sub_step_start`、`sub_step_done`、`agent_status`、`phase_update` 事件
- 调用 sessionStore 的 action 更新状态
- 自动重连 + session 终止时清理

### 6. 前端 — Store 更新

**文件**: `server/web/src/stores/sessionStore.ts`

新增 actions：
- `updateSubStep(phase, label, status, agent)` — 更新指定 phase 的子步骤
- `updateAgentStatus(phase, agent, status)` — 更新 agent 运行状态

### 7. 前端 — StepCard 增强

**文件**: `server/web/src/components/StepCard.tsx`

- running 状态：蓝色发光边框 + CSS 脉冲动画（`@keyframes cardPulse`）
- agents 行：根据 agent status 显示不同颜色（done=绿，running=蓝，pending=灰）
- 新增子步骤区域：缩进列表，用 ✓ / spinner / ○ 图标
- 每个子步骤显示关联的 agent 名称（monospace 小字）

### 8. 前端 — Workspace 集成

**文件**: `server/web/src/pages/Workspace.tsx`

- 在 session 运行时启动 SSE 连接
- session 终止或离开页面时断开

## 不在范围内

- 预估剩余时间（子步骤耗时不可预测，依赖 LLM 响应速度）
- 子步骤的重试/失败详情展开（error 信息已通过现有机制显示）
- WebSocket 替代 SSE（SSE 足够且更简单）

## 文件变更清单

| 文件 | 变更类型 |
|------|----------|
| `server/src/clef_server/sessions.py` | 修改 — PHASES agents、sub_steps 字段、SSE queue |
| `server/src/clef_server/routes.py` | 修改 — 补全 SSE endpoint |
| `server/src/clef_server/orchestrator.py` | 修改 — 各 phase 添加 sub_step 埋点 |
| `server/web/src/api/types.ts` | 修改 — 新增 SubStep 类型 |
| `server/web/src/hooks/useSSE.ts` | 新增 — SSE 连接管理 |
| `server/web/src/stores/sessionStore.ts` | 修改 — 新增 sub_step/agent status actions |
| `server/web/src/components/StepCard.tsx` | 修改 — 子步骤渲染 + 动画样式 |
| `server/web/src/pages/Workspace.tsx` | 修改 — 集成 SSE hook |
