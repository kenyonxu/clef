# Clef Web Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React SPA serving as the creative workspace for Clef music composition — compose prompt, track workflow steps, download output files.

**Architecture:** React 19 SPA (Vite 8) with Spotify dark theme, Zustand 5 stores, polling-based status updates. Dev mode proxies API calls to FastAPI :8900; production serves `dist/` via FastAPI StaticFiles.

**Tech Stack:** React 19, TypeScript 5.9, Vite 8, TailwindCSS 4, Zustand 5, Vitest, Playwright, FastAPI

**Design Spec:** `docs/superpowers/specs/2026-04-07-clef-web-frontend-design.md`

**Spotify Design Reference:** `docs/design-references/spotify/DESIGN.md`

---

## File Map

### New Frontend Files (`server/web/`)

| File | Responsibility |
|------|---------------|
| `package.json` | Dependencies and scripts |
| `vite.config.ts` | Vite config with TailwindCSS plugin + API proxy |
| `tsconfig.json` | TypeScript config (strict, JSX react-jsx) |
| `index.html` | SPA entry point with font preloads |
| `src/main.tsx` | React root mount |
| `src/index.css` | TailwindCSS 4 `@theme` with Spotify palette |
| `src/App.tsx` | Router setup (react-router-dom v7) |
| `src/api/types.ts` | All TypeScript interfaces for API responses |
| `src/api/client.ts` | Fetch wrapper with error handling |
| `src/stores/uiStore.ts` | Navigation, toast notifications |
| `src/stores/sessionStore.ts` | Compose workflow state, polling, session recovery |
| `src/hooks/usePolling.ts` | Polling interval with auto-stop |
| `src/components/Layout.tsx` | App shell: sidebar nav + main content area |
| `src/components/Toast.tsx` | Global notification toast |
| `src/components/StepCard.tsx` | Workflow step progress card |
| `src/components/StatusBadge.tsx` | Status indicator dot/label |
| `src/components/ChatMessage.tsx` | Single chat event message |
| `src/components/FileList.tsx` | Output file list with download |
| `src/pages/Workspace.tsx` | Two-column compose page |
| `src/pages/Settings.tsx` | Placeholder (Phase 2) |
| `src/pages/Sessions.tsx` | Placeholder (Phase 2) |
| `src/test/setup.ts` | Vitest setup (jsdom, cleanup) |

### Modified Server Files

| File | Change |
|------|--------|
| `server/src/clef_server/app.py` | Add CORSMiddleware, StaticFiles mount for dist/ |
| `server/src/clef_server/sessions.py` | Add workflow step tracking to ComposeSession |
| `server/src/clef_server/routes.py` | Extend StatusResponse with workflow_steps |

### New Server Test Files

| File | Coverage |
|------|----------|
| `server/tests/test_sessions_steps.py` | ComposeSession step tracking |
| `server/tests/test_routes_steps.py` | StatusResponse with workflow_steps |

---

## Task 1: Vite Scaffold + Spotify Theme

**Files:**
- Create: `server/web/package.json`
- Create: `server/web/vite.config.ts`
- Create: `server/web/tsconfig.json`
- Create: `server/web/index.html`
- Create: `server/web/src/main.tsx`
- Create: `server/web/src/App.tsx`
- Create: `server/web/src/index.css`
- Create: `server/web/src/pages/Workspace.tsx` (placeholder)
- Create: `server/web/src/pages/Settings.tsx` (placeholder)
- Create: `server/web/src/pages/Sessions.tsx` (placeholder)
- Create: `server/web/src/test/setup.ts`
- Create: `server/web/vitest.config.ts`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "clef-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "jsdom": "^25.0.0",
    "msw": "^2.0.0",
    "tailwindcss": "^4.0.0",
    "typescript": "~5.9.0",
    "vite": "^6.0.0",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/compose': 'http://localhost:8900',
      '/status': 'http://localhost:8900',
      '/result': 'http://localhost:8900',
      '/confirm': 'http://localhost:8900',
      '/cancel': 'http://localhost:8900',
      '/sessions': 'http://localhost:8900',
      '/api': 'http://localhost:8900',
      '/docs': 'http://localhost:8900',
      '/redoc': 'http://localhost:8900',
      '/openapi.json': 'http://localhost:8900',
    },
  },
})
```

- [ ] **Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create vitest.config.ts**

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    css: false,
  },
})
```

- [ ] **Step 5: Create index.html**

```html
<!DOCTYPE html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Clef — AI Music Composition</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet" />
  </head>
  <body class="bg-base text-white">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create src/index.css — Spotify Theme**

```css
@import "tailwindcss";

@theme {
  /* Surfaces */
  --color-base: #121212;
  --color-surface: #181818;
  --color-surface-mid: #1f1f1f;
  --color-surface-hover: #282828;

  /* Text */
  --color-white: #ffffff;
  --color-silver: #b3b3b3;
  --color-muted: #a7a7a7;

  /* Brand & Semantic */
  --color-brand: #1ed760;
  --color-error: #f3727f;
  --color-warning: #ffa42b;
  --color-info: #539df5;

  /* Borders */
  --color-border-subtle: rgba(255, 255, 255, 0.1);
  --color-border-standard: rgba(255, 255, 255, 0.2);
  --color-border-muted: #4d4d4d;
  --color-border-light: #7c7c7c;

  /* Shadows */
  --shadow-card: 0px 8px 8px rgba(0, 0, 0, 0.3);
  --shadow-dialog: 0px 8px 24px rgba(0, 0, 0, 0.5);

  /* Fonts */
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Geist Mono', monospace;
}

