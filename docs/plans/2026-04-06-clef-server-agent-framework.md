# Clef Server + AstrBot 设计文档 (Agent Framework 版)

> 基于 [原始设计文档](2026-04-02-clef-server-astrbot-design.md) 的修订版。
> 核心变化：用 Microsoft Agent Framework 替代自建 DAG Executor + Agent 运行时 + LiteLLM。

## 与原设计的关键差异

| 模块 | 原设计（自建） | 本版本（Agent Framework） | 变化 |
|------|:---:|:---:|------|
| DAG Executor | ~400 行手写工作流引擎 | AF 图工作流 ~100 行 | -75% |
| Agent 运行时 | ~350 行 prompt+调用+上下文 | AF Agent 类 ~150 行 | -57% |
| LLM Provider | LiteLLM Router ~30 行 | AF 内置 Provider ~20 行 | 持平 |
| Session/检查点 | ~180 行手写状态机 | AF Checkpoint ~80 行 | -56% |
| Tool Layer | ~180 行 | ~180 行（不变） | 0% |
| API Layer | ~250 行 | ~250 行（不变） | 0% |
| AstrBot 插件 | ~250 行 | ~250 行（不变） | 0% |
| **合计** | **~1640 行** | **~1030 行** | **-37%** |

**额外获得**（原设计未规划）：Superstep 状态隔离、OpenTelemetry 可观测性、DevUI 调试工具、Human-in-the-loop、YAML 声明式工作流。

---

## 背景

> 以下章节与原设计完全相同，保留供参考。

Clef 当前的多 Agent 作曲系统深度绑定 Claude Code 的 Skill/Agent 框架。用户只能在 Claude Code CLI 中触发作曲，限制了使用场景。

本设计将 Clef 的作曲能力封装为独立可部署的微服务，通过 AstrBot 接入多 IM 平台（Telegram/QQ/Slack 等），实现"随时随地触发作曲"的使用体验。

### 核心原则

- **共存，不替代** — Claude Code Skill 模式继续作为本地开发/精细控制的入口，AstrBot 模式面向 casual 使用场景
- **共享核心资产** — 两种模式复用同一套 Agent prompt、Python 工具链、乐理参考
- **架构解耦** — AstrBot 和 Clef Server 通过 REST API 解耦，各自可独立替换

---

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
│  │  Agent Framework Workflow           │    │
│  │  ┌─────────────────────────────┐    │    │
│  │  │ Graph Workflow Engine       │    │    │
│  │  │ Executors + Edges + State  │    │    │
│  │  │ Superstep · Checkpoint     │    │    │
│  │  └─────────────────────────────┘    │    │
│  │  ┌──────────┬──────────┬─────────┐  │    │
│  │  │Composer  │Harmonist │Rhythmist│  │    │
│  │  │(AF Agent)│(AF Agent)│(AF Agnt)│  │    │
│  │  └──────────┴──────────┴─────────┘  │    │
│  │  ┌──────────┬──────────┬─────────┐  │    │
│  │  │Reviewer  │Revision  │Leader   │  │    │
│  │  │(AF Agent)│(AF Agent)│(AF Agnt)│  │    │
│  │  └──────────┴──────────┴─────────┘  │    │
│  │  ┌─────────────────────────────┐    │    │
│  │  │ Provider Layer              │    │    │
│  │  │ Anthropic · OpenAI-compat   │    │    │
│  │  │ DeepSeek · GLM · Ollama     │    │    │
│  │  └─────────────────────────────┘    │    │
│  └──────────────┬──────────────────────┘    │
│                 ↓                            │
│  ┌─────────────────────────────────────┐    │
│  │ Tool Layer (不变)                    │    │
│  │ abc_to_midi / validate / merge      │    │
│  │ inject / snapshot / abc_lint        │    │
│  └─────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Agent Framework Workflow（替代 DAG Executor）

### 依赖

```bash
pip install agent-framework agent-framework-openai agent-framework-anthropic agent-framework-ollama
```

