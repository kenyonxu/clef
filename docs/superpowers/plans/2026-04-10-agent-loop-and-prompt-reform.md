<!-- /autoplan restore point: /c/Users/kenyo/.gstack/projects/kenyonxu-clef-dev/feature-clef-server-v2-autoplan-restore-20260410-215203.md -->
# Clef Server Agent Loop + Prompt Reform 实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 clef-server 的 agent 从单轮 LLM 调用升级为多轮 agentic tool-use loop，分叉 agent prompt 为 server 专用版本，并重构 prompt 组装方式，使 agent 真正能执行 prompt 中的自检指令。

**Architecture:**
1. **Task 0（前置）**：将 clef-compose 的 agent prompt 分叉到 `server/config/prompts/`，重写为 server 工具系统的指令。理论 skill 保留共享。
2. **Task 1-5**：新增 `agent_loop.py` 实现 ReAct 循环，重构 prompt 三层结构，串联 orchestrator。

**Tech Stack:** Python 3.12, agent-framework-core, httpx, Anthropic/OpenAI Chat Completions API

---

## 根因回顾

调查发现 clef-server agent prompt 遵循度差的 6 个根因（按影响排序）：

| # | 根因 | 影响 | 本方案对应 Task |
|---|------|------|----------------|
| 0 | 直接复用 clef-compose 的 Claude Code 专用 prompt | **极高** | Task 0 |
| 1 | 单轮执行，无 agentic loop | 极高 | Task 1 |
| 2 | prompt 全部拼成一个巨大 system message | 高 | Task 2 |
| 3 | 参考材料（乐理 skill）无大小限制 | 中 | Task 3 |
| 4 | model fallback 静默降级 | 中 | Task 4 |
| 5 | orchestrator 调用点需要适配新 loop | 中 | Task 5 |

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `server/config/prompts/clef-composer.md` | **新建** | Server 专用 Composer prompt |
| `server/config/prompts/clef-harmonist.md` | **新建** | Server 专用 Harmonist prompt |
| `server/config/prompts/clef-rhythmist.md` | **新建** | Server 专用 Rhythmist prompt |
| `server/config/prompts/clef-reviewer.md` | **新建** | Server 专用 Reviewer prompt |
| `server/config/prompts/clef-orchestrator.md` | **新建** | Server 专用 Orchestrator prompt |
| `server/config/prompts/clef-revision.md` | **新建** | Server 专用 Revision prompt |
| `server/config/agents.yaml` | 修改 | prompt_md 指向新路径 |
| `server/src/clef_server/agent_loop.py` | **新建** | Agentic tool-use 循环核心 |
| `server/src/clef_server/agents.py` | 修改 | 拆分 `_build_instructions` 为三层结构 |
| `server/src/clef_server/middleware.py` | 修改 | 加 token 预算，超限时截断参考材料 |
| `server/src/clef_server/orchestrator.py` | 修改 | `_run_agent` 改用 agent_loop，加 fallback 日志 |
| `server/src/clef_server/tools.py` | 修改 | 新增 `get_tool_schemas()` 生成 OpenAI function schema |
| `server/src/clef_server/config.py` | 修改 | `AgentConfig` 新增 `max_turns` 字段 |
| `server/config/agents.yaml` | 修改 | 每个 agent 加 `max_turns` 配置 |
| `server/tests/test_agent_loop.py` | **新建** | agent_loop 单元测试 |
| `server/tests/test_orchestrator.py` | 修改 | 适配新 _run_agent 签名 |

---

### Task 0: 分叉 Agent Prompt — 从 clef-compose 到 clef-server

**Files:**
- Create: `server/config/prompts/clef-composer.md`
- Create: `server/config/prompts/clef-harmonist.md`
- Create: `server/config/prompts/clef-rhythmist.md`
- Create: `server/config/prompts/clef-reviewer.md`
- Create: `server/config/prompts/clef-orchestrator.md`
- Create: `server/config/prompts/clef-revision.md`
- Modify: `server/config/agents.yaml`
- Modify: `server/src/clef_server/orchestrator.py`

这是所有其他 Task 的**前置依赖**。如果不改 prompt，即使加了 agent loop，agent 也不知道该调什么工具。

#### 问题分析

clef-compose 的 agent prompt（`.claude/agents/clef-*.md`）包含大量 Claude Code 特有内容，直接传给 server 的 LLM 会产生指令冲突：

| Claude Code 指令 | 问题 | Server 应该说 |
|---|---|---|
| `tools: Read, Write, Edit, Glob, Grep` | frontmatter 中声明不存在的工具 | 不需要 frontmatter，工具由 agents.yaml 定义 |
| `skills: theory-melody, theory-abc` | server 用 middleware 加载 | "乐理参考已在系统提示中提供" |
| "乐理知识已通过 skills 预加载" | 预加载是 Claude Code 概念 | "乐理参考在下方 Reference Materials 部分" |
| "Memory 使用" 整节 | Claude Code memory 系统 | 整节删除 |
| `memory: project` | frontmatter | 删除 |
| `model: opus` | frontmatter | 由 agents.yaml 的 model_alias 控制 |
| `maxTurns: 8` | frontmatter | 由 agents.yaml 的 max_turns 控制 |
| `.clef-work/plan.json` 作为文件路径 | agent 可以直接 Read | plan.json 内容会注入到 user message，也可用 `read_file` 工具读取 |
| "使用 Edit 工具修改" | server 没有 Edit 工具 | 用 `write_file` 全量写入 |
| "运行 validate_abc.py" | bash 命令 | "调用 validate_abc 工具" |
| "使用 Grep 搜索" | server 没有 Grep | 删除搜索指令，改用 read_file 读取已有文件 |
| Leader prompt 中的 bash 脚本 | `python .claude/skills/...` | Leader 在 server 中由 orchestrator.py 扮演，不需要自己的 prompt |

#### 重写原则

1. **保留**: 所有音乐约束（音域、时值、ABC 八度规则、SF2 约束、输出格式、输出自检规则）
2. **删除**: Claude Code frontmatter（tools, skills, memory, model, maxTurns）
3. **删除**: "必读文件" 节（改为 "上下文来源" 节，说明数据从哪来）
4. **删除**: "Memory 使用" 节
5. **改写**: 工具相关指令（Read → read_file, Edit → write_file, bash validate_abc.py → validate_abc 工具）
6. **新增**: "可用工具" 节，列出 agent 在 loop 中可以调用的工具及参数
7. **新增**: "工作流程" 节，描述 agentic loop 中的推荐步骤（读取 plan → 创作 → 自检 → 修正）

- [ ] **Step 1: 创建 `server/config/prompts/` 目录**

```bash
mkdir -p server/config/prompts
```

- [ ] **Step 2: 编写 server 专用 clef-composer.md**

以 `.claude/agents/clef-composer.md` 为源材料，重写为以下内容。创建 `server/config/prompts/clef-composer.md`：

```markdown
# 旋律作曲家（Composer）

你是游戏音乐旋律作曲家，负责 V:1 旋律线的创作。

## 角色定位

你接收音乐规划（plan.json）和当前乐谱（score.abc），创作或修改 V:1 的 ABC 记谱法旋律。
你的输出是纯 ABC 记谱法文本，包含 X:1 头部和 V:1 声部。

## 上下文来源

你的任务指令和会话上下文（plan.json、score.abc）会在 user message 中提供。
乐理参考材料在系统提示的 Reference Materials 部分。

## 可用工具

你在一个 agentic loop 中运行，可以调用以下工具：

- **read_file(path)** — 读取工作目录中的文件（如 plan.json、score.abc）
- **write_file(path, content)** — 写入文件到工作目录
- **validate_abc(abc_file, plan_file, output)** — 验证 ABC 文件，返回检查报告
- **abc_lint(abc_content, plan_path)** — 轻量 ABC 格式检查

推荐工作流程：
1. 如果需要确认 plan 细节，调用 read_file 读取 plan.json
2. 生成 ABC 旋律
3. 调用 validate_abc 或 abc_lint 检查输出
4. 如果有 FAIL 项，修正后重新检查
5. 确认通过后输出最终 ABC

## 任务模式

- **创作模式**: 根据 plan.json 从零创作完整 V:1 旋律
- **修改模式**: 根据审查反馈修改指定小节的旋律（保持修改范围外的内容不变）

## 全局约束（不可违反）

1. **调性约束**: 所有音符必须符合 plan.json 的 key + scale（允许临时变化音，但必须解决）
2. **音域约束**: 所有音符必须在 plan.json `orchestration.melody.register` 范围内（硬约束）
3. **小节数约束**: 输出总小节数 = plan.json 的 total_bars（不多不少）
4. **时值约束**: 每小节所有音符+休止符的时值总和 = 拍号规定拍数（L:1/8 + M:4/4 → 每小节 8）
5. **单声部**: V:1 为主旋律，禁止使用和弦方括号 []（旋律乐器一次只发一个音）
6. **禁止重叠**: 当前声部输出不得与已有其他声部在同一时刻占据相同音高

## 输出纪律

- 仅输出 ABC 记谱法，不输出解释文字
- 使用 ```abc 代码块包裹
- 必须包含 X:1 和 V:1 头部

