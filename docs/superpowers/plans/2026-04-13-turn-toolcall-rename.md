# Turn/ToolCall 语义重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `max_turns` 重命名为 `max_tool_calls`，使代码语义与实际行为一致（turn = 完整任务，tool_call = 单次工具调用）。

**Architecture:** 纯重命名重构，不改变运行时行为。涉及 5 个文件：agent_loop.py（核心循环）、config.py（配置加载）、orchestrator.py（调度）、agents.yaml（配置）、test_agent_loop.py（测试）。前端无引用。

**Tech Stack:** Python, pytest, PyYAML

---

## 概念定义（重构后的语义）

| 概念 | 含义 | 在代码中的位置 |
|------|------|---------------|
| **Turn** | Agent 完成一个完整任务（如 composer 完成一次编曲） | orchestrator 的 phase 方法（\_phase_create, \_phase_sample 等） |
| **Tool Call** | Agent loop 内一次 LLM→tool→result 循环 | agent_loop.py 的 while 循环内 |
| **Iteration** | 外层迭代轮次（leader 调度下一轮修订） | orchestrator 的 max_iteration_rounds |

## 影响范围

| 文件 | 改动内容 |
|------|---------|
| `server/src/clef_server/agent_loop.py` | 参数 `max_turns` → `max_tool_calls`，变量 `turns_used` → `tool_calls_used`，日志消息 |
| `server/src/clef_server/config.py` | `AgentConfig.max_turns` → `max_tool_calls`，load/save 函数 |
| `server/src/clef_server/orchestrator.py` | 硬编码默认值 `max_turns` → `max_tool_calls`，日志消息 |
| `server/config/agents.yaml` | 配置键 `max_turns` → `max_tool_calls` |
| `server/tests/test_agent_loop.py` | 所有断言和参数名 |
| `server/tests/test_orchestrator.py` | 无直接引用 max_turns 参数（通过 orchestrator 间接使用） |
| `server/tests/poc_two_pass_generation.py` | 参数名 |

**不涉及的文件**：前端（无引用）、docs（旧文档不需要改，新增文档独立）

---

### Task 1: 重命名 agent_loop.py 核心参数和变量

**Files:**
- Modify: `server/src/clef_server/agent_loop.py`

- [ ] **Step 1: 重命名 AgentLoopResult 字段**

```python
# 第 26 行：turns_used → tool_calls_used
@dataclass
class AgentLoopResult:
    """Result from an agentic tool-use loop execution."""
    text: str
    tool_calls_count: int = 0
    tool_calls_used: int = 1
```

- [ ] **Step 2: 重命名 run_agent_loop 参数和内部变量**

在 `run_agent_loop` 函数中：
- 参数 `max_turns: int = 5` → `max_tool_calls: int = 10`
- 局部变量 `turns_used = 0` → `tool_calls_used = 0`
- 循环条件 `while turns_used < max_turns` → `while tool_calls_used < max_tool_calls`
- 所有 `turns_used += 1` → `tool_calls_used += 1`
- 所有 `turns_used + 1` → `tool_calls_used + 1`
- 日志 `"Agent loop cancelled at turn %d"` → `"Agent loop cancelled after %d tool calls"`
- 日志 `"Agent loop reached max_turns=%d"` → `"Agent loop reached max_tool_calls=%d"`
- 日志 `"Agent loop turn %d: calling tool"` → `"Agent loop tool call %d: %s"`

- [ ] **Step 3: 更新 docstring**

第 1-7 行的模块 docstring 更新为：

```python
"""Agentic tool-use loop — ReAct-style LLM + tool execution cycle.

Each tool call cycle:
  1. Send messages to LLM (including tool schemas if any)
  2. Parse response: if function_call contents present, execute them, append results, repeat
  3. If no function_call contents (finish_reason="stop"), return final text

Terminology:
  - tool_calls: number of LLM→tool→result cycles executed
  - max_tool_calls: safety limit to prevent infinite loops
"""
```

- [ ] **Step 4: 运行测试确认破坏性变更**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_agent_loop.py -v 2>&1 | head -30`
Expected: 大量 FAIL（因为参数名和字段名变了）

---

### Task 2: 重命名 config.py 的 AgentConfig

**Files:**
- Modify: `server/src/clef_server/config.py`

- [ ] **Step 1: 重命名 AgentConfig 字段**

```python
@dataclass
class AgentConfig:
    prompt_md: Path
    model_alias: str
    temperature: float = 0.7
    max_tool_calls: int = 10
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
```

- [ ] **Step 2: 更新 load_agent_configs**

第 137 行：
```python
max_tool_calls=cfg.get("max_tool_calls", cfg.get("max_turns", 10)),
```

注意：保留 `max_turns` 回退读取，兼容旧配置文件。

- [ ] **Step 3: 更新 save_agent_configs**

第 323 行：
```python
"max_tool_calls": cfg.max_tool_calls,
```

- [ ] **Step 4: 运行测试**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_orchestrator.py -v 2>&1 | tail -20`
Expected: 可能部分 FAIL（因为 AgentConfig 字段名变了）