仅需 3 个包：`core`（工作流引擎 + Agent 类）、`openai`（OpenAI 兼容端点，覆盖 DeepSeek/GLM）、`anthropic`（Claude）。

### 工作流定义

使用 AF 图工作流表达 Clef 的 6 步作曲流程：

```python
from agent_framework import WorkflowBuilder, EdgeCondition
from agent_framework.openai import OpenAIChatCompletionClient

def build_compose_workflow(providers: dict[str, BaseChatClient]) -> Workflow:
    """构建 Clef 作曲工作流图"""

    # === 创建 Agent（AF Agent 类，每个 Agent 独立配置模型） ===
    composer = Agent(
        name="clef-composer",
        instructions=load_prompt("clef-composer"),     # 从 .md 加载
        client=providers["deepseek"],
        tools=get_tools("clef-composer"),               # 白名单工具子集
        temperature=0.8,
    )
    harmonist = Agent(
        name="clef-harmonist",
        instructions=load_prompt("clef-harmonist"),
        client=providers["deepseek"],
        tools=get_tools("clef-harmonist"),
        temperature=0.8,
    )
    rhythmist = Agent(
        name="clef-rhythmist",
        instructions=load_prompt("clef-rhythmist"),
        client=providers["deepseek"],
        tools=get_tools("clef-rhythmist"),
        temperature=0.7,
    )
    reviewer = Agent(
        name="clef-reviewer",
        instructions=load_prompt("clef-reviewer"),
        client=providers["claude"],
        tools=get_tools("clef-reviewer"),               # 只读工具
        temperature=0.3,
    )
    revision = Agent(
        name="clef-revision",
        instructions=load_prompt("clef-revision"),
        client=providers["deepseek"],
        tools=get_tools("clef-revision"),
        temperature=0.2,
    )
    orchestrator = Agent(
        name="clef-orchestrator",
        instructions=load_prompt("clef-orchestrator"),
        client=providers["claude"],
        tools=get_tools("clef-orchestrator"),
        temperature=0.5,
    )

    # === 功能型 Executor（确定性 Python 函数，不走 LLM） ===
    parse_executor = FunctionExecutor(parse_user_intent)     # Step 0
    plan_executor = FunctionExecutor(generate_plan)          # Step 1a
    merge_executor = FunctionExecutor(merge_voice_fragments) # 合并多声部
    validate_executor = FunctionExecutor(run_validation)     # 验证检查
    inject_executor = FunctionExecutor(inject_expression)    # Step 3

    # === 构建工作流图 ===
    workflow = (
        WorkflowBuilder()
        # Step 0: 解析用户意图
        .add_executor("parse", parse_executor)

        # Step 1a: 生成 plan.json
        .add_executor("plan", plan_executor)

        # Step 1b: 方向小样（并行）
        .add_executor("sample_composer", composer)
        .add_executor("sample_harmonist", harmonist)
        .add_executor("sample_rhythmist", rhythmist)

        # Step 2a: 完整创作（并行）
        .add_executor("full_composer", composer)
        .add_executor("full_harmonist", harmonist)
        .add_executor("full_rhythmist", rhythmist)

        # Step 2b: 迭代
        .add_executor("review", reviewer)
        .add_executor("revise", revision)
        .add_executor("merge", merge_executor)
        .add_executor("validate", validate_executor)

        # Step 3: 表现力注入
        .add_executor("express", orchestrator)

        # --- 边定义 ---
        .add_edge("parse", "plan")
        .add_edge("plan", "sample_composer")
        .add_edge("plan", "sample_harmonist")
        .add_edge("plan", "sample_rhythmist")

        # 小样合并 + 用户确认
        .add_edge_group(FanOutEdgeGroup(
            ["sample_composer", "sample_harmonist", "sample_rhythmist"],
            "merge_sample"
        ))
        .add_executor("merge_sample", merge_executor)
        .add_edge("merge_sample", "full_composer")
        .add_edge("merge_sample", "full_harmonist")
        .add_edge("merge_sample", "full_rhythmist")

        # 完整合并 + 进入迭代
        .add_edge_group(FanOutEdgeGroup(
            ["full_composer", "full_harmonist", "full_rhythmist"],
            "merge_full"
        ))
        .add_executor("merge_full", merge_executor)
        .add_edge("merge_full", "review")

        # 迭代循环（核心：条件边 + 回边）
        .add_edge("review", "revise",
                  condition=needs_revision)      # FAIL 且轮次 < 3
        .add_edge("review", "express",
                  condition=passed_all_checks)    # 全部 PASS
        .add_edge("revise", "validate")           # 修正后重新验证
        .add_edge("validate", "review")           # 验证结果送回评审

        .build()
    )

    return workflow


# === 条件谓词 ===
def needs_revision(ctx: WorkflowContext) -> bool:
    report = ctx.state.get("review_report")
    return not report.get("all_passed", False) and ctx.state.get("iteration_round", 0) < 3

def passed_all_checks(ctx: WorkflowContext) -> bool:
    report = ctx.state.get("review_report")
    return report.get("all_passed", False)
```