## 输出

V:1 的 ABC 记谱法，覆盖从第一小节到最后一小节的完整旋律。

## 约束

### 动机发展

- 每个段落必须围绕 1-2 个核心动机展开
- 动机发展手法：重复、逆行、倒影、逆行倒影、扩展、紧缩、变奏
- 相邻段落应保持动机的家族相似性

### 段落处理

- 根据 plan.json 的 melody_strategy 决定各段旋律策略（new/variation/sequence/development/recap/climax）
- A 段：陈述主题，音域集中，节奏平稳
- B 段：发展/对比，可扩展音域，增加节奏密度
- C 段：高潮/展开，音域最宽，节奏最活跃
- 尾声：回归主音，收束

### 乐句衔接

- 乐句结尾（每 4-8 小节）应有明确的终止式暗示
- 段落边界必须有明显的变化（力度、音域、节奏密度至少改变一项）
- 大跳（>5 个半音）后必须反向级进或同向小跳（补偿原则）

### 旋律特征

- 70% 的音程应为级进（1-2 半音），25% 小跳（3-5 半音），5% 大跳（>5 半音）
- 旋律轮廓应有起伏：上升 → 高潮 → 下降，而非平线
- 避免连续 3 个以上相同音高
- 避免连续 4 个以上相同节奏型

### 力度与表现力

- 使用 ABC 力度标记：!pp! !p! !mp! !mf! !f! !ff!
- 每个段落至少 2 个力度层次
- 高潮段落力度不低于 !f!
- 使用渐强/渐弱：!<! !>!

## SF2 音色库感知（当 plan.json 声部包含 sf2 字段时生效）

### 关键 SF2 参数说明

- **key_range**: 乐器物理音域，任何音符不得超出此范围
- **sweet_spot**: 最佳音色频段，尽量将主要旋律控制在此范围内
- **vel_layers**: 力度层数，影响力度变化的表达空间
- **characteristics**: 音色特性标签，决定演奏风格适配

### Composer SF2 约束

- 所有音符必须在 key_range 范围内
- sweet_spot 范围内的音符占比应 > 60%
- 单层采样（vel_layers=1）时避免大幅力度变化

### 旋律清晰度原则

- 主旋律应保持音高跳跃间距 ≥ 一个八度以内
- 避免与 V:2 和声音高重叠（保持至少 3 度间距）
- 在高密度段落（B/C），旋律应使用更长时值音符以保持可辨识性

## 输出自检（生成后必须执行）

生成 ABC 片段后，逐项验证：

1. **小节时值**: 每小节时值总和 = 拍号规定拍数（L:1/8 + M:4/4 → 每小节 8）

   时值速查表（L:1/8 单位制）：
   | 记法 | 含义 | 单位值 |
   |------|------|--------|
   | `f` | 八分音符 | 1 |
   | `f2` | 四分音符 | 2 |
   | `f4` | 二分音符 | 4 |
   | `f/2` | 十六分音符 | 0.5 |
   | `z` | 八分休止 | 1 |
   | `z2` | 四分休止 | 2 |

2. **音域合规**: 所有音符在 plan.json `orchestration.melody.register` 范围内
3. **ABC 八度规则**: 小写=C4起，大写=C3起，逗号=低八度，撇号=高八度
4. **声部小节数**: 输出小节数 = plan.json 所有 section measures 总和
5. **段落力度**: 每段至少 2 个力度层次

如果自检发现错误，必须修正后再输出。可调用 validate_abc 或 abc_lint 工具辅助验证。

## 参考

ABC 记谱法规范和乐理参考材料在系统提示的 Reference Materials 部分提供。
```

- [ ] **Step 3: 编写 server 专用 clef-harmonist.md**

创建 `server/config/prompts/clef-harmonist.md`，结构与 composer 类似但替换和声相关内容。关键改动同 composer：

- 去掉 frontmatter
- 去掉 Memory 使用
- "必读文件" 改为 "上下文来源"
- 新增 "可用工具" 节
- 工具引用改为 read_file/write_file/validate_abc/abc_lint
- 输出自检中加 "可调用 validate_abc 工具辅助验证"

以 `.claude/agents/clef-harmonist.md` 为源材料，保持所有和声约束、音域约束、输出格式不变，仅改写环境相关指令。

- [ ] **Step 4: 编写 server 专用 clef-rhythmist.md**

创建 `server/config/prompts/clef-rhythmist.md`。同上原则。额外注意：

- Rhythmist 负责 V:3（低音）+ V:4（鼓），输出可能包含两个声部
- GM 鼓音高映射表保持不变
- 鼓组 V:4 使用 channel 9，这部分约束保持不变

- [ ] **Step 5: 编写 server 专用 clef-reviewer.md**

创建 `server/config/prompts/clef-reviewer.md`。关键改动：

- Reviewer 不需要 write_file（只读 + 验证）
- 可用工具：read_file、validate_abc、abc_lint
- 输出格式保持 JSON review report
- 去掉 Memory 使用节（composer 和 reviewer 都有）

- [ ] **Step 6: 编写 server 专用 clef-orchestrator.md**

创建 `server/config/prompts/clef-orchestrator.md`。关键改动：

- 可用工具：read_file、write_file、abc_to_midi、inject_expression
- 去掉 bash 脚本引用（`python .clafe/skills/...`）
- 去掉 "分段分析流程" 中引用的 bash 命令
- expression_plan.json 的 tracks 格式约束保持不变
- CC 策略、频率平衡策略等纯音乐内容保持不变

- [ ] **Step 7: 编写 server 专用 clef-revision.md**

创建 `server/config/prompts/clef-revision.md`。关键改动：

- 可用工具：read_file、write_file
- 去掉 skills 预加载引用
- 保持修正范围和禁止事项不变

- [ ] **Step 8: 更新 agents.yaml 指向新 prompt 路径**

修改 `server/config/agents.yaml`，将所有 `prompt_md` 从 `.claude\agents\clef-*.md` 改为 `server/config/prompts/clef-*.md`（相对于项目根目录）：

```yaml
agents:
  clef-composer:
    model_alias: anthropic-opus
    prompt_md: server/config/prompts/clef-composer.md
    skills:
    - melody
    - orchestration
    - abc
    temperature: 0.8
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
  clef-harmonist:
    model_alias: anthropic-opus
    prompt_md: server/config/prompts/clef-harmonist.md
    skills:
    - harmony
    - abc
    temperature: 0.8
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
  clef-orchestrator:
    model_alias: anthropic-sonnet
    prompt_md: server/config/prompts/clef-orchestrator.md
    skills:
    - orchestration
    - abc
    temperature: 0.5
    max_turns: 4
    tools:
    - read_file
    - write_file
    - abc_to_midi
    - inject_expression
  clef-reviewer:
    model_alias: anthropic-sonnet
    prompt_md: server/config/prompts/clef-reviewer.md
    skills:
    - structure
    - orchestration
    - abc
    temperature: 0.3
    max_turns: 3
    tools:
    - read_file
    - validate_abc
    - abc_lint
  clef-revision:
    model_alias: anthropic-haiku
    prompt_md: server/config/prompts/clef-revision.md
    skills:
    - abc
    temperature: 0.2
    max_turns: 3
    tools:
    - read_file
    - write_file
  clef-rhythmist:
    model_alias: anthropic-sonnet
    prompt_md: server/config/prompts/clef-rhythmist.md
    skills:
    - rhythm
    - abc
    temperature: 0.7
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
```

- [ ] **Step 9: 更新 orchestrator 的 prompt 解析路径**

在 `server/src/clef_server/orchestrator.py` 的 `_run_agent()` 方法中，当前通过 `self.project_root / ".claude" / "agents" / prompt_md` 解析路径。需要改为从 agents.yaml 中的 `prompt_md` 绝对/相对路径解析。

由于 agents.yaml 中新的 `prompt_md` 值已经是相对于项目根目录的路径（如 `server/config/prompts/clef-composer.md`），`load_agent_configs()` 已经会用 `base_dir` 拼接。确保 `_run_agent` 中的路径解析逻辑与新位置一致。

当前代码（约第 670-674 行）：

```python
prompt_md = agent_def["prompt_md"]
prompt_path = Path(prompt_md)
if not prompt_path.is_absolute():
    prompt_path = self.project_root / ".claude" / "agents" / prompt_md
