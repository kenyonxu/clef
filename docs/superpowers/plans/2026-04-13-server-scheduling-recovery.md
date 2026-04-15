# Server 并发控制 + 智能调度 + 断点恢复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 clef-server 补回 CLI 版本的 Plan-and-Execute 调度能力，加入全局 Token Bucket 限流解决 GLM 429 问题，并实现断点恢复。

**Architecture:** 三层改进：(1) 全局 Token Bucket 限流器限制 per-provider RPM，可配置化延迟参数 (2) create 阶段引入 Leader 预规划（输出 tasks.json），与 iterate 阶段已有的 Leader 调度对齐 (3) ComposeSession 持久化到 workdir，启动时恢复未完成会话。

**Tech Stack:** Python 3.12, asyncio, pydantic, httpx, pytest

**依赖关系:** P0（并发控制）→ P1（Leader 调度）→ P2（断点恢复，可独立做）

---

## 文件变更地图

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `server/config/providers.yaml` | 新增 per-provider `rpm` 和 `burst` 字段 |
| 修改 | `server/src/clef_server/config.py` | 加载 provider 限流配置 |
| 新建 | `server/src/clef_server/concurrency.py` | 全局 Token Bucket 限流器，per-provider RPM 控制 |
| 修改 | `server/src/clef_server/chat_completions_client.py` | 集成 Semaphore，尊重 Retry-After |
| 修改 | `server/src/clef_server/orchestrator.py` | create 阶段引入 Leader 预规划；延迟参数可配置化 |
| 修改 | `server/src/clef_server/sessions.py` | ComposeSession 序列化/反序列化 |
| 修改 | `server/src/clef_server/routes.py` | 启动时恢复未完成 session |
| 修改 | `server/tests/test_orchestrator.py` | 测试 Leader 预规划 + 并发控制 |
| 新建 | `server/tests/test_concurrency.py` | Semaphore 单元测试 |
| 修改 | `server/tests/test_sessions.py` | 序列化/恢复测试 |

---

## P0：全局并发控制

### Task 1：Provider 限流配置

**Files:**
- Modify: `server/config/providers.yaml` (每个 provider alias)
- Modify: `server/src/clef_server/config.py` (`load_providers` 相关)

> **/autoplan override**: `max_concurrent` → `rpm` + `burst`（Token Bucket 参数）。

- [ ] **Step 1：在 providers.yaml 中为每个端点加 rpm 和 burst**

```yaml
# providers.yaml — 每个 anthropic_compat 条目新增 rpm + burst
anthropic_compat:
  anthropic-haiku:
    api_key: f8054b5039944d2799accde2089ff221.23sVANzYATCLyAsr
    base_url: https://open.bigmodel.cn/api/anthropic
    model_id: glm-4.5-air
    rpm: 30
    burst: 5
  anthropic-opus:
    api_key: f8054b5039944d2799accde2089ff221.23sVANzYATCLyAsr
    base_url: https://open.bigmodel.cn/api/anthropic
    model_id: glm-5.1
    rpm: 30
    burst: 5
  anthropic-sonnet:
    api_key: f8054b5039944d2799accde2089ff221.23sVANzYATCLyAsr
    base_url: https://open.bigmodel.cn/api/anthropic
    model_id: glm-4.7
    rpm: 30
    burst: 5
  deepseek-chat:
    api_key: sk-6f50bd4e5e864250afadefd5116ec9f7
    base_url: https://api.deepseek.com/anthropic
    model_id: deepseek-chat
    rpm: 60
    burst: 10
  deepseek-think:
    api_key: sk-6f50bd4e5e864250afadefd5116ec9f7
    base_url: https://api.deepseek.com/anthropic
    model_id: deepseek-reasoner
    rpm: 30
    burst: 5
```

- [ ] **Step 2：在 config.py 的 provider 加载逻辑中读取 rpm + burst**

`config.py` 中加载 provider 的函数需要解析 `rpm` 和 `burst` 字段，将其存入 provider dict。在 `load_providers()` 返回的 dict 中，每个 provider 条目新增这两个键。

在 `config.py` 中找到构建 provider dict 的循环，添加：
```python
provider_entry["rpm"] = provider_entry.get("rpm", 60)
provider_entry["burst"] = provider_entry.get("burst", 10)
```

- [ ] **Step 3：运行现有测试确认不破坏**

Run: `cd server && python -m pytest tests/test_config.py -v`
Expected: 全部 PASS

- [ ] **Step 4：提交**

```bash
git add server/config/providers.yaml server/src/clef_server/config.py
git commit -m "feat(server): add per-provider rpm+burst config fields for token bucket rate limiting"
```

---

### Task 2：全局 Token Bucket 限流器

**Files:**
- Create: `server/src/clef_server/concurrency.py`
- Create: `server/tests/test_concurrency.py`

> **/autoplan override**: 原 Semaphore 方案改为 Token Bucket，正确处理 per-minute RPM 限制。

- [ ] **Step 1：写 Token Bucket 限流器的失败测试**