---

### Task 3: 重命名 orchestrator.py 的默认值和日志

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`

- [ ] **Step 1: 更新硬编码默认值 \_AGENT_DEFS**

所有 `"max_turns": N` → `"max_tool_calls": N`（第 626-657 行）。

具体替换：
```python
# clef-composer (第 626 行)
"max_tool_calls": 10,

# clef-harmonist (第 632 行)
"max_tool_calls": 10,

# clef-rhythmist (第 638 行)
"max_tool_calls": 10,

# clef-reviewer (第 644 行)
"max_tool_calls": 10,

# clef-orchestrator (第 650 行)
"max_tool_calls": 10,

# clef-repair (第 657 行)
"max_tool_calls": 6,
```

默认值从 6/3 提高到 10/6，因为这才是"工具调用次数上限"的合理值。

- [ ] **Step 2: 更新 \_load_agent_defs 配置加载**

第 674 行：
```python
"max_tool_calls": cfg.max_tool_calls,
```

- [ ] **Step 3: 更新 \_run_agent 中的读取和日志**

第 750-765 行：
```python
max_tool_calls = agent_def.get("max_tool_calls", agent_def.get("max_turns", 10))
# ...
"Agent %s: starting loop (max_tool_calls=%d, tools=%s, model=%s)",
agent_name, max_tool_calls, [s["function"]["name"] for s in tool_schemas], model_alias,
# ...
max_tool_calls=max_tool_calls,
```

保留 `max_turns` 回退读取，兼容旧的 \_AGENT_DEFS 格式。

- [ ] **Step 4: 更新日志和 docstring**

第 693 行 docstring：
```python
"""Run an agent with agentic tool-use loop.

...
stops calling tools or max_tool_calls is reached.
"""
```

第 770 行日志：
```python
"Agent %s: loop completed (tool_calls=%d, total=%d)",
agent_name, result.tool_calls_used, result.tool_calls_count,
```

第 182 行注释：
```python
# Apply profile overrides (only model_alias, not temperature/max_tool_calls/etc.)
```

---

### Task 4: 更新 agents.yaml 配置

**Files:**
- Modify: `server/config/agents.yaml`

- [ ] **Step 1: 全局替换配置键**

所有 `max_turns:` → `max_tool_calls:`，值按以下调整：

| Agent | 旧值 | 新值 | 理由 |
|-------|------|------|------|
| clef-composer | 6 | 10 | 编曲需要多次 read/write/validate |
| clef-harmonist | 6 | 10 | 同上 |
| clef-orchestrator | 6 | 10 | 读文件 + 生成 JSON |
| clef-reviewer | 6 | 10 | 读文件 + validate + 输出 JSON 评审 |
| clef-revision | 3 | 6 | 简单格式修正 |
| clef-repair | 3 | 6 | 读 + 修正 + 验证 |
| clef-rhythmist | 6 | 10 | 同 composer |

- [ ] **Step 2: 验证 YAML 格式正确**

Run: `cd e:/GitHub/clef-dev && python -c "import yaml; yaml.safe_load(open('server/config/agents.yaml')); print('OK')"`
Expected: OK

---

### Task 5: 更新测试文件

**Files:**
- Modify: `server/tests/test_agent_loop.py`

- [ ] **Step 1: 全局替换参数名**

在 test_agent_loop.py 中：
- 所有 `max_turns=` 参数 → `max_tool_calls=`
- 所有 `result.turns_used` → `result.tool_calls_used`
- 测试函数名 `test_max_turns_*` → `test_max_tool_calls_*`

- [ ] **Step 2: 运行 agent_loop 测试**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_agent_loop.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 更新 poc_two_pass_generation.py**

所有 `max_turns=` 参数 → `max_tool_calls=`

---

### Task 6: 运行全量测试并提交

- [ ] **Step 1: 运行全部测试**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 提交**

```bash
cd e:/GitHub/clef-dev
git add server/src/clef_server/agent_loop.py server/src/clef_server/config.py server/src/clef_server/orchestrator.py server/config/agents.yaml server/tests/test_agent_loop.py server/tests/poc_two_pass_generation.py
git commit -m "refactor(server): rename max_turns to max_tool_calls for semantic clarity

Turn = one complete agent task (e.g. composer finishes a composition)
Tool call = one LLM→tool→result cycle within a turn
Max tool calls = safety limit per agent task, tuned by agent complexity"
```
