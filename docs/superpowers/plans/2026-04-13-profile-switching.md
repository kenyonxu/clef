# Provider Profile Switching 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户通过 Web UI 下拉框选择 provider profile，全量切换所有 agent 的 model_alias 映射，分散 API 请求压力。

**Architecture:** 新增 `config/profiles.yaml` 存储多个命名 profile（每个 profile 是一组 agent→model_alias 映射）。后端新增 `load_profiles()` 函数和 `GET /api/profiles` 端点。compose 请求可选携带 `profile` 参数，orchestrator 用 profile 覆盖 agents.yaml 的 model_alias。前端在 compose 输入框上方加 profile 下拉框。

**Tech Stack:** Python 3.12, YAML, FastAPI, React + TypeScript, localStorage

---

### Task 1: 创建 profiles.yaml + 后端加载函数

**Files:**
- Create: `server/config/profiles.yaml`
- Modify: `server/src/clef_server/config.py:105` (在 `load_agent_configs` 之后插入)
- Test: `server/tests/test_config.py` (新增)

- [x] **Step 1: 创建 `config/profiles.yaml`**

```yaml
profiles:
  default:
    display_name: "默认 (智谱 GLM)"
    agents:
      clef-composer: anthropic-opus
      clef-harmonist: anthropic-opus
      clef-rhythmist: anthropic-sonnet
      clef-orchestrator: anthropic-sonnet
      clef-reviewer: anthropic-sonnet
      clef-revision: anthropic-haiku
      clef-repair: anthropic-haiku

  cost-saving:
    display_name: "低成本 (全 DeepSeek)"
    agents:
      clef-composer: deepseek-chat
      clef-harmonist: deepseek-chat
      clef-rhythmist: deepseek-chat
      clef-orchestrator: deepseek-chat
      clef-reviewer: deepseek-chat
      clef-revision: deepseek-chat
      clef-repair: deepseek-chat

  mixed:
    display_name: "混合 (主力智谱+审查DeepSeek)"
    agents:
      clef-composer: anthropic-opus
      clef-harmonist: anthropic-opus
      clef-rhythmist: anthropic-sonnet
      clef-orchestrator: anthropic-sonnet
      clef-reviewer: deepseek-chat
      clef-revision: deepseek-chat
      clef-repair: deepseek-chat
```

- [x] **Step 2: 在 `config.py` 的 `load_agent_configs` 函数之后添加 `load_profiles`**

在 `server/src/clef_server/config.py` 的 `load_agent_configs` 函数结束后（line 141 之后），添加：

```python
# === Profile Loading ===

@dataclass
class ProfileInfo:
    id: str
    display_name: str
    agents: dict[str, str]  # agent_name -> model_alias


def load_profiles(path: Path) -> dict[str, ProfileInfo]:
    """Load provider profiles from YAML. Returns {profile_id: ProfileInfo}."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    profiles: dict[str, ProfileInfo] = {}
    for profile_id, cfg in (raw.get("profiles") or {}).items():
        if not isinstance(cfg, dict):
            continue
        profiles[profile_id] = ProfileInfo(
            id=profile_id,
            display_name=cfg.get("display_name", profile_id),
            agents=cfg.get("agents", {}),
        )
    return profiles
```

- [x] **Step 3: 写测试验证加载逻辑**

在 `server/tests/test_config.py`（如果不存在则创建）中添加：

```python
import tempfile
from pathlib import Path
import yaml

from clef_server.config import load_profiles, ProfileInfo


class TestLoadProfiles:
    def test_load_profiles_from_yaml(self, tmp_path):
        yaml_content = {
            "profiles": {
                "test-profile": {
                    "display_name": "Test",
                    "agents": {"clef-composer": "deepseek-chat"},
                },
            }
        }
        path = tmp_path / "profiles.yaml"
        path.write_text(yaml.dump(yaml_content), encoding="utf-8")
        profiles = load_profiles(path)
        assert "test-profile" in profiles
        assert profiles["test-profile"].display_name == "Test"
        assert profiles["test-profile"].agents == {"clef-composer": "deepseek-chat"}

    def test_load_profiles_missing_file(self, tmp_path):
        profiles = load_profiles(tmp_path / "nonexistent.yaml")
        assert profiles == {}

    def test_load_profiles_partial_agents(self, tmp_path):
        """Profile that only lists some agents should not affect unlisted ones."""
        yaml_content = {
            "profiles": {
                "sparse": {
                    "display_name": "Sparse",
                    "agents": {"clef-reviewer": "deepseek-chat"},
                },
            }
        }
        path = tmp_path / "profiles.yaml"
        path.write_text(yaml.dump(yaml_content), encoding="utf-8")
        profiles = load_profiles(path)
        assert profiles["sparse"].agents == {"clef-reviewer": "deepseek-chat"}
```

