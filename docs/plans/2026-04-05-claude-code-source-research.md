# Claude Code 源码深度研究报告

> 目标：从 Claude Code 源码中提取对 Clef Server + AstrBot 开发有参考价值的架构模式和实现细节。
>
> 源码版本：claude-code-2.1.88（`E:\GitHub\claude_code_src`）
>
> 研究日期：2026-04-05

## Executive Summary

Claude Code 的 Agent 系统采用 **Markdown-frontmatter Agent 定义 + Tool Pool + 异步执行循环** 的三层架构。其核心设计对 Clef Server 有极高参考价值：(1) Agent 定义为声明式 markdown 文件，(2) Tool 通过 Zod schema 定义输入输出，(3) Team/Swarm 通过文件系统和消息传递实现多 Agent 协作，(4) 上下文通过 `appendSystemPrompt` 和文件传递管理。以下提炼出可直接借鉴的设计模式。

---

## 1. Agent 定义与加载系统

### 1.1 Agent 数据结构（可直接复用）

**源码**: `src/tools/AgentTool/loadAgentsDir.ts`

Claude Code 的 Agent 定义是一个统一的数据结构，既支持内置（TypeScript 常量）也支持自定义（Markdown 文件）：

```typescript
// 核心字段（对 Clef Server 的 AgentDef 有直接参考价值）
interface AgentDefinition {
  agentType: string          // "clef-composer"
  whenToUse: string          // description，决定何时使用该 Agent
  model?: string             // "inherit" | "sonnet" | "opus" | "haiku" | 具体模型名
  maxTurns?: number          // 最大轮次
  tools?: string[]           // 允许的工具列表（白名单）
  disallowedTools?: string[] // 禁止的工具列表（黑名单）
  requiredMcpServers?: string[] // 需要的 MCP 服务器
  omitClaudeMd?: boolean     // 是否跳过 CLAUDE.md 注入
  getSystemPrompt: () => string  // 延迟构建系统提示词
  source: 'built-in' | 'user' | 'plugin'
}
```

**对 Clef Server 的启发**：设计文档中的 `AgentDef` dataclass 可以对齐此结构，增加 `disallowedTools`、`requiredMcpServers`、`maxTurns` 等字段。

### 1.2 Markdown Frontmatter 解析

**源码**: `loadAgentsDir.ts` → `parseAgentFromMarkdown()`

Agent 从 markdown 文件加载的流程：

1. 扫描 `.claude/agents/` 目录下所有 `.md` 文件
2. 解析 YAML frontmatter 提取 `name`、`description`、`model`、`tools`、`disallowedTools`、`skills`、`memory` 等字段
3. frontmatter 之后的 markdown body 作为 `getSystemPrompt()` 的内容
4. `skills` 字段引用其他 skill 文件，加载时注入为系统提示词的一部分
5. 如果 `memory: true`，自动注入 Read/Write/Edit 工具

**关键实现细节**：
- `description` 中的 `\\n` 转义为换行符
- `model` 字段支持 `inherit`（继承父 Agent 模型）或具体值
- `tools` 和 `disallowedTools` 互斥使用，分别定义白名单/黑名单
- `getSystemPrompt` 是**惰性函数**（每次调用重新构建），允许动态注入上下文

**对 Clef Server 的启发**：
- Clef 的 8 个 Agent `.md` 文件格式与 Claude Code 完全兼容
- Clef Server 可以直接复用 `parseAgentFromMarkdown()` 的解析逻辑
- `skills` 字段对应 Clef 的 theory-* 子技能，可以沿用相同的注入模式

### 1.3 内置 Agent 注册

**源码**: `src/tools/AgentTool/builtInAgents.ts`

内置 Agent 通过常量定义：

```typescript
export const EXPLORE_AGENT: BuiltInAgentDefinition = {
  agentType: 'Explore',
  whenToUse: '...描述何时使用...',
  disallowedTools: [AGENT_TOOL_NAME, FILE_EDIT_TOOL_NAME, FILE_WRITE_TOOL_NAME],
  model: process.env.USER_TYPE === 'ant' ? 'inherit' : 'haiku',
  omitClaudeMd: true,
  getSystemPrompt: () => getExploreSystemPrompt(),
}
```

