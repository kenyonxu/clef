# 外部 Agent 框架对 Clef 的适用性研究报告

> 日期: 2026-04-06
> 研究对象: hermes-agent (Nous Research)、agent-framework (Microsoft)
> 目标: 评估这两个框架对 Clef 当前及未来工作的帮助

---

## Executive Summary

**hermes-agent 对 Clef 的适用性极低**——它是单 Agent CLI 工具，不具备多 Agent 编排能力，且不原生支持 Windows。**agent-framework 适用性中等偏高**——其图工作流引擎和高级编排模式可解决 Clef Leader 手工调度的核心痛点，但引入成本较高，建议按需借鉴设计模式而非全量采纳。两个框架均无任何音乐/MIDI 相关功能。

---

## 1. 仓库概览对比

| 维度 | hermes-agent | agent-framework |
|------|-------------|-----------------|
| **开发者** | Nous Research | Microsoft |
| **版本** | v0.7.0 | v1.0.0 (GA) |
| **协议** | MIT | MIT |
| **语言** | Python 3.11+ | Python 3.10+ / .NET 8+ |
| **定位** | 自改进 CLI AI Agent | 多 Agent 编排框架 |
| **提交数** | 活跃开发中 | 1,834 commits |
| **项目年龄** | ~数月 | ~11 个月 |
| **Windows 支持** | 仅 WSL2 | 完整支持 |
| **音乐/MIDI** | 无（仅 TTS + Suno 提示词技能） | 无 |
| **多 Agent 编排** | 无 | 核心功能 |

---

## 2. Hermes Agent 详析

### 2.1 是什么

Hermes 是一个**面向终端用户的自改进 AI Agent CLI 工具**。它运行在终端中，通过 Skills 系统从经验中学习、改进自身能力。定位类似于 OpenClaw 的继任者，不是一个供开发者构建多 Agent 系统的框架。

### 2.2 核心架构

```
hermes (CLI)
├── agent/                    # 核心 Agent 循环
│   ├── memory_manager.py     # 持久化记忆管理
│   ├── memory_provider.py    # MemoryProvider ABC（可插拔）
│   ├── context_compressor.py # 上下文压缩
│   ├── prompt_builder.py     # Prompt 构建
│   ├── smart_model_routing.py# 智能模型路由
│   ├── skill_commands.py     # 技能命令
│   └── usage_pricing.py      # 用量/定价追踪
├── environments/             # 运行环境
│   ├── agent_loop.py         # Agent 主循环
│   ├── hermes_base_env.py    # 基础环境
│   └── tool_call_parsers/    # 多模型工具调用解析器
│       ├── deepseek_v3_parser.py
│       ├── glm45_parser.py
│       ├── glm47_parser.py
│       └── ...
├── gateway/                  # 消息网关
│   └── platforms/            # Telegram, Discord, Slack, WhatsApp...
├── optional-skills/          # 可选技能库
│   ├── creative/             # Blender MCP, Meme 生成
│   ├── communication/        # 131 法则
│   ├── blockchain/           # Solana
│   ├── devops/               # CLI 技能
│   └── autonomous-ai-agents/ # 黑盒/Honcho 集成
└── cron/                     # 定时任务调度
```

### 2.3 关键能力

| 能力 | 描述 |
|------|------|
| **Skills 系统** | SKILL.md 格式，与 Claude Code 类似。支持从经验中创建和改进技能 |
| **持久记忆** | MEMORY.md + USER.md，跨会话用户画像 |
| **智能模型路由** | 根据任务复杂度自动选择模型（类比 Claude Code 的 model frontmatter） |
| **上下文压缩** | `context_compressor.py` 自动压缩长对话历史 |
| **多模型工具调用解析** | 支持 DeepSeek、GLM、Llama、Mistral 等非标准格式 |
| **MCP 集成** | 可连接任意 MCP Server |
| **消息网关** | 6+ 平台（Telegram/Discord/Slack/WhatsApp/Signal/Home Assistant） |
| **定时任务** | Cron 调度器 |
| **RL 训练** | Tinker-Atropos 集成（可选），用于强化学习改进 Agent 行为 |

### 2.4 对 Clef 的适用性评估

#### 不可用（0/10）——多 Agent 编排