- [x] **Step 4: 运行测试**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/test_config.py -v`
Expected: All tests PASS

- [x] **Step 5: Commit**

```bash
git add server/config/profiles.yaml server/src/clef_server/config.py server/tests/test_config.py
git commit -m "feat(server): add profiles.yaml and load_profiles() config function"
```

---

### Task 2: 后端 GET /api/profiles 端点

**Files:**
- Modify: `server/src/clef_server/routes.py`

- [x] **Step 1: 在 routes.py 的 import 区域后添加 profiles 路由**

在 `server/src/clef_server/routes.py` 中，在 `compose` 路由之前（line ~170 之前），添加：

```python
@router.get("/profiles")
async def list_profiles():
    """Return available provider profiles."""
    from clef_server.config import load_profiles
    server_root = _get_server_root()
    profiles = load_profiles(server_root / "config" / "profiles.yaml")
    items = [
        {"id": p.id, "display_name": p.display_name}
        for p in profiles.values()
    ]
    return {"profiles": items}
```

- [x] **Step 2: 运行已有测试确认无回归**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [x] **Step 3: Commit**

```bash
git add server/src/clef_server/routes.py
git commit -m "feat(server): add GET /api/profiles endpoint"
```

---

### Task 3: 后端 compose 接收 profile + orchestrator 覆盖

**Files:**
- Modify: `server/src/clef_server/routes.py:32-34` (ComposeRequest model)
- Modify: `server/src/clef_server/routes.py:143-160` (_run_workflow)
- Modify: `server/src/clef_server/orchestrator.py:156-179` (ComposeOrchestrator.__init__)

- [x] **Step 1: 给 ComposeRequest 添加 profile 字段**

在 `server/src/clef_server/routes.py` line 32-34，将 `ComposeRequest` 改为：

```python
class ComposeRequest(BaseModel):
    prompt: str = Field(..., description="Music composition description", min_length=1)
    plan: dict | None = Field(None, description="Optional pre-defined plan.json")
    profile: str | None = Field(None, description="Provider profile name (from /api/profiles)")
```

- [x] **Step 2: 修改 _run_workflow 传递 profile 给 orchestrator**

在 `server/src/clef_server/routes.py` 中，修改 `_run_workflow` 函数签名和 body：

将 `_run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str)` 改为 `_run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str, profile: str | None = None)`。

在函数体内 `orchestrator = ComposeOrchestrator(...)` 调用处，添加 `profile_overrides=profile_overrides` 参数（详见 Step 3）。

完整修改后的函数开头：

```python
async def _run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str, profile: str | None = None) -> None:
    """Start the compose workflow via orchestrator."""
    session = _session_manager.get(session_id)
    if not session:
        logger.error(f"Session {session_id} not found")
        return

    try:
        from clef_server.config import load_provider_config, load_settings, load_profiles
        from clef_server.providers import create_providers
        from clef_server.orchestrator import ComposeOrchestrator

        server_root = Path(__file__).resolve().parent.parent.parent
        provider_config = load_provider_config(server_root / "config" / "providers.yaml")
        providers = create_providers(provider_config)
        settings = load_settings(server_root)

        # Load profile overrides (agent_name -> model_alias)
        profile_overrides: dict[str, str] = {}
        if profile:
            profiles = load_profiles(server_root / "config" / "profiles.yaml")
            if profile in profiles:
                profile_overrides = profiles[profile].agents
                logger.info("Applying profile '%s': %s", profile, profile_overrides)
            else:
                logger.warning("Profile '%s' not found, using defaults", profile)

        orchestrator = ComposeOrchestrator(
            session_id=session_id,
            providers=providers,
            workdir=workdir,
            settings=settings,
            profile_overrides=profile_overrides,
        )
        await orchestrator.start(prompt)
