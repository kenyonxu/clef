<!-- /autoplan restore point: /c/Users/kenyo/.gstack/projects/kenyonxu-clef-dev/feature-clef-server-v2-autoplan-restore-20260410-113132.md -->

# Clef Server Harness Engineering 优化计划

> 基于 Claude Code 源码分析与《Harness Engineering》六大支柱的修订方案
> 日期：2026-04-10
> 状态：Draft

## 背景

Claude Code 源码（`E:\GitHub\claude_code_src`）揭示了一套成熟的 Agent 工程实践。本文档将其中 6 个核心模式映射到 clef-server 的改进方案。

**核心设计哲学**（从源码提炼）：**文件优先、轻量级机制优先、fail-closed 默认值**。

---

## 改进 1：工具并发调度

**源码参考**：`src/services/tools/StreamingToolExecutor.ts` + `src/services/tools/toolOrchestration.ts`

### 源码关键模式

- `partitionToolCalls` 将工具调用分批：连续的 `isConcurrencySafe=true` 工具合并为一个并发批次，非安全工具独占执行
- `StreamingToolExecutor` 用 `TrackedTool` 状态机（`queued → executing → completed → yielded`）管理生命周期
- 结果按接收顺序（非完成顺序）yield，保证消息有序
- `siblingAbortController`：一个工具出错时立即终止兄弟进程，但不影响父级

### 当前 clef-server 问题

`_AGENT_TOOL_MAP` 是静态白名单，所有 Agent 串行执行。Review 阶段 `abc_lint` + `validate_abc` 明明是只读操作却无法并行。

### 实施方案

**文件**：`server/src/clef_server/tools.py`

```python
# 新增工具元数据注册表
from dataclasses import dataclass
from enum import Enum

class ToolSafety(Enum):
    READ_ONLY = "read_only"       # 可并发
    IDEMPOTENT_WRITE = "idempotent"  # 幂等写入，可并发
    EXCLUSIVE_WRITE = "exclusive"    # 独占写入

@dataclass(frozen=True)
class ToolMeta:
    safety: ToolSafety
    estimated_tokens: int = 500     # 预估输出 token

_TOOL_META: dict[str, ToolMeta] = {
    "read_file":        ToolMeta(ToolSafety.READ_ONLY, 1000),
    "write_file":       ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "validate_abc":     ToolMeta(ToolSafety.READ_ONLY, 800),
    "abc_lint":         ToolMeta(ToolSafety.READ_ONLY, 400),
    "abc_to_midi":      ToolMeta(ToolSafety.READ_ONLY, 100),
    "merge_abc":        ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "inject_expression": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 100),
    "snapshot":         ToolMeta(ToolSafety.IDEMPOTENT_WRITE, 50),
}
```

**文件**：`server/src/clef_server/orchestrator.py` — 新增分批调度

```python
import asyncio
from clef_server.tools import _TOOL_META, ToolSafety

@dataclass
class _CallBatch:
    safe: bool
    calls: list[dict]  # [{agent, prompt, tools}]

def _partition_agent_calls(self, calls: list[dict]) -> list[_CallBatch]:
    """将 Agent 调用按工具安全性分批（参考 partitionToolCalls）"""
    batches: list[_CallBatch] = []
    for call in calls:
        tools = call.get("tools", [])
        all_safe = all(
            _TOOL_META.get(t, ToolMeta(ToolSafety.EXCLUSIVE_WRITE)).safety != ToolSafety.EXCLUSIVE_WRITE
            for t in tools
        )
        if all_safe and batches and batches[-1].safe:
            batches[-1].calls.append(call)
        else:
            batches.append(_CallBatch(safe=all_safe, calls=[call]))
    return batches

async def _run_agent_batch(self, calls: list[dict]) -> list[dict]:
    """并发/串行调度 Agent 调用"""
    batches = self._partition_agent_calls(calls)
    results = []
    for batch in batches:
        if batch.safe:
            batch_results = await asyncio.gather(*[self._call_agent(c) for c in batch.calls])
            results.extend(batch_results)
        else:
            for call in batch.calls:
                results.append(await self._call_agent(call))
    return results
```

### 应用场景

- **Review 阶段**：`abc_lint` + `validate_abc` 并行执行，延迟减半
- **Express 阶段**：`abc_to_midi` + `inject_expression` 仍串行（前者是后者输入）
- **Leader 迭代**：`clef-composer` 和 `clef-harmonist` 如果 `generation_order` 无依赖，可并行

### 验收标准

- [ ] `_TOOL_META` 覆盖全部 8 个工具
- [ ] Review 阶段 abc_lint + validate_abc 并行执行
- [ ] 并行结果按原始调用顺序返回
- [ ] 单元测试覆盖分批逻辑（全部安全 / 全部独占 / 混合场景）

---

## 改进 2：Microcompact 上下文压缩