**对 Clef Server 的启发**：
- 按 Agent 角色设定不同的 `disallowedTools`（如 Reviewer 不需要 write_file）
- Read-only Agent（如 Reviewer）设置 `omitClaudeMd: true` 避免无关上下文
- 模型选择可以基于运行环境动态调整

---

## 2. Agent 执行引擎

### 2.1 runAgent 核心函数

**源码**: `src/tools/AgentTool/runAgent.ts`

这是 Claude Code Agent 系统的核心。签名：

```typescript
async function runAgent({
  agentDefinition,      // Agent 定义
  promptMessages,       // 初始用户消息列表
  toolUseContext,       // 工具执行上下文（包含 options、abortController 等）
  canUseTool,           // 权限检查函数
  isAsync,              // 是否异步执行
  forkContextMessages,  // Fork 子 Agent 的继承上下文
  override,             // 覆盖项（systemPrompt、abortController、agentId）
  model,                // 模型覆盖
  maxTurns,             // 最大轮次覆盖
  availableTools,       // 预计算的工具池
  allowedTools,         // 工具白名单（替代所有 allow 规则）
  onCacheSafeParams,    // prompt cache 优化回调
  useExactTools,        // Fork 模式：精确工具集
  worktreePath,         // 工作目录隔离路径
  description,          // 任务描述
  transcriptSubdir,     // 转录子目录
  onQueryProgress,      // 进度回调
}: RunAgentParams): Promise<AgentResult>
```

**执行流程**：
1. 解析 Agent 模型（`getAgentModel`）— 处理 `inherit`/`sonnet`/`opus`/`haiku` 别名
2. 组装工具池（`assembleToolPool`）— 根据 Agent 的 `tools`/`disallowedTools` 过滤
3. 解析 Agent MCP 服务器（`requiredMcpServers`）
4. 构建系统提示词（`buildEffectiveSystemPrompt`）— 基础 prompt + CLAUDE.md + Agent prompt + memory
5. 合并工具集（dedup by name）
6. 执行查询循环（`query()`）— LLM 调用 + tool 执行 + 结果回传

**对 Clef Server 的启发**：
- `runAgent` 的参数设计可以作为 Clef Server `AgentRuntime.call()` 的参考
- 工具过滤逻辑（白名单 vs 黑名单）是关键的安全边界
- 系统提示词的分层构建（base + agent + memory）值得借鉴

### 2.2 Fork 子 Agent 模式

**源码**: `src/tools/AgentTool/forkSubagent.ts`

Fork 模式是 Claude Code 的新特性，用于高效并行执行：

```typescript
// 构建 fork 子 Agent 的消息（优化 prompt cache）
function buildForkedMessages(directive, assistantMessage): MessageType[] {
  // 1. 克隆父 Agent 的完整 assistant 消息（所有 tool_use blocks、thinking、text）
  // 2. 构建单个 user 消息，包含所有 tool_result（使用相同占位符）
  // 3. 追加 per-child directive 文本块
  // 结果：只有最后的 directive 文本不同，最大化 cache hit
}
```

**关键设计决策**：
- Fork 子 Agent 继承父 Agent 的完整对话上下文
- 使用占位符 `FORK_PLACEHOLDER_RESULT` 替代真实 tool 结果（cache 优化）
- 每个 fork 子 Agent 只有一个不同的文本块（任务指令）

**对 Clef Server 的启发**：
- Step 1b（方向小样）的并行 Agent 调用可以参考 Fork 模式的消息构建
- 在同一 LLM 提供商内，prompt cache 可以显著降低成本

### 2.3 Agent 隔离模式

**源码**: `runAgent.ts` + `spawnInProcess.ts`

两种隔离模式：

| 模式 | 实现 | 适用场景 |
|------|------|----------|
| **In-Process** | AsyncLocalStorage 上下文隔离 | Team 内部 teammate |
| **Worktree** | Git worktree 文件系统隔离 | 独立子任务 |
| **Remote** | 远程 CCR 环境 | 大规模并行 |

**In-Process Teammate 状态管理**：

```typescript
interface InProcessTeammateTaskState {
  status: 'running' | 'idle' | 'completed' | 'failed'
  messages: Message[]           // 对话历史
  pendingUserMessages: string[]  // 待处理消息队列
  shutdownRequested: boolean     // 关闭请求
}
```

**对 Clef Server 的启发**：
- Clef Server 不需要 worktree 隔离（文件通过 session 目录天然隔离）
- In-Process 模式的 idle/active 状态机值得借鉴
- `pendingUserMessages` 队列模式可用于异步任务轮询

