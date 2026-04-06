# Clef Server + AstrBot 设计文档

> 定位：作为现有 Claude Code Skill 模式（`/clef-compose`）的**渐进增强**，而非替代。

## 背景

Clef 当前的多 Agent 作曲系统深度绑定 Claude Code 的 Skill/Agent 框架。用户只能在 Claude Code CLI 中触发作曲，限制了使用场景。

本设计将 Clef 的作曲能力封装为独立可部署的微服务，通过 AstrBot 接入多 IM 平台（Telegram/QQ/Slack 等），实现"随时随地触发作曲"的使用体验。

### 核心原则

- **共存，不替代** — Claude Code Skill 模式继续作为本地开发/精细控制的入口，AstrBot 模式面向 casual 使用场景
- **共享核心资产** — 两种模式复用同一套 Agent prompt、Python 工具链、乐理参考
- **架构解耦** — AstrBot 和 Clef Server 通过 REST API 解耦，各自可独立替换

## 整体架构

```
┌─────────────────────────────────────────────┐
│               用户触达层                      │
│  Telegram / QQ / Slack / Discord / WebUI     │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│            AstrBot (Python)                  │
│  · IM 消息适配（10+ 平台）                    │
│  · LLM 提供商路由（OpenAI/Claude/Gemini...）  │
│  · 对话会话管理 + 上下文压缩                   │
│  · 人格设定 / 指令注入                        │
│  · Clef 插件（意图解析 → 调用 Clef API）       │
└──────────────────┬──────────────────────────┘
                   ↓ HTTP (REST API)
┌─────────────────────────────────────────────┐
│           Clef Server (Python)               │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  API Layer (FastAPI)               │    │
│  │  POST /compose  GET /status/result │    │
│  └──────────────┬──────────────────────┘    │
│                 ↓                            │
│  ┌─────────────────────────────────────┐    │
│  │  DAG Executor                       │    │
│  │  固定 6 步工作流 · 依赖调度 · 重试   │    │
│  └──────────────┬──────────────────────┘    │
│          ┌──────┼──────┐                    │
│          ↓      ↓      ↓                    │
│     ┌────────┐ ┌────────┐ ┌────────┐        │
│     │Composer│ │Harmonist│ │Rhythmist│       │
│     │(md+LLM)│ │(md+LLM) │ │(md+LLM) │       │
│     └────┬───┘ └───┬────┘ └───┬────┘        │
│          └─────┬───┘──────────┘              │
│                ↓                             │
│     ┌──────────────────────┐                │
│     │ Tool Layer           │                │
│     │ abc_to_midi / validate│                │
│     │ merge / inject / snap │                │
│     └──────────────────────┘                │
│                                             │
└─────────────────────────────────────────────┘
```

## DAG Executor 与 Agent 运行时

### 工作流步骤

```
Session (作曲任务)
│
├─ Step 0: Parse          ← 用户意图 → plan.json
│     Agent: Leader (解析)
│
├─ Step 1a: Plan          ← plan.json 生成/完善
│     Agent: Leader
│
├─ Step 1b: Sample        ← 方向小样 (4-8小节)
│     Agent: Composer + Harmonist + Rhythmist (并行)
│     ⚡ 用户确认检查点
│
├─ Step 2a: Full          ← 完整创作
│     Agent: Composer + Harmonist + Rhythmist
│     顺序由 plan.generation_order 控制
│
├─ Step 2b: Iterate       ← 最多 3 轮
│     循环: Reviewer (打分) → [Composer|Harmonist|Rhythmist] (修正)
│           → Revision (格式) → validate (检查)
│     终止: 全部 PASS 或达上限
│
└─ Step 3: Express        ← 表现力注入
      Agent: Orchestrator → inject_expression.py → 最终 MIDI
```

### Agent 定义

```python
@dataclass
class AgentDef:
    name: str                          # "clef-composer"
    prompt_md: Path                    # 复用现有 .md 文件
    model: str                         # LiteLLM model_name（可按 Agent 配置不同模型）
    tools: list[str]                   # 允许的工具名列表（白名单）
    disallowed_tools: list[str]        # 禁止的工具名列表（黑名单，与 tools 互斥）
    temperature: float                 # 创作类高(0.8), 评审类低(0.3)
    max_turns: int = 5                 # 单次调用最大 tool-use 轮次
    is_readonly: bool = False          # 只读 Agent（不修改任何文件）
    omit_context: bool = False         # 跳过全局上下文注入（如 Reviewer 不需要 plan.json）
    skills: list[str] = field(default_factory=list)  # 引用的 theory-* 子技能

@dataclass
class ToolDef:
    name: str              # "abc_to_midi"
    handler: Callable      # 包装现有 Python 脚本
    schema: dict           # 输入输出 JSON Schema
    timeout: int = 60      # 超时秒数（Python subprocess 可能挂起）
    retry: int = 0         # 失败重试次数
    is_concurrent_safe: bool = False   # DAG Executor 判断是否可与其他 Tool 并行
    is_readonly: bool = False         # 是否只读（不修改文件）
```