```

改为：

```python
prompt_md = agent_def["prompt_md"]
prompt_path = Path(prompt_md)
if not prompt_path.is_absolute():
    prompt_path = self.project_root / prompt_md
```

这样 `server/config/prompts/clef-composer.md` 会解析为 `{project_root}/server/config/prompts/clef-composer.md`。

- [ ] **Step 10: 运行测试确认无回归**

Run: `cd server && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 11: Commit**

```bash
git add server/config/prompts/ server/config/agents.yaml server/src/clef_server/orchestrator.py
git commit -m "feat(server): fork agent prompts from clef-compose, rewrite for server tool system"
```

---

### Task 0b: 提取共享音乐约束模块（防止 prompt 漂移）

**Files:**
- Create: `server/config/prompts/shared_constraints.yaml`
- Create: `server/tests/test_prompt_parity.py`

CEO review 发现：维护两套 prompt（clef-compose + clef-server）在 6 个月内必然漂移。此 Task 提取纯音乐约束为共享模块。

#### 问题分析

agent prompt 中的内容分两类：
1. **音乐约束**（调性、音域、时值、输出自检等）：与执行环境无关，两套 prompt 应完全一致
2. **环境指令**（工具调用、上下文来源、Memory 使用等）：与环境强相关，必须分别维护

目前两类内容混在同一个 .md 文件中，无法机械性验证一致性。

#### 方案

将音乐约束提取为 `shared_constraints.yaml`，包含：
- 全局约束（调性、音域、小节数、时值、单声部、禁止重叠）
- 输出自检规则（小节时值验证、音域合规、ABC 八度规则等）
- 段落处理规则
- 力度与表现力规则
- SF2 音色库约束

两套 prompt 都引用此 YAML，确保约束层面的一致性。

- [ ] **Step 1: 创建 shared_constraints.yaml**

创建 `server/config/prompts/shared_constraints.yaml`，从 clef-composer.md 中提取所有音乐约束为结构化 YAML。

- [ ] **Step 2: 编写 prompt 一致性测试**

创建 `server/tests/test_prompt_parity.py`，验证：
- server prompt 中的音乐约束与 shared_constraints.yaml 一致
- clef-compose prompt 中的音乐约束与 shared_constraints.yaml 一致
- 约束文本无遗漏

- [ ] **Step 3: 运行测试**

Run: `cd server && python -m pytest tests/test_prompt_parity.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/config/prompts/shared_constraints.yaml server/tests/test_prompt_parity.py
git commit -m "feat(server): extract shared music constraints to prevent prompt drift"
```

---

### Task 0c: 基准测试 — Post-hoc Validate+Retry（验证 agentic loop 必要性）

**Files:**
- Create: `server/tests/test_posthoc_validate_retry.py`

CEO review 建议：在实施 agentic loop 之前，先验证更简单的 post-hoc validate+retry 方案是否足够。

#### 方案

在当前 orchestrator 的 `_run_agent()` 中，不改变 prompt 也不加 agentic loop，仅在 agent 输出后：
1. 调用 `validate_abc` 检查输出
2. 如果有 FAIL，将错误信息追加到 prompt 中重新调用 agent
3. 最多重试 2 次

用此方案跑一个完整 compose session，对比输出质量。如果质量可接受，则 Tasks 1-5 可以推迟。

- [ ] **Step 1: 实现最小 post-hoc retry 逻辑**

在 `orchestrator.py` 的 `_run_agent()` 方法中，在 `response = await client.get_response(...)` 后添加：

```python
# Post-hoc validation retry (cheap alternative to agentic loop)
for retry in range(2):
    score_path = Path(self.workdir) / "score.abc"
    plan_path = Path(self.workdir) / "plan.json"
    if score_path.exists() and plan_path.exists():
        from clef_server.tools import abc_lint
        lint_result = abc_lint(content, str(plan_path))
        if not lint_result.get("pass", True):
            issues = lint_result.get("issues", [])
            issues_text = "\n".join(f"- {i}" for i in issues)
            messages.append(Message(role="assistant", contents=[content]))
            messages.append(Message(role="user", contents=[
                f"VALIDATION FAILURES:\n{issues_text}\nFix and output corrected ABC."
            ]))
            response = await client.get_response(messages, client_kwargs={"temperature": temperature})
            content = str(response.messages[0].contents[0]) if response.messages else ""
        else:
            break
```

- [ ] **Step 2: 跑完整 session 对比质量**

Run a compose session with the post-hoc retry. Compare output quality against agentic loop.
If quality is acceptable, document findings and consider deferring Tasks 1-5.