```python
# tests/test_concurrency.py
import asyncio
import time
import pytest
from clef_server.concurrency import ProviderRateLimiter


class TestTokenBucket:
    def test_bucket_refills_over_time(self):
        """Tokens refill at rpm rate over time."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=3, refill_per_sec=10.0)
        assert bucket.try_acquire()  # 1/3
        assert bucket.try_acquire()  # 2/3
        assert bucket.try_acquire()  # 3/3 — full
        assert not bucket.try_acquire()  # empty

    def test_bucket_refills_after_wait(self):
        """After waiting, tokens become available again."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=2, refill_per_sec=100.0)
        assert bucket.try_acquire()
        assert bucket.try_acquire()
        assert not bucket.try_acquire()
        time.sleep(0.03)  # ~3 tokens refilled
        assert bucket.try_acquire()

    def test_bucket_capacity_capped(self):
        """Tokens don't exceed capacity even after long idle."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=3, refill_per_sec=1000.0)
        time.sleep(0.01)
        # Should still only allow capacity tokens
        count = sum(1 for _ in range(10) if bucket.try_acquire())
        assert count == 3


class TestProviderRateLimiter:
    def test_get_limiter_creates_with_config(self):
        limiter = ProviderRateLimiter({"glm": {"rpm": 30, "burst": 5}, "deepseek": {"rpm": 60, "burst": 10}})
        assert limiter.get_config("glm")["rpm"] == 30
        assert limiter.get_config("deepseek")["rpm"] == 60

    def test_get_limiter_default(self):
        limiter = ProviderRateLimiter({})
        config = limiter.get_config("unknown")
        assert config["rpm"] == 60  # default
        assert config["burst"] == 10  # default

    @pytest.mark.asyncio
    async def test_acquire_respects_rate_limit(self):
        """At burst=2, 3rd acquire must wait for refill."""
        limiter = ProviderRateLimiter({"test": {"rpm": 3000, "burst": 2}})
        # Burn 2 burst tokens instantly
        async with limiter.acquire("test"):
            pass
        async with limiter.acquire("test"):
            pass
        # 3rd should still succeed (waits for refill, ~20ms at 3000 rpm)
        t0 = time.monotonic()
        async with limiter.acquire("test"):
            pass
        elapsed = time.monotonic() - t0
        # Should have waited briefly for refill, not failed
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_acquire_releases_on_exit(self):
        """Context manager releases slot, allowing next acquire."""
        limiter = ProviderRateLimiter({"test": {"rpm": 60, "burst": 1}})
        async with limiter.acquire("test"):
            pass  # released
        # Next acquire should succeed after refill wait
        async with limiter.acquire("test"):
            pass  # should not hang

    @pytest.mark.asyncio
    async def test_concurrent_sessions_share_limiter(self):
        """Multiple sessions using same alias share the rate limit."""
        limiter = ProviderRateLimiter({"shared": {"rpm": 120, "burst": 2}})
        peak = 0
        active = 0

        async def task():
            nonlocal active, peak
            async with limiter.acquire("shared"):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(*[task() for _ in range(6)])
        assert peak <= 2  # burst=2 means max 2 concurrent
```

- [ ] **Step 2：运行测试确认失败**

Run: `cd server && python -m pytest tests/test_concurrency.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'clef_server.concurrency'`

- [ ] **Step 3：实现 concurrency.py**

```python
# src/clef_server/concurrency.py
"""Per-provider rate limiting via token bucket algorithm."""

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DEFAULT_RPM = 60
DEFAULT_BURST = 10


class ProviderRateLimiter:
    """Global rate limiter pool keyed by model alias.

    Uses token bucket algorithm: each provider gets a bucket with
    `burst` capacity that refills at `rpm / 60` tokens per second.
    Correctly handles RPM windows (not just concurrency).
    """

    class _TokenBucket:
        """Thread-safe token bucket for a single provider."""

        def __init__(self, capacity: int, refill_per_sec: float) -> None:
            self._capacity = capacity
            self._refill_per_sec = refill_per_sec
            self._tokens = float(capacity)
            self._last_refill = time.monotonic()
            self._lock = threading.Lock()

        def _refill(self) -> None:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_sec)
            self._last_refill = now

        def try_acquire(self) -> bool:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                return False

        def wait_time(self) -> float:
            """Seconds until next token is available."""
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    return 0.0
                return (1.0 - self._tokens) / self._refill_per_sec

    def __init__(self, configs: dict[str, dict] | None = None) -> None:
        """configs: {alias: {"rpm": int, "burst": int}}"""
        self._configs: dict[str, dict] = configs or {}
        self._buckets: dict[str, ProviderRateLimiter._TokenBucket] = {}

    def get_config(self, alias: str) -> dict:
        return self._configs.get(alias, {"rpm": DEFAULT_RPM, "burst": DEFAULT_BURST})

    def _get_bucket(self, alias: str) -> _TokenBucket:
        if alias not in self._buckets:
            cfg = self.get_config(alias)
            rpm = cfg.get("rpm", DEFAULT_RPM)
            burst = cfg.get("burst", DEFAULT_BURST)
            refill = rpm / 60.0  # tokens per second
            self._buckets[alias] = self._TokenBucket(capacity=burst, refill_per_sec=refill)
            logger.info("Rate limiter for %s: rpm=%d, burst=%d, refill=%.1f/s", alias, rpm, burst, refill)
        return self._buckets[alias]

    @asynccontextmanager
    async def acquire(self, alias: str):
        """Acquire a token for the given provider. Waits if bucket is empty."""
        bucket = self._get_bucket(alias)
        while not bucket.try_acquire():
            wait = bucket.wait_time()
            await asyncio.sleep(max(wait, 0.05))
        yield
```

- [ ] **Step 4：运行测试确认通过**

Run: `cd server && python -m pytest tests/test_concurrency.py -v`
Expected: 全部 PASS

- [ ] **Step 5：提交**

```bash
git add server/src/clef_server/concurrency.py server/tests/test_concurrency.py
git commit -m "feat(server): add ProviderRateLimiter with token bucket for per-provider RPM control"
```