Hermes 是**单 Agent 系统**。它没有任务依赖图、并行调度、迭代循环、或 Agent 间通信机制。Clef 的核心需求——Leader 管理多 Agent 协作——在 Hermes 中完全不存在。

#### 低适用性（2/10）——Skill 系统

Hermes 的 SKILL.md 格式与 Clef 的 theory 子技能在概念上相似，但 Clef 已在 Claude Code 原生 Skill 系统上构建，无需迁移。

#### 中等参考价值（4/10）——上下文压缩

`context_compressor.py` 的设计思路对 Clef 的 token 成本问题有参考价值。Clef 80%+ 的成本来自主会话上下文累积，Hermes 的压缩策略可作为未来优化的设计参考。

#### 中等参考价值（4/10）——智能模型路由

`smart_model_routing.py` 根据任务类型选择不同模型。这对应 Clef 的 P0 优化项——为不同 Agent 分配不同模型（如 Revision 用 Haiku、Composer 用 Sonnet）。可参考其路由逻辑。

#### 低适用性（1/10）——平台兼容性

Hermes 不支持原生 Windows，需 WSL2。Clef 的 Python 工具链和 Godot 插件均在 Windows 原生运行。

#### 结论：**不推荐引入**

Hermes 的定位与 Clef 需求错位。Hermes 是面向终端用户的 AI 助手，Clef 需要的是多 Agent 编排框架。唯一可借鉴的是上下文压缩和模型路由的设计模式，这些可通过阅读源码获取，无需引入依赖。

---

## 3. Agent Framework 详析

### 3.1 是什么

Microsoft Agent Framework 是一个**生产级多 Agent 编排框架**，提供从简单聊天到复杂多 Agent 工作流的完整解决方案。它是 Microsoft 统一 Semantic Kernel 和 AutoGen 的后续项目，已发布 Python v1.0.0 GA。

### 3.2 核心架构

```
agent-framework/
├── python/packages/
│   ├── core/                    # 核心 Agent 抽象
│   │   └── agent_framework/
│   │       ├── _workflows/      # ★ 图工作流引擎
│   │       │   ├── executors/   #   节点执行器（Agent 或函数）
│   │       │   ├── edges/       #   有向边（含条件分支）
│   │       │   ├── state.py     #   Superstep 状态管理
│   │       │   └── checkpoint/  #   状态持久化与恢复
│   │       ├── agent.py         # Agent 抽象（name/instructions/client/tools/middleware）
│   │       ├── middleware/      # 中间件管道
│   │       └── session.py       # 会话管理
│   ├── orchestrations/          # ★ 高级编排模式
│   │   ├── sequential.py        #   顺序执行
│   │   ├── concurrent.py        #   并行扇出
│   │   ├── handoff.py           #   去中心化交接
│   │   ├── group_chat.py        #   编排器指导的群聊
│   │   └── magentic_one.py      #   Magentic One（进度台账 + 计划审查）
│   ├── agent-framework-openai/
│   ├── agent-framework-anthropic/
│   ├── agent-framework-ollama/
│   ├── agent-framework-mcp/     # MCP 集成
│   ├── agent-framework-devui/   # 开发者 UI
│   └── ... (24 个子包)
├── dotnet/                      # .NET 实现
│   └── src/Microsoft.Agents.AI.Workflows/
└── docs/decisions/              # 23 个 ADR（架构决策记录）
```

### 3.3 关键能力

#### A. 图工作流引擎（最相关）

```
[Executor A] --条件边--> [Executor B]
     |                       |
     v                       v
[Executor C] <---扇出--- [Executor D]
     |
     v
[检查点保存/恢复]
```

**核心概念**：
- **Executor（节点）**: 可以是 Agent 或确定性 Python 函数
- **Edge（边）**: 有向、可选条件判断（同步或异步谓词）
- **FanOutEdgeGroup**: 并行扇出/扇入
- **Superstep 执行模型**: 同一 superstep 内所有节点看到相同的状态快照；写入暂存到 pending buffer，在 superstep 边界统一提交
- **Checkpointing**: 完整状态序列化，支持从中断处恢复
- **Human-in-the-loop**: 内置 `request_info` 事件