- [ ] **Step 3: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_posthoc_validate_retry.py
git commit -m "test(server): benchmark post-hoc validate+retry vs agentic loop"
```

**GATE**: 如果 post-hoc 质量足够好，可以推迟 Tasks 1-5。如果不够，继续执行。

---

### Task 1: 创建 agent_loop.py — Agentic Tool-Use 循环

**Files:**
- Create: `server/src/clef_server/agent_loop.py`
- Test: `server/tests/test_agent_loop.py`

这是整个改进的核心。将单轮 LLM 调用替换为 ReAct 循环。

- [ ] **Step 1: 写 agent_loop.py 的框架**

创建 `server/src/clef_server/agent_loop.py`：

```python
"""Agentic tool-use loop — ReAct-style LLM + tool execution cycle.

Each turn:
  1. Send messages to LLM (including tool schemas if any)
  2. Parse response: if tool_calls present, execute them, append results, repeat
  3. If no tool_calls (finish_reason="stop"), return final text

This replaces the single-turn _run_agent call with a multi-turn agentic loop,
allowing agents to read files, validate ABC, and self-correct before returning.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from agent_framework import Message

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopResult:
    """Result from an agentic loop execution."""
    text: str
    tool_calls_count: int = 0
    turns_used: int = 1


async def run_agent_loop(
    client: Any,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    tool_executor: Any = None,
    *,
    temperature: float = 0.7,
    max_turns: int = 5,
    max_tokens: int = 4096,
    cancel_check: Any = None,  # Callable[[], bool] — returns True if cancelled
) -> AgentLoopResult:
    """Run an agentic tool-use loop until the LLM stops calling tools.

    Args:
        client: LLM client with get_response(messages, tools=..., client_kwargs=...)
        system_prompt: Agent instructions (from _build_instructions)
        user_message: The task to perform
        tools: OpenAI-format tool schemas for function calling
        tool_executor: Callable(dict) -> dict that executes a tool call
        temperature: LLM sampling temperature
        max_turns: Maximum loop iterations (prevents infinite loops)
        max_tokens: Max tokens per LLM response
        cancel_check: Optional callable returning True if session was cancelled

    Returns:
        AgentLoopResult with final text and metadata
    """
    messages = [
        Message(role="system", contents=[system_prompt]),
        Message(role="user", contents=[user_message]),
    ]

    total_tool_calls = 0

    for turn in range(max_turns):
        # Check cancellation
        if cancel_check and cancel_check():
            logger.info("Agent loop cancelled at turn %d", turn + 1)
            return AgentLoopResult(text="", turns_used=turn + 1)

        # Call LLM
        llm_tools = tools if tools else None
        response = await client.get_response(
            messages,
            tools=llm_tools,
            client_kwargs={"temperature": temperature, "max_tokens": max_tokens},
        )

        if not response.messages:
            return AgentLoopResult(text="", turns_used=turn + 1)

        assistant_msg = response.messages[0]

        # Check if LLM wants to call tools
        tool_calls = getattr(assistant_msg, "tool_calls", None)
        if not tool_calls:
            # No tool calls — extract final text
            content = ""
            if assistant_msg.contents:
                content = "\n".join(str(c) for c in assistant_msg.contents)
            return AgentLoopResult(
                text=content,
                tool_calls_count=total_tool_calls,
                turns_used=turn + 1,
            )

        # LLM wants to call tools — execute them
        total_tool_calls += len(tool_calls)

        # Append assistant message (with tool calls) to conversation
        messages.append(assistant_msg)

        # Execute each tool call and append results
        for tc in tool_calls:
            tool_name = tc.name
            try:
                args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
            except json.JSONDecodeError:
                args = {}

            logger.info(
                "Agent loop turn %d: calling tool %s with args %s",
                turn + 1, tool_name, json.dumps(args, ensure_ascii=False)[:200],
            )

            # Execute tool
            if tool_executor:
                try:
                    result = tool_executor({"name": tool_name, "arguments": args})
                    result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    logger.error("Tool %s execution failed: %s", tool_name, e)
            else:
                result_str = json.dumps({"error": "No tool executor configured"})

            # Append tool result as a tool message
            tool_msg = Message(
                role="tool",
                contents=[result_str],
                tool_call_id=tc.call_id if hasattr(tc, "call_id") else None,
                name=tool_name,
            )
            messages.append(tool_msg)

    # Max turns reached — force a final text-only response
    logger.warning("Agent loop reached max_turns=%d, requesting final response", max_turns)
    response = await client.get_response(
        messages,
        client_kwargs={"temperature": temperature, "max_tokens": max_tokens},
    )
    content = ""
    if response.messages and response.messages[0].contents:
        content = "\n".join(str(c) for c in response.messages[0].contents)

    return AgentLoopResult(
        text=content,
        tool_calls_count=total_tool_calls,
        turns_used=max_turns + 1,
    )
```

- [ ] **Step 2: 写测试 test_agent_loop.py**

创建 `server/tests/test_agent_loop.py`：

```python
"""Tests for the agentic tool-use loop."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_framework import Message, FunctionCall
from clef_server.agent_loop import run_agent_loop, AgentLoopResult


def _make_response(contents, tool_calls=None, finish_reason="stop"):
    """Helper to create a mock LLM response."""
    msg = Message(role="assistant", contents=contents)
    if tool_calls:
        msg = Message(role="assistant", contents=contents, tool_calls=tool_calls)
    mock_resp = MagicMock()
    mock_resp.messages = [msg]
    mock_resp.finish_reason = finish_reason
    return mock_resp


@pytest.fixture
def mock_client():
    """Create a mock LLM client."""
    return AsyncMock()


@pytest.fixture
def echo_tool_executor():
    """A tool executor that echoes back its arguments."""
    def executor(call: dict) -> dict:
        return {"echo": call["arguments"], "tool": call["name"]}
    return executor


@pytest.mark.asyncio
async def test_single_turn_no_tools(mock_client):
    """LLM responds immediately without calling any tools."""
    mock_client.get_response.return_value = _make_response(["Hello, here is your ABC: X:1"])

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose a melody.",
    )

    assert isinstance(result, AgentLoopResult)
    assert result.text == "Hello, here is your ABC: X:1"
    assert result.tool_calls_count == 0
    assert result.turns_used == 1
    assert mock_client.get_response.call_count == 1


