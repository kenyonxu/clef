# Clef Web Frontend Design Spec

## Overview

A React SPA serving as the creative workspace for the Clef music composition server. Users configure LLM providers, compose music through a multi-turn workflow, and manage output files. The interface blends Spotify's immersive dark aesthetic with a music-production feel: the UI recedes so compositions glow.

Target audience: public users (developers, musicians, creators).

## Architecture

```
browser → React SPA (Vite) → REST API → FastAPI (Python)
```

- **Dev mode:** Vite dev server on :5173, CORS proxy to FastAPI :8900
- **Production:** `npm run build` → `dist/` served by FastAPI `StaticFiles` at `/`

### Tech Stack

| Category | Choice |
|----------|--------|
| Framework | React 19 + TypeScript 5.9 |
| Build | Vite 8 |
| Styling | TailwindCSS 4 (`@theme` variables) |
| State | Zustand 5 |
| Design | Spotify design system (dark immersive) |
| Fonts | Inter Variable + GeistMono |
| Testing | Vitest (unit) + Playwright (E2E) |

### Directory Structure

```
server/web/
  src/
    components/       # Reusable UI (StepCard, StatusBadge, ProviderCard, FileList)
    pages/
      Workspace.tsx   # / — compose + workflow steps + output
      Settings.tsx    # /settings — provider/agent config
      Sessions.tsx    # /sessions — history list
    stores/
      sessionStore.ts # workflow state, polling, messages
      settingsStore.ts # provider/agent config CRUD
      uiStore.ts      # navigation, selection
    api/
      client.ts       # fetch wrapper with error handling
      types.ts        # API response types
    hooks/
      usePolling.ts   # status polling with auto-stop
    index.css         # TailwindCSS theme (Spotify palette)
  index.html
  vite.config.ts
  package.json
  tsconfig.json
```

## Design System: Spotify

Dark immersive theme. UI recedes so content (music) glows.

### Color Palette

| Role | Color | Usage |
|------|-------|-------|
| Background base | `#121212` | Page background |
| Surface elevated | `#181818` | Cards, panels |
| Surface mid | `#1f1f1f` | Button backgrounds, interactive surfaces |
| Surface hover | `#282828` | Hover states |
| Primary text | `#ffffff` | Headings |
| Secondary text | `#b3b3b3` | Body text, inactive nav |
| Tertiary text | `#a7a7a7` | Metadata, timestamps |
| Brand accent | `#1ed760` | CTAs, active states, success |
| Error | `#f3727f` | Failed states |
| Warning | `#ffa42b` | Pending states |
| Info | `#539df5` | Running states |
| Border subtle | `rgba(255,255,255,0.1)` | Card borders |
| Border standard | `rgba(255,255,255,0.2)` | Input borders |
| Border muted | `#4d4d4d` | Button borders on dark |
| Border light | `#7c7c7c` | Outlined button borders |

### Typography

| Role | Font | Size | Weight | Notes |
|------|------|------|--------|-------|
| Page title | Inter Variable | 24px | 700 | SpotifyMixUITitle equivalent |
| Section heading | Inter Variable | 18px | 600 | Tight line-height (1.30) |
| Body bold | Inter Variable | 16px | 700 | Emphasized text |
| Body | Inter Variable | 14px | 400 | Standard body, metadata |
| Caption bold | Inter Variable | 14px | 700 | Bold metadata, timestamps |
| Caption | Inter Variable | 14px | 400 | Metadata |
| Button label | Inter Variable | 14px | 700 | Uppercase, letter-spacing 1.4px |
| Small bold | Inter Variable | 12px | 700 | Tags, counts |
| Small | Inter Variable | 12px | 400 | Fine print, helper text |
| Badge | Inter Variable | 10.5px | 600 | Status tags, capitalize |
| Code/technical | GeistMono | 13px | 400 | API keys, file paths |

### Component Patterns

**Buttons (3 variants):**