**Declarative Workflows**: 支持 YAML 定义工作流：
```yaml
# 示例：DeepResearch.yaml
executors:
  - name: planner
    type: agent
    ...
  - name: searcher
    type: agent
    ...
edges:
  - from: planner
    to: searcher
    condition: "needs_search"
```

#### B. 高级编排模式

| 模式 | 描述 | Clef 对应场景 |
|------|------|--------------|
| **SequentialBuilder** | 顺序链式执行 | Step 0 → 1a → 1b → 2a → 3 |
| **ConcurrentBuilder** | 并行扇出 | Composer/Harmonist/Rhythmist 并行生成 |
| **HandoffBuilder** | Agent 间去中心化交接 | — |
| **GroupChatBuilder** | 编排器指导多 Agent 讨论 | Leader + Reviewer 迭代评审 |
| **MagenticOneBuilder** | 管理者 Agent + 进度台账 + 任务规划 | **Leader Agent 的完美对标** |

**Magentic One 模式**最值得关注：
- 管理者 Agent 维护一个 `ProgressLedger`（进度台账）
- 创建/审查计划
- 在专业 Agent 间协调任务执行
- 内置终止条件判断

这与 Clef 的 Leader Agent（`tasks.json` + `depends_on` + 迭代循环）几乎完全对应，但更结构化、有状态管理、可重试。

#### C. 中间件管道

```python
# 示例：自动验证中间件
class AutoValidationMiddleware:
    async def on_tool_call(self, context, next):
        result = await next(context)
        if context.tool_name == "write_score":
            validation = await run_validate(context.output)
            if validation.has_failures:
                raise ValidationException(validation.report)
        return result
```

这直接对应 Clef 的 P1 需求——"PostToolUse hook 自动运行 validate_abc.py"。

#### D. Skills 系统

与 Clef 的 theory 子技能类似：
- 文件型（SKILL.md）、内联型（代码定义）、类库型（可复用 NuGet 包）
- Builder 模式组合多来源
- LLM 暴露为 3 个工具：`load_skill()`、`read_skill_resource()`、`run_skill_script()`

#### E. 上下文压缩

内置 `CompactionStrategy`（ADR 0019），可插拔的 tokenizer 协议。直接对应 Clef 的 token 成本问题。

#### F. 可观测性

内置 OpenTelemetry 集成，分布式追踪。对 Clef 迭代调试有价值——可以追踪每个 Agent 的 token 消耗、延迟、错误率。

#### G. LLM 提供商

10+ 提供商：OpenAI、Anthropic Claude、Azure AI、AWS Bedrock、Google Gemini、Ollama（本地模型）等。与 Clef 的多模型策略（DeepSeek/GLM/Claude）兼容。

### 3.4 对 Clef 的适用性评估

#### 高适用性（8/10）——多 Agent 编排替代 Leader

**当前痛点**: Leader Agent 手工管理 `tasks.json`、依赖排序、merge-validate-dispatch 循环和终止条件。本质是一个手写的工作流引擎，缺乏结构化错误处理、重试和可观测性。

**Agent Framework 的解决方案**:
- **Magentic One 模式**几乎完美对标 Leader 的职责
- **Superstep 状态模型**解决了并行 Agent 文件冲突（Issue #9）——每个节点看到一致的状态快照，写入在边界提交
- **Checkpointing**允许从中断的迭代轮次恢复
- **条件边**可以表达"validate 通过才 dispatch 下一个"的逻辑

**但引入成本高**: 需要将 7 个 Agent 从 Claude Code Agent 格式迁移为 Agent Framework Agent 类，重写 Leader 调度逻辑。

#### 高适用性（8/10）——迭代循环结构化

**当前痛点**: Leader 的 review→revise→validate 循环是手工实现的，最多 3 轮，无状态持久化，中断后无法恢复。

**Agent Framework 的解决方案**:
- 图工作流中的**循环边**自然表达迭代
- **Checkpointing**支持从任意 superstep 恢复
- **终止条件**可编程化（不仅是轮次限制，还可以基于质量分数）

#### 中等适用性（6/10）——中间件自动验证

**当前痛点**: P1 需求中的"PostToolUse hook 自动运行 validate_abc.py"。

**Agent Framework 的解决方案**: 中间件管道可以在任何工具调用后自动触发验证。比 Claude Code 的 hooks 更灵活（可访问完整调用上下文）。