### 与 Claude Code 的关键差异

- **不需要通用 REPL 循环** — 每个 Agent 是单次调用（prompt + 上下文 → 输出）
- **不需要自动 compaction** — 上下文就是 plan.json + 当前 score.abc + 上轮 review
- **每步输入输出都是文件**（JSON/ABC），不是流式对话
- **不需要权限系统** — 服务端内部调用，无用户交互确认环节
- **不需要 Hook 系统** — 直接调用 Python 函数，不需要 Pre/PostToolUse 拦截

### Agent Prompt 分层构建（参考 Claude Code buildEffectiveSystemPrompt）

```python
def build_system_prompt(agent: AgentDef, session: Session) -> str:
    """分层构建 Agent 系统提示词，每层可独立替换或跳过"""
    layers = []

    # Layer 1: Agent 专属 prompt（从 .md 文件加载，复用现有 Agent prompt）
    layers.append(agent.prompt_md.read_text(encoding="utf-8"))

    # Layer 2: Theory 子技能注入（从独立 .md 文件加载）
    for skill_name in agent.skills:
        skill_path = AGENTS_DIR / f"../skills/{skill_name}.md"
        if skill_path.exists():
            layers.append(skill_path.read_text(encoding="utf-8"))

    # Layer 3: 会话上下文（plan.json 摘要 + 当前 score.abc）
    if not agent.omit_context:
        layers.append(format_session_context(session))

    return "\n\n".join(layers)
```

> **注意**：现有 theory-* 是 Claude Code slash skills（内联 prompt），Clef Server 无法直接调用。
> 需要先将 6 个 theory 子技能导出为独立 `.md` 文件到 `.claude/skills/theory-*.md`。
> 这与 Claude Code 的 `skills` frontmatter 注入模式一致。

## LLM 提供商抽象层（LiteLLM）