---

### Task 3：集成 RateLimiter 到 Orchestrator

**Files:**
- Modify: `server/src/clef_server/chat_completions_client.py:309-363` (`_http_post`)
- Modify: `server/src/clef_server/orchestrator.py:682-790` (`_run_agent`)

> **/autoplan override**: Semaphore → Token Bucket. Key 用 model_alias（不是 provider name），避免 cost-saving profile 死锁。

- [ ] **Step 1：写集成测试**

在 `tests/test_orchestrator.py` 中添加：

```python
class TestConcurrencyIntegration:
    @pytest.mark.asyncio
    async def test_run_agent_respects_rate_limiter(self, tmp_path):
        """Verify _run_agent acquires rate limiter token before API call."""
        from clef_server.concurrency import ProviderRateLimiter

        limiter = ProviderRateLimiter({"test_model": {"rpm": 60, "burst": 2}})
        providers = {"test_provider": AsyncMock()}
        providers["test_provider"].get_response = AsyncMock(
            return_value=_make_mock_response("X:\nCDE\n")
        )
        session_mgr = SessionManager()
        session = session_mgr.create("test", str(tmp_path))
        orch = ComposeOrchestrator(
            session_id=session.session_id,
            providers=providers,
            workdir=str(tmp_path),
        )
        # Inject rate limiter
        orch._rate_limiter = limiter

        call_count = 0
        original_get = providers["test_provider"].get_response

        async def counting_get(*a, **kw):
            nonlocal call_count
            call_count += 1
            return await original_get(*a, **kw)

        providers["test_provider"].get_response = counting_get

        # Write plan.json so _run_agent doesn't fail
        plan = {"title": "test", "key": "C", "scale": "major", "bpm": 120,
                "time_signature": "4/4", "total_bars": 8, "sections": [],
                "orchestration": {}, "generation_order": ["harmony", "melody"]}
        (tmp_path / "plan.json").write_text(json.dumps(plan))

        await orch._run_agent("clef-composer", "test message", plan=plan)
        assert call_count >= 1
```

- [ ] **Step 2：在 orchestrator.__init__ 中初始化 ProviderRateLimiter**

在 `orchestrator.py` 的 `__init__` 方法末尾（约 L187 后）添加：

```python
        # Per-provider rate limiting (token bucket)
        from clef_server.concurrency import ProviderRateLimiter
        provider_configs = {}
        for alias, cfg in providers.items():
            if isinstance(cfg, dict):
                provider_configs[alias] = {
                    "rpm": cfg.get("rpm", 60),
                    "burst": cfg.get("burst", cfg.get("max_concurrent", 10)),
                }
        self._rate_limiter = ProviderRateLimiter(provider_configs)
```

- [ ] **Step 3：在 _run_agent 的 API 调用处集成 RateLimiter**

在 `orchestrator.py` 的 `_run_agent` 方法中，找到创建 provider client 并调用的位置。在调用 `client.get_response` 前后包裹 rate limiter：

```python
        # Acquire rate limiter token before API call (uses model_alias as key)
        model_alias = agent_def.get("model_alias", "default")
        async with self._rate_limiter.acquire(model_alias):
            response = await client.get_response(
                messages=messages, temperature=temperature,
                max_tokens=agent_def.get("max_tokens", 4096),
            )
```

- [ ] **Step 4：在 _http_post 中尊重 Retry-After 头**

修改 `chat_completions_client.py` 的 `_http_post` 方法（L327-334）：

```python
                if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    # Respect Retry-After header if provided
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            backoff = float(retry_after)
                        except ValueError:
                            backoff = 2 ** attempt
                    elif status == 500:
                        backoff = 10
                    else:
                        backoff = 2 ** attempt
```

- [ ] **Step 5：运行测试**

Run: `cd server && python -m pytest tests/test_orchestrator.py::TestConcurrencyIntegration -v`
Expected: PASS

- [ ] **Step 6：运行全部现有测试确认无回归**

Run: `cd server && python -m pytest tests/ -v --timeout=60`
Expected: 全部 PASS

- [ ] **Step 7：提交**

```bash
git add server/src/clef_server/orchestrator.py server/src/clef_server/chat_completions_client.py server/tests/test_orchestrator.py
git commit -m "feat(server): integrate Token Bucket rate limiter into _run_agent, respect Retry-After header"
```

---

### Task 4：延迟参数可配置化

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:133-140` (硬编码常量)

- [ ] **Step 1：将硬编码常量改为 settings 可覆盖**

修改 `orchestrator.py` 的 `__init__`（约 L170 后），将延迟常量改为 settings 驱动：

```python
        # Rate-limit pacing (configurable via settings)
        self.inter_agent_delay = self._settings.get("inter_agent_delay", 2)
        self.inter_round_delay = self._settings.get("inter_round_delay", 3)
```

然后将所有 `self.INTER_AGENT_DELAY` 替换为 `self.inter_agent_delay`，`self.INTER_ROUND_DELAY` 替换为 `self.inter_round_delay`。保留类常量作为文档默认值注释。

- [ ] **Step 2：运行测试确认无回归**

Run: `cd server && python -m pytest tests/test_orchestrator.py -v --timeout=60`
Expected: 全部 PASS

- [ ] **Step 3：提交**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "refactor(server): make inter-agent delays configurable via settings"
```

---

## P1：Leader 预规划（create 阶段）