**源码参考**：`src/services/compact/apiMicrocompact.ts`

### 源码关键模式

- **Microcompact（API 级）**：不调 LLM，直接清除大块工具输出（Shell、Glob、Grep、FileRead 结果），保留最近 40k token
- **Full Compact（LLM 级）**：调专用 LLM 生成对话摘要
- 清除后重新注入文件状态缓存、skill listing、async agent 状态
- `TOOLS_CLEARABLE_RESULTS` / `TOOLS_CLEARABLE_USES` 分类可清除工具

### 当前 clef-server 问题

Leader 迭代最多 3 轮，每轮 `validate_abc` 输出约 800-2000 token，`abc_lint` 约 400 token。3 轮累积约 3.6-7.2k token 的工具输出被原样保留在上下文中，而 LLM 只需要知道 pass/fail。

### 实施方案

**文件**：`server/src/clef_server/orchestrator.py` — 新增 microcompact 方法

```python
import json

# 可压缩的工具输出（只保留摘要）
_COMPRESSIBLE_TOOLS = {"validate_abc", "abc_lint"}

def _microcompact_messages(self, messages: list[dict]) -> list[dict]:
    """压缩工具输出，只保留 pass/fail 摘要（参考 apiMicrocompact.ts）

    不调 LLM，直接清除大块工具输出。
    """
    compressed = []
    for msg in messages:
        if (
            msg.get("role") == "tool"
            and msg.get("name") in _COMPRESSIBLE_TOOLS
        ):
            try:
                result = json.loads(msg.get("content", "{}"))
                summary = {
                    "tool": msg["name"],
                    "pass": result.get("pass", result.get("is_valid")),
                    "issues_count": result.get("count", len(result.get("issues", []))),
                    "has_failures": result.get("has_failures", False),
                }
                # 如果有 FAIL 项，保留 severity 列表
                if result.get("issues"):
                    fails = [i for i in result["issues"] if i.get("severity") == "FAIL"]
                    if fails:
                        summary["fail_items"] = [i.get("check") for i in fails]

                compressed.append({
                    "role": "tool",
                    "content": json.dumps(summary, ensure_ascii=False),
                    "name": msg.get("name"),
                })
            except (json.JSONDecodeError, KeyError):
                compressed.append(msg)  # 解析失败保留原文
        else:
            compressed.append(msg)
    return compressed
```

**调用时机**：在 Leader 每轮迭代前调用

```python
async def _phase_iterate(self, ...):
    # 迭代前压缩历史工具输出
    if self.session.history:
        self.session.history = self._microcompact_messages(self.session.history)
    # ... 正常迭代逻辑
```

### 收益估算

| 项目 | 压缩前 | 压缩后 | 节省 |
|------|--------|--------|------|
| validate_abc 单次输出 | ~1500 token | ~50 token | 97% |
| abc_lint 单次输出 | ~400 token | ~30 token | 93% |
| 3 轮迭代累积 | ~5700 token | ~240 token | 96% |

### 验收标准

- [ ] `_microcompact_messages` 正确压缩 validate_abc 和 abc_lint 输出
- [ ] FAIL severity 项被保留在摘要中
- [ ] 非 compressible 工具输出不受影响
- [ ] 端到端测试：3 轮迭代后上下文 token 数降低 80%+

---

## 改进 3：Per-Session 工具权限覆盖

**源码参考**：`src/hooks/toolPermission/permissionLogging.ts` + `src/constants/tools.ts`

### 源码关键模式

- `alwaysAllowRules` / `alwaysDenyRules` / `alwaysAskRules` 三层判定
- `shouldAvoidPermissionPrompts`：后台 Agent 自动拒绝（不弹 UI）
- `ALL_AGENT_DISALLOWED_TOOLS`：全局禁止工具列表（防止递归、状态冲突）
- `ASYNC_AGENT_ALLOWED_TOOLS`：白名单模式（只开放必要工具）
- 完整审计日志：每个 allow/deny 决策都记录来源 + 等待时间

### 当前 clef-server 问题

`_AGENT_TOOL_MAP` 是纯静态白名单，无法在运行时调整。Web 前端"只看模式"无法实现（用户想让 Agent 只 Review 不写文件）。

### 实施方案

**文件**：`server/src/clef_server/sessions.py` — 扩展 ComposeSession

```python
@dataclass
class ToolPermissions:
    """Per-session 工具权限覆盖（参考 ToolPermissionContext）"""
    denied_tools: frozenset[str] = frozenset()
    allowed_overrides: frozenset[str] = frozenset()

    def is_tool_allowed(self, tool: str, agent: str, base_map: dict[str, list[str]]) -> bool:
        """三层判定：deny > allow override > base map"""
        if tool in self.denied_tools:
            return False
        if tool in self.allowed_overrides:
            return True
        return tool in base_map.get(agent, [])


@dataclass
class ComposeSession:
    # ... existing fields ...
    tool_permissions: ToolPermissions = field(default_factory=ToolPermissions)
```

