# Server 并发控制 + 智能调度 + 断点恢复：从分析到实施

> 日期：2026-04-14
> 分支：`feature/clef-server-v2`
> 计划文档：`docs/superpowers/plans/2026-04-13-server-scheduling-recovery.md`

本文档记录 Clef Server 补回 CLI 版本 Plan-and-Execute 调度能力的完整过程：从 Agent 框架对比分析中发现缺失能力，到制定三层改进方案（Token Bucket 限流、Leader 预规划、断点恢复），到 Subagent-Driven Development 实施，再到代码审查发现并修复 3 个 CRITICAL 安全/逻辑问题。

---

## 1. 起因：CLI 能力缺失的 3 个发现

在对比 `docs/Agent框架概览.md` 与 clef-server 现有实现时，发现三个关键能力断层：

| # | 问题 | CLI 已有 | Server 缺失 | 影响 |
|---|------|---------|------------|------|
| 1 | GLM 并行请求 429 错误 | 手动间隔 + 重试 | 零并发控制 | 多 session 并行时频繁触发 GLM rate limit (code 1302) |
| 2 | create 阶段无 Plan-and-Execute | Leader 输出 tasks.json 做依赖调度 | 硬编码 `["harmony", "melody", "rhythm"]` | 无法按 plan 动态调度 agent，浪费调用 |
| 3 | 服务器重启丢失进度 | CLI 单次运行无此问题 | session 仅在内存 | 开发调试中服务器重启 = 进度归零 |

### 发现 1：GLM 429 的本质

GLM 的速率限制是 **per-minute RPM 窗口**（每分钟请求数），不是并发请求数。早期考虑的 Semaphore 方案只能限制同时进行的请求数，无法防止单分钟内总请求数超标。正确的抽象是 Token Bucket。

### 发现 2：CLI 的 Plan-and-Execute 遗失

CLI 版本中 `create` 阶段前有 Leader 输出 `tasks.json`，包含 `{agent, voice, depends_on, instruction}` 结构化任务列表。Server 的 `_call_leader` 只存在于 `iterate` 阶段，`_phase_create` 直接硬编码遍历三个声部。

### 发现 3：cost-saving profile 的死锁陷阱

`cost-saving` profile 将 7 个 agent 全部映射到 `deepseek-chat`。如果用 provider name 而非 model_alias 作为限流 key，单 session 就有 7 个并发调用竞争同一个 bucket，`burst=5` 时自我死锁。Eng review 中发现这个 CRITICAL 问题。

---

## 2. 实施方案：P0 → P1 → P2 三层改进

### 整体架构

```
providers.yaml (rpm/burst)
       │
  ┌────▼─────┐
  │ProviderRate│ ← Token Bucket: per-alias RPM control
  │  Limiter  │    Key = model_alias (NOT provider name)
  └────┬─────┘
       │ acquire()
  ┌────┼────────────────┐
  │    │                │
_run_agent         _run_agent         _run_agent
(session 1)        (session 1)        (session 2)
  │    │                │
  ┌▼────▼┐         ┌────▼────┐
  │Leader│         │ Leader  │  ← create 阶段预规划
  │tasks │         │tasks    │
  └──┬───┘         └────┬────┘
     │                  │
  ┌──▼───┐         ┌───▼────┐
  │Agent │         │ Agent  │
  │dispatch│       │dispatch│
  └──────┘         └────────┘
       ┌───────────▼───────────┐
       │ Session State (JSON)  │ ← 断点持久化
       │ per-phase persist     │
       └───────────────────────┘
```

### P0：并发控制（Task 1-4）

**Task 1: Provider 限流配置**
- `providers.yaml` 每个条目新增 `rpm` + `burst` 字段
- `OpenAICompatConfig` dataclass 新增 `rpm: int = 60`, `burst: int = 10`
- GLM 端点：rpm=30, burst=5；DeepSeek：rpm=60, burst=10

**Task 2: Token Bucket 限流器**
- 新建 `concurrency.py`，实现 `ProviderRateLimiter` + `_TokenBucket` 内部类
- `try_acquire()` 线程安全（`threading.Lock`）
- `acquire(alias)` 异步上下文管理器，token 耗尽时 `asyncio.sleep` 等待补充
- 默认值：rpm=60, burst=10