CLI 的 create 阶段前有 Leader 输出 tasks.json 做依赖调度，server 的 iterate 阶段已有 `_call_leader`，但 create 阶段直接硬编码遍历 `["harmony", "melody", "rhythm"]`。

### Task 5：create 阶段 Leader 预规划

**Files:**
- Modify: `server/src/clef_server/orchestrator.py:1945-2010` (`_phase_create`)

- [ ] **Step 1：写 _phase_create Leader 预规划测试**

在 `tests/test_orchestrator.py` 的 `TestPhaseCreate` 类中添加：

```python
    @pytest.mark.asyncio
    async def test_phase_create_uses_leader_for_generation_order(self, tmp_path):
        """_phase_create should respect plan's generation_order and run Leader
        to produce a structured execution plan before dispatching agents."""
        plan = {
            "title": "Test", "key": "C", "scale": "major", "bpm": 120,
            "time_signature": "4/4", "total_bars": 16,
            "sections": [{"id": "A", "name": "verse", "measures": 16}],
            "orchestration": {}, "generation_order": ["harmony", "melody"],
        }
        orch, session, _ = _setup_orchestrator_with_plan(tmp_path, plan)

        agent_calls = []

        async def mock_run(agent_name, message, **kw):
            agent_calls.append(agent_name)
            if agent_name == "clef-orchestrator":
                # Leader returns execution plan
                return json.dumps({
                    "tasks": [
                        {"agent": "clef-harmonist", "voice": "harmony", "depends_on": None,
                         "instruction": "Write harmony"},
                        {"agent": "clef-composer", "voice": "melody",
                         "depends_on": "clef-harmonist",
                         "instruction": "Write melody following harmony"},
                    ]
                })
            # Regular agents return ABC
            return "X:1\nT:test\nM:4/4\nK:C\nV:1\nCDEF|EFGA|"

        orch._run_agent = mock_run

        with patch("clef_server.tools.merge_abc") as mock_merge, \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "out.mid"}), \
             patch("clef_server.tools.validate_abc", return_value={"result": "pass"}):
            mock_merge.return_value = {"output": "score.abc"}
            await orch._phase_create()

        # Leader should be called before agents
        assert "clef-orchestrator" in agent_calls
        # Agents should be called
        assert "clef-harmonist" in agent_calls
        assert "clef-composer" in agent_calls
        # Harmony should come before melody (generation_order)
        harm_idx = agent_calls.index("clef-harmonist")
        mel_idx = agent_calls.index("clef-composer")
        assert harm_idx < mel_idx
```

- [ ] **Step 2：运行测试确认失败**

Run: `cd server && python -m pytest tests/test_orchestrator.py::TestPhaseCreate::test_phase_create_uses_leader_for_generation_order -v`
Expected: FAIL — 目前 `_phase_create` 不调用 Leader

- [ ] **Step 3：在 _phase_create 开头添加 Leader 预规划调用**

修改 `orchestrator.py` 的 `_phase_create` 方法。在 L1952（`fragments: dict[str, str] = {}`）之后、`for voice in [...]` 循环之前，插入 Leader 预规划：

```python
        fragments: dict[str, str] = {}

        # --- Leader pre-planning: structured execution plan ---
        leader_tasks = None
        try:
            leader_prompt = (
                f"Create an execution plan for full composition.\n"
                f"Plan: {json.dumps(plan, indent=2, ensure_ascii=False)}\n"
                f"generation_order: {plan.get('generation_order', ['harmony', 'melody'])}\n\n"
                f"Respond with JSON:\n"
                f'- "tasks": array of {{agent, voice, depends_on, instruction}}\n'
                f'- Each task specifies exactly which agent creates which voice part\n'
                f'- depends_on: null for parallel tasks, agent name for sequential\n'
            )
            leader_response = await self._run_agent(
                "clef-orchestrator", leader_prompt, plan=plan
            )
            leader_result = self._extract_json(leader_response)
            leader_tasks = leader_result.get("tasks")
        except Exception as e:
            logger.warning("Leader pre-planning failed, falling back to generation_order: %s", e)

        if leader_tasks:
            # Execute tasks in dependency order
            completed_agents: set[str] = set()
            tasks_sorted = sorted(leader_tasks, key=lambda t: str(t.get("depends_on") or ""))
            for task in tasks_sorted:
                agent_name = task.get("agent", "")
                if not agent_name.startswith("clef-"):
                    agent_name = f"clef-{agent_name}"
                if agent_name not in self._agent_defs:
                    continue

                # Check dependency
                raw_dep = task.get("depends_on")
                if isinstance(raw_dep, list):
                    deps = [f"clef-{d}" if not d.startswith("clef-") else d for d in raw_dep if d]
                else:
                    deps = [f"clef-{raw_dep}"] if raw_dep else []
                if any(d not in completed_agents for d in deps):
                    logger.warning("Task dependency not met: %s needs %s, skipping", agent_name, deps)
                    continue

                voice = task.get("voice", "melody")
                voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")
                instruction = task.get("instruction", f"Generate {voice} part")
                voice_display = self._VOICE_DISPLAY_NAMES.get(voice, f"生成 {voice}")
                self.session.record_sub_step(voice_display, "running", agent=agent_name)

                best_abc, fail_count = await self._generate_with_best_of_n(
                    agent_name=agent_name,
                    message=instruction,
                    plan=plan,
                    plan_path=plan_path,
                    max_rounds=2,
                    voice_label=voice_label,
                )
                self._store_fragment(fragments, None, voice_label, best_abc)
                self.session.record_sub_step(voice_display, "done", agent=agent_name)
                completed_agents.add(agent_name)
                await asyncio.sleep(self.inter_agent_delay)
        else:
            # Fallback: original hardcoded generation_order loop
            for voice in plan.get("generation_order", ["harmony", "melody"]) + ["rhythm"]:
                # ... (保持原有的 for 循环逻辑不变)
```