---

## 3. Tool 定义与执行

### 3.1 Tool 定义模式

**源码**: `src/Tool.ts`

```typescript
// 工具定义使用 Zod schema + builder 模式
export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return {
    ...TOOL_DEFAULTS,    // 默认值：isEnabled=true, isConcurrencySafe=false, isReadOnly=false
    userFacingName: () => def.name,
    ...def,
  } as BuiltTool<D>
}

// 工具的部分定义（只需提供必要部分）
type ToolDef<Input, Output> = Omit<Tool<Input, Output>, DefaultableToolKeys>
  & Partial<Pick<Tool<Input, Output>, DefaultableToolKeys>>
```

**对 Clef Server 的启发**：
- 设计文档中的 `ToolDef` dataclass 可以简化为此模式
- 使用 Pydantic 替代 Zod 进行 schema 定义
- `isReadOnly` / `isConcurrencySafe` 属性可以帮助 DAG Executor 判断并行安全性

### 3.2 Tool 执行流程

**源码**: `src/services/tools/toolExecution.ts`

完整执行流程：

1. **PreToolUse Hooks** — 输入修改/拦截
2. **权限检查** — `canUseTool()` 分类器 + 用户确认
3. **Schema 校验** — `inputSchema.parse(processedInput)`
4. **Tool 调用** — `tool.call(input, context, canUseTool, msg, progress)`
5. **结果映射** — `tool.mapToolResultToToolResultBlockParam(result, toolUseId)`
6. **PostToolUse Hooks** — 输出修改/格式化
7. **记录日志** — 性能追踪 + analytics

**对 Clef Server 的启发**：
- Clef Server 的 Tool Layer 可以简化为：schema 校验 → handler 调用 → 结果格式化
- 不需要 hook 系统和权限检查（服务端内部调用，无用户交互）
- 但需要 `timeout` 和 `retry` 机制（Python subprocess 可能挂起）

### 3.3 Tool Pool 组装

**源码**: `src/utils/toolPool.ts` + `runAgent.ts`

```typescript
function assembleToolPool(permissionContext, mcpTools): Tools {
  // 1. 从全局工具注册表获取所有工具
  // 2. 根据 Agent 的 tools/disallowedTools 过滤
  // 3. 合并 MCP 工具（去重）
  // 4. 返回最终工具池
}
```

**对 Clef Server 的启发**：
- 设计文档中的 `AGENT_TOOLS` 映射就是简化版 Tool Pool
- 可以增加 `isConcurrencySafe` 标记，让 DAG Executor 知道哪些工具可以并行调用

---

## 4. Team/Swarm 编排系统

### 4.1 Team 数据结构

**源码**: `src/utils/swarm/teamHelpers.ts`

```typescript
interface TeamFile {
  name: string
  description?: string
  createdAt: number
  leadAgentId: string
  leadSessionId?: string
  members: Array<{
    agentId: string
    name: string
    agentType?: string
    model?: string
    prompt?: string
    color?: string
    planModeRequired?: boolean
    joinedAt: number
    cwd: string
    worktreePath?: string
    sessionId?: string
    subscriptions: string[]   // 订阅的消息频道
    isActive?: boolean        // false = idle
    mode?: PermissionMode
  }>
}
```

### 4.2 Team 生命周期

**源码**: `src/tools/TeamCreateTool/TeamCreateTool.ts`

```
TeamCreate → 创建 team config JSON + task list directory
  → spawn teammates (InProcess/Remote)
    → teammates 通过 SendMessage 通信
    → 任务通过 TaskCreate/TaskUpdate 跟踪
  → TeamDelete → shutdown teammates → 清理文件
```

### 4.3 Swarm 权限同步

**源码**: `src/hooks/toolPermission/handlers/swarmWorkerHandler.ts`

Worker Agent 的权限处理：
1. 先尝试分类器自动批准（bash 命令）
2. 未通过则转发给 Team Lead 通过 mailbox 机制
3. 注册回调等待 Lead 响应

**对 Clef Server 的启发**：
- Team 数据结构对齐 Clef 设计文档的 session 概念
- `subscriptions` 字段可用于 Clef Server 的事件通知
- 权限同步在 Clef Server 中不需要（无用户交互），但 Leader → Worker 的任务分发模式值得借鉴