**Task 3: 集成到 Orchestrator**
- `orchestrator.__init__` 初始化 `_rate_limiter`，从 providers 读取 rpm/burst
- `_run_agent` 中用 `async with self._rate_limiter.acquire(model_alias)` 包裹 `run_agent_loop`
- `_http_post` 解析 `Retry-After` 头，用 `max(base_backoff, retry_after_sec)` 避免缩短退避
- `providers.py` 中 `create_providers()` 将 rpm/burst 设置到 client 实例

**Task 4: 延迟参数可配置化**
- `INTER_AGENT_DELAY=2`, `INTER_ROUND_DELAY=3` 改为 settings 驱动
- `self.inter_agent_delay = self._settings.get("inter_agent_delay", self.INTER_AGENT_DELAY)`

### P1：Leader 预规划（Task 5）

在 `_phase_create` 的声部生成循环前，调用 `clef-orchestrator` agent：

```
Leader prompt → "生成结构化执行计划"
       ↓
tasks: [
  {agent: "clef-harmonist", voice: "harmony", depends_on: null, instruction: "..."},
  {agent: "clef-composer", voice: "melody", depends_on: "clef-harmonist", instruction: "..."},
]
       ↓
按依赖排序 → 逐个执行
```

Fallback：Leader 失败时回退到原始硬编码循环（完全向后兼容）。

安全措施：DFS 环检测防止循环依赖导致无限等待（代码审查中发现并修复的 C3 问题）。

### P2：断点恢复（Task 6-8）

**Task 6: ComposeSession 序列化**
- 新增 `to_persist_dict()` — 序列化所有持久化字段（plan, profile, sub_steps, step_status, current_step）
- 新增 `from_dict()` 类方法 — 从序列化 dict 重建 session
- 运行时字段（`_event_queues`, `_cancel_requested`）不序列化

**Task 7: SessionManager 磁盘持久化**
- `__init__` 新增 `persist_dir` 参数
- `persist(session)` — 写入 `{session_id}.json` 到磁盘
- `restore(session_id)` — 从磁盘加载
- `restore_all_incomplete()` — 启动时恢复所有非终态 session
- `remove()` 同时清理内存和磁盘

**Task 8: Orchestrator 集成**
- `_advance_phase` 在 cancel/done/confirm/phase完成 后自动调用 `save()`
- `app.py` 的 `_lifespan` 中配置 persist_dir 并恢复未完成 session

---

## 3. 代码审查中发现的 5 个问题

采用 Subagent-Driven Development 工作流，8 个 task 由独立 subagent 实现。全部完成后进行 Opus 级代码审查，发现 3 个 CRITICAL + 2 个 IMPORTANT 问题。

### CRITICAL 问题（必须修复）

**C1. 路径遍历漏洞** — `sessions.py`

`persist()` 和 `remove()` 中 session_id 直接拼接到文件路径，无任何校验：
```python
path = self._persist_dir / f"{session.session_id}.json"
```

如果攻击者控制 session_id（如 `../../../etc/crontab`），可在任意位置读写文件。