| Variant | Background | Text | Border | Radius | Use |
|---------|-----------|------|--------|--------|-----|
| Primary | `#1ed760` | `#000000` | none | 500px | Compose, Save, CTAs |
| Secondary | `#1f1f1f` | `#ffffff` | none | 500px | Navigation, secondary actions |
| Danger | transparent | `#f3727f` | `1px solid #f3727f` | 9999px | Delete, Cancel |

All buttons: 14px weight 700, uppercase, letter-spacing 1.4px.

**Cards:**
- Background: `#181818`, border: `rgba(255,255,255,0.1)`, radius: 8px
- Hover: slight background lightening to `#1f1f1f`

**Inputs:**
- Background: `#282828`, radius: 8px (standard) or 500px (search)
- Inset border: `rgb(124,124,124) 0px 0px 0px 1px inset`

**Status badges:**
- Dot: 50% radius circle (6px)
- Label: pill shape with semantic background at 15% opacity

### Shadows

| Level | Shadow | Use |
|-------|--------|-----|
| Card | `rgba(0,0,0,0.3) 0px 8px 8px` | Elevated cards, dropdowns |
| Dialog | `rgba(0,0,0,0.5) 0px 8px 24px` | Modals, menus, overlays |

### Motion & Transitions

| Interaction | Duration | Easing | Notes |
|-------------|----------|--------|-------|
| Card hover | 150ms | ease | Background color transition |
| Button hover | 150ms | ease | Opacity or background shift |
| Status badge change | 300ms | ease-in-out | Color + text transition |
| Progress bar fill | 300ms | ease-out | Width animation |
| Page enter | 200ms | ease-out | Fade + slight translateY |
| Modal open | 200ms | ease-out | Fade in backdrop, scale content |
| Toast appear | 200ms | ease-out | Slide in from top |

## Pages

### Page 1: `/` — Workspace (Compose)

Two-column layout. Left: conversation input + history. Right: workflow steps + output.

**Left column (60%):**
- Prompt textarea at top with "Compose" button (Primary variant, `#1ed760`)
- Chat history below showing workflow events (status changes, agent completions, errors)
- After completion, user can type follow-up to iterate (clef-iterate workflow)
- Iterate: sends prompt to existing session, continues from last output

**Right column (40%):**
- Workflow step progress view:
  - Step 0: Requirement parsing (pending/running/done)
  - Step 1: Plan generation (pending/running/done)
  - Step 2: Full creation — expandable to show 3 agents (Composer, Harmonist, Rhythmist) with individual progress bars
  - Step 3: Expression injection (pending/running/done)
- User confirmation points: "Confirm Direction" / "Request Changes" buttons appear when awaiting_confirm
- Output files section: list of .abc / .mid files with download buttons
- Bottom bar: elapsed time, session ID

**State flow:** `created` → `running` → (poll every 3s) → `done` / `failed`

**Session recovery:** On page load with `?session=clef-xxx`:
1. Fetch `/status/{id}` immediately
2. If `running`: resume polling (3s interval)
3. If `done`/`failed`: show final state, no polling
4. If `created`: start polling (session may have started while page was closed)
5. If 404: clear URL param, show "Session not found" toast

**URL state:** `/?session=clef-xxx` for refresh recovery

### Page 2: `/settings` — Configuration

**Provider section:**
- Card per provider: name, model_id, base_url, masked API key (`sk-••••ggt`)
- Actions: Edit, Test (Secondary button, sends test prompt, shows latency), Delete (Danger button)
- "+ Add Provider" button (Secondary variant)
- API Key shown masked by default, toggle eye icon to reveal

**Agent section:**
- Row per agent: name, dropdown to select provider, temperature slider
- Agents: Composer, Harmonist, Rhythmist

**Output section:**
- Directory path input with "Browse" button (folder picker)
- Defaults to system temp dir

**Save button** (Primary variant) at bottom. Saves to server YAML files. New compose sessions use updated config; running sessions unaffected.

### Page 3: `/sessions` — History