body {
  background-color: var(--color-base);
  color: var(--color-white);
  font-family: var(--font-sans);
  margin: 0;
  -webkit-font-smoothing: antialiased;
}

/* Scrollbar styling for dark theme */
::-webkit-scrollbar {
  width: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
}
```

- [ ] **Step 7: Create src/main.tsx**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 8: Create src/App.tsx**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Workspace } from './pages/Workspace'
import { Settings } from './pages/Settings'
import { Sessions } from './pages/Sessions'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Workspace />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/sessions" element={<Sessions />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 9: Create placeholder pages**

`src/pages/Workspace.tsx`:
```tsx
export function Workspace() {
  return <div className="p-8 text-silver">Workspace — coming soon</div>
}
```

`src/pages/Settings.tsx`:
```tsx
export function Settings() {
  return <div className="p-8 text-silver">Settings — Phase 2</div>
}
```

`src/pages/Sessions.tsx`:
```tsx
export function Sessions() {
  return <div className="p-8 text-silver">Sessions — Phase 2</div>
}
```

- [ ] **Step 10: Create src/test/setup.ts**

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 11: Install dependencies and verify dev server**

Run: `cd server/web && npm install`
Run: `cd server/web && npm run dev`
Expected: Vite dev server starts on http://localhost:5173, shows placeholder page

- [ ] **Step 12: Commit**

```bash
git add server/web/
git commit -m "feat(web): scaffold Vite + React + TailwindCSS with Spotify theme"
```

---

## Task 2: TypeScript API Types

**Files:**
- Create: `server/web/src/api/types.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// === Workflow Step ===

export interface AgentProgress {
  name: string
  status: WorkflowStepStatus
}

export interface WorkflowStep {
  id: number
  name: string
  label: string
  status: WorkflowStepStatus
  agents?: AgentProgress[]
  error?: string
}

export type WorkflowStepStatus = 'pending' | 'running' | 'done' | 'failed'

// === Session ===

export interface Session {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workdir?: string
  output_files: string[]
  error?: string
  workflow_steps?: WorkflowStep[]
  created_at?: number
  updated_at?: number
}

export type SessionStatus = 'created' | 'running' | 'done' | 'failed' | 'cancelled' | 'awaiting_confirm'

// === API Request/Response ===

export interface ComposeRequest {
  prompt: string
  plan?: Record<string, unknown>
}

export interface ComposeResponse {
  session_id: string
  status: string
}

export interface StatusResponse {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workflow_steps?: WorkflowStep[]
  output_files: string[]
  error?: string
}

export interface CancelResponse {
  session_id: string
  status: string
}

export interface SessionsResponse {
  sessions: Session[]
}

export interface ResultResponse {
  session_id: string
  output_files: string[]
  workdir: string
}

// === Chat Messages (UI-only) ===

export interface ChatMessage {
  id: string
  type: 'user' | 'system' | 'error'
  content: string
  timestamp: number
}

// === Output Files (UI-only) ===

export interface OutputFile {
  filename: string
  path: string
  size?: number
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd server/web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add server/web/src/api/types.ts
git commit -m "feat(web): add TypeScript API types"
```

---

## Task 3: API Client (TDD)

**Files:**
- Create: `server/web/src/api/client.ts`
- Create: `server/web/src/test/client.test.ts`

- [ ] **Step 1: Write failing test for API client**

```typescript
// server/web/src/test/client.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiClient } from '../api/client'

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

beforeEach(() => {
  mockFetch.mockReset()
})

describe('apiClient', () => {
  describe('get', () => {
    it('calls fetch with correct URL and returns parsed JSON', async () => {
      const data = { session_id: 'clef-abc123', status: 'done' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(data),
      })

      const result = await apiClient.get('/status/clef-abc123')
      expect(mockFetch).toHaveBeenCalledWith('/status/clef-abc123')
      expect(result).toEqual(data)
    })

    it('throws ApiError on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: 'Session not found' }),
      })

      await expect(apiClient.get('/status/missing')).rejects.toThrow('Session not found')
    })

    it('throws "Cannot connect" on network error', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

      await expect(apiClient.get('/status/clef-abc123')).rejects.toThrow('Cannot connect to Clef Server')
    })
  })

  describe('post', () => {
    it('calls fetch with POST method and JSON body', async () => {
      const response = { session_id: 'clef-new', status: 'created' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(response),
      })

      const result = await apiClient.post('/compose', { prompt: 'Epic theme' })
      expect(mockFetch).toHaveBeenCalledWith('/compose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Epic theme' }),
      })
      expect(result).toEqual(response)
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/web && npx vitest run src/test/client.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement API client**

```typescript
// server/web/src/api/client.ts
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const apiClient = {
  async get<T>(path: string): Promise<T> {
    try {
      const res = await fetch(path)
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(body.detail ?? res.statusText, res.status)
      }
      return res.json() as Promise<T>
    } catch (err) {
      if (err instanceof ApiError) throw err
      throw new Error('Cannot connect to Clef Server')
    }
  },

  async post<T>(path: string, body: unknown): Promise<T> {
    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(errBody.detail ?? res.statusText, res.status)
      }
      return res.json() as Promise<T>
    } catch (err) {
      if (err instanceof ApiError) throw err
      throw new Error('Cannot connect to Clef Server')
    }
  },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/web && npx vitest run src/test/client.test.ts`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/web/src/api/client.ts server/web/src/test/client.test.ts
