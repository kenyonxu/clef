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
    name: str              # "clef-composer"
    prompt_md: Path        # 复用现有 .md 文件
    model: str             # 可按 Agent 配置不同模型
    tools: list[ToolDef]   # 该 Agent 可用的工具子集
    temperature: float     # 创作类高(0.8), 评审类低(0.3)

@dataclass
class ToolDef:
    name: str              # "abc_to_midi"
    handler: Callable      # 包装现有 Python 脚本
    schema: dict           # 输入输出 JSON Schema
```

### 与 Claude Code 的关键差异

- **不需要通用 REPL 循环** — 每个 Agent 是单次调用（prompt + 上下文 → 输出）
- **不需要自动 compaction** — 上下文就是 plan.json + 当前 score.abc + 上轮 review
- **每步输入输出都是文件**（JSON/ABC），不是流式对话

## LLM 提供商抽象层

```python
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse: ...

class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] | None  # name, arguments, id

# 适配器
class AnthropicProvider(LLMProvider): ...   # Claude
class OpenAIProvider(LLMProvider): ...       # GPT / DeepSeek / Moonshot
class GeminiProvider(LLMProvider): ...       # Gemini
```

### 按 Agent 配置模型

```yaml
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

约 200-300 行 Python，职责单一：意图识别 + API 转发 + 文件传输。

## Tool Layer

现有 `clef_tools.py` 子命令零改动封装为 Agent 可调用的 tools：

```python
TOOLS = {
    "abc_to_midi": ToolDef(
        handler=wrap_subprocess(["python", "scripts/abc_to_midi.py"]),
        input_schema={"input_abc": "path", "output_mid": "path"},
    ),
    "validate_abc": ToolDef(
        handler=wrap_subprocess(["python", "scripts/validate_abc.py"]),
        input_schema={"abc_file": "path", "plan_file": "path", "output": "path"},
    ),
    "merge_abc": ToolDef(
        handler=wrap_subprocess(["python", "scripts/merge_abc.py"]),
    ),
    "inject_expression": ToolDef(
        handler=wrap_subprocess(["python", "scripts/inject_expression.py"]),
    ),
    "snapshot": ToolDef(
        handler=wrap_subprocess(["python", "scripts/clef_tools.py", "snapshot"]),
    ),
    "read_file": ToolDef(handler=read_file, ...),
    "write_file": ToolDef(handler=write_file, ...),
}

# 每个 Agent 只暴露需要的工具子集
AGENT_TOOLS = {
    "clef-composer":    ["read_file", "write_file", "validate_abc"],
    "clef-reviewer":    ["read_file", "validate_abc"],
    "clef-revision":    ["read_file", "write_file"],
    "clef-orchestrator":["read_file", "write_file", "abc_to_midi", "inject_expression"],
    "clef-leader":      ["read_file", "write_file", "merge_abc", "snapshot", "validate_abc"],
}
```

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
   ├─ output/
   │   ├─ final.mid
   │   ├─ sample.mid
   │   └─ solos/
   └─ snapshots/
       ├─ step1_sample.abc
       ├─ step2a_full.abc
       └─ step2b_r1.abc
```

### 状态机

```
CREATED → PLANNING → SAMPLING → AWAITING_CONFIRM
                                     ↓ (用户确认)
                               COMPOSING → ITERATING → EXPRESSING → DONE
                                                  ↓ (失败/超限)
                                              FAILED
```

### API 端点

```python
POST   /compose              # 创建任务，返回 session_id
GET    /status/{id}          # 当前状态 + 进度描述
GET    /result/{id}          # 产出文件列表（MIDI/ABC/报告）
POST   /confirm/{id}         # Step 1b 用户确认方向小样
POST   /cancel/{id}          # 取消任务
GET    /sessions             # 历史任务列表
```

## 模块估算

| 模块 | 行数 | 说明 |
|------|------|------|
| LLM Provider 抽象 | ~200 | 3-4 个适配器 |
| Agent 运行时 | ~300 | prompt 加载 + 单次调用 |
| DAG Executor | ~400 | 6 步工作流 + 重试 + 检查点 |
| Tool Layer | ~150 | subprocess 封装 |
| API Layer (FastAPI) | ~200 | 6 个端点 |
| Session 管理 | ~150 | 状态机 + 文件操作 |
| AstrBot 插件 | ~250 | 意图识别 + API 转发 |
| **合计** | **~1650** | |

## 不需要重写的

- 7 个 Agent markdown prompt（`.claude/agents/*.md`）
- 所有 Python 工具链（`scripts/`）
- 乐理参考（`theory-*.md`）
- Godot 插件（`addons/clef/`）
- 现有 Claude Code Skill 模式（`/clef-compose`）

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
- [Claude Code 源码](https://github.com/anthropics/claude-code) — Agent 编排模式参考（`src/tools/AgentTool/`）
- [Anthropic Agent SDK](https://github.com/anthropics/claude-code-sdk-python) — Python SDK 参考