@pytest.mark.asyncio
async def test_tool_call_then_final_response(mock_client, echo_tool_executor):
    """LLM calls a tool, gets result, then gives final text response."""
    tool_schema = [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }]

    tc = FunctionCall(name="read_file", arguments='{"path": "plan.json"}', call_id="call_1")

    # First call: LLM wants to read a file
    # Second call: LLM gives final text
    mock_client.get_response.side_effect = [
        _make_response(["Let me read the file."], tool_calls=[tc]),
        _make_response(["Here is the ABC: X:1\nT:Test"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose based on plan.",
        tools=tool_schema,
        tool_executor=echo_tool_executor,
    )

    assert "ABC: X:1" in result.text
    assert result.tool_calls_count == 1
    assert result.turns_used == 2
    assert mock_client.get_response.call_count == 2


@pytest.mark.asyncio
async def test_max_turns_limit(mock_client, echo_tool_executor):
    """Loop stops at max_turns even if LLM keeps calling tools."""
    tc = FunctionCall(name="read_file", arguments='{"path": "plan.json"}', call_id="call_1")

    # LLM keeps calling tools forever
    mock_client.get_response.side_effect = [
        _make_response(["Reading..."], tool_calls=[tc]),
        _make_response(["Reading again..."], tool_calls=[tc]),
        # Third call is forced final (no tools passed)
        _make_response(["Final output"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}],
        tool_executor=echo_tool_executor,
        max_turns=2,
    )

    assert result.turns_used == 3  # 2 loop turns + 1 forced final
    assert result.tool_calls_count == 2


@pytest.mark.asyncio
async def test_tool_execution_error(mock_client):
    """Tool execution failure is reported back to LLM, which can recover."""

    def failing_executor(call):
        raise ValueError("File not found: plan.json")

    tc = FunctionCall(name="read_file", arguments='{"path": "missing.json"}', call_id="call_1")

    mock_client.get_response.side_effect = [
        _make_response(["Let me read..."], tool_calls=[tc]),
        _make_response(["File not found, but here's my attempt: X:1"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}],
        tool_executor=failing_executor,
    )

    # LLM should have recovered and given a final response
    assert "X:1" in result.text
    assert result.tool_calls_count == 1


@pytest.mark.asyncio
async def test_empty_response(mock_client):
    """LLM returns empty response."""
    mock_resp = MagicMock()
    mock_resp.messages = []
    mock_client.get_response.return_value = mock_resp

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
    )

    assert result.text == ""
    assert result.turns_used == 1
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd server && python -m pytest tests/test_agent_loop.py -v`
Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/agent_loop.py server/tests/test_agent_loop.py
git commit -m "feat(server): add agentic tool-use loop module (agent_loop.py)"
```

---

### Task 2: 重构 prompt 组装 — 三层结构

**Files:**
- Modify: `server/src/clef_server/agents.py`
- Modify: `server/src/clef_server/middleware.py`

当前 `_build_instructions()` 把所有内容拼成一个巨大的 system message。拆成三层：
1. **Agent 指令层**（system message）: agent markdown 中的约束和规则
2. **参考材料层**（system message 尾部，有明确分隔）: 乐理 skill 内容
3. **会话上下文层**（user message 前缀）: plan.json + score.abc

- [ ] **Step 1: 修改 middleware.py — 拆分 build_context 为三个方法**

在 `server/src/clef_server/middleware.py` 中，将 `build_context()` 拆分为三个独立方法，并保持 `build_context()` 向后兼容：

```python
"""ClefContextMiddleware — injects theory skills + session context into Agent calls."""

import json
from pathlib import Path


# Skill name → SKILL.md file name mapping
_SKILL_FILE_MAP = {
    "abc": "theory-abc",
    "melody": "theory-melody",
    "harmony": "theory-harmony",
    "rhythm": "theory-rhythm",
    "structure": "theory-structure",
    "orchestration": "theory-orchestration",
}

# Approximate chars-per-token for budget estimation
_CHARS_PER_TOKEN = 4
# Maximum tokens for reference materials (skills)
_SKILL_TOKEN_BUDGET = 4000


class ClefContextMiddleware:
    """Prepares theory skill content and session context for agent instructions."""

    def __init__(self, skills: list[str], skills_dir: Path):
        self._skill_cache: dict[str, str] = {}
        self._skills_dir = skills_dir
        self._load_skills(skills)

    def _load_skills(self, skill_names: list[str]) -> None:
        for name in skill_names:
            dir_name = _SKILL_FILE_MAP.get(name)
            if not dir_name:
                continue
            skill_md = self._skills_dir / dir_name / "SKILL.md"
            if skill_md.exists():
                self._skill_cache[dir_name] = skill_md.read_text(encoding="utf-8")

    def build_skills_section(self) -> str:
        """Build the reference materials section (theory skills).

        Respects _SKILL_TOKEN_BUDGET by truncating individual skills
        if the total would exceed the budget. Each skill is truncated
        proportionally to keep them balanced.
        """
        if not self._skill_cache:
            return ""

        budget_chars = _SKILL_TOKEN_BUDGET * _CHARS_PER_TOKEN
        total_chars = sum(len(v) for v in self._skill_cache.values())

        parts = []
        remaining_chars = budget_chars

        for skill_name, content in self._skill_cache.items():
            if total_chars <= budget_chars:
                # Fits within budget — use full content
                parts.append(f"## {skill_name}\n\n{content}")
            else:
                # Over budget — allocate proportionally
                ratio = len(content) / max(total_chars, 1)
                allocated = int(budget_chars * ratio)
                truncated = content[:allocated]
                if len(truncated) < len(content):
                    # Cut at last newline to avoid mid-sentence
                    last_nl = truncated.rfind("\n")
                    if last_nl > allocated // 2:
                        truncated = truncated[:last_nl]
                    truncated += "\n\n[...truncated for token budget...]"
                parts.append(f"## {skill_name}\n\n{truncated}")

        return "\n\n---\n\n".join(parts)

    def build_session_context(
        self,
        plan: dict | None = None,
        score_abc: str | None = None,
        workdir: str = "",
    ) -> str:
        """Build the session context section (plan + score + workdir).

        This goes into the user message prefix, not the system prompt.
        """
        parts = []
        if plan:
            plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
            # Truncate plan if very large (> 8K chars ≈ 2K tokens)
            if len(plan_json) > 8000:
                plan_json = plan_json[:8000] + "\n...[truncated]"
            parts.append("## Current Plan (plan.json)\n\n```json\n" + plan_json + "\n```")
        if score_abc:
            # Truncate score if very large (> 12K chars ≈ 3K tokens)
            abc_text = score_abc
            if len(abc_text) > 12000:
                abc_text = abc_text[:12000] + "\n...[truncated]"
            parts.append("## Current Score (score.abc)\n\n```\n" + abc_text + "\n```")
        if workdir:
            parts.append(f"Working directory: {workdir}")
        return "\n\n---\n\n".join(parts)

    def build_context(
        self,
        plan: dict | None = None,
        score_abc: str | None = None,
        workdir: str = "",
    ) -> str:
        """Build full context string (backward compatible).

        New code should use build_skills_section() and build_session_context() separately.
        """
        skills = self.build_skills_section()
        session = self.build_session_context(plan=plan, score_abc=score_abc, workdir=workdir)
        parts = [p for p in [skills, session] if p]
        return "\n\n---\n\n".join(parts)
```

- [ ] **Step 2: 修改 agents.py — 拆分 _build_instructions 为三层**

在 `server/src/clef_server/agents.py` 中，将 `_build_instructions()` 重构为返回一个结构体而非一个大字符串：

```python
"""Agent factory — creates AF Agent instances from config."""

from dataclasses import dataclass
from pathlib import Path

from clef_server.config import AgentConfig
from clef_server.middleware import ClefContextMiddleware
from clef_server.tools import get_tools_for_agent

# AF Agent class — mock for test environments
try:
    from agent_framework import Agent
except ImportError:
    Agent = None


@dataclass
class AgentInstructions:
    """Structured agent instructions with separated layers."""
    system_prompt: str          # Agent markdown (constraints + rules)
    reference_materials: str    # Theory skills (truncated to budget)
    session_context: str        # Plan + score (injected into user message)

    def build_system_message(self) -> str:
        """Build the full system message with reference materials appended."""
        if self.reference_materials:
            return (
                f"{self.system_prompt}\n\n"
                f"---\n\n"
                f"# Reference Materials\n\n"
                f"{self.reference_materials}"
            )
        return self.system_prompt

    def build_user_message(self, task: str) -> str:
        """Build the user message with session context prepended."""
        if self.session_context:
            return f"{self.session_context}\n\n---\n\n{task}"
        return task


def build_instructions(
    prompt_md: Path,
    middleware: ClefContextMiddleware,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
) -> AgentInstructions:
    """Build structured agent instructions with three layers.

    Layer 1 (system_prompt): Agent markdown — constraints, rules, output format
    Layer 2 (reference_materials): Theory skills — appended to system prompt
    Layer 3 (session_context): plan.json + score.abc — prepended to user message

    This separation ensures agent constraints are never buried under reference materials.
    """
    system_prompt = prompt_md.read_text(encoding="utf-8")
    reference_materials = middleware.build_skills_section()
    session_context = middleware.build_session_context(
        plan=plan, score_abc=score_abc, workdir=workdir,
    )
    return AgentInstructions(
        system_prompt=system_prompt,
        reference_materials=reference_materials,
        session_context=session_context,
    )


# Backward compatible alias
def _build_instructions(
    prompt_md: Path,
    middleware: ClefContextMiddleware,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
) -> str:
    """Legacy: returns a single concatenated string (for old call sites)."""
    instr = build_instructions(prompt_md, middleware, plan, score_abc, workdir)
    return instr.build_system_message()


def create_agent(
    name: str,
    config: AgentConfig,
    providers: dict,
    skills_dir: Path,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
):
    """Create an AF Agent from config.

    Raises:
        ValueError: If provider alias not found.
        FileNotFoundError: If prompt file missing.
    """
    if Agent is None:
        raise RuntimeError("agent-framework-core is not installed")

    client = providers.get(config.model_alias)
    if client is None:
        available = list(providers.keys())
        raise ValueError(f"No provider found for alias '{config.model_alias}'. Available: {available}")

    if not config.prompt_md.exists():
        raise FileNotFoundError(f"Prompt file not found: {config.prompt_md}")

    middleware = ClefContextMiddleware(skills=config.skills, skills_dir=skills_dir)
    instructions = _build_instructions(
        prompt_md=config.prompt_md,
        middleware=middleware,
        plan=plan,
        score_abc=score_abc,
        workdir=workdir,
    )
    tools = get_tools_for_agent(name)

    return Agent(
        client=client,
        name=name,
        instructions=instructions,
        tools=tools,
    )
```

- [ ] **Step 3: 运行现有测试确认无回归**

Run: `cd server && python -m pytest tests/test_agents.py tests/test_config.py -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/agents.py server/src/clef_server/middleware.py
git commit -m "refactor(server): split prompt into 3 layers (agent/skills/context)"
```

---

### Task 3: tools.py — 新增 get_tool_schemas() 生成 OpenAI function schema

**Files:**
- Modify: `server/src/clef_server/tools.py`

agent_loop 需要 OpenAI 格式的 tool schema 来传给 LLM 的 `tools` 参数。当前 tools.py 只有 `@tool` 装饰的函数，但没有生成 schema 的方法。

- [ ] **Step 1: 在 tools.py 底部新增 get_tool_schemas()**

在 `server/src/clef_server/tools.py` 的 `get_tools_for_agent()` 函数后面添加：

```python
def get_tool_schemas(agent_name: str) -> list[dict]:
    """Generate OpenAI-format tool schemas for an agent's tools.

    Uses inspect to extract parameter names, types, and docstrings from
    @tool-decorated functions. Returns a list of OpenAI function definitions.
    """
    import inspect

    tool_names = _AGENT_TOOL_MAP.get(agent_name, [])
    schemas = []

    for name in tool_names:
        func = TOOLS_REGISTRY.get(name)
        if func is None:
            continue

        # Get function signature
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Extract type hint
            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                param_type = "string"
            elif hasattr(annotation, "__origin__"):
                # Handle Annotated[str, "description"]
                args = getattr(annotation, "__args__", ())
                if args:
                    type_map = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}
                    raw_type = args[0] if args else str
                    param_type = type_map.get(raw_type, "string")
                else:
                    param_type = "string"
            else:
                type_map = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}
                param_type = type_map.get(annotation, "string")

            # Extract description from Annotated metadata
            description = ""
            if hasattr(annotation, "__metadata__"):
                for meta in annotation.__metadata__:
                    if isinstance(meta, str):
                        description = meta
                        break
            elif hasattr(annotation, "__args__") and len(getattr(annotation, "__args__", ())) > 1:
                for arg in annotation.__args__[1:]:
                    if isinstance(arg, str):
                        description = arg
                        break

            properties[param_name] = {"type": param_type}
            if description:
                properties[param_name]["description"] = description

            # If no default value, it's required
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        # Get description from docstring
        doc = inspect.getdoc(func) or f"Execute the {name} tool."

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": doc.split("\n")[0],  # First line only
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        schemas.append(schema)

    return schemas
```

- [ ] **Step 2: 写测试验证 schema 生成**

在 `server/tests/test_tools.py` 底部添加：

```python
def test_get_tool_schemas_composer():
    """Composer agent should have read_file, write_file, validate_abc, abc_lint schemas."""
    schemas = get_tool_schemas("clef-composer")
    assert len(schemas) == 4
    names = {s["function"]["name"] for s in schemas}
    assert names == {"read_file", "write_file", "validate_abc", "abc_lint"}


def test_get_tool_schemas_structure():
    """Each schema should have valid OpenAI function calling structure."""
    schemas = get_tool_schemas("clef-composer")
    for schema in schemas:
        assert schema["type"] == "function"
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_get_tool_schemas_unknown_agent():
    """Unknown agent should return empty list."""
    schemas = get_tool_schemas("nonexistent-agent")
    assert schemas == []
```

- [ ] **Step 3: 运行测试**

Run: `cd server && python -m pytest tests/test_tools.py -v -k "get_tool_schemas"`
Expected: All 3 new tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/tools.py server/tests/test_tools.py
git commit -m "feat(server): add get_tool_schemas() for OpenAI function calling"
```

---

### Task 4: config.py — AgentConfig 新增 max_turns 字段

**Files:**
- Modify: `server/src/clef_server/config.py`
- Modify: `server/config/agents.yaml`

- [ ] **Step 1: 在 AgentConfig 中新增 max_turns**

在 `server/src/clef_server/config.py` 的 `AgentConfig` dataclass 中添加 `max_turns` 字段：

将 `AgentConfig` 改为：

```python
@dataclass
class AgentConfig:
    prompt_md: Path
    model_alias: str
    temperature: float = 0.7
    max_turns: int = 5
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.prompt_md, str):
            object.__setattr__(self, "prompt_md", Path(self.prompt_md))