git commit -m "feat(web): add API client with error handling (TDD)"
```

---

## Task 4: Server CORS + StaticFiles

**Files:**
- Modify: `server/src/clef_server/app.py`
- Create: `server/tests/test_app.py`

- [ ] **Step 1: Write failing test for CORS and StaticFiles**

```python
# server/tests/test_app.py
"""Tests for app.py — CORS middleware and StaticFiles mount."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from clef_server.app import create_app


class TestCORS:
    def test_cors_middleware_allows_localhost_5173(self):
        app = create_app()
        # Check that CORS middleware is added
        middleware_types = [type(m).__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_types

    def test_cors_headers_in_response(self):
        app = create_app()
        client = pytest.importorskip("starlette.testclient", None)
        if client is None:
            from starlette.testclient import TestClient
            client = TestClient(app)
        else:
            client = client.TestClient(app)

        response = client.options(
            "/compose",
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestStaticFiles:
    def test_no_static_files_when_dist_missing(self):
        with patch("clef_server.app.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            app = create_app()
            # Should not mount StaticFiles
            routes = [r.path for r in app.routes]
            assert "/" not in routes or any(
                isinstance(r, type(app.routes[0])) for r in app.routes
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_app.py -v`
Expected: FAIL — no CORS middleware

- [ ] **Step 3: Modify app.py — add CORS + StaticFiles**

Replace `server/src/clef_server/app.py` with:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from clef_server.routes import create_router

_HOME_HTML = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Clef Server</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:3rem auto;padding:0 1.5rem;color:#222}
h1{font-size:1.5rem;margin-bottom:.25rem}
p.sub{color:#888;margin-bottom:2rem}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #eee}
th{color:#555;font-weight:500;font-size:.85rem}
code{background:#f4f4f4;padding:.15rem .4rem;border-radius:4px;font-size:.85rem}
a{color:#0066cc;text-decoration:none}
a:hover{text-decoration:underline}
.footer{margin-top:2rem;color:#aaa;font-size:.8rem}
</style>
</head>
<body>
<h1>Clef Server</h1>
<p class="sub">Multi-agent music composition microservice &middot; v0.1.0</p>
<table>
<tr><th>Endpoint</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/compose</code></td><td>POST</td><td>Create a new composition session</td></tr>
<tr><td><code>/status/{id}</code></td><td>GET</td><td>Get session status</td></tr>
<tr><td><code>/status/{id}/stream</code></td><td>GET</td><td>SSE real-time progress</td></tr>
<tr><td><code>/result/{id}</code></td><td>GET</td><td>Get composition output files</td></tr>
<tr><td><code>/confirm/{id}</code></td><td>POST</td><td>Confirm sample direction (Phase 2)</td></tr>
<tr><td><code>/cancel/{id}</code></td><td>POST</td><td>Cancel a session</td></tr>
<tr><td><code>/sessions</code></td><td>GET</td><td>List all sessions</td></tr>
</table>
<p style="margin-top:1.5rem"><a href="/docs">Swagger UI</a> &middot; <a href="/redoc">ReDoc</a></p>
<p class="footer">Powered by Microsoft Agent Framework</p>
</body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clef Server",
        description="Multi-agent music composition microservice",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes first (they take priority over StaticFiles mount)
    app.include_router(create_router())

    # Production: serve SPA from dist/ if it exists
    dist_dir = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def root():
            return _HOME_HTML

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Verify existing tests still pass**

Run: `cd server && PYTHONPATH=src python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add server/src/clef_server/app.py server/tests/test_app.py
git commit -m "feat(server): add CORS middleware and StaticFiles mount for SPA"
```

---

## Task 5: Server Workflow Step Tracking

**Files:**
- Modify: `server/src/clef_server/sessions.py`
- Modify: `server/src/clef_server/routes.py`
- Create: `server/tests/test_sessions_steps.py`
- Create: `server/tests/test_routes_steps.py`

- [ ] **Step 1: Write failing test for session step tracking**

```python
# server/tests/test_sessions_steps.py
"""Tests for ComposeSession workflow step tracking."""

from clef_server.sessions import ComposeSession, WORKFLOW_STEPS


class TestWorkflowSteps:
    def test_default_steps_are_all_pending(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
            user_prompt="test prompt",
        )
        steps = session.get_workflow_steps()
        assert len(steps) == 4
        assert all(s["status"] == "pending" for s in steps)

    def test_advance_step_marks_done_and_next_running(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.update_step(0, "running")

        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "running"
        assert steps[1]["status"] == "pending"

        session.advance_step(0)
        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "done"
        assert steps[1]["status"] == "running"

    def test_failed_step_sets_error(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.update_step(1, "failed", error="Plan generation failed")

        steps = session.get_workflow_steps()
        assert steps[1]["status"] == "failed"
        assert steps[1]["error"] == "Plan generation failed"

    def test_to_dict_includes_workflow_steps(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
            user_prompt="test",
        )
        session.set_running()
        session.update_step(0, "done")
        session.update_step(1, "running")

        data = session.to_dict()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"

    def test_workflow_steps_constant(self):
        assert len(WORKFLOW_STEPS) == 4
        assert WORKFLOW_STEPS[0]["name"] == "parse"
        assert WORKFLOW_STEPS[3]["name"] == "inject"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_sessions_steps.py -v`
Expected: FAIL — no `get_workflow_steps` method

- [ ] **Step 3: Modify sessions.py — add step tracking**

Add to `server/src/clef_server/sessions.py`:

```python
# Add after VALID_TRANSITIONS definition:

WORKFLOW_STEPS = [
    {"id": 0, "name": "parse", "label": "Requirement Parsing"},
    {"id": 1, "name": "plan", "label": "Plan Generation"},
    {"id": 2, "name": "create", "label": "Full Creation"},
    {"id": 3, "name": "inject", "label": "Expression Injection"},
]
```

Add to `ComposeSession` class — new field in `__init__`:
```python
    step_status: dict[int, str] = field(default_factory=lambda: {0: "pending", 1: "pending", 2: "pending", 3: "pending"})
    current_step: int = 0
```

Add methods to `ComposeSession`:
```python
    def update_step(self, step_id: int, status: str, *, error: str | None = None) -> None:
        """Update a workflow step's status."""
        self.step_status[step_id] = status
        self.updated_at = time.time()
        if error:
            self.step_errors = getattr(self, 'step_errors', {})
            self.step_errors[step_id] = error

    def advance_step(self, step_id: int) -> None:
        """Mark step as done and advance to next."""
        self.step_status[step_id] = "done"
        if step_id + 1 < len(WORKFLOW_STEPS):
            self.current_step = step_id + 1
            self.step_status[step_id + 1] = "running"
        self.updated_at = time.time()

    def get_workflow_steps(self) -> list[dict]:
        """Return workflow steps with current status."""
        steps = []
        for s in WORKFLOW_STEPS:
            status = self.step_status.get(s["id"], "pending")
            step = {**s, "status": status}
            if hasattr(self, 'step_errors') and s["id"] in self.step_errors:
                step["error"] = self.step_errors[s["id"]]
            steps.append(step)
        return steps