- Table/list of all sessions
- Columns: prompt (truncated), status badge, relative time, actions
- Actions per status:
  - `done`: View, Download All, Delete
  - `failed`: View, Retry (re-submit same prompt), Delete
  - `running`: View, Cancel
- "View" navigates to `/?session=clef-xxx`
- Empty state when no sessions exist

## State Management

### `useSessionStore`

```typescript
interface WorkflowStep {
  id: number
  name: string
  status: 'pending' | 'running' | 'done' | 'failed'
  agents?: Array<{
    name: string
    status: 'pending' | 'running' | 'done' | 'failed'
    progress?: number  // 0-100
  }>
  error?: string
}

interface ChatMessage {
  id: string
  type: 'user' | 'system' | 'error'
  content: string
  timestamp: number
}

interface OutputFile {
  filename: string
  path: string
  size?: number
}

interface SessionStore {
  currentSession: Session | null
  sessions: Session[]
  workflowSteps: WorkflowStep[]
  messages: ChatMessage[]
  outputFiles: OutputFile[]

  submitPrompt(prompt: string): Promise<void>
  iterate(prompt: string): Promise<void>
  pollStatus(sessionId: string): void  // starts interval
  cancelSession(sessionId: string): Promise<void>
  loadSessions(): Promise<void>
  downloadFile(path: string): Promise<Blob>
}
```

Polling: `setInterval(3000)` starts on `submitPrompt`, stops on `done`/`failed`/`cancelled`. On page load with `?session=` param, `pollStatus` is called to recover running sessions.

### `useSettingsStore`

```typescript
interface Provider {
  id: string
  name: string
  type: 'anthropic' | 'openai_compat'
  model_id: string
  base_url?: string
  api_key: string
}

interface AgentMapping {
  agent: string       // 'composer' | 'harmonist' | 'rhythmist'
  provider_id: string
  temperature: number
}

interface TestResult {
  ok: boolean
  latency_ms: number
  error?: string
}

interface SettingsStore {
  providers: Provider[]
  agentMappings: AgentMapping[]
  outputDir: string
  isDirty: boolean

  loadSettings(): Promise<void>
  addProvider(p: Provider): void
  updateProvider(id: string, data: Partial<Provider>): void
  deleteProvider(id: string): void
  testProvider(id: string): Promise<TestResult>
  updateAgentMapping(agent: string, providerAlias: string): void
  setOutputDir(path: string): void
  saveSettings(): Promise<void>
}
```

### `useUIStore`

```typescript
interface UIStore {
  currentPage: 'workspace' | 'settings' | 'sessions'
  selectedSessionId: string | null
  toast: { message: string; type: 'info' | 'error' | 'success' } | null
  navigate(page: string, sessionId?: string): void
  showToast(message: string, type: 'info' | 'error' | 'success'): void
}
```

## Server API

### Existing Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/compose` | POST | Create session, start workflow |
| `/status/{id}` | GET | Session status + progress |
| `/status/{id}/stream` | GET | SSE real-time progress |
| `/result/{id}` | GET | Output files (only when done) |
| `/confirm/{id}` | POST | Confirm sample direction |
| `/cancel/{id}` | POST | Cancel a session |
| `/sessions` | GET | List all sessions |

### New Settings Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings` | GET | Read providers.yaml + agents.yaml (API keys masked) |
| `/api/settings` | PUT | Write full config to YAML files |
| `/api/settings/providers` | POST | Add a provider entry |
| `/api/settings/providers/{id}` | PUT | Update a provider |
| `/api/settings/providers/{id}` | DELETE | Remove a provider |
| `/api/settings/providers/{id}/test` | POST | Send test prompt, return `{ok, latency_ms, error?}` |

### Status Response (Extended)

The `/status/{id}` response must include workflow step progress for the Workspace page:

