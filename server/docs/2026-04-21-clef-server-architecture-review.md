# Clef Server 架构分析与评审

日期：2026-04-21

## 1. 背景与范围

本文档针对 `server/` 目录中的 Clef Server 做一次静态架构分析与工程评审，目标是回答以下问题：

- 系统当前采用了什么样的架构形态
- 各核心模块的边界是否清晰
- 当前设计的优势与短板分别是什么
- 如果继续演进，优先应该优化哪些部分

本次评审基于以下材料：

- `graphify-out/GRAPH_REPORT.md`
- `server/src/clef_server/*.py`
- `server/web/src/*`
- `server/tests/*`

本次评审未实际启动服务、未执行测试，结论基于代码结构、职责分布、调用路径和测试覆盖面做出。

## 2. 执行摘要

Clef Server 当前不是一个传统的无状态 Web API，而是一个以“会话”为核心、围绕多阶段生成任务组织的长事务编排服务。后端负责：

- 会话状态与生命周期管理
- 多阶段工作流推进
- Agent 提示词与上下文装配
- LLM Provider 适配与调用
- 工具调用、文件工作区和生成产物管理
- 前端轮询/SSE 所需的过程状态输出

前端总体保持薄客户端定位，主要承担会话创建、状态展示、确认交互和结果浏览，不承担核心业务编排。

总体评价如下：

- 架构方向：正确
- 工程完成度：较高
- 可维护性：中等偏上
- 可扩展性：中等
- 当前综合评价：7.5/10

这套架构最突出的优点是：**系统模型与业务问题匹配**。音乐生成本质上是一个高不确定性的长时任务，天然需要阶段拆分、自动验证、人工确认和版本化产物管理。Clef Server 的设计基本贴合了这个事实。

当前最主要的问题不是“不能工作”，而是**核心编排器过重、恢复与取消语义不够统一、基础设施能力尚未完全沉淀为稳定边界**。如果继续迭代，系统会越来越依赖 `ComposeOrchestrator` 这一个中心类，后续变更成本会持续升高。

## 3. 系统定位与整体架构

### 3.1 系统定位

Clef Server 可以视为一个“多 Agent 音乐作曲微服务”，但更准确地说，它是：

> 一个以 `Session` 为核心聚合根、以工作区文件为事实载体、以多阶段状态机驱动的 Agent 编排服务。

这一定义很重要，因为它决定了系统不应被按“普通 CRUD 服务”的方式理解，而应按“带人工确认点的任务执行系统”理解。

### 3.2 整体分层

从代码结构看，系统可以分成五层：

1. 应用装配层
   - `app.py`
   - `main.py`
   - 负责 FastAPI 应用创建、日志接入、静态资源挂载、会话恢复

2. 接口与会话接入层
   - `routes.py`
   - 暴露 REST API、SSE、设置管理、Provider/Agent/Profile 配置管理

3. 领域与编排层
   - `sessions.py`
   - `orchestrator.py`
   - 定义会话状态机、阶段推进、确认点、工作流控制和产物管理

4. Agent 与基础设施层
   - `agents.py`
   - `chat_completions_client.py`
   - `providers.py`
   - `concurrency.py`
   - `middleware.py`
   - 负责提示词装配、Provider 抽象、协议兼容、限流和上下文注入

5. 工具与音乐处理层
   - `tools.py`
   - `validation.py`
   - `prompt_builder.py`
   - `response_parser.py`
   - `score_processor.py`
   - 负责脚本工具封装、ABC 校验、响应抽取、乐谱合并与处理

前端 `server/web/` 与后端之间通过 REST + SSE 协作，前端不拥有业务状态机，只消费服务端输出。

### 3.3 核心架构风格

Clef Server 当前混合了几种架构风格：

- 状态机驱动工作流
- 会话型应用服务
- 文件工作区驱动执行
- Agent/tool-use 编排
- 薄前端 + 厚后端

这种组合对当前问题域是合理的。尤其是“文件工作区驱动执行”这一点非常关键：音乐生成过程中间产物天然适合落成 `plan.json`、`score.abc`、`validation_report.json`、`review_*.json`、`base_r*.mid`、`final_r*.mid` 等文件，系统因此具备了良好的可检查性和可追溯性。

