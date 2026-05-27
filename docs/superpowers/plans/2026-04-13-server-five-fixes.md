# Server 模块 5 项系统性修复计划

> 日期：2026-04-13
> 分支：feature/clef-server-v2

## 概述

基于 `server/logs/clef-server.log`（GLM 500 错误）和 `server/logs/clef-server_last_deepseek_run.log`（完整 DeepSeek 运行）的日志对比分析，确认 5 个关键问题。核心发现：agent 在全部 max_turns 中盲猜文件路径（`score.abc`, `./score.abc`, 绝对路径, 标题.abc），0 次写入；GLM API 500 错误直接终止会话。

## 优先级排列

| 优先级 | 问题 | 修复文件 | 预估 |
|--------|------|----------|------|
| P0-1 | Agent 反复 read_file 找不到文件 | tools.py, middleware.py, orchestrator.py | 55min |
| P0-2 | Retry 不覆盖 500 错误 | chat_completions_client.py | 30min |
| P1-3 | abc_lint 重复调用 | orchestrator.py | 20min |
| P1-4 | 总耗时过长 | agent_loop.py (依赖 1,3) | 15min |
| P2-5 | Session resume 无容错 | orchestrator.py, routes.py | 45min |

---

## 问题 1（P0）：Agent 反复 read_file 找不到文件，浪费全部 tool turns

### 日志证据
- harmonist 3 轮全部浪费在读文件盲猜（5/5 turns = read_file）
- repair agent 尝试 `晨光中的洛尔达.abc`, `.`, `output.abc`, `晨光中的洛尔达_224627.abc`
- reviewer 也盲猜 `./score.abc`, `.`, `score.abc`
- **deepseek-think composer 同样浪费 turn 读 plan.json**，尽管 middleware 已在 session_context 中注入了 plan 内容

### 根因分析
1. Agent 不知道 workdir 下有哪些文件，只能盲猜路径
2. repair agent 的 abc 内容已被内联传给 agent，但 prompt 缺少"内容已在 message 中"的明确指引
3. middleware 注入的 session_context 可能格式不够显眼，LLM 忽略了

### 修复方案

**Task 1.1：新增 list_files 工具** (`server/src/clef_server/tools.py`)
- 新增 `list_files(workdir, pattern="*")` 工具，返回 workdir 下的文件列表
- 加入所有 agent 的工具列表
- 示例返回：`"plan.json\nscore.abc\nharmony_v2.abc"`

**Task 1.2：middleware 注入文件列表** (`server/src/clef_server/middleware.py`)
- 修改 `build_session_context`，扫描 workdir 下文件列表
- 输出格式：`## Available files in workdir\n\n- plan.json\n- score.abc\n- harmony_v2.abc`
- 确保此信息在 user message 中的位置足够醒目

**Task 1.3：修复 repair agent prompt** (`server/src/clef_server/orchestrator.py`)
- 修改 `_attempt_repair` 中的 repair_msg
- 添加明确指引："ABC 内容已在下方内联提供，直接使用 write_file 写出修正后的版本，不需要先读取文件"

### 成功标准
- agent 不再用超过 2 次 turn 做 read_file 路径盲猜

---

## 问题 2（P0）：Retry 不覆盖 500 错误

### 日志证据
```
11:00:34 ERROR API error (500): {"error":{"code":"1234","message":"网络错误..."}}
→ ChatClientException 未重试，session 直接 failed
```

### 修复方案

**Task 2.1：扩展 retry 状态码** (`server/src/clef_server/chat_completions_client.py`)
- 第 327 行：`(429, 502, 503)` → `{429, 500, 502, 503, 504}`
- 500 错误使用更长的退避时间（10s vs 普通指数退避 2^n s）
- 同时检查两个 _http_post 方法（Anthropic 和 OpenAI 兼容），确保都覆盖

### 成功标准
- 500 错误自动重试 3 次后才失败

---

## 问题 3（P1）：abc_lint 重复调用完全相同的内容

### 日志证据
- turn 3/4/5 连续调用 abc_lint，abc_content 完全相同
- 每次 ~15s，浪费 ~30s/agent
- validate_abc 和 validate_rhythm_skeleton 也可能存在同样问题

### 修复方案