### 工作流步骤对照

```
原设计 (DAG Executor)          AF 版本 (Graph Workflow)
─────────────────────          ──────────────────────────
Step 0: Parse                  parse_executor (FunctionExecutor)
Step 1a: Plan                  plan_executor (FunctionExecutor)
Step 1b: Sample                FanOut → [composer, harmonist, rhythmist] → merge_sample
       ⚡ 用户确认               merge_sample → await_human() (AF Human-in-the-loop)
Step 2a: Full                  FanOut → [composer, harmonist, rhythmist] → merge_full
Step 2b: Iterate               review → (条件边) → revise → validate → review (回边)
       终止: PASS 或 3 轮        条件边: needs_revision / passed_all_checks
Step 3: Express                orchestrator Agent + inject_executor
```

### Superstep 状态模型（解决 Issue #9）

AF 的 Superstep 执行模型从根本上解决了并行 Agent 文件冲突问题：

```
Superstep N: [sample_composer, sample_harmonist, sample_rhythmist]
  │
  ├── 每个 Agent 看到相同的状态快照（plan.json 初始状态）
  ├── 每个 Agent 独立写入自己的 pending buffer
  │     composer.pending: {voice_1.abc}
  │     harmonist.pending: {voice_2.abc}
  │     rhythmist.pending: {voice_3.abc, voice_4.abc}
  │
  └── Superstep 边界：pending buffer 统一提交到 committed state
       → merge_executor 在下一个 Superstep 看到完整的 {voice_1, voice_2, voice_3, voice_4}
       → 不存在文件覆盖冲突
```

**对比原设计的 `is_concurrent_safe` 方案**：
- 原方案：标记工具是否并发安全，避免并行调用同一工具（规避冲突）
- AF 方案：根本不存在冲突——每个 Agent 在独立快照上工作，合并由框架在边界统一处理

### Checkpointing（中断恢复）

AF 内置检查点，工作流任意位置可序列化并从断点恢复：

```python
# 保存检查点
checkpoint = workflow.save_checkpoint()

# 从检查点恢复（例如进程重启后）
workflow = WorkflowBuilder.from_checkpoint(checkpoint)
await workflow.resume()
```

对应 Clef 场景：Step 2b 迭代中进程崩溃 → 自动恢复到当前迭代轮次开始前，不丢失已完成的迭代结果。

---

## Agent 定义（基于 AF Agent 类）

### Prompt 分层构建（中间件模式）

使用 AF 中间件在每次 Agent 调用前动态注入上下文，而非预拼接到 `instructions`：