**修复**：新增 `_validate_session_id()` 函数，用正则 `^[a-zA-Z0-9_-]+$` 校验，拒绝 `/`、`\`、`..`。

**C2. remove() 返回值不一致** — `sessions.py`

原实现在 `persist_dir` 配置且文件存在时返回 `True`，但 session 仅在内存时返回 `was_in_memory`。两种路径的布尔语义不统一。

**修复**：统一返回 `was_in_memory or removed_disk`。

**C3. 循环依赖导致声部静默丢失** — `orchestrator.py`

Leader 预规划的 tasks 如果存在 A→B→A 循环依赖，两个任务都会因依赖未满足被跳过，但只记录了 WARNING 级日志。结果是声部无声丢失，用户看到不完整的输出。

**修复**：在执行前用 DFS 环检测，将循环中的 agent 加入 `circular_agents` 集合并跳过，同时记录 ERROR 级日志。

### IMPORTANT 问题（已修复）

**I2. restore 异常捕获过窄**

只捕获 `json.JSONDecodeError` 和 `KeyError`。磁盘文件权限问题（`PermissionError`）或编码错误（`OSError`）会导致整个恢复循环崩溃。

**修复**：扩展为 `except (json.JSONDecodeError, KeyError, OSError)`。

**I4. 直接设置私有属性**

`app.py` 中 `mgr._persist_dir = persist_dir` 绕过封装。

**修复**：新增 `configure_persistence(persist_dir)` 方法。

### 剩余 IMPORTANT（不影响合并，后续迭代）

| 问题 | 说明 | 影响 |
|------|------|------|
| I1: `_get_bucket` 竞态 | asyncio 单线程下无竞态，多线程才需修 | 当前无风险 |
| I3: `tool_permissions` 未序列化 | 默认空权限，无实际影响 | 加 schema_version 时一起处理 |
| I5: acquire 异常不释放 token | token bucket 自动补充 | 错误突发时桶会短暂耗尽 |
| I6: 无 schema_version | 后续格式变更无法迁移 | 加版本号解决 |

---

## 4. 文件变更总览

### 第一轮（9 个 commit）

| 操作 | 文件 | 行数变化 | 职责 |
|------|------|---------|------|
| 新建 | `server/src/clef_server/concurrency.py` | +90 | Token Bucket 限流器 |
| 新建 | `server/tests/test_concurrency.py` | +93 | 限流器单元测试（8 个） |
| 修改 | `server/config/providers.yaml` | +12 | per-provider rpm+burst |
| 修改 | `server/src/clef_server/config.py` | +8 | 读取 rpm+burst |
| 修改 | `server/src/clef_server/providers.py` | +10 | 传递 rpm+burst 到 client |
| 修改 | `server/src/clef_server/chat_completions_client.py` | +14 | Retry-After 头解析 |
| 修改 | `server/src/clef_server/orchestrator.py` | +150 | 限流集成 + Leader 预规划 + 延迟可配置 + 断点保存 |
| 修改 | `server/src/clef_server/sessions.py` | +110 | 序列化 + 磁盘持久化 + 安全校验 |
| 修改 | `server/src/clef_server/app.py` | +44 | 启动恢复 + 持久化配置 |
| 修改 | `server/tests/test_sessions.py` | +94 | 序列化/持久化测试（9 个） |

### 第二轮：E2E Create 阶段修复（4 个 commit）

| 操作 | 文件 | 行数变化 | 职责 |
|------|------|---------|------|
| 修改 | `server/src/clef_server/chat_completions_client.py` | +1 | 529 加入重试列表 |
| 修改 | `server/src/clef_server/orchestrator.py` | +90 | 三层解析 + prompt 约束 + fallback + DSML 剥离 + 保守回退 |
| 修改 | `server/tests/test_orchestrator.py` | +60 | 新增 13 个测试（resolve 7 + JSON fallback 3 + DSML strip 3） |

---

## 5. 测试结果

### 第一轮（90 tests）

| 测试文件 | 用例数 | 通过 |
|----------|--------|------|
| `test_orchestrator.py` | 56 | 56 |
| `test_concurrency.py` | 8 | 8 |
| `test_sessions.py` | 26 | 26 |
| **总计** | **90** | **90** |

### 第二轮（69 tests in test_orchestrator.py）

| 测试类 | 用例数 | 说明 |
|--------|--------|------|
| `TestResolveAgentName` | 7 | 精确匹配、大小写、别名、voice 路由、无匹配 |
| `TestExtractJsonConservativeFallback` | 3 | DSML → revise、无效 JSON → revise、有效 JSON 保留 |
| `TestStripToolMarkers` | 3 | 无标记不变、剥离 DSML、剥离 invoke |
| 全部 orchestrator tests | **69** | **69** |

### 覆盖场景

| 场景 | 测试 |
|------|------|
| Token Bucket 容量/补充/封顶 | `TestTokenBucket` (3 个) |
| Provider 配置读取/默认值 | `TestProviderRateLimiter` (2 个) |
| 异步 acquire 等待/释放 | `TestProviderRateLimiter` (2 个) |
| 多 session 共享限流 | `test_concurrent_sessions_share_limiter` |
| Session 序列化 roundtrip | `TestSessionSerialization` (3 个) |
| 磁盘持久化 save/restore/remove | `TestSessionPersistence` (6 个) |
| 损坏 JSON 恢复 | `test_corrupted_json_returns_none` |
| 终态 session 跳过 | `test_restore_all_incomplete_skips_terminal` |
| Leader 预规划 + fallback | `test_phase_create_*` (现有 + Leader 路径) |

### 未覆盖（Eng Review 标记）

- 循环 `depends_on` 死锁 — 代码已修复但无专门测试
- `Retry-After` 头解析 — 在 `_http_post` 中实现但无单元测试
- `_run_agent_batch_raw` 是否绕过限流 — 当前代码路径不使用 batch_raw

---

## 6. Commit 清单

### 第一轮：并发控制 + Leader 预规划 + 断点恢复（9 个 commit）

```
338eba8 feat(server): add per-provider rpm+burst config fields for token bucket rate limiting
774274f feat(server): add ProviderRateLimiter with token bucket for per-provider RPM control
15506a3 feat(server): integrate Token Bucket rate limiter into _run_agent, respect Retry-After header
896e5c9 fix(server): wire per-provider rpm/burst from config through to rate limiter
6a0f2e9 refactor(server): make inter-agent delays configurable via settings
e5718ed feat(server): add Leader pre-planning to create phase with dependency dispatch
3133769 feat(server): add ComposeSession serialization and SessionManager disk persistence
0927987 feat(server): auto-persist sessions after each phase, restore incomplete on startup
e0f2f19 fix(server): address code review findings — path traversal, remove semantics, circular deps
```

### 第二轮：E2E Create 阶段级联失败修复（4 个 commit）

```
c390558 fix(server): add 529 to retry list for overloaded API providers
5a9413b feat(server): add three-layer agent name resolution with alias and voice routing
229f9f5 fix(server): enhance Leader prompts with agent constraints and use _resolve_agent_name in create/iterate
8d385a1 fix(server): change _extract_json fallback from pass to revise and add DSML stripping for content recovery
```

---

## 7. E2E 测试暴露的 Create 阶段级联失败

> 日期：2026-04-14（同日第二轮修复）
> Session：`clef-2ef9c7a0`（cost-saving profile / DeepSeek）
> 输出目录：`addons/clef/output/Cheerful Morning Tow_155400/`

### 现象

E2E 测试全流程跑通（parse → sample → create → iterate ×3 → review → express → done），但最终 `final_r3.mid` 只有 56 字节（空 MIDI），`score.abc` 只有头部没有音符。

### 根因分析

四个问题级联导致 create 阶段完全失效：

| # | 问题 | 影响 | 严重程度 |
|---|------|------|---------|
| C4 | Leader 返回 `clef-melodist` / `clef-bassist` 等无效 agent 名 | 所有 create 任务被 skip，无声部生成 | CRITICAL |
| C5 | `_extract_json` 解析失败时 fallback `{"verdict":"pass"}` | iterate 阶段误判为"无需修改"，3 轮迭代无实质修改 | CRITICAL |
| C6 | Leader tasks 全被 skip 时不触发 fallback | `leader_tasks` 非空（只是名字无效），不进入硬编码循环 | CRITICAL |
| C7 | DeepSeek DSML `<\|DSML\|>` 污染文本输出 | agent loop 用完 max_tool_calls 仍无法提取有效 ABC | IMPORTANT |

级联效应：

```
Leader 返回 clef-melodist / clef-bassist
         │
         ▼
  所有 create tasks 被 skip (C4+C6)
         │
         ▼
  fragments = {} → score.abc 只有头部 → base_r1.mid = 56 bytes
         │
         ▼
  Reviewer 输出含 DSML → _extract_json fallback "pass" (C5)
         │
         ▼
  Iterate 3 轮无实质修改 (C7)
         │
         ▼
  final_r3.mid = 56 bytes (空)