## 4. 核心模块拆解

### 4.1 应用装配：`app.py`

`app.py` 很薄，这是一件好事。它主要负责：

- 初始化 FastAPI
- 配置 CORS
- 注册路由
- 在生命周期中接入文件日志
- 配置 session 持久化目录并恢复未完成会话
- 如果前端构建产物存在，则直接挂载 SPA

这一层没有侵入业务流程，职责相对纯净。应用入口保持轻量，说明当前架构没有把核心业务泄漏到框架装配层。

评价：

- 优点：职责单一，清晰
- 风险：恢复的是 session 状态，不是后台执行体

### 4.2 接口层：`routes.py`

`routes.py` 是当前的“应用服务入口”。它承担了三类职责：

1. 会话类接口
   - `/compose`
   - `/status/{id}`
   - `/status/{id}/stream`
   - `/confirm/{id}`
   - `/cancel/{id}`
   - `/sessions`

2. 配置类接口
   - `/settings`
   - `/settings/providers`
   - `/settings/agents`
   - `/profiles`

3. 运维/诊断类接口
   - `/settings/diagnostics`
   - `/settings/cleanup`
   - `/tools`

这里的设计整体合理，但 `routes.py` 已经不只是“协议适配层”，也开始承担部分流程拼装职责，例如：

- 加载 provider config
- 创建 provider clients
- 加载 settings
- 读取 profile overrides
- 创建 orchestrator
- 异步起后台任务

这意味着它已经部分进入“应用编排层”。

评价：

- 优点：接口直观，围绕 session 组织，适合前端消费
- 风险：有继续膨胀成“大路由文件”的趋势

### 4.3 会话模型：`sessions.py`

`ComposeSession` 与 `SessionManager` 是当前后端架构最健康的部分之一。

`ComposeSession` 负责建模：

- `status`
- `current_phase`
- `confirmation_data`
- `phase_history`
- `sub_steps`
- `output_files`
- `iteration_count`
- `sample_round`
- SSE 监听队列

`SessionManager` 负责：

- session 创建与查询
- TTL 管理
- 磁盘持久化
- 磁盘恢复
- 删除

同时，`PHASES` 和 `PHASE_ORDER` 明确表达了系统的领域流程：

- `parse`
- `sample`
- `create`
- `iterate`
- `review`
- `express`

这个模块的价值在于：Clef Server 没有把“状态”散落在路由、编排器和前端中，而是集中沉淀在统一的 session 模型里。

评价：

- 优点：领域建模清楚，是系统的稳定核心
- 风险：取消语义存在双轨制，`request_cancel()` 与 `set_cancelled()` 没有统一为单一机制

### 4.4 编排核心：`orchestrator.py`

`ComposeOrchestrator` 是系统的绝对中心，也是最大的风险点。

它当前同时承担以下职责：

- 流程状态机推进
- 读取/写入工作区文件
- 生成 plan
- 驱动 sample/create/iterate/review/express 各阶段
- 调用 reviewer / leader / repair 等 agent
- 处理 best-of-N、repair、re-validate、版本化 MIDI 输出
- 控制确认点和 phase 自动推进
- 处理一部分限流、消息压缩、缓存和容错

也就是说，它已经不是单纯的 orchestrator，而更像是：

> 工作流状态机 + 应用服务 + 任务协调器 + 质量闭环控制器 + 文件产物控制器

这是当前维护性最大的隐患。

但需要强调的是，这不是“设计错误”，而是“设计已经走到该拆分的阶段”。在系统形成期，先把业务闭环集中到一个类中是常见做法；问题在于当前功能已经明显超过了单类的舒适边界。

评价：

- 优点：业务闭环完整，问题域理解很深
- 风险：单点过重，后续修改成本和回归风险会持续上升

### 4.5 Agent 装配：`agents.py` + `middleware.py`

Agent 装配层的结构是比较干净的：

- 从 `AgentConfig` 读取 prompt、skills、temperature、tools
- 用 `ClefContextMiddleware` 构造参考材料和 session context
- 把 prompt、reference materials、session context 拼成 instructions
- 为 Agent 绑定正确的 provider 和工具集