**文件**：`server/src/clef_server/orchestrator.py` — 权限检查

```python
def _get_tools_for_agent(self, agent: str) -> list:
    """获取 Agent 可用工具（含权限覆盖）"""
    base_tools = get_tools_for_agent(agent)
    return [
        t for t in base_tools
        if self.session.tool_permissions.is_tool_allowed(
            t.name, agent, _AGENT_TOOL_MAP
        )
    ]
```

**文件**：`server/src/clef_server/routes.py` — 新增 API

```
PATCH /sessions/{id}/permissions
Body: { "denied_tools": ["write_file", "merge_abc"] }
```

### 验收标准

- [ ] `ToolPermissions.is_tool_allowed` 三层判定正确
- [ ] PATCH API 可动态调整工具权限
- [ ] Orchestrator 每次调用 Agent 前重新获取工具列表
- [ ] Web 前端可设置"只看模式"（deny 所有写入工具）

---

## 改进 4：Agent 间元数据层

**源码参考**：`src/utils/teammateMailbox.ts`

### 源码关键模式

- 基于**文件系统**的 inbox（`~/.claude/teams/{team}/inboxes/{agent}.json`）
- 用 `proper-lockfile` + retry with backoff 处理并发写入
- 消息结构极简：`{from, text, timestamp, read, color, summary}`
- **没有**引入消息中间件——文件优先

### 当前 clef-server 问题

Agent 间通信全靠 score.abc 文件本身，Reviewer 读文件时不知道当前版本是谁、第几轮生成的。

### 实施方案

在现有文件通信上增加**结构化元数据头**（零基础设施成本）：

**文件**：`server/src/clef_server/orchestrator.py`

```python
# Agent 写入 ABC 片段时附加元数据注释
def _stamp_agent_meta(self, content: str, agent: str, voice: str, round_num: int) -> str:
    """在 ABC 内容头部注入 Agent 元数据（以 % 注释形式）"""
    meta = json.dumps({
        "agent": agent,
        "voice": voice,
        "round": round_num,
        "timestamp": time.time(),
    }, ensure_ascii=False)
    return f"% ClefMeta: {meta}\n{content}"
```

**文件**：`.clef-work/` 下的 score.abc 中可见：

```
% ClefMeta: {"agent": "clef-composer", "voice": "V:1", "round": 2, "timestamp": 1712736000.0}
X:1
T:Melody
V:1
...
```

Reviewer 读文件时可解析这些注释获取生成上下文。

### 验收标准

- [ ] 每个 Agent 写入时自动附加 `% ClefMeta:` 注释
- [ ] Reviewer 可解析元数据知道版本来源
- [ ] 元数据不影响 ABC 解析（注释行被忽略）
- [ ] merge_abc 合并时保留所有元数据注释

---

## 改进 5：优雅关闭 + 终态守卫

**源码参考**：`src/Task.ts` + `src/tasks/InProcessTeammateTask/`

### 源码关键模式

- `isTerminalTaskStatus(status)` 作为守卫函数在多处使用
- `shutdownRequested` 标记：请求关闭但不立即终止，Agent 可完成当前 turn
- 终态任务自动被 eviction 清理

### 当前 clef-server 问题

用户取消 session 时直接 `set_cancelled()`，如果 LLM 正在流式输出，会导致孤儿请求。

### 实施方案

**文件**：`server/src/clef_server/sessions.py`

```python
TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})

@dataclass
class ComposeSession:
    # ... existing fields ...
    _cancel_requested: bool = False

    @property
    def is_terminal(self) -> bool:
        """终态守卫（参考 isTerminalTaskStatus）"""
        return self.status in TERMINAL_STATES

    def request_cancel(self) -> None:
        """标记取消意图，允许当前 phase 完成后停止"""
        if self.is_terminal:
            return  # 已终止，忽略
        self._cancel_requested = True
        self.updated_at = time.time()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    # 修改原 _transition 方法
    def _transition(self, new_status: str) -> None:
        if self.is_terminal:
            raise ValueError(f"Session is terminal ({self.status}), cannot transition to {new_status}")
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(f"Cannot transition from '{self.status}' to '{new_status}'. Allowed: {allowed}")
        self.status = new_status
        self.updated_at = time.time()
```

**文件**：`server/src/clef_server/orchestrator.py` — phase 间隙检查

```python
async def _advance_phase(self, ...):
    # phase 间隙检查取消请求
    if self.session.cancel_requested:
        self.session.set_cancelled()
        logger.info("Session %s cancelled after phase completion", self.session_id)
        return
    # ... 正常推进
```

### 验收标准