#### 中等适用性（6/10）——上下文压缩

**当前痛点**: 80%+ token 成本来自主会话上下文累积。理论乐理知识（117KB）每次调用全量加载。

**Agent Framework 的解决方案**: 内置 `CompactionStrategy`，可在迭代轮次间压缩历史。

#### 低适用性（3/10）——数据契约/Schema 验证

**当前痛点**: Agent 间通过文件通信（plan.json、score.abc、review_report.json），无正式 Schema。

**Agent Framework 的解决方案**: `pydantic` 数据模型可以定义输入输出 Schema，但 Agent Framework 不强制要求 Agent 间有 Schema 约束。这需要 Clef 自行设计。

#### 低适用性（2/10）——Skills 系统

Clef 的 theory 子技能系统已在 Claude Code 原生 Skill 上构建良好，迁移到 Agent Framework 的 Skills 系统无收益。

#### 不适用（0/10）——MIDI/音乐

Agent Framework 没有任何音乐相关功能。Clef 的 ABC→MIDI→表现力注入管道不受影响。

#### 引入障碍

| 障碍 | 影响 |
|------|------|
| **架构迁移成本** | 需将 7 个 Claude Code Agent 重写为 AF Agent 类 |
| ** Claude Code 依赖** | Clef 深度依赖 Claude Code 的 Skill/Agent/MCP 系统，迁移意味着脱离 CC 生态 |
| **过度设计风险** | AF 是企业级框架（23 个 ADR、OpenTelemetry、A2A 协议），对 Clef 当前规模可能过重 |
| **学习曲线** | 双语言（Python + .NET）、24 个子包的概念模型 |
| **失去 CC 生态** | 迁移后无法使用 CC 的 TodoWrite、Plan Mode、Bash 等工具 |

---

## 4. Clef 痛点与框架匹配矩阵