**Task 3.1：tool executor 层去重** (`server/src/clef_server/orchestrator.py`)
- 在 `_make_tool_executor` 闭包中增加 `_call_history` dict
- 对 `abc_lint`, `validate_abc`, `validate_rhythm_skeleton` 三个只读工具缓存结果
- key = `(tool_name, sorted(args).items())`
- 相同参数命中缓存时直接返回，日志标记 `[DEDUP]`

### 成功标准
- 相同参数的验证工具调用只执行 1 次

---

## 问题 4（P1）：总耗时过长（18min 只完成 Phase 1）

### 根因
- 30% tool calls 浪费在文件查找（问题 1）
- abc_lint 重复调用（问题 3）
- deepseek-think 单次思考 ~30s
- agent 单轮无超时，可能无限等待

### 修复方案

**Task 4.1：agent_loop 增加 turn 超时** (`server/src/clef_server/agent_loop.py`)
- 新增 `turn_timeout: float = 120.0` 参数
- 用 `asyncio.wait_for` 包装 `client.get_response`
- 超时时记录警告并返回空结果，让 agent 继续下一 turn
- 注意：不影响 write_file 等关键操作的超时

### 成功标准
- Phase 1 总耗时从 ~18min 降至 ~10min 以内（通过解决问题 1+3 间接达成）

---

## 问题 5（P2）：Session resume 无容错

### 日志证据
```
11:00:34 RuntimeError: Agent clef-composer failed: API error (500)
→ routes.py _resume_workflow except → sess.set_failed()
→ 用户必须从头开始
```

### 修复方案

**Task 5.1：新增 RecoverableAgentError** (`server/src/clef_server/orchestrator.py`)
- 新增异常类 `RecoverableAgentError(RuntimeError)`
- `_run_agent` 中对 500/502/503/504/timeout 错误抛 RecoverableAgentError
- 对 400/401/403 等业务错误保持 RuntimeError

**Task 5.2：_generate_with_best_of_n 容错** (`server/src/clef_server/orchestrator.py`)
- 捕获 RecoverableAgentError，等待 5s 后继续下一轮生成
- 最后一轮也失败则返回空字符串而非 crash
- 日志标记 `[RECOVERABLE]` 和重试次数

**Task 5.3：routes.py resume 降级** (`server/src/clef_server/routes.py`)
- 捕获 RecoverableAgentError 时将 session 状态回到 `awaiting_confirm`（而非 `failed`）
- 前端显示"服务暂时不可用，请重试"而非"生成失败"

### 成功标准
- API 500 不导致 session failed，回到可恢复确认点

---

## 实施顺序

```
Phase 1 (独立修复，可并行)
  ├── Task 1.1: tools.py — list_files 工具
  ├── Task 1.2: middleware.py — 文件列表注入
  ├── Task 1.3: orchestrator.py — repair prompt 修复
  └── Task 2.1: chat_completions_client.py — 500 retry

Phase 2 (依赖 Phase 1)
  ├── Task 3.1: orchestrator.py — abc_lint 去重
  └── Task 4.1: agent_loop.py — turn 超时

Phase 3 (依赖 Phase 1+2)
  ├── Task 5.1: orchestrator.py — RecoverableAgentError
  ├── Task 5.2: orchestrator.py — best-of-N 容错
  └── Task 5.3: routes.py — resume 降级

Phase 4 (验证)
  └── Task V1: 端到端冒烟测试
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `server/src/clef_server/chat_completions_client.py` | L327: 扩展 retry 状态码 |
| `server/src/clef_server/tools.py` | 新增 list_files, 更新工具注册表 |
| `server/src/clef_server/middleware.py` | build_session_context 注入文件列表 |
| `server/src/clef_server/orchestrator.py` | tool executor 去重, repair prompt, RecoverableAgentError, best-of-N 容错 |
| `server/src/clef_server/agent_loop.py` | run_agent_loop 增加 turn_timeout |
| `server/src/clef_server/routes.py` | _resume_workflow 降级处理 |

## 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| list_files 工具增加 token 消耗 | LOW | 文件列表通常 <5 个文件，<100 字符 |
| 500 retry 增加延迟 | LOW | 退避策略限制总重试时间 <30s |
| tool 去重缓存内存泄漏 | LOW | 在 agent loop 级别作用域，loop 结束自动释放 |
| turn 超时截断有效响应 | MEDIUM | 设 120s 足够长，只影响真正的卡死 |
| resume 降级可能隐藏真实错误 | MEDIUM | 日志完整记录，保留 set_failed 路径 |