- [ ] `is_terminal` 守卫阻止终态后的非法转换
- [ ] `request_cancel` 允许当前 phase 完成
- [ ] `_advance_phase` 在间隙检查 `cancel_requested`
- [ ] 已终止 session 的 API 调用返回 409 Conflict

---

## 改进 6：跨轮次文件变化缓存

**源码参考**：`src/services/compact/compact.ts` — `createPostCompactFileAttachments`

### 源码关键模式

Compact 后通过 `createPostCompactFileAttachments` 重新注入：
- 文件状态缓存（`readFileState`）
- Agent 列表（`getAgentListingDeltaAttachment`）
- Skill 已调用记录（`invoked_skills`）
- 异步 Agent 状态（`createAsyncAgentAttachmentsIfNeeded`）

### 当前 clef-server 问题

Leader 迭代每轮都冷读 plan.json 和 score.abc，没有利用"大部分内容未变"的事实。

### 实施方案

**文件**：`server/src/clef_server/orchestrator.py`

```python
import hashlib

@dataclass
class _FileCache:
    """跨轮次文件变化检测（参考 compact 的 readFileState）"""
    _hashes: dict[str, str] = field(default_factory=dict)
    _contents: dict[str, str] = field(default_factory=dict)

    def get_if_unchanged(self, path: str) -> str | None:
        """如果文件未变化则返回缓存内容，否则返回 None"""
        try:
            current = Path(path).read_text(encoding="utf-8")
            h = hashlib.md5(current.encode()).hexdigest()
            if self._hashes.get(path) == h:
                return self._contents[path]
            self._hashes[path] = h
            self._contents[path] = current
            return None  # 变化了，调用者应重新处理
        except FileNotFoundError:
            return None

    def invalidate(self, path: str) -> None:
        """主动失效（Agent 写入后调用）"""
        self._hashes.pop(path, None)
        self._contents.pop(path, None)
```

**使用方式**：

```python
class ComposeOrchestrator:
    def __init__(self, ...):
        # ...
        self._file_cache = _FileCache()

    async def _build_agent_context(self, agent: str) -> list[dict]:
        """构建 Agent 上下文消息，利用文件缓存"""
        messages = []
        for path in ["plan.json", "score.abc"]:
            cached = self._file_cache.get_if_unchanged(path)
            if cached:
                # 未变化：只发送引用标记
                messages.append({"role": "system", "content": f"{path} 未变化（使用上轮版本）"})
            else:
                # 变化了：发送完整内容
                content = Path(path).read_text(encoding="utf-8")
                messages.append({"role": "system", "content": f"{path}:\n{content}"})
        return messages
```

### 验收标准

- [ ] `_FileCache` 正确检测文件变化（MD5 哈希）
- [ ] 未变化文件只发送引用标记，不传完整内容
- [ ] Agent 写入后主动失效对应缓存
- [ ] 端到端：3 轮迭代中 plan.json 只传 1 次，score.abc 每轮传最新版

---

## 实施优先级与依赖

```
Phase 1（基础安全，0.5 天）
  ├── 改进 5：优雅关闭 + 终态守卫    ← 无依赖，独立可做
  └── 改进 1：工具并发调度（元数据注册）← 改进 2 的前置

Phase 2（性能优化，1 天）
  ├── 改进 2：Microcompact 压缩      ← 依赖改进 1 的 _TOOL_META
  └── 改进 6：跨轮次文件缓存         ← 无依赖

Phase 3（可观测性，1 天）
  ├── 改进 3：Per-Session 工具权限    ← 无依赖
  └── 改进 4：Agent 间元数据层       ← 依赖改进 6 的文件缓存基础设施
```

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 并行工具执行引入竞态 | 默认 `EXCLUSIVE_WRITE`，只有显式标记 `READ_ONLY` 的才并行 |
| Microcompact 过度压缩丢失关键信息 | 保留 FAIL severity 项，只压缩 PASS 详情 |
| 文件缓存与实际文件不同步 | Agent 写入后主动 `invalidate` |
| 元数据注释被 ABC 解析器误读 | `%` 开头行在 ABC 标准中是注释，安全 |

## 不做的事

- **不引入消息队列**（Redis/RabbitMQ）：Claude Code 用文件系统就够了
- **不做 Full Compact**（LLM 摘要）：Microcompact 已解决 80% 问题，Full Compact 成本高
- **不做 OTel 遥测**：clef-server 规模不需要分布式追踪
- **不做 Agent SDK 集成**：当前 AF 框架足够，等 Agent SDK Python 版成熟再说

---

<!-- AUTONOMOUS DECISION LOG -->

