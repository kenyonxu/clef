# Clef Web Frontend Design Spec

## Overview

A React SPA serving as the control panel for the Clef music composition server. Users configure LLM providers, compose music through a step-based workflow, and manage output files. The target audience is public users.

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
| Surface hover | `#282828` | Hover states |
| Primary text | `#ffffff` | Headings |
| Secondary text | `#b3b3b3` | Body text |
| Tertiary text | `#a7a7a7` | Metadata, timestamps |
| Brand accent | `#1ed760` | CTAs, active states, success |
| Error | `#f3727f` | Failed states |
| Warning | `#ffa42b` | Pending states |
| Info | `#539df5` | Running states |
| Border subtle | `rgba(255,255,255,0.1)` | Card borders |
| Border standard | `rgba(255,255,255,0.2)` | Input borders |

### Typography

| Role | Font | Size | Weight |
|------|------|------|--------|
| Page title | Inter Variable | 24px | 700 |
| Section heading | Inter Variable | 16px | 700 |
| Body | Inter Variable | 14px | 400 |
| Caption | Inter Variable | 12px | 400 |
| Button label | Inter Variable | 14px | 700, uppercase, 1.4px spacing |
| Code/technical | GeistMono | 13px | 400 |

### Component Patterns

- **Buttons:** 500px pill radius, uppercase labels, wide letter-spacing
- **Cards:** `#181818` background, `rgba(255,255,255,0.1)` border, 8px radius
- **Inputs:** `#282828` background, 8px radius, 500px pill for search
- **Status badges:** 50% radius circle for dots, pill for labels
- **Shadows:** Heavy on elevated elements `rgba(0,0,0,0.5) 0px 8px 24px`

## Pages

### Page 1: `/` — Workspace (Compose)

Two-column layout. Left: conversation input + history. Right: workflow steps + output.

**Left column (60%):**
- Prompt textarea at top with "Compose" button
- Chat history below showing workflow events (status changes, agent completions, errors)
- Iterate: after completion, user can type follow-up to refine

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
**URL state:** `/?session=clef-xxx` for refresh recovery

### Page 2: `/settings` — Configuration

**Provider section:**
- Card per provider: name, model_id, base_url, masked API key (`sk-••••ggt`)
- Actions: Edit, Test (sends test prompt, shows latency), Delete
- "+ Add Provider" button
- API Key shown masked by default, toggle to reveal

**Agent section:**
- Row per agent: name, dropdown to select provider, temperature slider
- Agents: Composer, Harmonist, Rhythmist

**Output section:**
- Directory path input with "Browse" button (folder picker)
- Defaults to system temp dir

**Save button** at bottom. Saves to server YAML files. New compose sessions use updated config; running sessions unaffected.

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

Polling: `setInterval(3000)` starts on `submitPrompt`, stops on `done`/`failed`/`cancelled`.

### `useSettingsStore`

```typescript
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
  navigate(page: string, sessionId?: string): void
}
```

## New Server API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings` | GET | Read providers.yaml + agents.yaml (API keys masked) |
| `/api/settings` | PUT | Write full config to YAML files |
| `/api/settings/providers` | POST | Add a provider entry |
| `/api/settings/providers/{id}` | PUT | Update a provider |
| `/api/settings/providers/{id}` | DELETE | Remove a provider |
| `/api/settings/providers/{id}/test` | POST | Send test prompt, return `{ok, latency_ms, error?}` |

### Security

- API keys: HTTPS in production, masked in GET responses (show last 4 chars only)
- Config file `providers.yaml` already in `.gitignore`
- No auth on API (same-origin in production, CORS in dev)

## Error Handling

| Scenario | UI Response |
|----------|------------|
| Server unreachable | Global toast: "Cannot connect to Clef Server" |
| Compose fails immediately | Chat message with error details, session → failed |
| Workflow step fails | Red step card, chat message with stack trace |
| Provider test fails | Red badge on provider card, error text |
| API key invalid | Provider card shows "Connection failed" |
| Output dir not writable | Warning in settings, compose fails with clear message |

## Implementation Phases

### Phase 1 — MVP (Workspace)
1. Vite + React + TailwindCSS scaffold
2. API client + types
3. Workspace page: prompt input, status polling, step view, file download
4. Server: settings CRUD API

### Phase 2 — Config & History
5. Settings page: provider CRUD, agent mapping, output dir
6. Sessions page: history list with actions

### Phase 3 — Polish
7. Iterate workflow (multi-turn conversation)
8. SSE real-time step updates (replace polling)
9. Keyboard shortcuts
10. Playwright E2E tests

## Testing

- **Vitest:** API client, Zustand store actions, utility functions
- **Playwright:** Compose → poll → download flow; Settings CRUD → save → verify compose uses new config
- **Existing pytest:** Server-side settings API tests