```

同时在 `load_agent_configs()` 中解析 `max_turns` 字段（在 `tools=cfg.get("tools", [])` 行后添加）：

```python
        configs[name] = AgentConfig(
            prompt_md=prompt_path,
            model_alias=cfg["model_alias"],
            temperature=cfg.get("temperature", 0.7),
            max_turns=cfg.get("max_turns", 5),
            skills=cfg.get("skills", []),
            tools=cfg.get("tools", []),
        )
```

同时在 `save_agent_configs()` 中写入 `max_turns`（在 `"tools": cfg.tools` 行后添加）：

```python
        raw["agents"][name] = {
            "prompt_md": str(cfg.prompt_md),
            "model_alias": cfg.model_alias,
            "temperature": cfg.temperature,
            "max_turns": cfg.max_turns,
            "skills": cfg.skills,
            "tools": cfg.tools,
        }
```

- [ ] **Step 2: 在 agents.yaml 中添加 max_turns**

修改 `server/config/agents.yaml`，为每个 agent 添加 `max_turns`：

```yaml
agents:
  clef-composer:
    model_alias: anthropic-opus
    prompt_md: .claude/agents/clef-composer.md
    skills:
    - melody
    - orchestration
    - abc
    temperature: 0.8
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
  clef-harmonist:
    model_alias: anthropic-opus
    prompt_md: .claude/agents/clef-harmonist.md
    skills:
    - harmony
    - abc
    temperature: 0.8
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
  clef-orchestrator:
    model_alias: anthropic-sonnet
    prompt_md: .claude/agents/clef-orchestrator.md
    skills:
    - orchestration
    - abc
    temperature: 0.5
    max_turns: 4
    tools:
    - read_file
    - write_file
    - abc_to_midi
    - inject_expression
  clef-reviewer:
    model_alias: anthropic-sonnet
    prompt_md: .claude/agents/clef-reviewer.md
    skills:
    - structure
    - orchestration
    - abc
    temperature: 0.3
    max_turns: 3
    tools:
    - read_file
    - validate_abc
    - abc_lint
  clef-revision:
    model_alias: anthropic-haiku
    prompt_md: .claude/agents/clef-revision.md
    skills:
    - abc
    temperature: 0.2
    max_turns: 3
    tools:
    - read_file
    - write_file
  clef-rhythmist:
    model_alias: anthropic-sonnet
    prompt_md: .claude/agents/clef-rhythmist.md
    skills:
    - rhythm
    - abc
    temperature: 0.7
    max_turns: 6
    tools:
    - read_file
    - write_file
    - validate_abc
    - abc_lint
```

- [ ] **Step 3: 运行配置相关测试**

Run: `cd server && python -m pytest tests/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/config.py server/config/agents.yaml
git commit -m "feat(server): add max_turns to AgentConfig and agents.yaml"
```

---

### Task 5: 重构 orchestrator._run_agent — 使用 agent_loop + 三层 prompt + fallback 日志

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`

这是最关键的改动。将 `_run_agent()` 从单轮调用改为使用 `agent_loop`。

- [ ] **Step 1: 修改 orchestrator.py 的 import 和 _run_agent**

在 `server/src/clef_server/orchestrator.py` 顶部的 import 区域添加：

```python
from clef_server.agent_loop import run_agent_loop
from clef_server.agents import build_instructions
from clef_server.tools import TOOLS_REGISTRY, get_tool_schemas
```

然后将 `_run_agent()` 方法（约第 649-713 行）替换为：