```

Update `to_dict` to include workflow_steps:
```python
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "user_prompt": self.user_prompt,
            "workdir": self.workdir,
            "output_files": self.output_files,
            "error": self.error,
            "workflow_steps": self.get_workflow_steps(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
```

- [ ] **Step 4: Run session step tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_sessions_steps.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Write failing test for extended StatusResponse**

```python
# server/tests/test_routes_steps.py
"""Tests for StatusResponse with workflow_steps."""

import pytest
from fastapi.testclient import TestClient
from clef_server.app import create_app
from clef_server.sessions import SessionManager


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def session_mgr():
    return SessionManager()


class TestStatusResponseWithSteps:
    def test_status_includes_workflow_steps(self, client, session_mgr, monkeypatch):
        monkeypatch.setattr("clef_server.routes._session_manager", session_mgr)
        session = session_mgr.create("test prompt", "/tmp/test")
        session.set_running()
        session.update_step(0, "done")
        session.update_step(1, "running")

        response = client.get(f"/status/{session.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"
        assert len(data["workflow_steps"]) == 4
```

- [ ] **Step 6: Modify routes.py — add workflow_steps to StatusResponse**

Update the `StatusResponse` model in `server/src/clef_server/routes.py`:
```python
class StatusResponse(BaseModel):
    session_id: str
    status: str
    user_prompt: str = ""
    workflow_steps: list[dict] = []
    output_files: list[str] = []
    error: str | None = None
```

Update the `get_status` endpoint:
```python
@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusResponse(
        session_id=session.session_id,
        status=session.status,
        user_prompt=session.user_prompt,
        workflow_steps=session.get_workflow_steps(),
        output_files=session.output_files,
        error=session.error,
    )
```

- [ ] **Step 7: Run all server tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/ -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 8: Commit**

```bash
git add server/src/clef_server/sessions.py server/src/clef_server/routes.py \
       server/tests/test_sessions_steps.py server/tests/test_routes_steps.py
git commit -m "feat(server): add workflow step tracking to sessions and StatusResponse"
```

---

## Task 6: UI Store + Layout + Navigation

**Files:**
- Create: `server/web/src/stores/uiStore.ts`
- Create: `server/web/src/components/Toast.tsx`
- Create: `server/web/src/components/Layout.tsx`

- [ ] **Step 1: Create UI Store**

```typescript
// server/web/src/stores/uiStore.ts
import { create } from 'zustand'

export interface ToastData {
  message: string
  type: 'info' | 'error' | 'success'
}

interface UIState {
  currentPage: 'workspace' | 'settings' | 'sessions'
  toast: ToastData | null
  showToast: (message: string, type: ToastData['type']) => void
  clearToast: () => void
}

export const useUIStore = create<UIState>((set) => ({
  currentPage: 'workspace',
  toast: null,
  showToast: (message, type) => {
    set({ toast: { message, type } })
    setTimeout(() => set({ toast: null }), 4000)
  },
  clearToast: () => set({ toast: null }),
}))
```

- [ ] **Step 2: Create Toast component**

```tsx
// server/web/src/components/Toast.tsx
import { useUIStore } from '../stores/uiStore'

export function Toast() {
  const toast = useUIStore((s) => s.toast)
  const clearToast = useUIStore((s) => s.clearToast)

  if (!toast) return null

  const bg =
    toast.type === 'error'
      ? 'bg-error/20 border-error'
      : toast.type === 'success'
        ? 'bg-brand/20 border-brand'
        : 'bg-info/20 border-info'

  return (
    <div className="fixed top-4 right-4 z-50" role="alert">
      <div
        className={`${bg} border rounded-lg px-4 py-3 text-sm text-white shadow-dialog max-w-sm`}
        onClick={clearToast}
      >
        {toast.message}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create Layout component**

```tsx
// server/web/src/components/Layout.tsx
import { NavLink, Outlet } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Workspace' },
  { to: '/settings', label: 'Settings' },
  { to: '/sessions', label: 'Sessions' },
] as const

export function Layout() {
  return (
    <div className="flex h-screen bg-base">
      {/* Sidebar */}
      <nav className="w-56 flex-shrink-0 bg-surface border-r border-border-subtle flex flex-col">
        <div className="p-6 pb-4">
          <h1 className="text-xl font-bold text-brand">Clef</h1>
          <p className="text-xs text-muted mt-1">AI Music Composition</p>
        </div>
        <ul className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `block px-3 py-2 rounded-lg text-sm font-bold transition-colors duration-150 ${
                    isActive
                      ? 'bg-surface-mid text-white'
                      : 'text-silver hover:text-white hover:bg-surface-hover'
                  }`
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
```

- [ ] **Step 4: Update App.tsx to use Layout**

```tsx
// server/web/src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Toast } from './components/Toast'
import { Workspace } from './pages/Workspace'
import { Settings } from './pages/Settings'
import { Sessions } from './pages/Sessions'

export function App() {
  return (
    <BrowserRouter>
      <Toast />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Workspace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/sessions" element={<Sessions />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 5: Verify dev server renders nav**

Run: `cd server/web && npm run dev`
Expected: Sidebar with "Workspace", "Settings", "Sessions" links. Clicking navigates between pages.

- [ ] **Step 6: Commit**

```bash
git add server/web/src/stores/uiStore.ts server/web/src/components/Toast.tsx \
       server/web/src/components/Layout.tsx server/web/src/App.tsx
git commit -m "feat(web): add Layout, Toast, and UI store with navigation"
```

---

## Task 7: usePolling Hook (TDD)

**Files:**
- Create: `server/web/src/hooks/usePolling.ts`
- Create: `server/web/src/test/usePolling.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
// server/web/src/test/usePolling.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls callback at interval', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()

    renderHook(() => usePolling(callback, 1000))

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(2)
  })

  it('stops polling when stop condition returns true', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()
    let shouldStop = false

    renderHook(() =>
      usePolling(callback, 1000, () => shouldStop),
    )

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    shouldStop = true
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    // Should not have been called again after stop
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('cleans up interval on unmount', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()

    const { unmount } = renderHook(() => usePolling(callback, 1000))

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    unmount()

    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/web && npx vitest run src/test/usePolling.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement usePolling**

```typescript
// server/web/src/hooks/usePolling.ts
import { useEffect, useRef } from 'react'

export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  shouldStop?: () => boolean,
): void {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    const id = setInterval(() => {
      if (shouldStop?.()) {
        clearInterval(id)
        return
      }
      callbackRef.current()
    }, intervalMs)

    return () => clearInterval(id)
  }, [intervalMs, shouldStop])
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/web && npx vitest run src/test/usePolling.test.ts`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/web/src/hooks/usePolling.ts server/web/src/test/usePolling.test.ts
git commit -m "feat(web): add usePolling hook with auto-stop (TDD)"
```

---

## Task 8: Session Store (TDD)

**Files:**
- Create: `server/web/src/stores/sessionStore.ts`
- Create: `server/web/src/test/sessionStore.test.ts`

- [ ] **Step 1: Write failing test for session store**

```typescript
// server/web/src/test/sessionStore.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSessionStore } from '../stores/sessionStore'

vi.mock('../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

// Import mocked module
import { apiClient } from '../api/client'

const mockedPost = vi.mocked(apiClient.post)
const mockedGet = vi.mocked(apiClient.get)

beforeEach(() => {
  vi.clearAllMocks()
  useSessionStore.setState({
    currentSession: null,
    sessions: [],
    workflowSteps: [],
    messages: [],
    outputFiles: [],
  })
})

describe('useSessionStore', () => {
  describe('submitPrompt', () => {
    it('calls POST /compose and sets current session', async () => {
      mockedPost.mockResolvedValueOnce({
        session_id: 'clef-new123',
        status: 'created',
      })

      await useSessionStore.getState().submitPrompt('Epic battle theme')

      expect(mockedPost).toHaveBeenCalledWith('/compose', {
        prompt: 'Epic battle theme',
      })
      expect(useSessionStore.getState().currentSession?.session_id).toBe('clef-new123')
    })

    it('adds user message to chat', async () => {
      mockedPost.mockResolvedValueOnce({
        session_id: 'clef-new123',
        status: 'created',
      })

      await useSessionStore.getState().submitPrompt('Test prompt')

      const messages = useSessionStore.getState().messages
      expect(messages).toHaveLength(1)
      expect(messages[0].type).toBe('user')
      expect(messages[0].content).toBe('Test prompt')
    })

    it('adds error message on failure', async () => {
      mockedPost.mockRejectedValueOnce(new Error('Server error'))

      await useSessionStore.getState().submitPrompt('Test')

      const messages = useSessionStore.getState().messages
      expect(messages.some((m) => m.type === 'error')).toBe(true)
    })
  })

  describe('pollStatus', () => {
    it('updates session and steps on poll', async () => {
      mockedGet.mockResolvedValue({
        session_id: 'clef-abc',
        status: 'running',
        user_prompt: 'test',
        workflow_steps: [
          { id: 0, name: 'parse', label: 'Parse', status: 'done' },
          { id: 1, name: 'plan', label: 'Plan', status: 'running' },
          { id: 2, name: 'create', label: 'Create', status: 'pending' },
          { id: 3, name: 'inject', label: 'Inject', status: 'pending' },
        ],
        output_files: [],
      })

      useSessionStore.setState({ currentSession: { session_id: 'clef-abc', status: 'created', user_prompt: '', output_files: [] } })
      await useSessionStore.getState().pollOnce('clef-abc')

      const steps = useSessionStore.getState().workflowSteps
      expect(steps[0].status).toBe('done')
      expect(steps[1].status).toBe('running')
    })
  })

  describe('loadSessions', () => {
    it('fetches and sets sessions list', async () => {
      mockedGet.mockResolvedValueOnce({
        sessions: [
          { session_id: 'clef-a', status: 'done', user_prompt: 'A', output_files: [] },
          { session_id: 'clef-b', status: 'failed', user_prompt: 'B', output_files: [], error: 'oops' },
        ],
      })

      await useSessionStore.getState().loadSessions()

      expect(useSessionStore.getState().sessions).toHaveLength(2)
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/web && npx vitest run src/test/sessionStore.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement session store**

```typescript
// server/web/src/stores/sessionStore.ts
import { create } from 'zustand'
import { apiClient } from '../api/client'
import type {
  Session,
  WorkflowStep,
  ChatMessage,
  OutputFile,
  ComposeResponse,
  StatusResponse,
  SessionsResponse,
} from '../api/types'

interface SessionState {
  currentSession: Session | null
  sessions: Session[]
  workflowSteps: WorkflowStep[]
  messages: ChatMessage[]
  outputFiles: OutputFile[]

  submitPrompt: (prompt: string) => Promise<void>
  pollOnce: (sessionId: string) => Promise<void>
  cancelSession: (sessionId: string) => Promise<void>
  loadSessions: () => Promise<void>
}

function createMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

function fileFromPath(path: string): OutputFile {
  const filename = path.split('/').pop() ?? path
  return { filename, path }
}

export const useSessionStore = create<SessionState>((set, get) => ({
  currentSession: null,
  sessions: [],
  workflowSteps: [],
  messages: [],
  outputFiles: [],

  submitPrompt: async (prompt: string) => {
    set((s) => ({
      messages: [
        ...s.messages,
        { id: createMessageId(), type: 'user', content: prompt, timestamp: Date.now() },
      ],
    }))

    try {
      const res = await apiClient.post<ComposeResponse>('/compose', { prompt })
      set({ currentSession: { session_id: res.session_id, status: 'created', user_prompt: prompt, output_files: [] } })
    } catch (err) {
      set((s) => ({
        messages: [
          ...s.messages,
          { id: createMessageId(), type: 'error', content: err instanceof Error ? err.message : 'Compose failed', timestamp: Date.now() },
        ],
      }))
    }
  },

  pollOnce: async (sessionId: string) => {
    try {
      const data = await apiClient.get<StatusResponse>(`/status/${sessionId}`)
      set({
        currentSession: data,
        workflowSteps: data.workflow_steps ?? [],
        outputFiles: data.output_files.map(fileFromPath),
      })

      // Auto-stop conditions handled by usePolling shouldStop callback
    } catch {
      // Silently ignore poll errors — will retry on next interval
    }
  },

  cancelSession: async (sessionId: string) => {
    try {
      await apiClient.post(`/cancel/${sessionId}`)
      set((s) => ({
        currentSession: s.currentSession ? { ...s.currentSession, status: 'cancelled' } : null,
      }))
    } catch (err) {
      set((s) => ({
        messages: [
          ...s.messages,
          { id: createMessageId(), type: 'error', content: err instanceof Error ? err.message : 'Cancel failed', timestamp: Date.now() },
        ],
      }))
    }
  },

  loadSessions: async () => {
    try {
      const data = await apiClient.get<SessionsResponse>('/sessions')
      set({ sessions: data.sessions })
    } catch {
      // Silent fail — sessions page will show empty state
    }
  },
}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/web && npx vitest run src/test/sessionStore.test.ts`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/web/src/stores/sessionStore.ts server/web/src/test/sessionStore.test.ts
git commit -m "feat(web): add session store with compose/poll/cancel (TDD)"
```

---

## Task 9: Workspace Components

**Files:**
- Create: `server/web/src/components/StatusBadge.tsx`
- Create: `server/web/src/components/StepCard.tsx`
- Create: `server/web/src/components/ChatMessage.tsx`
- Create: `server/web/src/components/FileList.tsx`

- [ ] **Step 1: Create StatusBadge**

```tsx
// server/web/src/components/StatusBadge.tsx
import type { WorkflowStepStatus, SessionStatus } from '../api/types'

type Status = WorkflowStepStatus | SessionStatus

const STATUS_COLORS: Record<Status, string> = {
  pending: 'bg-muted/20 text-muted',
  running: 'bg-info/20 text-info',
  done: 'bg-brand/20 text-brand',
  failed: 'bg-error/20 text-error',
  created: 'bg-muted/20 text-muted',
  cancelled: 'bg-muted/20 text-muted',
  awaiting_confirm: 'bg-warning/20 text-warning',
}

const DOT_COLORS: Record<Status, string> = {
  pending: 'bg-muted',
  running: 'bg-info animate-pulse',
  done: 'bg-brand',
  failed: 'bg-error',
  created: 'bg-muted',
  cancelled: 'bg-muted',
  awaiting_confirm: 'bg-warning',
}

interface StatusBadgeProps {
  status: Status
  label?: string
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const displayLabel = label ?? status
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${STATUS_COLORS[status]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${DOT_COLORS[status]}`} />
      {displayLabel}
    </span>
  )
}
```

- [ ] **Step 2: Create StepCard**

```tsx
// server/web/src/components/StepCard.tsx
import type { WorkflowStep } from '../api/types'
import { StatusBadge } from './StatusBadge'

interface StepCardProps {
  step: WorkflowStep
  isExpanded?: boolean
}

export function StepCard({ step, isExpanded = false }: StepCardProps) {
  return (
    <div className={`rounded-lg border border-border-subtle bg-surface p-3 transition-colors duration-150 ${
      step.status === 'running' ? 'border-info/30' : ''
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted">Step {step.id}</span>
          <span className="text-sm font-bold text-white">{step.label}</span>
        </div>
        <StatusBadge status={step.status} />
      </div>

      {step.error && (
        <p className="mt-2 text-xs text-error">{step.error}</p>
      )}

      {isExpanded && step.agents && (
        <div className="mt-2 ml-6 space-y-1.5 border-l border-border-subtle pl-3">
          {step.agents.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between">
              <span className="text-xs text-silver">{agent.name}</span>
              <StatusBadge status={agent.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create ChatMessage**

```tsx
// server/web/src/components/ChatMessage.tsx
import type { ChatMessage as ChatMessageType } from '../api/types'

interface ChatMessageProps {
  message: ChatMessageType
}

const MESSAGE_STYLES: Record<ChatMessageType['type'], string> = {
  user: 'bg-surface-mid text-white ml-auto',
  system: 'bg-surface text-silver',
  error: 'bg-error/10 text-error',
}

export function ChatMessage({ message }: ChatMessageProps) {
  const time = new Date(message.timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${MESSAGE_STYLES[message.type]}`}>
      <p className="whitespace-pre-wrap">{message.content}</p>
      <span className="mt-1 block text-right text-[10px] text-muted">{time}</span>
    </div>
  )
}
```

- [ ] **Step 4: Create FileList**

```tsx
// server/web/src/components/FileList.tsx
import type { OutputFile } from '../api/types'

interface FileListProps {
  files: OutputFile[]
}

export function FileList({ files }: FileListProps) {
  if (files.length === 0) return null

  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted">Output Files</h3>
      {files.map((file) => (
        <a
          key={file.path}
          href={`/result/${file.path.split('/').slice(-2).join('/')}`}
          className="flex items-center gap-2 rounded-lg bg-surface-mid px-3 py-2 text-sm text-silver hover:text-white transition-colors duration-150"
          download={file.filename}
        >
          <span className="text-brand">↓</span>
          <span className="font-mono text-xs">{file.filename}</span>
        </a>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add server/web/src/components/StatusBadge.tsx server/web/src/components/StepCard.tsx \
       server/web/src/components/ChatMessage.tsx server/web/src/components/FileList.tsx
git commit -m "feat(web): add StatusBadge, StepCard, ChatMessage, FileList components"
```

---

## Task 10: Workspace Page

**Files:**
- Modify: `server/web/src/pages/Workspace.tsx`

- [ ] **Step 1: Implement Workspace page**

```tsx
// server/web/src/pages/Workspace.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { usePolling } from '../hooks/usePolling'
import { StepCard } from '../components/StepCard'
import { ChatMessage } from '../components/ChatMessage'
import { FileList } from '../components/FileList'
import { StatusBadge } from '../components/StatusBadge'
import type { SessionStatus } from '../api/types'

const TERMINAL_STATUSES: SessionStatus[] = ['done', 'failed', 'cancelled']

export function Workspace() {
  const [prompt, setPrompt] = useState('')
  const [searchParams] = useSearchParams()
  const chatEndRef = useRef<HTMLDivElement>(null)

  const currentSession = useSessionStore((s) => s.currentSession)
  const workflowSteps = useSessionStore((s) => s.workflowSteps)
  const messages = useSessionStore((s) => s.messages)
  const outputFiles = useSessionStore((s) => s.outputFiles)
  const submitPrompt = useSessionStore((s) => s.submitPrompt)
  const pollOnce = useSessionStore((s) => s.pollOnce)
  const cancelSession = useSessionStore((s) => s.cancelSession)
  const showToast = useUIStore((s) => s.showToast)

  // Session recovery from URL
  const sessionIdFromUrl = searchParams.get('session')
  useEffect(() => {
    if (sessionIdFromUrl && !currentSession) {
      pollOnce(sessionIdFromUrl)
    }
  }, [sessionIdFromUrl, currentSession, pollOnce])

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Polling
  const isTerminal = currentSession
    ? TERMINAL_STATUSES.includes(currentSession.status as SessionStatus)
    : true

  const stablePollOnce = useCallback(() => {
    if (currentSession?.session_id) {
      pollOnce(currentSession.session_id)
    }
  }, [currentSession?.session_id, pollOnce])

  usePolling(stablePollOnce, 3000, () => isTerminal)

  // Submit handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    const text = prompt.trim()
    setPrompt('')
    await submitPrompt(text)
  }

  // Cancel handler
  const handleCancel = async () => {
    if (!currentSession?.session_id) return
    await cancelSession(currentSession.session_id)
    showToast('Session cancelled', 'info')
  }

  return (
    <div className="flex h-full">
      {/* Left column — Chat */}
      <div className="flex w-[60%] flex-col border-r border-border-subtle">
        {/* Chat messages */}
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {messages.length === 0 && !currentSession && (
            <div className="flex h-full items-center justify-center text-muted">
              <p>Describe the music you want to compose.</p>
            </div>
          )}
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={chatEndRef} />
        </div>

        {/* Prompt input */}
        <form onSubmit={handleSubmit} className="border-t border-border-subtle p-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe your composition..."
            rows={3}
            className="w-full resize-none rounded-lg bg-surface-mid px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
            disabled={!!currentSession && !isTerminal}
          />
          <div className="mt-2 flex items-center justify-between">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error transition-opacity hover:opacity-80"
              style={{ visibility: currentSession && !isTerminal ? 'visible' : 'hidden' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!prompt.trim() || (!!currentSession && !isTerminal)}
              className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Compose
            </button>
          </div>
        </form>
      </div>

      {/* Right column — Steps + Output */}
      <div className="flex w-[40%] flex-col overflow-auto p-4 space-y-4">
        {/* Session status */}
        {currentSession && (
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">Workflow</h2>
            <StatusBadge status={currentSession.status as SessionStatus} />
          </div>
        )}

        {/* Workflow steps */}
        <div className="space-y-2">
          {workflowSteps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
              isExpanded={step.name === 'create'}
            />
          ))}
        </div>

        {/* Output files */}
        {outputFiles.length > 0 && <FileList files={outputFiles} />}

        {/* Session info */}
        {currentSession && (
          <div className="mt-auto border-t border-border-subtle pt-3">
            <p className="text-[10px] text-muted font-mono">
              Session: {currentSession.session_id}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify the page renders in dev**

Run: `cd server/web && npm run dev`
Expected: Two-column layout. Left side has textarea + Compose button. Right side shows "Workflow" header. Typing and clicking Compose should work (will fail to connect to server if not running).

- [ ] **Step 3: Commit**

```bash
git add server/web/src/pages/Workspace.tsx
git commit -m "feat(web): implement Workspace page with compose flow and step view"
```

---

## Task 11: Frontend Build Verification

**Files:** None new

- [ ] **Step 1: Run TypeScript type check**

Run: `cd server/web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 2: Run all frontend tests**

Run: `cd server/web && npm test`
Expected: All tests PASS (client, usePolling, sessionStore)

- [ ] **Step 3: Run production build**

Run: `cd server/web && npm run build`
Expected: `dist/` directory created with index.html and assets

- [ ] **Step 4: Run all server tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit (if any fixes needed)**

---

## Task 12: End-to-End Smoke Test

**Files:** None new

- [ ] **Step 1: Start the server**

Run: `cd server && PYTHONPATH=src python -m uvicorn clef_server.app:app --port 8900`
Expected: Server starts, no errors

- [ ] **Step 2: Start the frontend dev server**

Run: `cd server/web && npm run dev` (in separate terminal)
Expected: Vite dev server on http://localhost:5173

- [ ] **Step 3: Manual test — compose flow**

1. Open http://localhost:5173
2. Verify: sidebar nav, two-column layout, textarea visible
3. Type "A short happy melody in C major" and click Compose
4. Verify: user message appears in chat, workflow steps appear on right
5. Wait for session to reach done/failed status
6. If done: verify output files appear with download links

- [ ] **Step 4: Manual test — session recovery**

1. After a compose completes, note the session ID
2. Refresh the page (the URL should have `?session=clef-xxx` or navigate to it)
3. Verify: session state is restored, output files still visible

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(web): complete Phase 1 MVP — workspace with compose, polling, step tracking"
```

---

## Self-Review Checklist

- [x] Spec coverage: All Phase 1 items from design spec have tasks
  - Vite scaffold (Task 1)
  - API client + types (Task 2, 3)
  - Server CORS + StaticFiles (Task 4)
  - Server workflow step tracking (Task 5)
  - UI store + Layout (Task 6)
  - Polling hook (Task 7)
  - Session store (Task 8)
  - Workspace components (Task 9)
  - Workspace page (Task 10)
  - Session recovery via URL (Task 10)
  - File download (Task 9, 10)
  - Tests (Tasks 3, 5, 7, 8, 11)
- [x] No placeholders — all steps have actual code or commands
- [x] Type consistency — TypeScript types in Task 2 match usage in Tasks 3, 8, 9, 10
- [x] Server changes match existing codebase patterns (dataclass, Pydantic, pytest)
- [x] Spotify theme follows design spec (colors, shadows, typography, button variants)
- [x] Not covered (intentional — Phase 2): Settings page, Sessions page, Iterate workflow, SSE