```json
{
  "session_id": "clef-abc12345",
  "status": "running",
  "user_prompt": "Epic battle theme",
  "workflow_steps": [
    { "id": 0, "name": "parse", "status": "done" },
    { "id": 1, "name": "plan", "status": "done" },
    { "id": 2, "name": "create", "status": "running",
      "agents": [
        { "name": "composer", "status": "running" },
        { "name": "harmonist", "status": "pending" },
        { "name": "rhythmist", "status": "pending" }
      ]
    },
    { "id": 3, "name": "inject", "status": "pending" }
  ],
  "output_files": [],
  "error": null
}
```

### Server-Side Requirements

1. **CORS middleware** — `app.py` must add `CORSMiddleware` for dev mode (Vite :5173 → FastAPI :8900)
2. **StaticFiles** — `app.py` must mount `dist/` at `/` for production builds
3. **Config save functions** — `config.py` needs `save_provider_config(path, config)` and `save_agent_configs(path, configs)` to write YAML
4. **Workflow step tracking** — `sessions.py` needs to store and update per-step progress during workflow execution

### Security

- API keys: HTTPS in production, masked in GET responses (show last 4 chars only)
- Config file `providers.yaml` already in `.gitignore`
- No auth on API (same-origin in production, CORS in dev)

## Error Handling

| Scenario | UI Response |
|----------|------------|
| Server unreachable | Global toast: "Cannot connect to Clef Server" |
| Compose fails immediately | Chat message with error details, session → failed |
| Workflow step fails | Red step card, chat message with error |
| Provider test fails | Red badge on provider card, error text |
| API key invalid | Provider card shows "Connection failed" |
| Output dir not writable | Warning in settings, compose fails with clear message |
| Session not found (URL recovery) | Toast "Session not found", clear URL param |

## Implementation Phases

### Phase 1 — MVP (Workspace)

1. Vite + React + TailwindCSS scaffold with Spotify theme
2. Server: add `CORSMiddleware` to `app.py`
3. Server: add `StaticFiles` mount for production builds
4. API client + types (including `WorkflowStep`, `ChatMessage`, `OutputFile`)
5. Workspace page: prompt input, status polling, step view, file download
6. Server: extend `StatusResponse` with `workflow_steps`
7. Server: add step-level tracking to workflow execution
8. Session recovery on page load with `?session=` param
9. Tests: API client unit tests, Workspace page smoke tests

### Phase 2 — Config, History & Iterate

1. Server: add `save_provider_config()` / `save_agent_configs()` to `config.py`
2. Server: add settings CRUD endpoints (`/api/settings/*`)
3. Settings page: provider CRUD, agent mapping, output dir
4. Sessions page: history list with actions
5. Iterate workflow: multi-turn conversation (follow-up prompts on existing session)
6. `agents.yaml.example` template file
7. Tests: Settings CRUD integration tests

### Phase 3 — Polish

1. SSE real-time step updates (replace polling)
2. Keyboard shortcuts
3. Responsive layout (mobile / tablet)
4. Playwright E2E tests: Compose → poll → download flow; Settings CRUD → save → verify compose uses new config
5. Performance optimization: lazy route loading, memoized components

## Testing

### Unit Tests (Vitest)

| File | Coverage |
|------|----------|
| `api/client.test.ts` | Fetch wrapper, error handling, retry logic |
| `stores/sessionStore.test.ts` | submitPrompt, pollStatus, cancelSession |
| `stores/settingsStore.test.ts` | CRUD operations, dirty tracking |
| `hooks/usePolling.test.ts` | Interval start/stop, auto-stop conditions |

### Integration Tests (Vitest + msw)

| File | Coverage |
|------|----------|
| `api/settings.test.ts` | Settings CRUD against mocked server |
| `pages/Workspace.test.tsx` | Submit → poll → status update → file download |
| `pages/Settings.test.tsx` | Add/edit/delete provider, save |

### E2E Tests (Playwright — Phase 3)

| Test | Flow |
|------|------|
| `compose-flow.spec.ts` | Open workspace → type prompt → click compose → wait for done → download file |
| `settings-flow.spec.ts` | Open settings → add provider → save → open workspace → compose (uses new config) |
| `session-recovery.spec.ts` | Start compose → refresh page → verify polling resumes |