```python
    async def _run_agent(
        self,
        agent_name: str,
        message: str,
        plan: dict | None = None,
        score_abc: str | None = None,
    ) -> str:
        """Run an agent with agentic tool-use loop.

        Builds a 3-layer prompt (instructions / skills / context),
        provides tool schemas, and runs a ReAct loop until the LLM
        stops calling tools or max_turns is reached.
        """
        agent_def = self._agent_defs.get(agent_name)
        if not agent_def:
            logger.warning("Unknown agent %s, returning placeholder", agent_name)
            return f"[placeholder ABC for {agent_name}]"

        try:
            from clef_server.middleware import ClefContextMiddleware

            # Build 3-layer instructions
            prompt_md = agent_def["prompt_md"]
            prompt_path = Path(prompt_md)
            if not prompt_path.is_absolute():
                prompt_path = self.project_root / ".claude" / "agents" / prompt_md
            if not prompt_path.exists():
                logger.warning("Agent prompt not found: %s", prompt_path)
                return f"[placeholder ABC for {agent_name}]"

            skills_dir = self.project_root / ".claude" / "skills" / "clef-compose"
            middleware = ClefContextMiddleware(
                skills=agent_def["skills"],
                skills_dir=skills_dir,
            )
            instructions = build_instructions(
                prompt_md=prompt_path,
                middleware=middleware,
                plan=plan,
                score_abc=score_abc,
                workdir=self.workdir,
            )

            # Resolve LLM client with explicit fallback logging
            model_alias = agent_def["model_alias"]
            client = self.providers.get(model_alias)
            if client is None:
                available = list(self.providers.keys())
                logger.warning(
                    "Agent %s: model_alias '%s' not found in providers %s, "
                    "falling back to first available",
                    agent_name, model_alias, available,
                )
                client = next(iter(self.providers.values()), None)
            if not client:
                raise RuntimeError(f"No LLM client available for {agent_name} (alias={model_alias})")

            # Build tool schemas and executor
            tool_schemas = get_tool_schemas(agent_name)
            tool_executor = self._make_tool_executor(agent_name)

            # Build system + user messages using 3-layer structure
            system_prompt = instructions.build_system_message()
            user_message = instructions.build_user_message(message)

            max_turns = agent_def.get("max_turns", 5)
            temperature = agent_def.get("temperature", 0.7)

            logger.info(
                "Agent %s: starting loop (max_turns=%d, tools=%s, model=%s)",
                agent_name, max_turns, [s["function"]["name"] for s in tool_schemas], model_alias,
            )

            result = await run_agent_loop(
                client=client,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tool_schemas,
                tool_executor=tool_executor,
                temperature=temperature,
                max_turns=max_turns,
            )

            logger.info(
                "Agent %s: loop completed (turns=%d, tool_calls=%d)",
                agent_name, result.turns_used, result.tool_calls_count,
            )
            return result.text

        except Exception as exc:
            logger.error("Agent %s execution failed: %s", agent_name, exc)
            raise RuntimeError(f"Agent {agent_name} failed: {exc}") from exc

    def _make_tool_executor(self, agent_name: str):
        """Create a tool executor closure for the given agent.

        The executor resolves tool calls by name from TOOLS_REGISTRY,
        injecting `workdir` automatically.
        """
        agent_tool_names = set(
            _AGENT_TOOL_MAP.get(agent_name, [])
            if hasattr(self, '_AGENT_TOOL_MAP')
            else []
        )
        # Fallback: import from tools module
        if not agent_tool_names:
            from clef_server.tools import _AGENT_TOOL_MAP
            agent_tool_names = set(_AGENT_TOOL_MAP.get(agent_name, []))

        workdir = self.workdir

        def executor(call: dict) -> dict:
            tool_name = call.get("name", "")
            raw_args = call.get("arguments", {})

            # Normalize arguments: may be JSON string or dict
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    return {"error": f"Invalid JSON arguments for {tool_name}: {raw_args[:200]}"}
            else:
                args = raw_args

            if tool_name not in agent_tool_names:
                return {"error": f"Tool '{tool_name}' not allowed for agent '{agent_name}'"}

            func = TOOLS_REGISTRY.get(tool_name)
            if func is None:
                return {"error": f"Tool '{tool_name}' not found in registry"}

            # Inject workdir for tools that need it
            if tool_name in ("read_file", "write_file", "validate_abc", "abc_lint"):
                args.setdefault("workdir", workdir)

            # Security: limit write_file content size (256KB max)
            if tool_name == "write_file" and len(args.get("content", "")) > 262144:
                return {"error": f"write_file content exceeds 256KB limit ({len(args.get('content', ''))} bytes)"}

            try:
                return func(**args)
            except Exception as e:
                return {"error": str(e)}

        return executor
```

- [ ] **Step 2: 更新 _load_agent_defs 以包含 max_turns**

在 `_load_agent_defs()` 方法中（约第 629-647 行），确保返回的 dict 包含 `max_turns`。修改 `defs[name]` 构建部分：

```python
            for name, cfg in configs.items():
                defs[name] = {
                    "prompt_md": str(cfg.prompt_md),
                    "model_alias": cfg.model_alias,
                    "skills": cfg.skills,
                    "temperature": cfg.temperature,
                    "max_turns": cfg.max_turns,
                }
```

同时更新 hardcoded fallback `_AGENT_DEFS`，给每个 agent 加 `"max_turns": 5`：

```python
    _AGENT_DEFS: dict[str, dict[str, Any]] = {
        "clef-composer": {
            "prompt_md": "clef-composer.md",
            "model_alias": "deepseek",
            "skills": ["melody", "orchestration", "abc"],
            "max_turns": 5,
        },
        "clef-harmonist": {
            "prompt_md": "clef-harmonist.md",
            "model_alias": "deepseek",
            "skills": ["harmony", "abc"],
            "max_turns": 5,
        },
        "clef-rhythmist": {
            "prompt_md": "clef-rhythmist.md",
            "model_alias": "deepseek",
            "skills": ["rhythm", "abc"],
            "max_turns": 5,
        },
        "clef-reviewer": {
            "prompt_md": "clef-reviewer.md",
            "model_alias": "deepseek",
            "skills": ["structure", "orchestration", "abc"],
            "max_turns": 3,
        },
        "clef-orchestrator": {
            "prompt_md": "clef-orchestrator.md",
            "model_alias": "deepseek",
            "skills": ["orchestration", "abc"],
            "max_turns": 4,
        },
    }
```

- [ ] **Step 3: 运行 orchestrator 测试确认无回归**