```python
from agent_framework import AgentMiddleware

class ClefContextMiddleware(AgentMiddleware):
    """在 Agent 调用前注入会话上下文（plan.json + score.abc + theory skills）"""

    def __init__(self, agent_config: AgentConfig):
        self.config = agent_config
        self._skill_cache: dict[str, str] = {}  # 缓存已加载的 skill 内容

    async def on_invoke(self, context, call_next):
        # 注入 theory 子技能（Layer 2）
        for skill_name in self.config.skills:
            if skill_name not in self._skill_cache:
                path = SKILLS_DIR / f"theory-{skill_name}" / "SKILL.md"
                self._skill_cache[skill_name] = path.read_text("utf-8")
            context.state["extra_context"] += f"\n\n{self._skill_cache[skill_name]}"

        # 注入会话上下文（Layer 3）
        if not self.config.omit_context:
            session_ctx = format_session_context(context.state)
            context.state["extra_context"] += f"\n\n{session_ctx}"

        return await call_next(context)
```

### Agent 配置（YAML）

```yaml
# config/agents.yaml
agents:
  clef-composer:
    prompt_md: .claude/agents/clef-composer.md
    model: openai-compat          # provider 别名
    model_id: deepseek-chat
    base_url: https://api.deepseek.com/v1
    temperature: 0.8
    skills: [melody, abc]         # 引用的 theory 子技能
    tools: [read_file, write_file, validate_abc, abc_lint]

  clef-harmonist:
    prompt_md: .claude/agents/clef-harmonist.md
    model: openai-compat
    model_id: deepseek-chat
    base_url: https://api.deepseek.com/v1
    temperature: 0.8
    skills: [harmony, abc]
    tools: [read_file, write_file, validate_abc, abc_lint]

  clef-rhythmist:
    prompt_md: .claude/agents/clef-rhythmist.md
    model: openai-compat
    model_id: deepseek-chat
    base_url: https://api.deepseek.com/v1
    temperature: 0.7
    skills: [rhythm, abc]
    tools: [read_file, write_file, validate_abc, abc_lint]

  clef-reviewer:
    prompt_md: .claude/agents/clef-reviewer.md
    model: anthropic
    model_id: claude-sonnet-4-20250514
    temperature: 0.3
    skills: [structure, harmony, melody, rhythm, orchestration]
    omit_context: false
    tools: [read_file, validate_abc, abc_lint]

  clef-revision:
    prompt_md: .claude/agents/clef-revision.md
    model: openai-compat
    model_id: deepseek-chat
    base_url: https://api.deepseek.com/v1
    temperature: 0.2
    skills: [abc]
    tools: [read_file, write_file]

  clef-orchestrator:
    prompt_md: .claude/agents/clef-orchestrator.md
    model: anthropic
    model_id: claude-sonnet-4-20250514
    temperature: 0.5
    skills: [orchestration, abc]
    tools: [read_file, write_file, abc_to_midi, inject_expression]
```

### 工厂函数

```python
def create_agent(name: str, config: dict, providers: dict) -> Agent:
    """从配置创建 AF Agent"""
    client = providers[config["model"]]

    agent = Agent(
        name=name,
        instructions=config["prompt_md"].read_text("utf-8"),  # Layer 1: 固定 prompt
        client=client,
        tools=[TOOLS[t] for t in config["tools"]],
        temperature=config["temperature"],
    )

    # 附加上下文注入中间件
    agent.middleware.add(ClefContextMiddleware(AgentConfig(
        skills=config.get("skills", []),
        omit_context=config.get("omit_context", False),
    )))

    return agent
```

---

## LLM Provider 层（替代 LiteLLM）

### 使用 AF 内置 Provider

Clef 使用的 3 个模型系列均可被 AF 覆盖，无需引入 LiteLLM：

```python
from agent_framework.anthropic import AnthropicClient
from agent_framework.openai import OpenAIChatCompletionClient

def create_providers(config: dict) -> dict[str, BaseChatClient]:
    providers = {}

    # Claude — 原生支持
    if "anthropic" in config:
        providers["anthropic"] = AnthropicClient(
            api_key=config["anthropic"]["api_key"],
            model=config["anthropic"].get("default_model", "claude-sonnet-4-20250514"),
        )

    # OpenAI 兼容端点 — 覆盖 DeepSeek、GLM、千问等
    for alias, cfg in config.get("openai_compat", {}).items():
        providers[alias] = OpenAIChatCompletionClient(
            model=cfg["model_id"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
        )

    return providers
```