## CEO Review (via /autoplan)

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|----------|
| 1 | CEO | Mode: SELECTIVE EXPANSION | Mechanical | P3 | 6 improvements already scoped, cherry-pick expansions in blast radius | — |
| 2 | CEO | Add profiling gate before改进 1,2,6 | Taste | P3 | Subagent flagged unverified bottleneck assumptions. 1h profiling < 2.5d wasted | Skip profiling |
| 3 | CEO | Check AF parallel tool_use support before building partitionToolCalls | Taste | P4 | Claude API supports native parallel tool execution. AF may already handle it | Build custom |
| 4 | CEO | Improvements 3,4,5 proceed without profiling | Mechanical | P5 | Architectural improvements (permissions, metadata, graceful shutdown) not performance-dependent | — |
| 5 | CEO | Keep % ClefMeta comments as ABC comments | Mechanical | P5 | % is standard ABC comment syntax, zero compatibility risk | — |

### Premise Challenge (0A)

All 4 premises confirmed by user:
1. Claude Code patterns transferable — confirmed, 6 concrete mappings provided
2. Performance/token cost is the right optimization target — confirmed (musical quality is separate)
3. File-first philosophy — confirmed (matches Claude Code's teammate mailbox pattern)
4. Incremental over rewrite — confirmed (all 6 changes are additive)

### Existing Code Leverage (0B)

| Sub-problem | Existing Code | Leverage |
|-------------|--------------|----------|
| Tool safety metadata | `_AGENT_TOOL_MAP` in tools.py | Extend with `_TOOL_META` dict |
| Session state machine | `VALID_TRANSITIONS` in sessions.py | Add `TERMINAL_STATES`, `request_cancel` |
| SSE event delivery | `_event_queues` in sessions.py | No changes needed for improvements 1-6 |
| Agent config loading | `_load_agent_defs()` in orchestrator.py | Reuse for per-agent tool config |
| File hash comparison | None (new) | New `_FileCache` dataclass |

### Dream State Mapping (0C)

```
CURRENT ──────────────────> THIS PLAN ──────────────────> 12-MONTH IDEAL
                            (after 6 improvements)
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│ Serial agent calls  │   │ Parallel read-only   │   │ Adaptive scheduling │
│ Full tool output    │──>│ Microcompact (97%    │──>│ Auto-context budget │
│ in every iteration  │   │ token reduction)     │   │ per agent/task      │
│ Static tool perms   │   │ Per-session override │   │ RBAC + rate limits  │
│ No cancel graceful  │   │ Graceful shutdown    │   │ Full lifecycle mgmt │
│ Cold file reads     │   │ File change cache    │   │ Shared memory pool  │
│ No agent metadata   │   │ % ClefMeta comments  │   │ Structured protocol │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

### Implementation Alternatives (0C-bis)

```
APPROACH A: Current Plan (6 incremental improvements)
  Summary: Add 6 focused improvements to existing orchestrator
  Effort:  M (2.5 days)
  Risk:    Low
  Pros:    Additive, no breaking changes, each independently valuable
  Cons:    Doesn't address architectural ceiling
  Reuses:  sessions.py, tools.py, orchestrator.py structures

APPROACH B: AF-Native Parallel + Prompt-Based Permissions
  Summary: Drop改进 1+3, use AF's built-in parallel and system prompt constraints
  Effort:  S (1 day)
  Risk:    Low
  Pros:    Less custom code, leverages framework
  Cons:    Depends on AF capability verification, less control
  Reuses:  AF framework features

APPROACH C: Full Workflow Engine Rewrite
  Summary: Replace orchestrator with state machine library (e.g., Python-statemachine)
  Effort:  XL (2+ weeks)
  Risk:    High
  Pros:    Production-grade lifecycle, visual debugging, persistence
  Cons:    Massive scope creep, breaks existing tests
  Reuses:  Only plan schema and tool wrappers
```

**RECOMMENDATION**: Approach A with one modification from B — verify AF parallel support first (Taste Decision #2).

### Error & Rescue Registry

| Error Scenario | Current Handling | Plan Improvement | Gap |
|---------------|-----------------|------------------|-----|
| LLM rate limit mid-phase | Session → failed | No change (no retry in plan) | WARN: should add retry for改进 5 |
| Agent tool_use rejected | Return error dict | No change | OK: tools return error dicts |
| Cancel during LLM call | Session → cancelled immediately | 改进 5: `request_cancel` + phase gap check | FIXED |
| File not found | `FileNotFoundError` in tools.py | No change | OK: explicit error |
| Context overflow | Not handled | 改进 2: microcompact | Partial: only compresses tool output |
| Session not found | `RuntimeError` in orchestrator | No change | OK: explicit error |

### Failure Modes Registry

| Failure Mode | Severity | Mitigation | Critical Gap? |
|-------------|----------|------------|---------------|
| asyncio.gather error propagates to entire batch | HIGH | Wrap each gather item in try/except (改进 1) | YES — plan doesn't specify error isolation |
| Microcompact removes FAIL items | MEDIUM | Preserve severity=FAIL in summary (改进 2) | No — already specified |
| File cache returns stale data after external edit | LOW | Invalidate on write + hash check (改进 6) | No |
| % ClefMeta breaks external ABC tools | LOW | ABC spec confirms % is comment | No |

### NOT in Scope

- Musical quality optimization (separate concern, confirmed by user)
- Full LLM-based context compression (cost > benefit for current scale)
- Message queue / event bus infrastructure
- OTel distributed tracing
- Agent SDK migration (wait for Python maturity)
- Retry/resilience for LLM API calls (noted for future)

### What Already Exists

- `sessions.py`: State machine with `VALID_TRANSITIONS` — extend, don't replace
- `tools.py`: 8 tools with `_AGENT_TOOL_MAP` white list — add metadata layer
- `orchestrator.py`: 6-phase workflow with `_advance_phase` — add hooks for cancel/check
- SSE streaming infrastructure — no changes needed
- `routes.py`: 7 REST endpoints — add 1 PATCH endpoint for permissions

### Dream State Delta

This plan moves clef-server from "functional serial pipeline" to "optimized parallel pipeline with graceful lifecycle." The 12-month ideal requires further investment in adaptive scheduling, shared memory, and structured agent protocols, which are correctly deferred.

### CEO Completion Summary

```
+====================================================================+
|            CEO REVIEW — COMPLETION SUMMARY                         |
+====================================================================+
| Mode selected        | SELECTIVE EXPANSION                         |
| Premises             | All 4 confirmed by user                     |
| Existing leverage    | 5 existing modules extended (not replaced)  |
| Error/Rescue Registry| 6 scenarios mapped, 1 CRITICAL GAP          |
| Failure Modes        | 4 total, 1 CRITICAL (gather error iso)      |
| NOT in scope         | 6 items deferred with rationale             |
| What already exists  | 5 modules mapped                            |
| Dream state delta    | Serial → Optimized parallel (12mo gap noted)|
| Alternatives         | 3 considered, A recommended with B hybrid   |
| Outside voice        | Claude subagent [subagent-only, codex 401]  |
| Taste decisions      | 2 (profiling gate, AF parallel check)       |
| Lake Score           | 5/5 chose completeness                      |
+====================================================================+
```

### CEO Dual Voices Consensus

```
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Premises valid?                   YES     N/A    CONFIRMED
  2. Right problem to solve?           YES     N/A    CONFIRMED
  3. Scope calibration correct?        PARTIAL N/A    NEEDS DATA
  4. Alternatives explored enough?     NO      N/A    DISAGREE
  5. Competitive risks covered?        YES     N/A    CONFIRMED
  6. 6-month trajectory sound?         YES     N/A    CONFIRMED
═══════════════════════════════════════════════════════════════
CONFIRMED: 4/6. DISAGREE: 1 (alternatives — AF native parallel).
NEEDS DATA: 1 (profiling to validate bottleneck assumptions).
Source: [subagent-only] (codex 401 unavailable)
```

---

## Eng Review (via /autoplan)

### Architecture ASCII Diagram

```
                        ┌──────────────────────────────────────────────┐
                        │              routes.py (FastAPI)             │
                        │  POST /compose  PATCH /sessions/{id}/perms  │
                        └──────────┬───────────────────┬──────────────┘
                                   │                   │
                        ┌──────────▼───────────────────▼──────────────┐
                        │         orchestrator.py (ComposeOrchestrator)│
                        │  ┌─────────────────────────────────────────┐│
                        │  │ _partition_agent_calls ─── asyncio.gather││  ← 改进 1
                        │  │ _microcompact_messages                  ││  ← 改进 2
                        │  │ _stamp_agent_meta                       ││  ← 改进 4
                        │  │ _advance_phase (cancel check)            ││  ← 改进 5
                        │  │ _FileCache (跨轮次缓存)                  ││  ← 改进 6
                        │  └─────────────────────────────────────────┘│
                        └──────┬──────────────────────────┬───────────┘
                               │                          │
                ┌──────────────▼──────┐      ┌────────────▼──────────┐
                │   sessions.py       │      │   tools.py            │
                │ ┌─────────────────┐ │      │ ┌──────────────────┐  │
                │ │ TERMINAL_STATES │ │      │ │ _TOOL_META        │  │ ← 改进 1
                │ │ request_cancel  │ │      │ │ ToolSafety enum   │  │
                │ │ is_terminal     │ │      │ └──────────────────┘  │
                │ │ ToolPermissions │ │      │ ┌──────────────────┐  │
                │ └─────────────────┘ │      │ │ _AGENT_TOOL_MAP  │  │
                └─────────────────────┘      │ └──────────────────┘  │
                                             └───────────────────────┘
                    ← 改进 3 (permissions)      ← 改进 5 (shutdown)

                ┌─────────────────────────────────────────────────────┐
                │  .clef-work/ (file system)                         │
                │  plan.json ←→ _FileCache ←→ score.abc (% ClefMeta)│
                └─────────────────────────────────────────────────────┘
                    ← 改进 4 (metadata)    ← 改进 6 (cache)
```

Coupling assessment: All 6 improvements touch orchestrator.py, but through independent methods. Low coupling risk.

### Eng Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|-----------|-----------|----------|
| 6 | Eng | Add path traversal guard to write_file/read_file | Mechanical | P1 | CRITICAL security issue, must fix |
| 7 | Eng | asyncio.gather with return_exceptions=True | Mechanical | P1 | CRITICAL gap from CEO review, must fix |
| 8 | Eng | FileCache always sends content, skips only disk read | Taste | P5 | Subagent flagged LLM confusion risk. Cache saves I/O, not tokens |
| 9 | Eng | Microcompact preserves full FAIL issues array | Mechanical | P1 | HIGH finding, Revision agent needs details |
| 10 | Eng | allowed_overrides intersected with base map | Mechanical | P1 | HIGH finding, least privilege violation |
| 11 | Eng | Add session TTL (24h default) | Taste | P2 | In blast radius, <5 files, prevents memory leak |

### Scope Challenge (Step 0)

Examined actual code:
- `sessions.py`: Clean state machine, ~120 lines. Extendable.
- `tools.py`: 190 lines, simple registry. Adding `_TOOL_META` is additive.
- `orchestrator.py`: ~500+ lines, complex but well-structured. New methods fit existing pattern.

**Pre-implementation gate**: Before starting改进 1, add profiling instrumentation to measure actual phase durations. This addresses CEO's "NEEDS DATA" consensus item. ~30 min effort.

### Test Coverage Diagram

```
Current: 11 test files, ~30 test cases
                           Coverage
改进 1 (parallel)          NEW — _partition, gather error isolation, ordering
改进 2 (microcompact)      NEW — compress, preserve FAIL, malformed input
改进 3 (permissions)       NEW — deny/override/intersection, PATCH API
改进 4 (metadata)          NEW — stamp format, ABC parse, merge preserve
改进 5 (shutdown)          EXTEND test_sessions.py — cancel, terminal guard
改进 6 (file cache)        NEW — hash check, invalidation, concurrent reads

Security (path traversal)  NEW — workdir boundary validation
```

### Failure Modes Update

| Failure Mode | Severity | Mitigation | Status |
|-------------|----------|------------|--------|
| Path traversal via write_file | CRITICAL | Add `_validate_path()` workdir boundary | NEW from Eng review |
| gather error propagation | CRITICAL | `return_exceptions=True` + error dict wrapping | ESCALATED from CEO |
| FileCache "unchanged" confuses LLM | HIGH | Always send content, cache only skips disk I/O | FIXED (design change) |
| Microcompact strips FAIL details | HIGH | Preserve full `issues` array for FAIL severity | FIXED |
| Permission expansion via override | MEDIUM | Intersect with base map | FIXED |
| Session memory leak | MEDIUM | Add 24h TTL + periodic cleanup | NEW |

### Eng Completion Summary

```
+====================================================================+
|            ENG REVIEW — COMPLETION SUMMARY                         |
+====================================================================+
| Scope challenge      | Examined 3 core modules, low coupling risk  |
| Architecture issues  | 2 CRITICAL, 2 HIGH, 2 MEDIUM               |
| Test coverage        | ~40 new test cases needed across 6 files     |
| Test plan artifact   | Written to ~/.gstack/projects/$SLUG/        |
| Security issues      | 1 CRITICAL (path traversal), 3 standard     |
| NOT in scope         | LLM API retry/resilience (deferred)         |
| What already exists  | 11 test files, solid session lifecycle tests |
| Failure modes        | 6 total, 2 CRITICAL GAPS addressed          |
| Outside voice        | Claude subagent [subagent-only]              |
| Taste decisions      | 2 (FileCache design, session TTL)            |
| Lake Score           | 6/6 chose completeness                      |
+====================================================================+
```

### Eng Dual Voices Consensus

```
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Architecture sound?               YES     N/A    CONFIRMED
  2. Test coverage sufficient?         NO      N/A    DISAGREE (need ~40 new)
  3. Performance risks addressed?      PARTIAL N/A    NEEDS PROFILING
  4. Security threats covered?         NO      N/A    CRITICAL GAP (traversal)
  5. Error paths handled?              NO      N/A    CRITICAL GAP (gather)
  6. Deployment risk manageable?       YES     N/A    CONFIRMED
═══════════════════════════════════════════════════════════════
CONFIRMED: 2/6. CRITICAL GAPS: 2 (security, error isolation).
Source: [subagent-only] (codex 401 unavailable)
```

**PHASE 3 COMPLETE.** Claude subagent: 8 findings (2 critical, 2 high, 2 medium, 2 low).
Consensus: 2/6 confirmed, 2 critical gaps identified and addressed.
Passing to Phase 3.5 (DX Review).

---

## DX Review (via /autoplan)

### DX Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|-----------|-----------|----------|
| 12 | DX | Add Pydantic model for PATCH permissions | Mechanical | P1 | CRITICAL — no validation, no OpenAPI schema |
| 13 | DX | Add GET /sessions/{id}/permissions + GET /tools | Taste | P2 | In blast radius, <5 files. Discoverability is core DX |
| 14 | DX | Update code block to reflect allowed_overrides intersection | Mechanical | P1 | HIGH — plan text contradicts Eng decision |
| 15 | DX | Add description= and examples to all new routes | Taste | P2 | In blast radius, standard FastAPI practice |
| 16 | DX | Expose compact_threshold and session_ttl in ComposeRequest | Taste | P3 | Borderline scope — defer to TODOS.md |

### Developer Persona

Primary: **Frontend developer integrating with clef-server REST API** (React/SSE).
Secondary: **Backend developer extending the orchestrator** (adding new agents/phases).

### DX Scorecard

| Dimension | Score | Key Gap |
|-----------|-------|---------|
| 1. Getting Started | 6/10 | TTHW ~3 steps for PATCH, but no GET to inspect state first |
| 2. API/CLI Design | 5/10 | PATCH breaks Pydantic pattern, no tool name discovery endpoint |
| 3. Error Messages | 7/10 | FastAPI auto-generates 422 from Pydantic (if models added) |
| 4. Documentation | 4/10 | No docstrings, examples, or description= on new endpoints |
| 5. Upgrade Path | 8/10 | All changes additive, no breaking changes |
| 6. Dev Environment | 8/10 | Existing pytest + FastAPI test client, no new tooling needed |
| 7. Community | N/A | Internal project, not open source |
| 8. DX Measurement | 3/10 | No API response time tracking, no developer feedback loop |
| **Overall** | **5.9/10** | |

### DX Dual Voices Consensus

```
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Getting started < 5 min?          YES     N/A    CONFIRMED
  2. API/CLI naming guessable?         NO      N/A    DISAGREE
  3. Error messages actionable?        PARTIAL N/A    NEEDS PYDANTIC
  4. Docs findable & complete?         NO      N/A    DISAGREE
  5. Upgrade path safe?                YES     N/A    CONFIRMED
  6. Dev environment friction-free?    YES     N/A    CONFIRMED
═══════════════════════════════════════════════════════════════
CONFIRMED: 3/6. DISAGREE: 2 (API design, docs).
Source: [subagent-only] (codex 401 unavailable)
```

**PHASE 3.5 COMPLETE.** DX overall: 5.9/10. TTHW: 3 steps.
5 findings (1 critical, 2 high, 2 medium).
Passing to Phase 4 (Final Gate).

---

## /autoplan Final Status

**APPROVED** — 2026-04-10, all 16 decisions accepted.

### Implementation Order (修订版)

```
Phase 0: Profiling Gate (1h)
  └── Measure actual phase durations + token usage across 3 iterations

Phase 1: Critical Security + Safety (0.5d)
  ├── CRITICAL FIX: Path traversal guard in tools.py (_validate_path)
  ├── CRITICAL FIX: asyncio.gather error isolation (return_exceptions=True)
  ├── 改进 5: Graceful shutdown + terminal guard (sessions.py)
  └── CRITICAL FIX: Pydantic model for PATCH permissions endpoint

Phase 2: Core Optimizations (1d)
  ├── 改进 1: Tool concurrency (_TOOL_META + _partition_agent_calls)
  │   └── Verify AF native parallel support first
  ├── 改进 2: Microcompact (preserve full FAIL issues array)
  └── 改进 6: FileCache (always send content, cache skips only disk I/O)

Phase 3: API Surface + Observability (1d)
  ├── 改进 3: Tool permissions (intersect override with base map)
  ├── 改进 4: Agent metadata (% ClefMeta comments)
  ├── GET /sessions/{id}/permissions (read-before-write)
  ├── GET /tools (discoverable tool names)
  └── Session TTL (24h default)
```

### Test Plan
Written to: `~/.gstack/projects/kenyonxu-clef-dev/kenyo-feature-clef-server-v2-eng-review-test-plan-20260410-115019.md`
~40 new test cases across 6 areas.

### Deferred to TODOS.md
- LLM API retry/resilience mechanism
- Adaptive context budget per agent/task (12-month ideal)
- Shared memory pool for agents (12-month ideal)
- Structured agent communication protocol (12-month ideal)
- Configurable thresholds via API (compact_threshold, session_ttl)
- OTel distributed tracing
- Agent SDK migration