```

### 修复方案

**修复 1：三层 Agent 名解析**（解决 C4）

新增 `_resolve_agent_name()` 方法，三层防御：
1. 直接匹配（case-insensitive）— 处理 `clef-Composer` → `clef-composer`
2. 别名映射 — 处理 `clef-melodist` → `clef-composer`、`clef-bassist` → `clef-rhythmist` 等 20 个常见同义词
3. Voice 路由 — 用 Leader 返回的 `voice` 字段（melody/harmony/rhythm，LLM 几乎不会搞错）+ 已有的 `VOICE_AGENT_MAP` 路由

关键设计决策：**Voice 路由比模糊匹配更可靠**。`voice` 字段的取值范围只有 3 个值（melody/harmony/rhythm），远比 agent 名稳定。

**修复 2：Leader Prompt 约束**（预防 C4）

在 `_phase_create` 的 Leader prompt 和 `_call_leader` 的消息中明确列出合法 agent 名：

```
VALID AGENTS (use EXACTLY these names): ['clef-composer', 'clef-harmonist', 'clef-rhythmist']
Available voices: melody, harmony, rhythm
```

**修复 3：Create 阶段 Zero-Task Fallback**（解决 C6）

Leader 路径执行完毕后检查 `completed_agents`：
- 如果为空（所有 task 被 skip），设置 `leader_tasks = None`
- 将 `if/else` 结构改为顺序 `if` + `if not`，确保 fallback 触发

**修复 4：`_extract_json` 保守回退**（解决 C5）

两处 fallback 从 `{"verdict": "pass"}` 改为 `{"verdict": "revise"}`：
- DSML 标记检测失败 → `"revise"`
- JSON 解析失败 → `"revise"`

**修复 5：DSML 剥离预处理**（缓解 C7）

新增 `_strip_tool_markers()` 方法，在拒绝前先尝试剥离 DSML/function_calls/invoke 标记，保留周围内容。应用于 `_extract_abc`、`_extract_json`、`_extract_rhythm` 三个方法。

### 文件变更

| 操作 | 文件 | 行数变化 | 职责 |
|------|------|---------|------|
| 修改 | `server/src/clef_server/orchestrator.py` | +90 | 三层解析 + prompt 约束 + fallback + DSML 剥离 + 保守回退 |
| 修改 | `server/tests/test_orchestrator.py` | +60 | 新增 TestResolveAgentName(7) + TestExtractJsonConservativeFallback(3) + TestStripToolMarkers(3) |

### Commit 清单

```
5a9413b feat(server): add three-layer agent name resolution with alias and voice routing
229f9f5 fix(server): enhance Leader prompts with agent constraints and use _resolve_agent_name in create/iterate
8d385a1 fix(server): change _extract_json fallback from pass to revise and add DSML stripping for content recovery
```

### 测试结果

69 tests 全绿（从 63 增长到 69），零回归。

---

## 8. 经验总结

### 第一轮：并发控制 + Leader 预规划 + 断点恢复

1. **Token Bucket > Semaphore 处理 RPM 限制**：Semaphore 限制并发数，但 GLM 的限制是 per-minute RPM 窗口。Token Bucket 的 refill rate 精确匹配 RPM 语义。

2. **限流 key 必须是 model_alias**：cost-saving profile 下 7 个 agent 共享一个 provider。用 provider name 做 key 会导致 burst=5 < 7 的自我死锁。

3. **循环依赖检测不能省**：LLM 返回的 tasks.json 不受控，A→B→A 循环在生产中完全可能发生。DFS 环检测是必要的防御性编程。

4. **路径遍历是持久化的标配风险**：`_validate_session_id` 正则校验是最小成本防护。

5. **审查流程有效但需要 Opus 级深度**：安全/并发/边界问题需要 Opus 级审查才能发现。

6. **Subagent-Driven Development 效率高但需要补充修复轮**：subagent 间的集成缝隙需要主控方人工修复。

### 第二轮：E2E Create 阶段级联失败修复

7. **LLM 输出的 agent 名不可信，voice 字段更可靠**：Leader 返回的 `agent` 字段经常是编造的名字（`clef-melodist`、`clef-bassist`），但 `voice` 字段（melody/harmony/rhythm）几乎不会出错。三层解析（直接匹配 → 别名 → voice 路由）中，voice 路由是最后一道也是最可靠的防线。

8. **Prompt 约束 > 后处理修复**：在 Leader prompt 中明确列出合法 agent 名，从源头减少 LLM 出错概率，比事后解析更高效。

9. **Fallback 的 fallback**：Leader pre-planning 本身就是硬编码循环的 fallback。但当 Leader 返回了 tasks（只是名字都无效）时，`leader_tasks` 非空，原代码不会触发 fallback。必须检测"实际执行了几个 task"而非"返回了几个 task"。

10. **`_extract_json` 的 fallback 必须保守**：解析失败返回 `{"verdict":"pass"}` 意味着"一切正常"，系统会跳过必要的迭代。改为 `"revise"` 后，即使解析失败也会触发下一轮审查，代价是多一次 API 调用，收益是避免空输出。

11. **DSML 剥离比完全拒绝更好**：DeepSeek 的 DSML 格式会在文本中混入工具调用标记，但标记之间往往包含有效内容。剥离标记后重试提取，比直接返回空更能恢复有用的输出。

12. **E2E 测试必须验证输出质量，不能只看流程完成**：本次 E2E 所有阶段都返回 "done"，但最终 MIDI 是空的。仅检查 status=done 不够，必须验证输出文件大小和内容。