```

- [x] **Step 3: 修改 ComposeOrchestrator.__init__ 接收 profile_overrides**

在 `server/src/clef_server/orchestrator.py` line 156-162，修改 `__init__` 签名和 body：

```python
    def __init__(
        self,
        session_id: str,
        providers: dict[str, Any],
        workdir: str,
        settings: dict[str, Any] | None = None,
        profile_overrides: dict[str, str] | None = None,
    ) -> None:
        self.session_id = session_id
        self.providers = providers
        self.workdir = workdir
        # Resolve project root (where .claude/agents/ lives)
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        # Settings-driven workflow params (shadow class constants)
        self._settings = settings or {}
        self.max_iteration_rounds = self._settings.get("max_iterations", self.MAX_ITERATION_ROUNDS)
        self.max_melody_gate_retries = self.MAX_MELODY_GATE_RETRIES
        self.review_threshold = self._settings.get("review_threshold", 7)
        self.skip_review = self._settings.get("skip_review", False)
        self._validation_failures: list[dict] = []
        self._file_cache = _FileCache()
        self._iteration_history: list[dict] = []

        # Load agent configs from agents.yaml (falls back to hardcoded defaults)
        self._agent_defs = self._load_agent_defs()

        # Apply profile overrides (only model_alias, not temperature/max_turns/etc.)
        if profile_overrides:
            for agent_name, model_alias in profile_overrides.items():
                if agent_name in self._agent_defs:
                    self._agent_defs[agent_name]["model_alias"] = model_alias
                    logger.info("Profile override: %s → %s", agent_name, model_alias)
```

- [x] **Step 4: 修改 compose 调用处传递 profile 参数**

在 `routes.py` 的 `create_compose` 函数（line 183），将 `task = asyncio.create_task(_run_workflow(session_id, req.prompt, req.plan, workdir))` 改为 `task = asyncio.create_task(_run_workflow(session_id, req.prompt, req.plan, workdir, req.profile))`

- [x] **Step 5: 运行测试确认无回归**

Run: `cd e:/GitHub/clef-dev/server && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [x] **Step 6: Commit**

```bash
git add server/src/clef_server/routes.py server/src/clef_server/orchestrator.py
git commit -m "feat(server): accept profile param in compose, apply model_alias overrides in orchestrator"
```

---

### Task 4: 前端 types + API + store 更新

**Files:**
- Modify: `server/web/src/api/types.ts:82-85` (ComposeRequest)
- Modify: `server/web/src/stores/sessionStore.ts:55-68` (submitPrompt)

- [x] **Step 1: 给 ComposeRequest 加 profile 字段**

在 `server/web/src/api/types.ts` line 82-85，将 `ComposeRequest` 改为：

```typescript
export interface ComposeRequest {
  prompt: string
  plan?: Record<string, unknown>
  profile?: string
}
```

- [x] **Step 2: 在 types.ts 添加 ProfileList 类型**

在 `types.ts` 的 `ComposeResponse` 之后（line ~91 之后），添加：

```typescript
export interface ProfileItem {
  id: string
  display_name: string
}

export interface ProfileListResponse {
  profiles: ProfileItem[]
}
```

- [x] **Step 3: 给 sessionStore 添加 profile state 和 fetchProfiles**

在 `server/web/src/stores/sessionStore.ts` 中：

1. 在 store 的 state 初始值中添加 `selectedProfile: string`，从 localStorage 读取默认值：

```typescript
selectedProfile: localStorage.getItem('clef-last-profile') || '',
```

2. 添加 `fetchProfiles` 函数（在 `submitPrompt` 之前）：

```typescript
fetchProfiles: async () => {
    try {
      const res = await apiClient.get<ProfileListResponse>('/profiles')
      set({ profiles: res.profiles })
    } catch {
      // Silently ignore — profile selector will just not appear
    }
},
```

3. 修改 `submitPrompt` 传递 profile：