这个设计体现了一个好习惯：**把“提示词文本”“参考知识”“运行时上下文”分层管理**，而不是全部混成一个大字符串。

评价：

- 优点：可读性好，后续做 prompt 管理和 context budget 控制时也有扩展空间
- 风险：真正的 token 预算治理目前仍比较轻，后续复杂化后可能需要独立的 context assembler

### 4.6 Provider 与协议兼容：`providers.py` + `chat_completions_client.py`

这是当前基础设施层中质量较高的一部分。

系统通过 `ProviderConfig` 加载：

- Anthropic 直连
- OpenAI-compatible providers
- Anthropic-compatible providers

然后统一包装成 `ChatCompletionsClient`。这个 client 负责：

- OpenAI Chat Completions 格式转换
- Anthropic Messages 格式转换
- tool schema 转换
- 错误分类与重试
- 使用量信息回填

这种设计的好处是：上层 orchestrator 几乎不需要关心协议差异，只需要按统一接口 `get_response()` 调用。

评价：

- 优点：Provider 抽象清楚，适合多模型切换和 profile override
- 风险：流式输出尚未支持；协议差异仍由单个 client 承担，后续再增加 provider 类型时会变重

### 4.7 工具系统：`tools.py`

工具层当前做了三件有价值的事：

1. 把 `.claude/skills/clef-compose/scripts/` 的脚本包装成可调用工具
2. 给工具打上 `ToolSafety` 元数据
3. 对文件读写提供 path traversal 防护

工具类型分为：

- `READ_ONLY`
- `IDEMPOTENT_WRITE`
- `EXCLUSIVE_WRITE`

同时不同 Agent 有自己的工具白名单映射。

这是一个好的开始，说明系统已经意识到“Agent 能做什么”本身也是架构的一部分，而不是 prompt 里一句话就算约束。

但当前问题在于：安全模型存在，统一执行策略边界还不够强。也就是说，安全元数据更多还是“说明性数据”，尚未完全沉淀成系统级强约束。

评价：

- 优点：安全意识明确，工具能力模型已成形
- 风险：缺少独立的 tool policy / tool execution boundary

### 4.8 限流与并发：`concurrency.py`

`ProviderRateLimiter` 使用 token bucket 做 provider 级别的速率控制，这是合理方案。相比单纯控制并发数，它更贴近真实 RPM 限制。

系统里也能看到并发意识：

- safe/unsafe tool batch 分组
- error-isolated gather
- 微压缩 tool output
- 延迟控制避免 429

但从主流程实现来看，很多地方仍然是“显式串行 + sleep 节流”。这在系统规模不大时完全可接受，但未来若要支持更复杂的并发调度，需要把“调度策略”与“业务阶段逻辑”拆开。

评价：

- 优点：有限流与容错意识，不是裸并发
- 风险：并发控制逻辑分散在 orchestrator 各处，难以统一演进

### 4.9 前端：`server/web`

前端当前是典型的流程可视化客户端：

- `api/client.ts` 封装基础 HTTP 调用
- `sessionStore.ts` 保存当前会话、workflow steps、confirmation data 等状态
- `usePolling.ts` 和 `useSSE.ts` 负责过程同步
- `Workspace.tsx` 负责 chat/steps/output 展示和用户确认入口

从边界来看，前端没有承担业务编排，这是正确的。复杂状态主要仍由后端 session 提供，前端负责投影和交互。

评价：

- 优点：边界健康，适合当前阶段
- 风险：若后续交互变复杂，可能需要更明确的前端状态模型，但当前不是主要问题

## 5. 关键运行流程

### 5.1 创建会话

流程如下：

1. 前端调用 `/compose`
2. 路由生成 `session_id`
3. 根据 settings 生成工作目录
4. `SessionManager.create()` 创建 session
5. 后台异步启动 `_run_workflow()`
6. `ComposeOrchestrator.start()` 进入 `parse`

这一流程体现了“请求快速返回、后台长任务执行”的典型模式，适合生成型任务。

### 5.2 阶段推进

阶段推进由 `_advance_phase()` 统一管理，其职责包括：

- 检查取消请求
- 计算下一阶段
- 判断是否需要用户确认
- 更新 session 状态
- 触发下一阶段方法
- 在阶段结束后持久化 session

