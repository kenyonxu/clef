# Provider Profile Switching 设计

## 背景

当前 `agents.yaml` 把每个 agent 的 `model_alias` 硬编码为 `anthropic-opus/sonnet/haiku`，所有 agent 走同一个智谱 API 端点。密集的 compose 会话（30-50 次 LLM 调用）容易触发单一端点的速率限制（429 code 1302）。

需要一种机制让用户在 Web UI 上切换不同的 provider 配置（profile），将不同 agent 分散到不同的 API 端点，降低单端点的请求压力。

## 需求

- **全量切换**：一次切换所有 agent 的 model_alias 映射
- **Web UI 触发**：Compose 表单上的下拉框选择 profile
- **Per-session + 记忆**：每次 session 可以选不同 profile，前端记住上次选择
- **不侵入现有配置**：`agents.yaml` 和 `providers.yaml` 保持不变，profile 作为覆盖层

## 数据结构

### `config/profiles.yaml`

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

Profile 只覆盖 `model_alias`。不覆盖 `temperature`、`max_turns`、`tools`、`prompt_md`、`skills`。

如果某个 agent 未在 profile 的 `agents` 中列出，使用 `agents.yaml` 的默认值。

## 后端改动

### 文件

- 新增: `config/profiles.yaml`
- 修改: `server/src/clef_server/config.py` — 加载 profiles
- 修改: `server/src/clef_server/routes.py` — 新增 GET /api/profiles，修改 POST /api/compose
- 修改: `server/src/clef_server/orchestrator.py` — 接收 profile 覆盖并应用

### API

**GET `/api/profiles`**

返回：
```json
{
  "profiles": [
    {"id": "default", "display_name": "默认 (智谱 GLM)"},
    {"id": "cost-saving", "display_name": "低成本 (全 DeepSeek)"},
    {"id": "mixed", "display_name": "混合 (主力智谱+审查DeepSeek)"}
  ],
  "last_used": "default"
}
```

**POST `/api/compose`** — 扩展现有请求体：

```json
{
  "prompt": "...",
  "profile": "mixed"
}
```

`profile` 字段可选。如果为空或未指定，使用 `agents.yaml` 默认值。

### 覆盖逻辑

在 `ComposeOrchestrator.__init__` 中，如果传入了 profile 覆盖：

1. 加载 `agents.yaml` 作为基础配置
2. 用 `profiles[profile].agents` 覆盖对应 agent 的 `model_alias`
3. 后续所有 `_run_agent` 调用自动使用覆盖后的 alias

## 前端改动

### 文件

- 修改: `server/web/src/api/types.ts` — ComposeRequest 加 `profile` 字段
- 修改: `server/web/src/api/client.ts` — compose() 传 profile
- 修改: `server/web/src/components/PlanConfirm.tsx`（或对应 compose 输入组件） — 加 profile 下拉框

### UI

Compose 输入区域上方加一行：profile 下拉框（左对齐，和 prompt 输入框同宽）。

- 选项从 `GET /api/profiles` 动态加载
- 默认选中 `localStorage.getItem('clef-last-profile')` 或第一个 profile
- 选择后存 `localStorage.setItem('clef-last-profile', selected)`

## 不改动

- `agents.yaml` — 保持不变，作为 fallback
- `providers.yaml` — 保持不变
- Profile 不影响 temperature / max_turns / tools / prompt_md / skills

## 实现顺序

1. 后端：创建 `profiles.yaml` + config 加载逻辑
2. 后端：`GET /api/profiles` 端点
3. 后端：`POST /api/compose` 接收 profile 参数 + orchestrator 覆盖逻辑
4. 前端：types + API client 更新
5. 前端：profile 下拉框组件
6. 测试