| Clef 痛点 | 优先级 | hermes-agent | agent-framework | 自研改进 |
|-----------|--------|:---:|:---:|:---:|
| Leader 手工编排（tasks.json） | P0 | — | ★★★ | ★★ |
| Agent 并行文件冲突 (#9) | P0 | — | ★★★ | ★★ |
| 迭代循环无状态/不可恢复 | P1 | — | ★★★ | ★ |
| validate_abc.py 自动触发 | P1 | — | ★★ | ★★★ |
| Agent 模型分配 (frontmatter) | P0 | ★ (参考) | ★★ | ★★★ |
| theory 知识拆分减负 | P1 | — | — | ★★★ |
| 跨会话学习 | P2 | ★★ | ★★ | ★★ |
| 数据契约/Schema | P2 | — | ★ | ★★ |
| 上下文压缩降本 | P1 | ★ (参考) | ★★ | ★★ |
| abc_to_midi.py V:2 偏移 bug | P0 | — | — | ★★★ |
| merge_abc.py 去重 | P0 | — | — | ★★★ |
| validate_abc.py 多声部误报 | P1 | — | — | ★★★ |

**图例**: ★★★ 直接解决 / ★★ 可借鉴设计 / ★ 有参考价值 / — 无关

---

## 5. 推荐方案

### 方案 A：维持现状 + 自研改进（推荐）

**策略**: 保持 Claude Code 生态，逐步实施 P0/P1 优化项。

**具体行动**:

| 序号 | 行动 | 对应痛点 | 复杂度 |
|------|------|---------|--------|
| 1 | 为 7 个 Agent 添加 `model`/`allowedTools`/`maxTurns` frontmatter | P0 模型分配 + 防无限循环 | 低 |
| 2 | 修复 abc_to_midi.py V:2 八度偏移 bug | P0 工具链 bug | 低 |
| 3 | merge_abc.py 去重 ABC header | P0 工具链 bug | 低 |
| 4 | PostToolUse hook 自动运行 validate_abc.py | P1 自动验证 | 低 |
| 5 | theory 知识拆分为 per-agent 子技能 | P1 上下文减负 | 中 |
| 6 | 参考 hermes `context_compressor.py` 设计迭代间上下文压缩 | P1 token 降本 | 中 |
| 7 | Leader 增加 checkpoint 机制（JSON 快照） | P1 可恢复性 | 中 |
| 8 | 定义 Agent 间 JSON Schema（plan.json / review_report.json） | P2 数据契约 | 中 |

**预期效果**: P0 项实施后 Revision 成本降低 ~60%，工具链关键 bug 清除；P1 项实施后整体 token 消耗降低 ~40%。

### 方案 B：引入 Agent Framework（长期考虑）

**时机**: 当 Clef 需要脱离 Claude Code 运行（如部署为独立服务、支持 Web UI、多用户场景）时。

**迁移路径**:
1. **Phase 1**: 仅用图工作流引擎替代 Leader 调度（其他 Agent 仍通过 CC 调用）
2. **Phase 2**: 将 Composer/Harmonist/Rhythmist 迁移为 AF Agent 类
3. **Phase 3**: 完全脱离 CC，用 AF 的 DevUI 替代终端交互

**不建议现在执行的原因**:
- Clef 深度依赖 CC 的 Skill 系统（theory 子技能）、Bash 工具、MCP 服务器
- 当前 P0/P1 问题均可通过自研低成本解决
- AF 的企业级特性（OpenTelemetry、A2A、Durable Task）对当前规模无用

### 方案 C：从 Agent Framework 借鉴设计模式

**策略**: 不引入依赖，仅参考其设计理念改进 Clef。

| AF 设计模式 | Clef 借鉴方式 |
|-------------|-------------|
| Superstep 状态模型 | Leader 的 merge 步骤改为"先收集所有 Agent 输出，再统一合并"，避免文件冲突 |
| Magentic One 进度台账 | tasks.json 增加状态字段（pending/running/done/failed）和进度百分比 |
| 条件边 | depends_on 逻辑从字符串匹配改为可编程谓词 |
| Checkpointing | 每次 Leader 迭代开始前保存 `.clef-work/checkpoint_N.json` |
| 中间件管道 | PostToolUse hook 链（validate → lint → snapshot） |

---

## 6. 结论

| 框架 | 适用性 | 推荐行动 |
|------|--------|---------|
| **hermes-agent** | 极低 | 不引入。仅参考 `context_compressor.py` 和 `smart_model_routing.py` 的设计 |
| **agent-framework** | 中等偏高 | 短期不引入，长期（脱离 CC 时）考虑。现在借鉴其 Superstep、Magentic One、Checkpoint 设计模式改进 Leader |

**核心判断**: Clef 当前的瓶颈不在编排框架本身，而在工具链 bug（abc_to_midi V:2 偏移、merge 去重）和 Agent 配置缺失（model frontmatter、tool 权限）。这些问题通过自研改进即可解决，引入外部框架的成本远大于收益。

---

## 7. 针对 Clef Server + AstrBot 计划的专项评估

> 参考设计文档: `docs/plans/2026-04-02-clef-server-astrbot-design.md`

### 前提变化

原始报告假设 Clef 留在 Claude Code 生态内。AstrBot 计划意味着 Clef 需要一个**独立可部署的 Agent 运行时**，脱离 CC 的 Skill/Agent/MCP 系统。这彻底改变了 agent-framework 的价值定位：

| 维度 | CC 生态内（原评估） | Clef Server（AstrBot 计划） |
|------|:---:|:---:|
| Agent 运行时 | CC 内置，无需自建 | **需自建**（设计文档估算 ~350 行） |
| DAG Executor | Leader Agent 手工实现 | **需自建**（设计文档估算 ~400 行） |
| LLM 提供商 | CC 内置 | 设计选了 LiteLLM（~30 行配置） |
| 会话/检查点 | 无 | **需自建**（设计文档估算 ~180 行） |
| 可观测性 | 终端输出 | **需自建**（agent_logs + SSE） |
| **agent-framework 适用性** | 中等偏高 | **高** |

### 逐模块对照：agent-framework 能替代/增强什么

#### 7.1 DAG Executor（设计文档 ~400 行）→ agent-framework 图工作流

**这是最大的收益点。**

设计文档规划的 DAG Executor 需要自建：
- 6 步工作流定义与调度
- Agent 间依赖关系（`depends_on`）
- 并行执行（Step 1b/2a 的 Composer+Harmonist+Rhythmist）
- 迭代循环（Step 2b 最多 3 轮 review→revise→validate）
- 条件分支（validate 通过才继续，FAIL 则进入下一轮或终止）
- 检查点（中断恢复）
- 重试逻辑

**agent-framework 图工作流原生提供以上全部能力**：

| 需求 | 设计文档自建 | agent-framework |
|------|------------|-----------------|
| 步骤定义与调度 | 手写状态机 | Executor 节点 + 有向边 |
| 依赖调度 | `depends_on` 字符串匹配 | Edge 的 source/target + 条件谓词 |
| 并行执行 | `asyncio.gather` | `FanOutEdgeGroup` |
| 迭代循环 | `while round < 3` | 循环边（Edge 指向前序节点） |
| 条件分支 | `if validate.passed` | `EdgeCondition`（同步/异步谓词） |
| 检查点 | 设计文档提到但未实现 | 内置 `Checkpoint`（序列化/恢复） |
| 重试 | 设计文档提到但未实现 | 中间件或 Executor 层重试 |
| 状态隔离 | 无（文件系统直接读写） | **Superstep 模型**（同一 superstep 内节点看到一致快照，写入在边界提交） |

**Superstep 模型对 Clef 的特殊价值**：解决 Issue #9（并行 Agent 文件冲突）。设计文档用 `is_concurrent_safe` 标记工具来避免冲突，但这只是规避。Superstep 模型从根本上解决了这个问题——每个 Agent 在自己的快照上工作，合并由框架在 superstep 边界统一处理。

**代码量节省**：设计文档估算 DAG Executor ~400 行。用 agent-framework 的 `WorkflowBuilder` 定义等效工作流约 **~80-100 行**。

```python
# 用 agent-framework 表达 Clef 工作流的伪代码
workflow = (
    WorkflowBuilder()
    .add_executor("parse", LeaderParseExecutor())
    .add_executor("plan", LeaderPlanExecutor())
    .add_executor("sample_composer", ComposerExecutor(), group="sampling")
    .add_executor("sample_harmonist", HarmonistExecutor(), group="sampling")
    .add_executor("sample_rhythmist", RhythmistExecutor(), group="sampling")
    .add_executor("full_composer", ComposerExecutor())
    .add_executor("review", ReviewerExecutor())
    .add_executor("revise_composer", ComposerExecutor())
    .add_executor("express", OrchestratorExecutor())

    .add_edge("parse", "plan")
    .add_edge("plan", "sample_composer")
    .add_edge("plan", "sample_harmonist")  # FanOut
    .add_edge("plan", "sample_rhythmist")  # FanOut
    .add_edge_group(FanOutEdgeGroup(["sample_composer", "sample_harmonist", "sample_rhythmist"], "full_composer"))
    .add_edge("full_composer", "review")
    # 迭代循环：review → revise（条件：未通过且轮次 < 3）
    .add_edge("review", "revise_composer", condition=lambda ctx: not ctx["passed"] and ctx["round"] < 3)
    .add_edge("revise_composer", "review")  # 回边
    .add_edge("review", "express", condition=lambda ctx: ctx["passed"])
    .build()
)
```

#### 7.2 Agent 运行时（~350 行）→ agent-framework Agent 类

设计文档规划的 Agent 运行时需要：
- `AgentDef` 数据类（name, prompt_md, model, tools, temperature...）
- `build_system_prompt()` 分层加载（agent prompt → theory skills → session context）
- 单次 LLM 调用 + tool-use 循环
- 上下文构建（plan.json + score.abc + review）

**agent-framework 的 `Agent` 类已提供**：
- `name`, `instructions`（= prompt_md）, `client`（= LLM provider）, `tools`, `middleware`
- `agent.run()` / `agent.run_streaming()` — 内置 tool-use 循环
- `Structured output` — 可声明输出 JSON Schema
- `Middleware` — 可注入上下文压缩、日志、验证

**但需要适配**：
- agent-framework 的 `instructions` 是字符串，需要包装 `build_system_prompt()` 为中间件
- agent-framework 的 `client` 用 `BaseChatClient` 抽象，需要写一个 LiteLLM 适配器（或直接用 agent-framework 的 10+ 内置 provider）
- agent-framework 的 tool 是 Python 函数，需要包装现有的 subprocess 脚本

**代码量节省**：从 ~350 行降至 **~100-150 行**（主要是适配代码 + 中间件）。

**关键取舍**：agent-framework 自带 OpenAI/Anthropic/Ollama 等 provider。如果选择 agent-framework，**可以去掉 LiteLLM 依赖**，直接用内置 provider。但 provider 数量（10+ vs 100+）和 fallback 策略灵活性不如 LiteLLM。

| 方案 | Provider 数 | 代码量 | Fallback | 成本追踪 |
|------|:---:|:---:|:---:|:---:|
| 设计文档方案（LiteLLM） | 100+ | ~30 行 | 内置，灵活 | 内置 |
| AF 内置 provider | 10+ | ~20 行 | 需自行配置 | 需 OpenTelemetry |
| AF + LiteLLM 适配器 | 100+ | ~50 行 | 双重 | 双重 |

**推荐**：如果主要用 DeepSeek/GLM/Claude（3-5 个 provider），AF 内置足够；如果需要广泛兼容，保留 LiteLLM。

#### 7.3 会话管理与检查点（~180 行）→ agent-framework Session + Checkpoint

设计文档规划：
- `meta.json` 状态机（CREATED → PLANNING → SAMPLING → ... → DONE）
- `agent_logs/` 日志目录
- `snapshots/` 版本快照

**agent-framework 已提供**：
- `AgentSession` + `SessionContext` — 会话管理
- `HistoryProvider` 接口 — 可插拔（InMemory / Redis / Cosmos DB）
- `Checkpoint` — 完整工作流状态序列化/恢复
- `CompactionStrategy` — 上下文压缩

**但需要适配**：
- agent-framework 的 Session 是通用对话会话，没有 Clef 特有的"作曲进度"概念
- 状态机（PLANNING → SAMPLING → ITERATING 等）需要自定义，但可基于 AF 的 superstep 状态推断
- `agent_logs` 的成本追踪需要通过 OpenTelemetry middleware 实现

**代码量节省**：从 ~180 行降至 **~50-80 行**。

#### 7.4 可观测性（agent_logs + SSE）→ OpenTelemetry

设计文档规划的 `agent_logs` 只存摘要（token 数、耗时、tool 调用）。agent-framework 内置 OpenTelemetry 可以自动捕获这些指标，无需手写日志。

SSE 进度推送需要自定义（AF 的 `WorkflowRunResult` 事件可以映射到 SSE 事件）。

#### 7.5 AstrBot 插件（~250 行）→ 不受影响

AstrBot 插件是独立模块，与 agent-framework 无关。无论是否使用 AF，这 250 行都一样。

### 7.6 引入后的架构变化

```
┌─────────────────────────────────────────────┐
│          AstrBot (Python)                    │
│  Clef 插件 (意图 → API → 文件传输)            │
└──────────────────┬──────────────────────────┘
                   ↓ HTTP
┌─────────────────────────────────────────────┐
│          Clef Server (Python)                │
│                                             │
│  FastAPI Layer (~250 行，不变)               │
│        ↓                                    │
│  ┌──────────────────────────────────┐       │
│  │ agent-framework Workflow         │       │
│  │ (替代原 DAG Executor ~400→~100)  │       │
│  │                                  │       │
│  │  Executor: Agent (AF Agent 类)   │       │
│  │  Edge: 条件/循环/FanOut           │       │
│  │  State: Superstep + Checkpoint   │       │
│  └──────────────────────────────────┘       │
│        ↓                                    │
│  Tool Layer (~180 行，不变)                  │
│                                             │
└─────────────────────────────────────────────┘
```

### 7.7 代码量对比

| 模块 | 设计文档自建 | 用 agent-framework | 节省 |
|------|:---:|:---:|:---:|
| DAG Executor | ~400 | ~100 | **-75%** |
| Agent 运行时 | ~350 | ~150 | **-57%** |
| Session/检查点 | ~180 | ~80 | **-56%** |
| LLM Provider | ~30 (LiteLLM) | ~20 (AF 内置) 或 ~50 (AF+LiteLLM) | 持平或+67% |
| Tool Layer | ~180 | ~180 (不变) | 0% |
| API Layer | ~250 | ~250 (不变) | 0% |
| AstrBot 插件 | ~250 | ~250 (不变) | 0% |
| **合计** | **~1640** | **~1030 或 ~1060** | **-37%** |

### 7.8 额外收益（设计文档未规划但 AF 自带）

| 收益 | 说明 |
|------|------|
| **Magentic One 进度台账** | 比 `tasks.json` 更结构化的任务追踪，内置计划审查和终止判断 |
| **Declarative Workflow (YAML)** | 可将工作流定义外置为 YAML，用户可自定义步骤顺序 |
| **OpenTelemetry** | 自动追踪每个 Agent 的 token 消耗、延迟、错误率 |
| **Human-in-the-loop** | 内置 `request_info` 事件，Step 1b 用户确认可直接用 |
| **DevUI** | AF 的开发者 UI 可直接用于调试工作流，无需自己建 WebUI |
| **A2A 协议** | 未来可暴露为标准 Agent 服务，供其他框架调用 |

### 7.9 引入成本与风险

| 成本/风险 | 影响 | 缓解措施 |
|-----------|------|---------|
| 新增依赖（`agent-framework` + 子包） | 生态耦合 | AF 是 MIT 协议、v1.0 GA、Microsoft 维护，风险可控 |
| 学习曲线（Superstep/Executor/Edge 概念） | 开发效率 | AF 有大量示例（DeepResearch/Marketing/CustomerSupport YAML） |
| Agent prompt 适配 | 需将 CC Agent `.md` 转为 AF `instructions` | 设计文档已规划 `build_system_prompt()` 分层加载，改动小 |
| Tool 定义适配 | AF tool 是 Python 函数，不是 subprocess | 设计文档的 `ToolDef.handler=wrap_subprocess` 直接适用 |
| AF 内置 provider vs LiteLLM | Provider 数量减少 | 保留 LiteLLM 作为 AF ChatClient 适配器 |
| AF 是面向通用 Agent 的框架 | 可能有 Clef 不需要的抽象 | 只用 Workflow + Agent 核心包，不引入不需要的子包 |

### 7.10 结论：AstrBot 场景下 agent-framework 推荐等级上调

**从"中期考虑"上调为"建议在 Clef Server 实现阶段引入"**。

理由：
1. DAG Executor 是 Clef Server 中最复杂、最易出 bug 的模块（~400 行自建工作流引擎），AF 直接替代，节省 75%
2. Superstep 模型从根本上解决并行 Agent 文件冲突（Issue #9），这是设计文档的 `is_concurrent_safe` 方案无法根本解决的
3. 内置 Checkpointing + OpenTelemetry 省去 ~200 行自建代码
4. 总代码量从 ~1640 降至 ~1030，减少 37%
5. 额外获得 Magentic One、DevUI、Human-in-the-loop、Declarative Workflow 等能力

**推荐引入策略**：
- **Phase 1**（Clef Server MVP）：仅引入 `agent-framework` 核心包 + `agent-framework-openai`（或 LiteLLM 适配器），用图工作流替代 DAG Executor
- **Phase 2**（增强）：引入 `agent-framework-devui` 用于调试，`agent-framework-ag-ui` 用于前端进度展示
- **不引入**：`agent-framework-a2a`、`agent-framework-durabletask`、`.NET 包`等 Clef 不需要的模块

---

## Sources

[1] hermes-agent 仓库: `E:\GitHub\hermes-agent` (Nous Research, MIT, v0.7.0)
[2] agent-framework 仓库: `E:\GitHub\agent-framework` (Microsoft, MIT, v1.0.0)
[3] Clef CLAUDE.md: `E:\GitHub\clef-dev\CLAUDE.md`
[4] Clef 已知问题: `feedback_clef_compose_issues.md`（18 项技术问题）
[5] Clef Token 成本: `reference_clef_token_cost.md`（单次 ~3.1M tokens）
[6] Clef 最佳实践: `feedback_best_practice_research.md`（10 项优化建议，来源于 shanraisshan/claude-code-best-practice）
[7] Agent Framework ADR 0001: Agent Run Response Design（与 AutoGen/LangGraph/OpenAI ADK 对比）
[8] Agent Framework ADR 0019: Context Compaction Strategy
[9] Agent Framework ADR 0021: Agent Skills Design