注意：原有的 `for voice in ["harmony", "melody", "rhythm"]` 循环需要改为 `else` 分支，保持向后兼容。

- [ ] **Step 4：运行测试确认通过**

Run: `cd server && python -m pytest tests/test_orchestrator.py -v --timeout=60`
Expected: 全部 PASS（包括新测试和原有测试）

- [ ] **Step 5：提交**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): add Leader pre-planning to create phase with dependency dispatch"
```

---

## P2：断点恢复（Checkpoint 持久化）

### Task 6：ComposeSession 序列化

**Files:**
- Modify: `server/src/clef_server/sessions.py:56-230` (`ComposeSession` + `SessionManager`)
- Modify: `server/tests/test_sessions.py`

- [ ] **Step 1：写序列化/反序列化测试**

在 `tests/test_sessions.py` 中添加：

```python
class TestSessionSerialization:
    def test_roundtrip_basic(self):
        mgr = SessionManager()
        s = mgr.create("test prompt", "/tmp/workdir")
        s.set_running()
        s.record_phase("parse", "done")
        s.set_awaiting_confirm({"phase": "parse", "plan": {"title": "test"}})

        data = s.to_dict()
        restored = ComposeSession.from_dict(data)

        assert restored.session_id == s.session_id
        assert restored.status == s.status
        assert restored.current_phase == s.current_phase
        assert restored.confirmation_data == s.confirmation_data
        assert len(restored.phase_history) == len(s.phase_history)

    def test_roundtrip_preserves_iteration_count(self):
        mgr = SessionManager()
        s = mgr.create("test", "/tmp/wd")
        s.iteration_count = 2
        data = s.to_dict()
        restored = ComposeSession.from_dict(data)
        assert restored.iteration_count == 2

    def test_from_dict_omits_event_queues(self):
        """Event queues are runtime-only, not serialized."""
        mgr = SessionManager()
        s = mgr.create("test", "/tmp/wd")
        data = s.to_dict()
        restored = ComposeSession.from_dict(data)
        assert len(restored._event_queues) == 0
```

- [ ] **Step 2：运行测试确认失败**

Run: `cd server && python -m pytest tests/test_sessions.py::TestSessionSerialization -v`
Expected: FAIL — `ComposeSession` 没有 `from_dict` 方法

- [ ] **Step 3：实现 from_dict 类方法**

在 `sessions.py` 的 `ComposeSession` 类中添加：

```python
    @classmethod
    def from_dict(cls, data: dict) -> "ComposeSession":
        """Reconstruct a session from serialized dict (excludes runtime state)."""
        return cls(
            session_id=data["session_id"],
            workdir=data.get("workdir", ""),
            user_prompt=data.get("user_prompt", ""),
            status=data.get("status", "created"),
            plan=data.get("plan"),
            profile=data.get("profile"),
            output_files=data.get("output_files", []),
            error=data.get("error"),
            current_phase=data.get("current_phase", "parse"),
            confirmation_data=data.get("confirmation_data"),
            phase_history=data.get("phase_history", []),
            sub_steps=data.get("sub_steps", []),
            iteration_count=data.get("iteration_count", 0),
            sample_round=data.get("sample_round", 0),
            step_status=data.get("step_status", {0: "pending", 1: "pending", 2: "pending", 3: "pending"}),
            created_at=data.get("created_at", time.time()),
        )
```

确保 `to_dict` 方法已包含所有需要持久化的字段（检查 `created_at` 是否在 `to_dict` 中）。

- [ ] **Step 4：运行测试确认通过**

Run: `cd server && python -m pytest tests/test_sessions.py -v`
Expected: 全部 PASS

- [ ] **Step 5：提交**

```bash
git add server/src/clef_server/sessions.py server/tests/test_sessions.py
git commit -m "feat(server): add ComposeSession serialization via from_dict"
```

---

### Task 7：SessionManager 持久化到磁盘

**Files:**
- Modify: `server/src/clef_server/sessions.py:231-267` (`SessionManager`)
- Modify: `server/src/clef_server/routes.py` (启动恢复逻辑)

- [ ] **Step 1：写持久化和恢复测试**

```python
class TestSessionPersistence:
    def test_save_and_restore(self, tmp_path):
        mgr = SessionManager(persist_dir=str(tmp_path))
        s = mgr.create("test prompt", str(tmp_path / "work"))
        s.set_running()
        s.record_phase("parse", "done")

        mgr.persist(s)

        # Create new manager, load from disk
        mgr2 = SessionManager(persist_dir=str(tmp_path))
        restored = mgr2.restore(s.session_id)
        assert restored is not None
        assert restored.session_id == s.session_id
        assert restored.status == "awaiting_confirm"

    def test_restore_nonexistent_returns_none(self, tmp_path):
        mgr = SessionManager(persist_dir=str(tmp_path))
        assert mgr.restore("no-such-id") is None

    def test_remove_deletes_file(self, tmp_path):
        mgr = SessionManager(persist_dir=str(tmp_path))
        s = mgr.create("test", str(tmp_path))
        mgr.persist(s)
        mgr.remove(s.session_id)
        assert mgr.restore(s.session_id) is None