这是系统的关键控制点，也是后续最值得保留和强化的设计资产。

### 5.3 质量闭环

系统不是简单地“生成一次就结束”，而是至少包含三层质量机制：

1. 生成后技术校验
2. 失败后 repair
3. reviewer + leader 驱动迭代

这说明系统设计已经从“prompt engineering”进化到“process engineering”。对于音乐生成这类强结构内容，这是正确方向。

### 5.4 人机协作闭环

系统在 `parse`、`sample`、`review` 处设置确认点，允许用户：

- 继续
- 取消
- revise 并附反馈

这使系统具备了“半自动创作工作台”的形态，而不是黑盒生成器。

## 6. 架构优点

### 6.1 业务模型与架构模型高度一致

Clef Server 没有强行把复杂生成任务压平到单次请求，而是把 session、phase、sub-step、confirmation 这些真正存在的业务概念建模出来。这是本系统最大的优点。

### 6.2 厚后端、薄前端的边界是对的

当前复杂性主要来自：

- LLM 调用
- 工作流推进
- 文件产物控制
- 校验与修复

这些都应该留在后端。前端只做展示和控制面板，这个边界健康。

### 6.3 文件工作区提高了可观测性与可追溯性

中间产物全部落盘，使系统具备：

- 可调试性
- 可恢复性
- 可审计性
- 可做离线比对和人工检查

对生成式系统来说，这是比“纯内存流水线”更稳妥的路线。

### 6.4 Provider 与 Agent 配置具备一定产品化能力

支持：

- providers.yaml
- agents.yaml
- profiles.yaml
- settings.json

并通过 API 暴露修改入口，说明系统已经开始具备“可运营配置”能力，而不是纯研发脚本。

### 6.5 测试覆盖面广

仓库中 `server/tests/` 和前端测试覆盖了 routes、session、orchestrator、providers、tools、workflow、integration 等多个层次，说明该系统具备一定回归基础，后续重构不是完全无保护状态。

## 7. 架构风险与问题

### 7.1 `ComposeOrchestrator` 已成为高风险中心

这是当前最重要的问题。

表现为：

- 文件过大
- 职责过多
- 大量阶段细节内聚于单类
- 多种基础设施能力混入业务逻辑

风险包括：

- 改动一个阶段时容易影响其他阶段
- 测试和推理成本上升
- 新需求继续堆入时会加速失控

这个问题不是立即阻断性的，但已经足够明确，应该列为第一优先级技术债。

### 7.2 恢复能力恢复了“状态”，没有完整恢复“执行”

系统重启后会恢复未完成 session，但不会自动把这些 session 重新绑定到正在运行的后台执行体。也就是说：

- 可以看到之前任务“还没结束”
- 但任务是否能自动继续推进，并没有被完整建模

这类系统如果要强调“恢复”，就需要更明确地区分：

- 恢复 session 记录
- 恢复可继续执行的 workflow

当前实现更接近前者。

### 7.3 取消语义不一致

当前同时存在：

- `request_cancel()`：软取消，允许阶段边界生效
- `set_cancelled()`：硬切状态

而路由层使用的是后者。结果是取消机制在模型上并不统一，未来如果引入更多异步边界、并发任务或子任务，很容易出现：

- session 已 cancelled，但后台逻辑尚未完全停下
- 某些阶段只检查软取消，不检查硬状态

### 7.4 安全能力存在，但还没有统一收口

当前安全相关机制包括：

- 路径越界防护
- tool 白名单
- `ToolSafety`
- session 级 permission override

问题在于这些能力分布在多处，没有形成清晰的“唯一执行入口”。系统后续如果继续引入更多工具和 Agent，建议将工具执行统一收敛到独立的 policy/executor 层。

### 7.5 路由层承担了过多装配逻辑

`routes.py` 当前已涉及：

- 配置加载
- provider 创建
- profile 解析
- orchestrator 创建
- resume/recover 逻辑

这会让接口层越来越像应用编排层。短期没有大碍，但如果继续增长，建议抽出独立的 application service。

### 7.6 并发与调度策略尚未沉淀成基础设施