使用 [LiteLLM](https://github.com/BerriAI/litellm) Router 统一 100+ LLM 提供商，无需手写适配器。

```python
from litellm import Router

router = Router(
    model_list=[
        {"model_name": "claude-sonnet", "litellm_params": {"model": "anthropic/claude-sonnet-4-20250514", "api_key": "..."}},
        {"model_name": "gpt-4o",       "litellm_params": {"model": "openai/gpt-4o", "api_key": "..."}},
        {"model_name": "deepseek",     "litellm_params": {"model": "deepseek/deepseek-chat", "api_key": "..."}},
    ],
    fallbacks=[{"claude-sonnet": ["gpt-4o", "deepseek"]}],
    num_retries=2,
    timeout=120,
)

# 统一调用接口，返回 OpenAI 格式
response = await router.acompletion(
    model="claude-sonnet",
    messages=messages,
    tools=tools,        # OpenAI tool 格式，LiteLLM 自动转换
    temperature=0.7,
)
# tool_calls 在 response.choices[0].message.tool_calls
```

### 按 Agent 配置模型

```yaml
# config/agents.yaml
agents:
  clef-composer:
    model: anthropic/claude-sonnet-4-20250514
    temperature: 0.8
  clef-reviewer:
    model: openai/gpt-4o
    temperature: 0.3
  clef-revision:
    model: deepseek/deepseek-chat
    temperature: 0.2
  clef-orchestrator:
    model: anthropic/claude-sonnet-4-20250514
    temperature: 0.5
```

Clef Server **自带** LLM 调用能力，不依赖 AstrBot 转发。AstrBot 的 LLM 路由只用于对话理解（意图识别、参数提取）。

### 为什么选 LiteLLM 而非自写 Protocol

| 维度 | 自写 Protocol | LiteLLM |
|------|--------------|---------|
| 代码量 | ~200 行（3 个适配器） | ~10 行配置 |
| 提供商数 | 3 个 | 100+ |
| Tool Schema | 手动转换 OpenAI/Anthropic 格式 | 自动转换 |
| Fallback/重试 | 需自行实现 | 内置 |
| 成本追踪 | 需自行实现 | 内置 callback |
| 异步支持 | 需自行实现 | 原生 `acompletion()` |

## AstrBot Clef 插件

### 交互流程

```
用户: "帮我写一首C大调的爵士钢琴曲，4/4拍，32小节"
  → 意图识别 → 作曲请求
  → 参数提取 → {key: "C", genre: "jazz", time_sig: "4/4", bars: 32}
  → POST /compose → 返回 session_id

用户: "写好了吗？"
  → GET /status/{session_id}
  → 返回进度: "Step 2b 迭代中 (2/3轮)"

用户: "发给我"
  → GET /result/{session_id}
  → 发送 MIDI 文件 + ABC 文本预览
```

### 插件核心

```python
@command("作曲")
async def compose_cmd(msg, args):
    params = await llm.extract_compose_params(args)
    session = await clef_api.post("/compose", params)
    await msg.reply(f"作曲任务已创建 #{session.id}")

@command("作曲状态")
async def status_cmd(msg, session_id):
    status = await clef_api.get(f"/status/{session_id}")
    await msg.reply(format_status(status))

@command("获取乐谱")
async def result_cmd(msg, session_id):
    result = await clef_api.get(f"/result/{session_id}")
    await msg.reply(file=result.midi)
    await msg.reply(text=result.abc_preview)
```

约 250 行 Python，职责单一：意图识别 + SSE 进度监听 + API 转发 + 文件传输。

## Tool Layer

现有 `clef_tools.py` 子命令零改动封装为 Agent 可调用的 tools：

```python
TOOLS = {
    "abc_to_midi": ToolDef(
        handler=wrap_subprocess(["python", "scripts/abc_to_midi.py"]),
        input_schema={"input_abc": "path", "output_mid": "path"},
        is_concurrent_safe=False, is_readonly=True,
    ),
    "validate_abc": ToolDef(
        handler=wrap_subprocess(["python", "scripts/validate_abc.py"]),
        input_schema={"abc_file": "path", "plan_file": "path", "output": "path"},
        is_concurrent_safe=True, is_readonly=True,
    ),
    "abc_lint": ToolDef(
        handler=wrap_function(abc_lint.lint),  # 轻量 ABC 格式检查，零外部依赖
        input_schema={"abc_content": "str", "plan_path": "path?"},
        is_concurrent_safe=True, is_readonly=True,
    ),
    "merge_abc": ToolDef(
        handler=wrap_subprocess(["python", "scripts/merge_abc.py"]),
        is_concurrent_safe=False, is_readonly=False,
    ),
    "inject_expression": ToolDef(
        handler=wrap_subprocess(["python", "scripts/inject_expression.py"]),
        is_concurrent_safe=False, is_readonly=False,
    ),
    "snapshot": ToolDef(
        handler=wrap_subprocess(["python", "scripts/clef_tools.py", "snapshot"]),
        is_concurrent_safe=True, is_readonly=False,
    ),
    "read_file": ToolDef(handler=read_file, is_concurrent_safe=True, is_readonly=True),
    "write_file": ToolDef(handler=write_file, is_concurrent_safe=False, is_readonly=False),
}

# 每个 Agent 只暴露需要的工具子集
AGENT_TOOLS = {
    "clef-composer":    ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-reviewer":    ["read_file", "validate_abc", "abc_lint"],
    "clef-revision":    ["read_file", "write_file"],
    "clef-orchestrator":["read_file", "write_file", "abc_to_midi", "inject_expression"],
    "clef-leader":      ["read_file", "write_file", "merge_abc", "snapshot", "validate_abc"],
}
```

> `abc_lint` 是轻量的 ABC 格式检查（19KB，纯 stdlib，零外部依赖），可在创作阶段即时自检，
> 不必等到 Reviewer 阶段才发现格式问题。

## 会话状态与 API

### 文件结构

```
sessions/
└─ {session_id}/
   ├─ meta.json             # 状态机元数据
   ├─ plan.json
   ├─ score.abc
   ├─ review_report.json
   ├─ expression_plan.json
   ├─ agent_logs/           # 每步 Agent 的 LLM 请求/响应摘要（调试 + 成本追踪）
   │   ├─ step1b_composer.json
   │   ├─ step1b_harmonist.json
   │   ├─ step2b_r1_reviewer.json
   │   └─ step3_orchestrator.json
   ├─ output/
   │   ├─ final.mid
   │   ├─ sample.mid
   │   └─ solos/
   └─ snapshots/
       ├─ step1_sample.abc
       ├─ step2a_full.abc
       └─ step2b_r1.abc
```

agent_logs 只存摘要（token 数、耗时、tool 调用列表），不存完整 messages，避免磁盘膨胀：

```python
@dataclass
class AgentLogEntry:
    step: str              # "1b", "2a", "2b_r1"
    agent: str             # "clef-composer"
    model: str             # "anthropic/claude-sonnet-4"
    input_tokens: int
    output_tokens: int
    latency_ms: int
    tool_calls: list[str]  # ["validate_abc", "write_file"]
    cost_usd: float
```

### 状态机

```
CREATED → PLANNING → SAMPLING → AWAITING_CONFIRM
                                     ↓ (用户确认)
                               COMPOSING → ITERATING → EXPRESSING → DONE
                                              │
                                              ├→ ITERATING_AGENT_RUNNING   # Agent 正在执行
                                              ├→ ITERATING_REVIEWING       # Reviewer 打分中
                                              ├→ ITERATING_WAITING_RETRY   # 等待下次迭代
                                              └→ FAILED (超限/异常)
```

细化 `ITERATING` 状态让 `GET /status` 和 SSE 能返回精确进度。

### API 端点

```python
POST   /compose              # 创建任务，返回 session_id
GET    /status/{id}          # 当前状态 + 进度描述（轮询）
GET    /status/{id}/stream   # SSE 实时进度推送（推荐 AstrBot 使用）
GET    /result/{id}          # 产出文件列表（MIDI/ABC/报告）
POST   /confirm/{id}         # Step 1b 用户确认方向小样
POST   /cancel/{id}          # 取消任务
GET    /sessions             # 历史任务列表
```

SSE 事件格式（`GET /status/{id}/stream`）：

```python
# FastAPI StreamingResponse
async def status_stream(session_id: str):
    async for event in session_events(session_id):
        yield f"data: {event.model_dump_json()}\n\n"

# event 示例：
# {"type": "step_start", "step": "2b", "round": 1, "agent": "clef-reviewer"}
# {"type": "agent_thinking", "agent": "clef-reviewer", "partial": "正在分析..."}
# {"type": "tool_call", "agent": "clef-composer", "tool": "validate_abc", "args": {...}}
# {"type": "step_complete", "step": "2b", "round": 1, "result": "PASS"}
# {"type": "done", "files": ["output/final.mid", "output/final.abc"]}
```

## 模块估算

| 模块 | 行数 | 说明 |
|------|------|------|
| LLM Provider（LiteLLM） | ~30 | Router 配置 + model 映射（原 ~200 行适配器已省去） |
| Agent 运行时 | ~350 | prompt 分层加载 + 单次调用 + 上下文构建 |
| DAG Executor | ~400 | 6 步工作流 + 依赖调度 + 重试 + 检查点 |
| Tool Layer | ~180 | subprocess 封装 + 超时/重试 + abc_lint |
| API Layer (FastAPI) | ~250 | 7 个端点 + SSE 进度推送 |
| Session 管理 | ~180 | 细化状态机 + agent_logs + 文件操作 |
| AstrBot 插件 | ~250 | 意图识别 + SSE 监听 + API 转发 |
| **合计** | **~1640** | |

## 不需要重写的

- 8 个 Agent markdown prompt（`.claude/agents/*.md`）
- 所有 Python 工具链（`scripts/`）
- Godot 插件（`addons/clef/`）
- 现有 Claude Code Skill 模式（`/clef-compose`）

## 需要前置导出的

- 6 个 theory 子技能（`theory-abc/harmony/melody/orchestration/rhythm/structure`）— 从 Claude Code slash skills 导出为独立 `.md` 文件，供 Clef Server 的 `build_system_prompt()` 加载。这与 Claude Code 的 `skills` frontmatter 注入模式一致。

## 两种模式对比

| 维度 | Claude Code Skill | Clef Server + AstrBot |
|------|-------------------|----------------------|
| 触发方式 | CLI `/clef-compose` | IM 消息（任意平台） |
| 用户交互 | 终端内对话 | IM 聊天 |
| 适用场景 | 本地开发、精细控制 | 随时随地、快速作曲 |
| LLM 模型 | 绑定 Claude Code 设置 | 可按 Agent 独立配置 |
| 上下文管理 | Claude Code 自动处理 | 文件传递，手动管理 |
| 可观测性 | 终端输出 | API + WebUI |
| 核心资产 | 共享（Agent prompt / 工具链 / 乐理） | 共享 |

## 参考

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — 28K star Agentic IM 聊天框架
- [LiteLLM](https://github.com/BerriAI/litellm) — 统一 LLM Provider 抽象层
- [Claude Code 源码](https://github.com/anthropics/claude-code) — Agent 编排模式参考（`src/tools/AgentTool/`）
- [Claude Code 源码研究报告](./2026-04-05-claude-code-source-research.md) — 设计调整依据