### Provider 配置

```yaml
# config/providers.yaml
anthropic:
  api_key: ${ANTHROPIC_API_KEY}
  default_model: claude-sonnet-4-20250514

openai_compat:
  deepseek:
    model_id: deepseek-chat
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
  glm:
    model_id: glm-4
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key: ${GLM_API_KEY}
  # 未来可扩展：千问、Moonshot、SiliconFlow 等
  # qwen:
  #   model_id: qwen-max
  #   base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  #   api_key: ${QWEN_API_KEY}
```

### 为什么不再需要 LiteLLM

| 维度 | 原方案 (LiteLLM) | AF 版本 |
|------|----------------|---------|
| Clef 使用的模型 | DeepSeek, GLM, Claude | 全部覆盖 |
| 提供商数 | 100+ | 8 内置 + 无限 OpenAI 兼容 |
| Tool Schema 转换 | 自动 | AF 自动（`tools` 参数统一格式） |
| Fallback/重试 | 内置 Router | AF 中间件或外层 wrapper |
| 成本追踪 | 内置 callback | OpenTelemetry middleware |
| 额外依赖 | litellm (~2MB) | 无（AF 已包含） |
| Tool-use 循环 | 需自行实现 | AF Agent.run() 内置 |

**如果未来需要 100+ Provider 或更复杂的 Fallback 策略**，可写一个 `LiteLLMChatClient(BaseChatClient)` 适配器，约 50 行。但 MVP 阶段不需要。

---

## Tool Layer（不变）

与原设计完全一致，现有 `clef_tools.py` 子命令零改动封装为 AF `@tool` 格式：

```python
from agent_framework import tool

@tool
async def abc_to_midi(input_abc: str, output_mid: str) -> dict:
    """将 ABC 记谱法转换为 MIDI 文件"""
    result = await run_subprocess(["python", "scripts/abc_to_midi.py", input_abc, "-o", output_mid])
    return {"output": output_mid, "exit_code": result.returncode}

@tool
async def validate_abc(abc_file: str, plan_file: str, output: str) -> dict:
    """验证 ABC 文件（6 项检查：调性/音域/大跳/时值/对齐/重叠）"""
    result = await run_subprocess([
        "python", "scripts/validate_abc.py", abc_file, plan_file, "-o", output
    ])
    report = json.loads(Path(output).read_text())
    return {"report": report, "has_failures": any(r["severity"] == "FAIL" for r in report)}

@tool
async def abc_lint(abc_content: str, plan_path: str | None = None) -> dict:
    """轻量 ABC 格式检查（零外部依赖）"""
    from scripts.abc_lint import lint
    issues = lint(abc_content, plan_path)
    return {"issues": issues, "count": len(issues)}

@tool
async def merge_abc(voice_files: list[str], output: str, options: dict = None) -> dict:
    """合并多声部 ABC 文件"""
    args = ["python", "scripts/merge_abc.py"] + voice_files + ["-o", output]
    result = await run_subprocess(args)
    return {"output": output}

@tool
async def inject_expression(midi_file: str, plan_file: str, output: str) -> dict:
    """注入 CC/弯音表现力到 MIDI"""
    result = await run_subprocess([
        "python", "scripts/inject_expression.py", midi_file, plan_file, output
    ])
    return {"output": output}

@tool
async def snapshot(step: int, output: str, note: str = "") -> dict:
    """备份当前 score.abc + 步骤日志"""
    result = await run_subprocess([
        "python", "scripts/clef_tools.py", "snapshot",
        "--step", str(step), "--output", output, "--note", note,
    ])
    return {"snapshot": output}

@tool
async def read_file(path: str) -> str:
    """读取文件内容"""
    return Path(path).read_text("utf-8")

@tool
async def write_file(path: str, content: str) -> dict:
    """写入文件"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, "utf-8")
    return {"path": path}


# Agent → Tool 映射
AGENT_TOOLS = {
    "clef-composer":    [read_file, write_file, validate_abc, abc_lint],
    "clef-harmonist":   [read_file, write_file, validate_abc, abc_lint],
    "clef-rhythmist":   [read_file, write_file, validate_abc, abc_lint],
    "clef-reviewer":    [read_file, validate_abc, abc_lint],
    "clef-revision":    [read_file, write_file],
    "clef-orchestrator":[read_file, write_file, abc_to_midi, inject_expression],
}
```