### 4.4 Agent Memory 系统

**源码**: `src/tools/AgentTool/agentMemory.ts` + `agentMemorySnapshot.ts`

Agent Memory 的三层架构：

```
Agent Memory
├── Local Memory    — ~/.claude/agents/<type>/memory/*.md  （Agent 自身知识）
├── Project Memory  — <project>/.claude/agent-memory-snapshots/<type>/  （项目快照）
└── Team Memory     — <memoryBase>/team/MEMORY.md  （团队共享知识）
```

Memory 同步机制：
- `initializeFromSnapshot()` — 首次从项目快照初始化
- `replaceFromSnapshot()` — 用快照替换本地 memory
- `getSnapshotDriftAction()` — 检测快照与本地 memory 的差异

**对 Clef Server 的启发**：
- Clef Server 的 theory-* 技能可以 modeled 为 Agent Memory
- 项目快照机制可用于在 Server 和 Claude Code Skill 之间共享乐理知识
- Team Memory 可以用于 Agent 间共享中间状态（如 plan.json 的变更历史）

---

## 5. 上下文与系统提示词管理

### 5.1 系统提示词构建

**源码**: `src/utils/systemPrompt.ts` + `runAgent.ts`

```typescript
// 系统提示词分层构建
buildEffectiveSystemPrompt({
  mainThreadAgentDefinition,
  toolUseContext,
  customSystemPrompt,      // 完全替换
  appendSystemPrompt,      // 追加到末尾
})
```

层级结构：
1. **Base System Prompt** — Claude Code 核心指令（工具使用、输出格式等）
2. **CLAUDE.md** — 项目级指令（从 `.claude/` 和项目根加载）
3. **Agent System Prompt** — Agent 特定指令（from markdown body）
4. **Nested Memory** — Agent Memory 注入
5. **Skills** — Agent 引用的技能内容
6. **Session Context** — 当前会话状态

**对 Clef Server 的启发**：
- 设计文档的 Agent prompt 加载可以直接复用此分层模式
- 层级：base music theory → agent-specific prompt → plan.json context → current score.abc
- `appendSystemPrompt` 可以用于注入 session 状态信息

### 5.2 上下文压缩

**源码**: `src/services/compact/` + `src/utils/contextAnalysis.ts`

Claude Code 使用自动 compaction（上下文压缩）管理对话长度。关键机制：

- **Compact Boundary** — 在对话历史中标记压缩边界，边界之前的消息被压缩为摘要
- **Micro Compact** — API 层面的微型压缩（`apiMicrocompact.ts`）
- **Context Window Upgrade Check** — 根据模型自动调整上下文窗口大小

**对 Clef Server 的启发**：
- Clef Server **不需要**自动 compaction（设计文档明确指出"上下文就是文件传递"）
- 但可以借鉴 compact boundary 的思路：每次迭代只保留 `plan.json + score.abc + last_review`，丢弃更早的 LLM 消息历史

---

## 6. Agent SDK 导出模式

### 6.1 Tool 注册 API

**源码**: `src/entrypoints/agentSdkTypes.ts`

```typescript
// SDK 的工具定义 API（MCP 兼容）
export function tool<Schema extends AnyZodRawShape>(
  name: string,
  description: string,
  inputSchema: Schema,        // Zod schema
  handler: (args: InferShape<Schema>, extra: unknown) => Promise<CallToolResult>,
  extras?: {
    annotations?: ToolAnnotations
    searchHint?: string
    alwaysLoad?: boolean
  },
): SdkMcpToolDefinition<Schema>
```

**对 Clef Server 的启发**：
- 使用类似的 `@tool` 装饰器模式注册 Python 工具函数
- handler 签名：`async (args) -> ToolResult`（输入校验 + 输出格式化）
- LiteLLM 的 tool schema 使用 OpenAI 格式，与 MCP 的 JSON Schema 可以直接映射

### 6.2 Query API

```typescript
export function query(params: {
  prompt: string | AsyncIterable<SDKUserMessage>,
  options?: Options,
}): Query
```

Query 对象是异步迭代器，yield 每个 LLM 响应事件（text、tool_use 等）。

**对 Clef Server 的启发**：
- Clef Server 的 Agent 运行时可以设计为类似模式：`async def call(agent, messages, tools) -> AgentResponse`
- 不需要流式迭代（单次调用），但 `AgentResponse` 结构应对齐：`content + tool_calls`