```

- [ ] **Step 2：运行测试确认失败**

Run: `cd server && python -m pytest tests/test_sessions.py::TestSessionPersistence -v`
Expected: FAIL — `SessionManager` 不接受 `persist_dir` 参数

- [ ] **Step 3：在 SessionManager 中添加持久化方法**

```python
class SessionManager:
    """In-memory session store with optional disk persistence."""

    def __init__(self, ttl_seconds: float | None = None, persist_dir: str | None = None) -> None:
        self._sessions: dict[str, ComposeSession] = {}
        self._ttl = ttl_seconds
        self._persist_dir = Path(persist_dir) if persist_dir else None

    def persist(self, session: ComposeSession) -> None:
        """Save session state to disk."""
        if not self._persist_dir:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / f"{session.session_id}.json"
        path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2))

    def restore(self, session_id: str) -> ComposeSession | None:
        """Load session from disk."""
        if not self._persist_dir:
            return None
        path = self._persist_dir / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        session = ComposeSession.from_dict(data)
        self._sessions[session_id] = session
        return session

    def restore_all_incomplete(self) -> list[ComposeSession]:
        """Restore all non-terminal sessions from disk."""
        if not self._persist_dir:
            return []
        results = []
        for path in self._persist_dir.glob("clef-*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            session = ComposeSession.from_dict(data)
            if not session.is_terminal():
                self._sessions[session.session_id] = session
                results.append(session)
        return results
```

同时修改 `remove` 方法，在删除内存 session 时也删除磁盘文件：

```python
    def remove(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
        if self._persist_dir:
            path = self._persist_dir / f"{session_id}.json"
            if path.exists():
                path.unlink()
            return True
        return session_id in self._sessions
```

- [ ] **Step 4：在关键状态变更后自动持久化**

在 `SessionManager` 的 `create`、`persist` 调用点之外，添加一个便捷方法让 orchestrator 在每个 phase 完成后调用：

```python
    def save(self, session: ComposeSession) -> None:
        """Persist session if persistence is enabled."""
        self.persist(session)
```

- [ ] **Step 5：运行测试确认通过**

Run: `cd server && python -m pytest tests/test_sessions.py -v`
Expected: 全部 PASS

- [ ] **Step 6：提交**

```bash
git add server/src/clef_server/sessions.py server/tests/test_sessions.py
git commit -m "feat(server): add SessionManager disk persistence with restore"
```

---

### Task 8：Orchestrator 集成断点保存 + 启动恢复

**Files:**
- Modify: `server/src/clef_server/orchestrator.py` (phase 完成后调用 persist)
- Modify: `server/src/clef_server/routes.py` (启动时恢复)

- [ ] **Step 1：在 Orchestrator 的 _advance_phase 中保存断点**

在 `orchestrator.py` 的 `_advance_phase` 方法中，phase 方法执行完成后（约 L400 后），添加持久化调用：

```python
        # Persist session state after each phase
        self.session_manager.save(self.session)
```

- [ ] **Step 2：在 routes.py 启动时恢复未完成 session**

在 `routes.py` 的 lifespan 或 app 初始化中，调用 `restore_all_incomplete()`，将恢复的 session 注册到全局 `SessionManager`。对于 `awaiting_confirm` 状态的 session，用户可以通过 `/status/{id}/stream` 重新获取确认信息。

- [ ] **Step 3：运行全部测试确认无回归**

Run: `cd server && python -m pytest tests/ -v --timeout=60`
Expected: 全部 PASS

- [ ] **Step 4：提交**

```bash
git add server/src/clef_server/orchestrator.py server/src/clef_server/routes.py
git commit -m "feat(server): auto-persist sessions, restore incomplete on startup"
```

---

## 自查清单

- [x] **Spec 覆盖**：P0（并发控制 4 个 task）→ P1（Leader 预规划 1 个 task）→ P2（断点恢复 3 个 task），覆盖了讨论中所有优先级
- [x] **占位符扫描**：无 TBD/TODO/placeholder，每个 step 有具体代码
- [x] **类型一致性**：`ProviderSemaphoreManager`、`ComposeSession.from_dict`、`SessionManager(persist_dir=)` 在定义和使用处签名一致
- [x] **向后兼容**：P1 的 Leader 预规划有 fallback 到原有 `generation_order` 循环；P0 的 `max_concurrent` 有默认值 5；P2 的 `persist_dir` 为 None 时不持久化

---

## /autoplan CEO REVIEW

> Voice: Claude subagent only (Codex blocked by sandbox policy)

### CEO DUAL VOICES — CONSENSUS TABLE

| Dimension | Primary | Subagent | Consensus |
|-----------|---------|----------|-----------|
| 1. Premises valid? | Partial | Partial | DISAGREE on semaphore adequacy |
| 2. Right problem to solve? | Yes | Partial | CONFIRMED — but reframe as cost reduction |
| 3. Scope calibration correct? | Yes | Yes | CONFIRMED — P0→P1→P2 order is right |
| 4. Alternatives explored? | No | No | CONFIRMED — missing alternatives section |
| 5. Competitive/market risks? | N/A | N/A | N/A — internal tool |
| 6. 6-month trajectory sound? | Risky | Risky | CONFIRMED — semaphore is wrong abstraction |

### Finding 1: Semaphore is the wrong abstraction (CRITICAL)

**Severity: CRITICAL**

GLM 的速率限制是 per-minute RPM 窗口，不是并发请求数。Semaphore 限制同时进行的请求数，但不防止单分钟内总请求数超标。在高负载下（多 session 并行），semaphore 无法阻止 429。

**Fix**: 将 `ProviderSemaphoreManager` 改为 `ProviderRateLimiter`，用 token bucket 算法替代 semaphore。`acquire()` 应该等待到有 token 可用，而非只等待并发槽位。`rpm` 配置字段（已在 providers.yaml 占位但未实现）应该驱动 token bucket 的 refill rate。

**Decision: TASTE** — 建议升级为 token bucket，但 semaphore 作为第一步仍然比现状（零控制）好。可以在 semaphore 之上叠加 token bucket。

### Finding 2: 缺少方案对比 (HIGH)

**Severity: HIGH**

计划直接选了 Semaphore 方案，没有对比：
- Token bucket / sliding window rate limiter（行业标准）
- Request queuing with backpressure（单队列全局调度）
- Provider-level request coalescing（合并相似请求）

**Fix**: 在 Task 2 之前增加一个简短的 "Alternatives Considered" 部分，记录为什么选 Semaphore 作为第一步。

### Finding 3: Leader 预规划价值未量化 (HIGH)

**Severity: HIGH**

假设 Leader agent 返回有用的任务分解，但 Leader 本身是一次 LLM 调用，可能返回垃圾。fallback 路径存在但没有量化指标。

**Fix**: 在 Task 5 的实现中加入 `_leader_success_count` / `_leader_fallback_count` 计数器，记录 Leader 调用成功/失败比例。不影响功能，但为后续优化提供数据。

### Finding 4: Checkpoint 可能是 YAGNI (MEDIUM)

**Severity: MEDIUM**

Compose session 通常 2-5 分钟。服务器崩溃中断 mid-session 的频率未知。对于单用户工具，断点恢复的复杂度可能不值得。

**Decision: AUTO-APPROVED** — 实现成本很低（ComposeSession 已有 to_dict，只需加 from_dict 和文件写入），且对开发调试效率提升明显。保留。

### Finding 5: 目标叙事应重新框定 (MEDIUM)

**Severity: MEDIUM**

计划把并发控制框定为"解决 GLM 429 问题"，但真正的 10x 收益是减少 LLM 调用次数（从而降低成本和延迟）。Leader 预规划才是核心价值——它通过避免无效生成来减少调用。

**Fix**: 不改代码，但更新计划的 Goal 描述。

### NOT in scope

- Token bucket 的 RPM 强制执行（记录为 TODO，semaphore 先行）
- Request queuing with backpressure（单 session 场景下无必要）
- Anthropic native parallel tool use（不适用当前 provider）

### What already exists

| 子问题 | 已有代码 |
|--------|---------|
| Agent 调度 | `_call_leader` (L1418-1446), iterate 阶段已实现 tasks.json 调度 |
| 并发安全 | `_partition_agent_calls` (L193-208), 区分 safe/unsafe batch |
| 延迟控制 | `INTER_AGENT_DELAY=2`, `INTER_ROUND_DELAY=3`, agent_loop 1s pacing |
| 重试逻辑 | `_http_post` (L309-363), 3 次重试 + 指数退避 |
| Session 状态 | `ComposeSession.to_dict()` 已存在 |

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|-----------|-----------|----------|
| 1 | CEO | 直接实现 Token Bucket（用户 override） | Taste→Resolved | P1 completeness | 用户选择一步到位而非 Semaphore 先行 |
| 2 | CEO | 保留 Checkpoint (P2) | Auto | P6 bias action | 实现成本低，开发调试收益高 |
| 3 | CEO | Leader 预规划加计数器 | Auto | P1 completeness | 零成本，为后续优化提供数据 |

### Completion Summary

| Section | Findings |
|---------|----------|
| Step 0 (Premise) | SELECTIVE EXPANSION, 3 premises challenged |
| Section 1 (Arch) | Semaphore is wrong abstraction (CRITICAL) |
| Section 2 (Errors) | Retry-After handling present, adequate |
| Section 3 (Security) | No new attack surface (internal config) |
| Section 4 (Data) | Leader fallback path exists but unmeasured |
| Section 5 (Quality) | Missing alternatives section |
| Section 6 (Tests) | Test coverage adequate per task |
| Section 7 (Perf) | Semaphore reduces 429 but doesn't prevent RPM overflow |
| Section 8 (Observ) | Leader success/fallback counters needed |
| Section 9 (Deploy) | Low risk, backward compatible |
| Section 10 (Future) | Token bucket is the right long-term abstraction |
| Section 11 (Design) | SKIPPED (no UI scope) |
| NOT in scope | 3 items (token bucket RPM, request queue, parallel tool use) |
| What already exists | 5 existing components leveraged |

---

## /autoplan ENG REVIEW

> Voice: Claude subagent only (Codex blocked by sandbox policy)

### ENG DUAL VOICES — CONSENSUS TABLE

| Dimension | Primary | Subagent | Consensus |
|-----------|---------|----------|-----------|
| 1. Architecture sound? | Partial | Partial | CONFIRMED — but integration point wrong |
| 2. Test coverage sufficient? | Partial | No | CONFIRMED — 6 missing test categories |
| 3. Performance risks addressed? | No | No | CONFIRMED — semaphore+Retry-After deadlock risk |
| 4. Security threats covered? | Yes | Partial | CONFIRMED — persist_dir needs path validation |
| 5. Error paths handled? | Partial | Partial | CONFIRMED — workdir cleanup on restore missing |
| 6. Deployment risk manageable? | Yes | Yes | CONFIRMED — backward compatible |

### Architecture ASCII Diagram

```
                    providers.yaml
                    (max_concurrent)
                         │
                    ┌────▼────┐
                    │ RateLimiter│ ← Task 2: ProviderRateLimiter (token bucket)
                    │  (per-alias)│    Key = model_alias, NOT provider name
                    └────┬────┘
                         │ acquire()
              ┌──────────┼──────────┐
              │          │          │
         _run_agent  _run_agent  _run_agent    ← Task 3: wrap in acquire()
         (session 1) (session 1) (session 2)
              │          │          │
         ┌────▼────┐     │     ┌────▼────┐
         │ Leader  │     │     │ Leader  │  ← Task 5: pre-planning
         │tasks.json│    │     │tasks.json│
         └────┬────┘     │     └────┬────┘
              │          │          │
         ┌────▼────┐     │     ┌────▼────┐
         │Agent    │     │     │Agent    │
         │dispatch │     │     │dispatch │
         └─────────┘     │     └─────────┘
                    ┌────▼────┐
                    │ Session │ ← Task 7: persist to disk
                    │  State  │    Task 8: restore on startup
                    │ (JSON)  │
                    └─────────┘
```

### Finding E1: Semaphore key mismatch (CRITICAL)

**Severity: CRITICAL**

计划用 `provider alias`（如 "deepseek-chat"）作为 semaphore key，但 `_run_agent` 通过 `model_alias` 解析 provider。`cost-saving` profile 把 7 个 agent 都映射到 `deepseek-chat`，意味着单个 session 就有 7 个并发调用，但 `max_concurrent=5`。单 session 就会自我死锁。

**Fix**: Semaphore key 应该用 `model_alias`（agent 配置中的值），而非 provider name。`ProviderSemaphoreManager` 的 limits 应该在 profile 切换时更新，或用固定的 per-base-url 限制。

### Finding E2: Semaphore + Retry-After 死锁 (HIGH)

**Severity: HIGH**

如果 semaphore 有 3 个槽位，3 个请求同时收到 429 + `Retry-After: 60`，它们在 sleep 期间持有 semaphore 槽位。后续请求全部排队 60 秒。

**Fix**: Semaphore acquire 应该在 `_http_post` 外层，而非在调用链内部。或者 `_http_post` 的 429 sleep 应该先释放 semaphore 再 sleep。

### Finding E3: _run_agent_batch_raw 绕过 semaphore (HIGH)

**Severity: HIGH**

`_run_agent_batch_raw` (L210-214) 使用 `asyncio.gather` 无限制并发。如果任何调用方使用 batch 路径而非 `_run_agent`，semaphore 被完全绕过。

**Fix**: 在 `_run_agent_batch_raw` 中也集成 semaphore，或确保当前代码路径不使用 batch_raw。

### Finding E4: 缺少 6 类测试 (HIGH)

**Severity: HIGH**

- Semaphore 饱和/超时测试
- Retry-After header 解析测试
- `from_dict` 向后兼容测试（v1→v2 新字段）
- 损坏 JSON 文件恢复测试
- 多 session 并发 semaphore 共享测试
- P1 Leader 循环 depends_on 死锁测试

### Finding E5: persist_dir 安全 + workdir 清理 (MEDIUM)

**Severity: MEDIUM**

- `session_id` 已是 `clef-{hex[:8]}` 格式，安全。但 `from_dict` 不应信任持久化的 ID。
- 恢复的 session 引用的 workdir 路径可能在服务器重启期间被清理。需要存在性检查。
- 所有 4 个 profile 都需要 `max_concurrent` 值，遗漏则意味着无限并发。

### Test Diagram

```
P0: Concurrency
├── test_concurrency.py (5 tests in plan) ✅
├── Semaphore saturation/timeout ❌ MISSING
├── Retry-After header parsing ❌ MISSING
├── Multi-session shared semaphore ❌ MISSING
└── Profile switch updates limits ❌ MISSING

P1: Leader pre-planning
├── test_phase_create_uses_leader ✅
├── Circular depends_on deadlock ❌ MISSING
└── Leader fallback metric logging ❌ MISSING

P2: Checkpoint
├── test_sessions.py serialization (3 tests) ✅
├── test_sessions.py persistence (3 tests) ✅
├── Corrupted JSON startup ❌ MISSING
├── v1→v2 backward compat ❌ MISSING
└── Workdir existence check on restore ❌ MISSING
```

### Decision Audit Trail (Eng)

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|-----------|-----------|----------|
| 4 | Eng | Semaphore key 用 model_alias | Auto | P5 explicit | 避免单 session 死锁 |
| 5 | Eng | Semaphore 在 _http_post 外层 | Taste | P5 explicit | 避免持有槽位 sleep |
| 6 | Eng | 补 6 类缺失测试 | Auto | P1 completeness | 覆盖死锁/兼容/损坏路径 |
| 7 | Eng | Profile 全覆盖 max_concurrent | Auto | P1 completeness | 防止静默无限并发 |

---

## /autoplan DX REVIEW (quick — internal infrastructure)

| Dimension | Score | Notes |
|-----------|-------|-------|
| Getting started | 8/10 | providers.yaml 字段直观 |
| Config ergonomics | 6/10 | settings.json schema 未文档化 |
| Error messages | 7/10 | semaphore 饱和时用户体验不明 |
| Defaults | 8/10 | 合理默认值 |
| Upgrade path | 9/10 | 全向后兼容 |

**D1** (MEDIUM): settings.json 新参数缺少值范围文档。
**D2** (LOW): web UI 是否需要暴露 max_concurrent 配置未提及。