```typescript
submitPrompt: async (prompt: string) => {
    set((s) => ({
      messages: [
        ...s.messages,
        { id: createMessageId(), type: 'user', content: prompt, timestamp: Date.now() },
      ],
      confirmationData: null,
      currentPhase: 'parse',
      sampleRound: 0,
      iterationCount: 0,
    }))

    try {
      const body: Record<string, unknown> = { prompt }
      if (get().selectedProfile) {
        body.profile = get().selectedProfile
      }
      const res = await apiClient.post<ComposeResponse>('/compose', body)
      set({
        currentSession: {
          session_id: res.session_id,
          status: 'created',
          user_prompt: prompt,
          output_files: [],
        },
      })
```

- [x] **Step 4: 在组件初始化时调用 fetchProfiles**

在 `Workspace.tsx` 中添加初始化调用。在已有的 `useEffect` 块之后，添加：

```typescript
const fetchProfiles = useSessionStore((s) => s.fetchProfiles)
useEffect(() => { fetchProfiles() }, [fetchProfiles])
```

- [x] **Step 5: 运行前端类型检查**

Run: `cd e:/GitHub/clef-dev/server/web && npx tsc --noEmit`
Expected: No errors

- [x] **Step 6: Commit**

```bash
git add server/web/src/api/types.ts server/web/src/stores/sessionStore.ts server/web/src/pages/Workspace.tsx
git commit -m "feat(web): add profile types, API call, and localStorage persistence"
```

---

### Task 5: 前端 Profile 下拉框组件

**Files:**
- Modify: `server/web/src/pages/Workspace.tsx:87-95` (compose form 区域)

- [x] **Step 1: 在 compose form 中添加 profile 下拉框**

在 `server/web/src/pages/Workspace.tsx` 中：

1. 从 store 获取 profiles 和 selectedProfile：

```typescript
const profiles = useSessionStore((s) => s.profiles)
const selectedProfile = useSessionStore((s) => s.selectedProfile)
const setSelectedProfile = useSessionStore((s) => s.selectedProfile)
```

2. 在 `<form onSubmit={handleSubmit}>` 内，`<textarea>` 之前添加 profile 下拉框：

```tsx
{profiles.length > 0 && (
  <div className="mb-2 flex items-center gap-2">
    <label className="text-xs font-medium text-muted whitespace-nowrap">Profile:</label>
    <select
      value={selectedProfile}
      onChange={(e) => setSelectedProfile(e.target.value)}
      className="rounded-lg bg-surface-mid px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand"
      disabled={!!currentSession && !isTerminal}
    >
      {profiles.map((p) => (
        <option key={p.id} value={p.id}>{p.display_name}</option>
      ))}
    </select>
  </div>
)}
```

- [x] **Step 2: 运行类型检查**

Run: `cd e:/GitHub/clef-dev/server/web && npx tsc --noEmit`
Expected: No errors

- [x] **Step 3: Commit**

```bash
git add server/web/src/pages/Workspace.tsx
git commit -m "feat(web): add profile selector dropdown in compose form"
```

---

### Task 6: 集成验证

**Files:** No code changes — manual verification only

- [x] **Step 1: 启动服务器，访问 Web UI**

1. `cd e:/GitHub/clef-dev/server && python -u -m uvicorn clef_server.app:app --host 0.0.0.0 --port 8900`
2. 打开 http://localhost:5173

- [x] **Step 2: 验证 /api/profiles 返回三个 profile**

Run: `curl -s http://localhost:8900/profiles | python -m json.tool`
Expected: 返回 default / cost-saving / mixed 三个 profile

- [x] **Step 3: 验证 compose 请求携带 profile 参数**

在 Web UI 选择 "混合" profile，发送 compose，检查后端日志出现：
```
Applying profile 'mixed': {...}
Profile override: clef-reviewer → deepseek-chat
```

- [ ] **Step 4: 验证 profile 记忆**

刷新页面，确认下拉框默认选中 "混合"（上次选择）。

- [ ] **Step 5: 验证不传 profile 时回退到默认**

在 Web UI 选择第一个 profile "默认"（即 agents.yaml 的值），确认 orchestrator 使用原始 model_alias 无 profile 覆盖。