系统已经在做限流、重试、sleep pacing、microcompact、batch partition，但这些能力多数还混在 orchestrator 内部。未来如果要支持更多阶段并发、更多 Agent 组合或更复杂的 repair 策略，这种分布式实现会变得难以维护。

## 8. 演进建议与优先级

### P0：拆分 `ComposeOrchestrator`

优先建议：

- 保留 `ComposeOrchestrator` 作为顶层阶段协调器
- 把各阶段拆成独立执行器
  - `ParsePhaseRunner`
  - `SamplePhaseRunner`
  - `CreatePhaseRunner`
  - `IteratePhaseRunner`
  - `ExpressPhaseRunner`
- 把 Agent 调用下沉到统一的 `AgentRunner`
- 把工具调用/文件操作/校验闭环进一步封装成能力服务

目标不是“拆小文件”本身，而是让每个执行单元只负责一类变化原因。

### P1：统一取消与恢复模型

建议明确以下语义：

- `cancel_requested`：用户提出取消请求
- `cancelled`：系统确认执行终止
- `recoverable checkpoint`：允许从指定阶段恢复
- `restored session`：仅恢复状态
- `resumed workflow`：恢复执行

如果这组语义明确，很多边界问题会自然消失。

### P1：建立统一 Tool Execution Boundary

建议引入统一工具执行入口，集中处理：

- tool 白名单
- session permission override
- path validation
- safety level
- 审计日志
- dedup
- 错误包装

这样 `tools.py` 中的元数据才会从“定义”变成“强制约束”。

### P2：抽离 Application Service

可考虑引入：

- `ComposeApplicationService`
- `SettingsApplicationService`
- `ProfileApplicationService`

让 `routes.py` 只保留：

- HTTP 参数校验
- 状态码转换
- 调用应用服务
- 返回响应

### P2：强化 workflow resume 能力

若后续希望提升“服务重启后不中断任务”的能力，需要进一步设计：

- phase checkpoint 数据结构
- 挂起任务恢复条件
- 幂等保障
- 部分阶段是否允许重入

这件事复杂度较高，不建议在拆分 orchestrator 之前做。

### P3：进一步治理上下文预算与观测

可后续补强：

- 按阶段记录 token usage
- 记录 provider/model 维度成功率与耗时
- 区分 LLM 错误、工具错误、业务规则错误
- 对 sample/create/iterate 做结构化耗时统计

这些能力更偏平台化，当前不是第一优先级。

## 9. 结论

Clef Server 当前已经不是原型脚本，而是一套具备明确产品形态的多 Agent 编排服务。其核心优点是：

- 正确理解了音乐生成任务的长事务本质
- 通过 session 和 phase 做了合理建模
- 形成了“生成-校验-修复-复审-确认”的质量闭环
- 让前端保持薄客户端，保证复杂性留在后端

它当前最大的风险不是方向错误，而是**中心编排器承载过多责任**。只要后续按优先级先拆编排器、统一取消恢复模型，再收拢工具执行策略，这套系统是有机会继续平稳扩展的。

换句话说，Clef Server 当前最需要的不是重写，而是**在保留现有领域模型的前提下做结构性拆分**。

## 10. 附录：关键文件索引

后端入口与装配：

- `server/src/clef_server/main.py`
- `server/src/clef_server/app.py`
- `server/src/clef_server/routes.py`

核心领域与编排：

- `server/src/clef_server/sessions.py`
- `server/src/clef_server/orchestrator.py`

Agent 与 Provider：

- `server/src/clef_server/agents.py`
- `server/src/clef_server/middleware.py`
- `server/src/clef_server/providers.py`
- `server/src/clef_server/chat_completions_client.py`
- `server/src/clef_server/concurrency.py`

工具与音乐处理：

- `server/src/clef_server/tools.py`
- `server/src/clef_server/prompt_builder.py`
- `server/src/clef_server/response_parser.py`
- `server/src/clef_server/validation.py`
- `server/src/clef_server/score_processor.py`

前端：

- `server/web/src/api/client.ts`
- `server/web/src/stores/sessionStore.ts`
- `server/web/src/hooks/useSSE.ts`
- `server/web/src/pages/Workspace.tsx`

测试：

- `server/tests/`
- `server/web/src/test/`
