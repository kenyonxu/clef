# Turn-Wasting 系统性修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 3 个导致 agent 浪费 max_turns 回合配额的系统性问题。

**Architecture:** 三处定向修复 — DEDUP cache key 归一化、prompt 强化、workdir 强制注入补全。

**Tech Stack:** Python 3.12, pytest

---

### Task 1: DEDUP Cache Key 归一化 + list_files workdir 注入

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:808-827`
- Test: `server/tests/test_agent_loop.py` (新增)

**问题 A:** `abc_lint` 虽在 `_DEDUP_TOOLS` 中，但 cache key 用 `json.dumps(args)` 精确匹配。LLM 在不同 turn 中调用 `abc_lint` 时，`plan_path` 参数有时有、有时没有，或者 `abc_content` 尾部空白不同，导致 cache miss。

日志证据：
```
13:33:18 abc_lint {"abc_content": "...", "plan_path": "E:\\...\\plan.json"}
13:33:24 abc_lint {"abc_content": "...", "plan_path": "plan.json"}  ← plan_path 不同，cache miss
```

**问题 B:** `list_files` 不在 line 826 的 workdir 强制注入集合中。当 agent 调用 `list_files(workdir=".")` 时，workdir 不会被覆盖为正确路径。

- [ ] **Step 1: 修改 cache key 计算 — 对 abc_lint 的 abc_content 做 strip 归一化**

在 `server/src/clef_server/orchestrator.py` line 808-816，将 DEDUP cache key 计算改为：

```python
            # Deduplication: return cached result for identical read-only tool calls
            if tool_name in _DEDUP_TOOLS:
                # Normalize args for cache key: strip string values to avoid
                # whitespace-only differences causing cache misses
                norm_args = {
                    k: (v.strip() if isinstance(v, str) else v)
                    for k, v in args.items()
                }
                cache_key = json.dumps({"tool": tool_name, "args": norm_args}, sort_keys=True)
                if cache_key in _call_cache:
                    logger.info("[DEDUP] %s — returning cached result (annotated)", tool_name)
                    cached = _call_cache[cache_key]
                    if isinstance(cached, dict):
                        return {**cached, "_dedup": True, "_dedup_note": "You already called this tool with identical arguments. Use the previous result instead of calling again."}
                    return cached
```

- [ ] **Step 2: 将 list_files 加入 workdir 强制注入集合**

在 `server/src/clef_server/orchestrator.py` line 826，将：
```python
            if tool_name in ("read_file", "write_file", "validate_abc", "abc_lint"):
```
改为：
```python
            if tool_name in ("read_file", "write_file", "validate_abc", "abc_lint", "list_files"):
```

- [ ] **Step 3: 运行已有测试确认无回归**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_agent_loop.py tests/test_tools.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "fix(server): normalize DEDUP cache keys and enforce workdir for list_files

- Strip string args before computing DEDUP cache key to avoid
  whitespace-only cache misses (abc_lint plan_path differences)
- Add list_files to workdir enforcement set so agents can't
  override it with '.' or relative paths"
```

---

### Task 2: Composer Prompt 强化 — 先写后读

**Files:**
- Modify: `server/config/prompts/clef-composer.md`

**问题:** Composer agent 在多个 loop 中把 6 个回合全部花在 read_file/list_files/abc_lint 上，没有调用 write_file。根源是 prompt 中的工作流指引不够强调"先写后读"。

日志证据：
```
13:38:29 turn 1: read_file score.abc
13:38:40 turn 2: list_files
13:38:53 turn 3: read_file _tmp_V_2.abc
13:39:08 turn 4: list_files        ← 重复
13:39:14 turn 5: read_file _tmp_V_1.abc
13:39:19 turn 6: read_file score.abc ← 重复
→ max_turns=6, 没有写任何东西
```

- [ ] **Step 1: 修改 clef-composer.md 工作流指引**

在 `server/config/prompts/clef-composer.md` 的工作流部分，将现有的被动式指引改为强调"先写后读"：

找到当前工作流指引（大约在 line 20-26 附近），替换为：

```markdown
## 推荐工作流

1. **阅读 plan.json**（1 次），理解调性、乐器、小节数
2. **立即生成 ABC 片段并写入 _tmp 文件**（write_file）— 不要反复读取文件
3. **可选：调用 abc_lint 自检**（最多 1 次），如有问题直接修正后重新写入
4. **不要再调用 read_file 或 list_files** — 你已经读过 plan.json，不需要重复读取

### Turn Budget 警告
你最多只有 6 个回合。每个回合只能调用 1 个工具。合理分配：
- turn 1: read_file plan.json
- turn 2-3: write_file（写入 ABC 片段）
- turn 4: abc_lint 自检（可选）
- turn 5-6: 如有错误，修正后 write_file

**不要**在 turn 4-6 继续调用 read_file 或 list_files，这会浪费回合导致无法输出结果。
```

- [ ] **Step 2: 运行已有测试**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_tools.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add server/config/prompts/clef-composer.md
git commit -m "fix(server): strengthen composer prompt to write-early-read-late

Add explicit turn budget warning and recommended workflow to prevent
composer agent from spending all max_turns on read operations."
```

---

### Task 3: 集成验证

**Files:** No code changes — manual verification only

- [ ] **Step 1: 启动服务器运行 compose 会话**

1. 启动服务器: `cd e:/GitHub/clef-dev/server && python -u -m uvicorn clef_server.app:app --host 0.0.0.0 --port 8900`
2. 发送 compose 请求（8 measures, 2 voices）
3. 等待 Phase 1 完成
4. 停止服务器

- [ ] **Step 2: 检查日志验证修复效果**

验证以下指标：
1. `[DEDUP] abc_lint — returning cached result (annotated)` 出现（cache hit）
2. Composer agent 的 loop 中 write_file 出现在 turn 2-3（而非 turn 6+）
3. `list_files` 调用不再出现 `workdir="."`
4. max_turns 警告数量相比之前减少

| 指标 | Before | After (预期) |
|------|--------|---------------|
| abc_lint DEDUP hits per session | 0 | 2+ |
| Composer loops with 0 writes | ~2 | 0 |
| max_turns warnings per session | 4-5 | 1-2 |
| list_files workdir="." | 出现 | 消失 |