---

## 会话状态与 API（简化）

### 状态管理

AF 内置 Checkpoint 和 State 管理，原设计的 `meta.json` 状态机可大幅简化：

```python
# 原设计：手写状态机 (~180 行)
# AF 版本：利用 workflow state + checkpoint (~80 行)

@dataclass
class ComposeSession:
    session_id: str
    workflow: Workflow
    run_handle: WorkflowRunHandle
    created_at: datetime
    status: str = "created"  # created | running | awaiting_confirm | done | failed

    # AF checkpoint 自动处理迭代恢复
    # agent_logs 通过 AF OpenTelemetry 自动采集

sessions: dict[str, ComposeSession] = {}
```

### API 端点（不变）

```python
POST   /compose              # 创建任务，返回 session_id
GET    /status/{id}          # 当前状态 + 进度描述（轮询）
GET    /status/{id}/stream   # SSE 实时进度推送（推荐 AstrBot 使用）
GET    /result/{id}          # 产出文件列表（MIDI/ABC/报告）
POST   /confirm/{id}         # Step 1b 用户确认方向小样
POST   /cancel/{id}          # 取消任务
GET    /sessions             # 历史任务列表
```

### SSE 进度推送（映射 AF WorkflowRunResult 事件）

```python
async def status_stream(session_id: str):
    session = sessions[session_id]
    async for event in session.run_handle.events():
        # 将 AF 工作流事件映射为 SSE
        match event.type:
            case "executor_start":
                yield sse_event("step_start", {
                    "executor": event.executor_name,
                    "agent": event.agent_name,
                })
            case "tool_call":
                yield sse_event("tool_call", {
                    "agent": event.agent_name,
                    "tool": event.tool_name,
                    "args": event.tool_args,
                })
            case "superstep_complete":
                yield sse_event("step_complete", {
                    "superstep": event.superstep_id,
                    "state_keys": list(event.committed_state.keys()),
                })
            case "human_input_required":
                yield sse_event("awaiting_confirm", {
                    "message": "请确认方向小样",
                })
            case "workflow_complete":
                yield sse_event("done", {
                    "files": list_output_files(session_id),
                })
```

### 文件结构（简化）

```
sessions/
└─ {session_id}/
   ├─ state.json             # AF workflow state (自动序列化)
   ├─ checkpoint.json        # AF checkpoint (自动序列化)
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

**变化**：
- `meta.json` → 由 AF `state.json` + `checkpoint.json` 替代
- `agent_logs/` → 由 AF OpenTelemetry 替代（自动采集 token 数、延迟、错误率）
- 手动状态机 → AF 工作流状态推断

---

## 可观测性（OpenTelemetry）

AF 内置 OpenTelemetry 集成，自动采集每个 Agent 的性能指标：

```python
# 启用 OpenTelemetry（~10 行配置）
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

provider = TracerProvider()
provider.add_span_exporter(ConsoleSpanExporter())
trace.set_tracer_provider(provider)