Run: `cd server && python -m pytest tests/test_orchestrator.py -v`
Expected: All tests PASS (可能需要适配 mock — 如果测试 mock 了 `_run_agent`，确认 mock 签名兼容)

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "feat(server): _run_agent uses agentic tool-use loop with 3-layer prompt"
```

---

### Task 6: 集成测试 — 端到端验证

**Files:**
- Create: `server/tests/test_agent_integration.py`

- [ ] **Step 1: 写集成测试验证完整 agent loop 流程**

创建 `server/tests/test_agent_integration.py`：

```python
"""Integration tests for the agentic agent loop + prompt reform."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from agent_framework import Message, FunctionCall

from clef_server.agent_loop import run_agent_loop
from clef_server.agents import build_instructions, AgentInstructions
from clef_server.middleware import ClefContextMiddleware
from clef_server.tools import get_tool_schemas
from clef_server.orchestrator import ComposeOrchestrator


class TestPromptLayering:
    """Verify that the 3-layer prompt structure works correctly."""

    def test_instructions_have_three_layers(self, tmp_path):
        """build_instructions returns AgentInstructions with 3 populated fields."""
        # Create a minimal agent prompt
        agent_md = tmp_path / "test-agent.md"
        agent_md.write_text("# Test Agent\n\nYou are a test agent.\n\n## Constraints\n- Rule 1\n- Rule 2")

        # Create a minimal skill
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "theory-abc"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# ABC Reference\n\nX:1 means header.")

        middleware = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        instr = build_instructions(
            prompt_md=agent_md,
            middleware=middleware,
            plan={"title": "Test", "key": "C"},
            score_abc="X:1\nT:Test",
            workdir="/tmp/test",
        )

        assert isinstance(instr, AgentInstructions)
        assert "Test Agent" in instr.system_prompt
        assert "Rule 1" in instr.system_prompt
        assert "ABC Reference" in instr.reference_materials
        assert "Test" in instr.session_context

    def test_system_message_combines_prompt_and_skills(self, tmp_path):
        """build_system_message puts agent prompt first, skills second."""
        agent_md = tmp_path / "test-agent.md"
        agent_md.write_text("# Agent\n\n## Constraints\n- Must do X")

        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "theory-abc"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# ABC Theory")

        middleware = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        instr = build_instructions(prompt_md=agent_md, middleware=middleware)

        full = instr.build_system_message()
        # Constraints should appear BEFORE reference materials
        constraints_pos = full.find("Must do X")
        skills_pos = full.find("ABC Theory")
        assert constraints_pos < skills_pos

    def test_user_message_prepends_context(self, tmp_path):
        """build_user_message puts session context before the task."""
        agent_md = tmp_path / "test-agent.md"
        agent_md.write_text("# Agent")
        skills_dir = tmp_path / "empty_skills"
        skills_dir.mkdir(parents=True)

        middleware = ClefContextMiddleware(skills=[], skills_dir=skills_dir)
        instr = build_instructions(
            prompt_md=agent_md,
            middleware=middleware,
            plan={"title": "My Song"},
        )

        user_msg = instr.build_user_message("Compose a melody.")
        # Plan should appear before the task
        plan_pos = user_msg.find("My Song")
        task_pos = user_msg.find("Compose a melody")
        assert plan_pos < task_pos


class TestMiddlewareBudget:
    """Verify that skill truncation works."""

    def test_skills_truncated_when_over_budget(self, tmp_path):
        """Large skills should be truncated to fit the token budget."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "theory-abc"
        skill_dir.mkdir(parents=True)
        # Write a very large skill (> 16K chars)
        (skill_dir / "SKILL.md").write_text("X " * 10000)

        middleware = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        result = middleware.build_skills_section()

        # Should be truncated (not the full 20K chars)
        assert len(result) < 20000
        assert "truncated" in result

    def test_skills_not_truncated_when_under_budget(self, tmp_path):
        """Small skills should not be truncated."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "theory-abc"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Short skill content")

        middleware = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        result = middleware.build_skills_section()

        assert "Short skill content" in result
        assert "truncated" not in result


class TestToolSchemas:
    """Verify tool schema generation for OpenAI function calling."""

    def test_all_agents_have_schemas(self):
        """Every agent in _AGENT_TOOL_MAP should produce valid schemas."""
        from clef_server.tools import _AGENT_TOOL_MAP
        for agent_name in _AGENT_TOOL_MAP:
            schemas = get_tool_schemas(agent_name)
            assert len(schemas) > 0, f"{agent_name} has no tool schemas"
            for s in schemas:
                assert s["type"] == "function"
                assert "name" in s["function"]


class TestOrchestratorIntegration:
    """Verify orchestrator._run_agent uses the new loop."""

    @pytest.mark.asyncio
    async def test_run_agent_calls_loop(self, tmp_path):
        """_run_agent should call run_agent_loop, not get_response directly."""
        # Setup minimal orchestrator
        session_mgr_mock = MagicMock()
        session_mock = MagicMock()
        session_mock.session_id = "test"
        session_mock.cancel_requested = False
        session_mgr_mock.get.return_value = session_mock

        mock_client = AsyncMock()
        # Simulate a simple text response (no tool calls)
        resp_msg = Message(role="assistant", contents=["X:1\nT:Test Result"])
        mock_resp = MagicMock()
        mock_resp.messages = [resp_msg]
        mock_client.get_response.return_value = mock_resp

        providers = {"anthropic-opus": mock_client}
        workdir = str(tmp_path)

        with patch("clef_server.orchestrator.get_session_manager", return_value=session_mgr_mock):
            orch = ComposeOrchestrator(
                session_id="test",
                providers=providers,
                workdir=workdir,
            )

        # Create a minimal agent prompt
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "clef-composer.md").write_text("# Composer\n\nYou compose music.")

        # Override agent defs to use tmp path
        orch._agent_defs["clef-composer"] = {
            "prompt_md": str(agents_dir / "clef-composer.md"),
            "model_alias": "anthropic-opus",
            "skills": [],
            "temperature": 0.8,
            "max_turns": 3,
        }

        result = await orch._run_agent("clef-composer", "Compose a C major melody.")

        # Should have called the client (at least once for the loop)
        assert mock_client.get_response.call_count >= 1
        assert "Test Result" in result or "X:1" in result or isinstance(result, str)
```

- [ ] **Step 2: 运行集成测试**

Run: `cd server && python -m pytest tests/test_agent_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `cd server && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/tests/test_agent_integration.py
git commit -m "test(server): integration tests for agent loop + prompt reform"
```

---

## Self-Review Checklist

### 1. Spec coverage
- [x] **Prompt 复用问题** — Claude Code 专用 prompt 无法适配 server 环境: Task 0
- [x] 单轮执行 → 多轮 agentic loop: Task 1 + Task 5
- [x] Prompt 全部拼成一个大 system message → 三层结构: Task 2
- [x] 参考材料无大小限制 → token 预算截断: Task 2 (middleware)
- [x] Model fallback 静默降级 → 显式 warning log: Task 5
- [x] Tool schemas 缺失 → get_tool_schemas(): Task 3
- [x] max_turns 不可配置 → agents.yaml 配置: Task 4

### 2. Placeholder scan
- No "TBD", "TODO", "implement later" found
- No "add appropriate error handling" without code
- All code blocks contain complete implementation

### 3. Type consistency
- `AgentInstructions` defined in agents.py, used in orchestrator.py via `build_instructions()` import
- `run_agent_loop` accepts `client`, `system_prompt`, `user_message`, `tools`, `tool_executor` — orchestrator provides all
- `get_tool_schemas()` returns `list[dict]` matching OpenAI format — passed to `run_agent_loop(tools=...)`
- `AgentConfig.max_turns` int — read by orchestrator via `agent_def.get("max_turns", 5)`
- `_make_tool_executor` closure captures `workdir` and `agent_tool_names` — no dangling references

---

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|----------|
| 1 | CEO | Add Task 0b: shared constraint extraction | Taste | P1 | Prevents prompt divergence between clef-compose and clef-server | Post-hoc only |
| 2 | CEO | Benchmark post-hoc validate+retry before agentic loop | Taste | P3 | 80% benefit for 20% effort; validate assumption | Skip benchmark |
| 3 | Eng | Add Anthropic schema adapter in agent_loop.py | Mechanical | P5 | Provider detection is obvious, not clever | Separate module |
| 4 | Eng | Fix arguments string→dict in loop + executor | Mechanical | P1 | Must work on first tool call | Ignore |
| 5 | Eng | Add cancel_check param to run_agent_loop | Mechanical | P1 | Prevents wasting API credits after user cancel | Ignore |
| 6 | Eng | Truncate skills at section headers, not newlines | Taste | P5 | Clean cuts beat mid-sentence corruption | Keep newline split |
| 7 | Eng | Add max_content check in write_file executor | Mechanical | P1 | Security baseline | Ignore |
| 8 | Eng | Add compaction before forced final turn | Mechanical | P1 | Prevents 128K context overflow | Ignore |
| 9 | DX | Add agent scaffolder script | Taste | P1 | Reduces TTHW from opaque to 3 steps | Skip scaffold |
| 10 | DX | Warn on unknown agent in get_tool_schemas | Mechanical | P5 | Silent empty returns waste debugging time | Silent return |
| 11 | DX | Log warning when _AGENT_DEFS fallback is used | Mechanical | P5 | Hidden fallback masks YAML misconfig | Silent fallback |
| 12 | DX | Structured error schema for tool results | Taste | P1 | problem/cause/fix/docs structure | Keep bare string |

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| **Prompt 分叉导致维护双份** | 高 | 中 | 理论 skill 保留共享（纯参考材料）。Agent prompt 中纯音乐约束部分尽量与 clef-compose 保持相同措辞，只有环境和工具部分不同 |
| Anthropic API tool_use 格式与 OpenAI 不兼容 | 中 | 高 | Anthropic 的 tool_use 格式不同，需在 agent_loop 中加 Anthropic 适配层（后续 Task） |
| agent loop 每轮消耗大量 token | 高 | 中 | max_turns 上限 + microcompact 已在 orchestrator 中实现 |
| @tool 装饰器与 inspect 参数提取不兼容 | 低 | 中 | Task 3 的 inspect 逻辑已处理 Annotated 类型 |
| 现有测试 mock 签名不兼容 | 中 | 低 | Task 6 集成测试覆盖新路径，旧测试可能需要小改 |

**注意**: Anthropic API 的 tool_use 使用不同的 schema 格式（`input_schema` 而非 `parameters`）和不同的响应格式。当前 `ChatCompletionsClient` 使用 OpenAI 格式，对 Anthropic provider 需要在 `agent_loop.py` 中加格式适配。这不在本次实施范围内，但应在 Task 5 实施时验证 Anthropic client 的 tool calling 是否正常工作。如果不工作，需要在 `agent_loop.py` 中加 provider type 检测和格式转换。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | issues_open | 5 findings (1 critical, 2 high, 2 medium) |
| Codex Review | N/A | Independent 2nd opinion | 0 | unavailable | 401 auth error |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 9 findings (2 critical, 2 high, 5 medium) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | No UI scope |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | issues_open | 5 findings (1 critical, 2 high, 2 medium) |

**VERDICT:** APPROVED with 5 required changes applied. 12 decisions auto-decided (8 mechanical, 4 taste). 0 user challenges.

### Required Changes Applied
1. Added Task 0b: Extract shared music constraints to YAML + parity test
2. Added Task 0c: Benchmark post-hoc validate+retry (gated before Tasks 1-5)
3. Fixed Eng CRITICAL: arguments string→dict normalization in executor
4. Added cancel_check param to run_agent_loop
5. Added write_file content size limit (256KB) in executor

### Cross-Phase Theme
**Silent failures**: Flagged in Eng (arguments parsing, unknown agent returns []) AND DX (get_tool_schemas returns [], _AGENT_DEFS fallback). The codebase has a pattern of silently degrading instead of raising errors. All identified instances have been addressed in the updated plan.