---

## 7. 关键设计模式总结

### 7.1 可直接借鉴的模式

| 模式 | Claude Code 实现 | Clef Server 对应 |
|------|-----------------|-----------------|
| 声明式 Agent 定义 | Markdown frontmatter | 复用现有 8 个 .md 文件 |
| 惰性系统提示词 | `getSystemPrompt()` 函数 | Python 闭包 / callable |
| 工具白名单过滤 | `tools`/`disallowedTools` | `AGENT_TOOLS` 映射 |
| 文件传递上下文 | Agent 读写文件 | `session_dir/` 下的 JSON/ABC |
| 并行子 Agent | Fork 模式 | Step 1b 并行 + DAG 调度 |
| 模型按 Agent 分配 | `model` frontmatter | `agents.yaml` 配置 |
| 会话状态机 | Task status enum | `CREATED → PLANNING → ...` |
| Agent Memory | `.claude/agents/<type>/memory/` | theory-*.md 文件 |

### 7.2 Clef Server 应简化的部分

| Claude Code 特性 | 为何简化 |
|-----------------|---------|
| Prompt Cache 优化 | Clef Server 每步独立调用，cache 收益有限 |
| 自动 Compaction | 上下文 = 文件传递，无需压缩 |
| 权限系统（canUseTool） | 服务端内部调用，无用户交互 |
| Hook 系统（Pre/PostToolUse） | 直接调用 Python 函数，不需要拦截 |
| Worktree 隔离 | Session 目录天然隔离 |
| Team Memory 同步 | 文件系统共享即可 |

### 7.3 Clef Server 应增强的部分

| 方向 | 建议 |
|------|------|
| LLM 提供商抽象 | 使用 LiteLLM（统一 100+ 提供商） |
| Tool 执行超时 | Python subprocess 需要 timeout + retry |
| 并行安全性标记 | Tool 增加 `isConcurrencySafe` 属性 |
| 会话持久化 | JSON 状态文件 + 文件系统快照 |
| 进度通知 | WebSocket 或 SSE 推送到 AstrBot |
| 错误恢复 | 单步重试 + session 状态回滚 |

---

## 8. 源码文件索引

### 核心参考文件

| 文件路径 | 内容 | 参考价值 |
|---------|------|---------|
| `src/tools/AgentTool/runAgent.ts` | Agent 执行引擎 | ★★★★★ |
| `src/tools/AgentTool/loadAgentsDir.ts` | Agent 定义解析 | ★★★★★ |
| `src/tools/AgentTool/forkSubagent.ts` | 并行子 Agent | ★★★★ |
| `src/tools/AgentTool/builtInAgents.ts` | 内置 Agent 注册 | ★★★★ |
| `src/tools/AgentTool/constants.ts` | Agent 常量 | ★★★ |
| `src/Tool.ts` | Tool 定义抽象 | ★★★★ |
| `src/services/tools/toolExecution.ts` | Tool 执行流程 | ★★★ |
| `src/utils/swarm/teamHelpers.ts` | Team 数据结构 | ★★★★ |
| `src/tools/TeamCreateTool/TeamCreateTool.ts` | Team 创建流程 | ★★★ |
| `src/tasks/InProcessTeammateTask/` | Teammate 生命周期 | ★★★ |
| `src/tools/AgentTool/agentMemory.ts` | Agent Memory 系统 | ★★★ |
| `src/tools/AgentTool/agentMemorySnapshot.ts` | Memory 快照同步 | ★★★ |
| `src/utils/swarm/spawnInProcess.ts` | 进程内 Teammate 生成 | ★★★ |
| `src/hooks/toolPermission/handlers/swarmWorkerHandler.ts` | Swarm 权限处理 | ★★ |
| `src/entrypoints/agentSdkTypes.ts` | SDK API 导出 | ★★★ |
| `src/tools/AgentTool/built-in/exploreAgent.ts` | Explore Agent 示例 | ★★★★ |
| `src/tools/AgentTool/built-in/generalPurposeAgent.ts` | 通用 Agent 示例 | ★★★ |
| `src/tools/AgentTool/resumeAgent.ts` | Agent 恢复/继续 | ★★ |
| `src/tools/AgentTool/prompt.ts` | Agent Tool 的 prompt 模板 | ★★★ |