# AF 自动为每个 Agent 调用创建 span，包含：
# - token 数 (input/output)
# - 延迟 (ms)
# - tool_calls 列表
# - 错误信息（如有）
# - 模型名称
```

无需手写 `AgentLogEntry`——OpenTelemetry 自动采集，可导出到：
- 控制台（开发调试）
- Prometheus + Grafana（生产监控）
- Jaeger/Zipkin（分布式追踪）

---

## AstrBot Clef 插件（不变）

与原设计完全一致，~250 行 Python。

---

## 模块估算

| 模块 | 行数 | 说明 |
|------|------|------|
| Provider 配置与工厂 | ~60 | AF Provider 初始化 + YAML 加载 |
| Agent 配置与工厂 | ~80 | AF Agent 创建 + 中间件 + tool 映射 |
| 工作流定义 | ~100 | WorkflowBuilder + 条件边 + FanOut |
| 上下文注入中间件 | ~50 | ClefContextMiddleware（theory skills + session context） |
| Tool Layer (AF @tool) | ~120 | 原有 subprocess 封装 + AF @tool 装饰器 |
| 会话管理 | ~80 | Session + Checkpoint + 状态推断（简化） |
| API Layer (FastAPI) | ~250 | 7 端点 + SSE（AF 事件映射） |
| OpenTelemetry 配置 | ~20 | 导出器配置 |
| AstrBot 插件 | ~250 | 意图识别 + SSE 监听 + API 转发 |
| 配置文件 (YAML) | ~60 | agents.yaml + providers.yaml |
| **合计** | **~1070** | |

对比原设计 ~1640 行，减少 **35%**。且省去了最易出 bug 的 DAG Executor 自建部分。

---

## 引入路径

### Phase 1: MVP（最小可用）

仅引入 3 个 AF 包 + 核心工作流：

```
agent-framework            # 工作流引擎 + Agent 类 + State
agent-framework-openai     # OpenAI 兼容端点（DeepSeek/GLM）
agent-framework-anthropic  # Claude
```

实现 Step 0 → 1a → 2a → 3 的基本流程（不含 Step 1b 用户确认和 Step 2b 迭代）。

### Phase 2: 完整工作流

加入 Step 1b Human-in-the-loop、Step 2b 迭代循环、Checkpointing。

### Phase 3: 增强（可选）

按需引入 AF 扩展包：

| 包 | 用途 |
|----|------|
| `agent-framework-devui` | 浏览器内调试工作流，可视化 Executor/Edge/State |
| `agent-framework-ag-ui` | 前端进度展示（SSE 可视化） |
| `agent-framework-mcp` | 将 Clef Agent 暴露为 MCP Server，供其他框架调用 |

**不引入**：`agent-framework-a2a`、`agent-framework-durabletask`、`.NET 包`、`agent-framework-bedrock`、`agent-framework-foundry` 等不需要的模块。

---

## 不需要重写的（与原设计一致）

- 8 个 Agent markdown prompt（`.claude/agents/*.md`）
- 所有 Python 工具链（`scripts/`）
- Godot 插件（`addons/clef/`）
- 现有 Claude Code Skill 模式（`/clef-compose`）

## 需要前置导出的（与原设计一致）

- 6 个 theory 子技能（`theory-abc/harmony/melody/orchestration/rhythm/structure`）— 从 Claude Code slash skills 导出为独立 `.md` 文件。

---

## 两种模式对比（更新）

| 维度 | Claude Code Skill | Clef Server + AstrBot (AF 版) |
|------|-------------------|-------------------------------|
| 触发方式 | CLI `/clef-compose` | IM 消息（任意平台） |
| 用户交互 | 终端内对话 | IM 聊天 |
| 适用场景 | 本地开发、精细控制 | 随时随地、快速作曲 |
| LLM 模型 | 绑定 Claude Code 设置 | 可按 Agent 独立配置 |
| 上下文管理 | Claude Code 自动处理 | AF State + Superstep 隔离 |
| 可观测性 | 终端输出 | OpenTelemetry + DevUI |
| 并行安全 | 文件锁 + is_concurrent_safe | Superstep 状态隔离（根本解决） |
| 中断恢复 | 无 | AF Checkpointing |
| 核心资产 | 共享（Agent prompt / 工具链 / 乐理） | 共享 |

---

## 参考

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — Agentic IM 聊天框架
- [Agent Framework](https://github.com/microsoft/agent-framework) — Microsoft 多 Agent 编排框架
- [Agent Framework 文档](https://learn.microsoft.com/en-us/agent-framework/) — 官方文档
- [原始设计文档](2026-04-02-clef-server-astrbot-design.md) — 自建版本参考
- [框架适用性研究报告](../agent-frameworks-research.md) — AF 对 Clef 的详细评估
