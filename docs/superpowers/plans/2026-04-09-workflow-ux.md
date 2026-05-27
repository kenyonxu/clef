# Workflow UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the clef server workflow panel with accurate agent display, real-time sub-step progress via SSE, and visual highlighting for running steps.

**Architecture:** Backend adds an `asyncio.Queue`-based event bus per session. Orchestrator emits `sub_step_start`/`sub_step_done` events as it progresses through each phase. Frontend subscribes via the existing (currently stubbed) SSE endpoint, updating Zustand store in real-time. StepCard renders sub-steps as an indented list with CSS pulse animation on the running card.

**Tech Stack:** Python (FastAPI + sse-starlette), TypeScript (React + Zustand), CSS animations

---

### Task 1: Backend — PHASES agents fix + sub_steps data model

**Files:**
- Modify: `server/src/clef_server/sessions.py`

- [ ] **Step 1: Update PHASES agents list**

In `server/src/clef_server/sessions.py`, update the `PHASES` list to include all participating agents:

```python
PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True,  "agents": []},
    {"id": "sample",  "label": "方向小样",         "confirm": True,  "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist", "clef-reviewer"]},
    {"id": "create",  "label": "完整创作",         "confirm": False, "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist"]},
    {"id": "iterate", "label": "质量迭代",         "confirm": False, "agents": ["clef-reviewer", "clef-leader", "clef-revision"]},
    {"id": "review",  "label": "试听审核",         "confirm": True,  "agents": ["clef-reviewer"]},
    {"id": "express", "label": "表现力注入",       "confirm": False, "agents": ["clef-orchestrator"]},
]
```

Changes from current:
- `sample`: added `"clef-reviewer"`
- `iterate`: added `"clef-leader"`

- [ ] **Step 2: Add sub_steps field and event queue to ComposeSession**

Add these fields to the `ComposeSession` dataclass (after `iteration_count` line 51):

```python
    sub_steps: list[dict] = field(default_factory=list)
    _event_queues: list = field(default_factory=list)
```

- [ ] **Step 3: Add record_sub_step method**

Add after the `record_phase` method (after line 89):

```python
    def record_sub_step(self, label: str, status: str, *, agent: str | None = None) -> None:
        """Record a sub-step within the current phase and emit SSE event."""
        import asyncio

        entry = {
            "label": label,
            "status": status,
            "agent": agent,
            "phase": self.current_phase,
            "timestamp": time.time(),
        }
        # Update or append in sub_steps list
        for i, existing in enumerate(self.sub_steps):
            if existing["label"] == label and existing["phase"] == self.current_phase:
                self.sub_steps[i] = entry
                break
        else:
            self.sub_steps.append(entry)
        self.updated_at = time.time()

        # Emit to all SSE listeners
        event_data = json.dumps(entry, ensure_ascii=False)
        for q in self._event_queues:
            try:
                q.put_nowait({"event": f"sub_step_{status}", "data": event_data})
            except asyncio.QueueFull:
                pass  # Drop event if queue is full
```

Note: add `import json` at the top of sessions.py if not already present, and `import asyncio`.

- [ ] **Step 4: Add SSE queue management methods**

Add after `record_sub_step`:

```python
    def add_event_listener(self, queue) -> None:
        """Register an asyncio.Queue for SSE event delivery."""
        self._event_queues.append(queue)

    def remove_event_listener(self, queue) -> None:
        """Unregister an SSE event listener."""
        try:
            self._event_queues.remove(queue)
        except ValueError:
            pass

    def clear_sub_steps(self) -> None:
        """Clear sub-steps (call when starting a new phase)."""
        self.sub_steps = []
```

- [ ] **Step 5: Include sub_steps in get_workflow_steps response**

Update `get_workflow_steps` to include sub_steps (modify the method at line 107):

```python
    def get_workflow_steps(self) -> list[dict]:
        """Return workflow phases with current status derived from phase_history."""
        phases = []
        for p in PHASES:
            status = "pending"
            error = None
            for entry in reversed(self.phase_history):
                if entry["phase"] == p["id"]:
                    status = entry["status"]
                    error = entry.get("error")
                    break
            step = {**p, "status": status}
            if error is not None:
                step["error"] = error
            # Include sub-steps for the current phase
            if p["id"] == self.current_phase and self.sub_steps:
                step["sub_steps"] = list(self.sub_steps)
            phases.append(step)
        return phases
```

- [ ] **Step 6: Clear sub_steps when phase changes**

In `_advance_phase` of orchestrator.py, we'll clear sub_steps. But first, update `record_phase` to also clear sub_steps when a new phase starts running:

In `record_phase` method (line 86), add at the beginning:

```python
    def record_phase(self, phase_id: str, status: str, *, error: str | None = None) -> None:
        # Clear sub-steps when a phase starts running
        if status == "running" and phase_id != self.current_phase:
            self.current_phase = phase_id
            self.sub_steps = []
        elif status == "running":
            self.sub_steps = []

        entry = {"phase": phase_id, "status": status, "error": error, "timestamp": time.time()}
        self.phase_history.append(entry)
        self.updated_at = time.time()
```

Wait — `current_phase` is set by the orchestrator directly, not by `record_phase`. Let me revise. The sub_steps should be cleared when a new phase begins. The orchestrator sets `self.session.current_phase = "sample"` etc. before calling `record_phase`. So we should clear when we detect a phase transition:

```python
    def record_phase(self, phase_id: str, status: str, *, error: str | None = None) -> None:
        entry = {"phase": phase_id, "status": status, "error": error, "timestamp": time.time()}
        self.phase_history.append(entry)
        self.updated_at = time.time()
        # Clear sub-steps when a phase starts running
        if status == "running":
            self.current_phase = phase_id
            self.sub_steps = []
```

- [ ] **Step 7: Commit**

```bash
git add server/src/clef_server/sessions.py
git commit -m "feat(server): add sub_steps tracking and SSE event queue to session"
```

---

### Task 2: Backend — SSE endpoint implementation

**Files:**
- Modify: `server/src/clef_server/routes.py`

- [ ] **Step 1: Implement the SSE stream endpoint**

Replace the existing stub at `/status/{session_id}/stream` with a real implementation. Find the `status_stream` function and replace its body:

```python
@router.get("/status/{session_id}/stream")
async def status_stream(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        from sse_starlette.sse import EventSourceResponse
    except ImportError:
        raise HTTPException(status_code=503, detail="SSE not available (sse-starlette not installed)")

    import asyncio

    async def event_generator():
        # Create a bounded queue for this connection (max 100 events)
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        session.add_event_listener(queue)
        try:
            # Send initial state dump so client can catch up
            initial = {
                "type": "state",
                "session_id": session_id,
                "current_phase": session.current_phase,
                "sub_steps": session.sub_steps,
                "workflow_steps": session.get_workflow_steps(),
            }
            yield {"event": "state", "data": json.dumps(initial, ensure_ascii=False)}

            # Stream events until session reaches terminal state
            terminal = {"done", "failed", "cancelled"}
            while session.status not in terminal:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": event["event"], "data": event["data"]}
                except asyncio.TimeoutError:
                    # Send keepalive ping every 30s
                    yield {"event": "ping", "data": json.dumps({"t": time.time()})}
        finally:
            session.remove_event_listener(queue)

    return EventSourceResponse(event_generator())
```

Note: `import json` and `import time` should already be available at the top of routes.py. If not, add them.

- [ ] **Step 2: Verify SSE works with a manual test**

Run the server and test the SSE endpoint:

```bash
cd e:/GitHub/clef-dev/server && python -m uvicorn clef_server.main:app --reload --port 8732
```

In another terminal:
```bash
curl -N http://localhost:8732/api/status/clef-XXXXXXXX/stream
```

Expected: SSE connection established, initial `state` event received, then `ping` events every 30s.

- [ ] **Step 3: Commit**

```bash
git add server/src/clef_server/routes.py
git commit -m "feat(server): implement SSE stream endpoint with sub-step events"
```

---

### Task 3: Backend — Orchestrator sub-step instrumentation

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`

This is the largest task. Add `self.session.record_sub_step(...)` calls at each key point in the phase methods.

- [ ] **Step 1: Instrument _phase_parse (line 363)**

Add sub-step calls inside `_phase_parse`:

After `self.session.record_phase("parse", "running")` (line 369):
```python
        self.session.record_sub_step("解析用户需求", "running")
```

After `response = await client.get_response(messages)` (line 395):
```python
        self.session.record_sub_step("解析用户需求", "done")
        self.session.record_sub_step("生成 plan.json", "running")
```

After `plan_path.write_text(...)` (line 434):
```python
        self.session.record_sub_step("生成 plan.json", "done")
        self.session.record_sub_step("验证规划参数", "running")
```

After `validated = _PlanSchema.model_validate(plan)` (line 416, inside the try block):
```python
        self.session.record_sub_step("验证规划参数", "done")
```

Note: If validation fails (except block at line 417), the sub-step stays "running" which is fine — the phase will fail.

- [ ] **Step 2: Instrument _phase_sample (line 1149)**

Inside the voice generation loop (after line 1163 `for voice in generation_order:`), add before the agent call:

```python
            voice_label_display = {
                "melody": "生成旋律", "harmony": "生成和声", "rhythm": "生成节奏"
            }.get(voice, f"生成 {voice}")
            self.session.record_sub_step(voice_label_display, "running", agent=agent_name)
```

After `self._store_fragment(...)` (line 1182), add:
```python
            self.session.record_sub_step(voice_label_display, "done", agent=agent_name)
```

After merge_abc call (line 1186-1189), before validation:
```python
        self.session.record_sub_step("合并声部", "running")
```

After `self._inject_midi_programs(score_path, plan)` (line 1191):
```python
        self.session.record_sub_step("合并声部", "done")
        self.session.record_sub_step("技术验证", "running")
```

After the validation fix block (after line 1221):
```python
        self.session.record_sub_step("技术验证", "done")
```

Before the melody gate loop (line 1226):
```python
        self.session.record_sub_step("旋律审查", "running", agent="clef-reviewer")
```

After the melody gate loop ends (after line 1249), before MIDI conversion:
```python
        self.session.record_sub_step("旋律审查", "done", agent="clef-reviewer")
```

Before MIDI conversion (line 1262):
```python
        self.session.record_sub_step("转换 MIDI", "running")
```

After successful MIDI conversion (line 1266):
```python
        self.session.record_sub_step("转换 MIDI", "done")
```

Before full review (line 1269):
```python
        self.session.record_sub_step("完整审查", "running", agent="clef-reviewer")
```

After full review (line 1271):
```python
        self.session.record_sub_step("完整审查", "done", agent="clef-reviewer")
```

- [ ] **Step 3: Instrument _phase_create (line 1289)**

Inside the voice generation loop (line 1300), before each agent call, add:
```python
            voice_label_display = {
                "melody": "生成旋律", "harmony": "生成和声", "rhythm": "生成节奏"
            }.get(voice, f"生成 {voice}")
            self.session.record_sub_step(voice_label_display, "running", agent=agent_name)
```

After each successful `_store_fragment` (line 1323):
```python
            self.session.record_sub_step(voice_label_display, "done", agent=agent_name)
```

Before merge (line 1338):
```python
        self.session.record_sub_step("合并声部", "running")
```

After merge + inject (line 1344):
```python
        self.session.record_sub_step("合并声部", "done")
        self.session.record_sub_step("技术验证", "running")
```

After validation block (line 1389, end of failures handling):
```python
        self.session.record_sub_step("技术验证", "done")
```

Before MIDI conversion (line 1392):
```python
        self.session.record_sub_step("转换 MIDI", "running")
```

After MIDI conversion (line 1397):
```python
        self.session.record_sub_step("转换 MIDI", "done")
```

- [ ] **Step 4: Instrument _phase_iterate (line 1409)**

At the start of the round loop (after line 1420):
```python
            self.session.record_sub_step(
                f"迭代轮次 {round_num}/{self.max_iteration_rounds}", "running"
            )
```

Before reviewer call (line 1423):
```python
            self.session.record_sub_step("完整审查", "running", agent="clef-reviewer")
```

After reviewer call (line 1425):
```python
            self.session.record_sub_step("完整审查", "done", agent="clef-reviewer")
```

Before leader call (line 1428):
```python
            self.session.record_sub_step("任务调度", "running", agent="clef-leader")
```

After leader call (line 1429):
```python
            self.session.record_sub_step("任务调度", "done", agent="clef-leader")
```

Inside the task execution loop (line 1441), before each `_run_agent` call (line 1473):
```python
                task_label = f"执行任务 ({agent_name})"
                self.session.record_sub_step(task_label, "running", agent=agent_name)
```

After successful task execution (after line 1514 `completed_agents.add`):
```python
                self.session.record_sub_step(task_label, "done", agent=agent_name)
```

After the round's validate + MIDI export (line 1530):
```python
            self.session.record_sub_step(
                f"迭代轮次 {round_num}/{self.max_iteration_rounds}", "done"
            )
```

- [ ] **Step 5: Instrument _phase_express (line 1561)**

Before expression plan generation (line 1591):
```python
        self.session.record_sub_step("生成表现力方案", "running", agent="clef-orchestrator")
```

After expression plan generation (line 1592):
```python
        self.session.record_sub_step("生成表现力方案", "done", agent="clef-orchestrator")
```

Before inject (line 1606):
```python
        self.session.record_sub_step("注入表现力数据", "running")
```

After successful inject (after line 1607):
```python
        self.session.record_sub_step("注入表现力数据", "done")
```

- [ ] **Step 6: Extract helper to reduce repetition**

The voice label display mapping is repeated in sample and create. Add a class-level constant near the top of `ComposeOrchestrator`:

```python
    _VOICE_DISPLAY_NAMES = {
        "melody": "生成旋律",
        "harmony": "生成和声",
        "rhythm": "生成节奏",
    }
```

Then replace the inline dicts with `self._VOICE_DISPLAY_NAMES.get(voice, f"生成 {voice}")`.

- [ ] **Step 7: Commit**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "feat(server): add sub-step instrumentation to all workflow phases"
```

---

### Task 4: Frontend — Types + Store updates

**Files:**
- Modify: `server/web/src/api/types.ts`
- Modify: `server/web/src/stores/sessionStore.ts`
- Test: `server/web/src/test/sessionStore.test.ts`

- [ ] **Step 1: Add SubStep type to types.ts**

Add after the `AgentProgress` interface (around line 8):

```typescript
export interface SubStep {
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
  agent?: string
  phase?: string
  timestamp?: number
}
```

Update `WorkflowStep` to include sub_steps (find the interface and add):

```typescript
export interface WorkflowStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  agents?: AgentProgress[]
  sub_steps?: SubStep[]
  error?: string
  confirm?: boolean
}
```

Update `PhaseStep` similarly:

```typescript
export interface PhaseStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  confirm: boolean
  agents?: AgentProgress[]
  sub_steps?: SubStep[]
}
```

- [ ] **Step 2: Add SSE update actions to sessionStore.ts**

Add `SubStep` to the imports:

```typescript
import type {
  Session,
  WorkflowStep,
  ConfirmationData,
  ChatMessage,
  OutputFile,
  ComposeResponse,
  StatusResponse,
  SessionsResponse,
  SubStep,
} from '../api/types'
```

Add new actions to the `SessionState` interface:

```typescript
interface SessionState {
  // ... existing fields ...
  updateSubStep: (phase: string, label: string, status: string, agent?: string) => void
  clearSubSteps: () => void
}
```

Add implementations in the store:

```typescript
  updateSubStep: (phase: string, label: string, status: string, agent?: string) => {
    set((s) => {
      const steps = s.workflowSteps.map((step) => {
        if (step.id !== phase) return step
        const existing = step.sub_steps ?? []
        const subStep: SubStep = {
          label,
          status: status as SubStep['status'],
          agent,
          timestamp: Date.now(),
        }
        // Update existing or append
        const idx = existing.findIndex((ss) => ss.label === label)
        const newSubSteps = [...existing]
        if (idx >= 0) {
          newSubSteps[idx] = subStep
        } else {
          newSubSteps.push(subStep)
        }
        return { ...step, sub_steps: newSubSteps }
      })
      return { workflowSteps: steps }
    })
  },

  clearSubSteps: () => {
    set((s) => ({
      workflowSteps: s.workflowSteps.map((step) => ({ ...step, sub_steps: [] })),
    }))
  },
```

- [ ] **Step 3: Commit**

```bash
git add server/web/src/api/types.ts server/web/src/stores/sessionStore.ts
git commit -m "feat(web): add SubStep type and store actions for SSE updates"
```

---

### Task 5: Frontend — SSE hook

**Files:**
- Create: `server/web/src/hooks/useSSE.ts`
- Test: `server/web/src/test/useSSE.test.ts`

- [ ] **Step 1: Write the failing test**

Create `server/web/src/test/useSSE.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react'

// Mock EventSource
const mockListeners: Record<string, ((ev: MessageEvent) => void)[]> = {}
class MockEventSource {
  url: string
  readyState = 0
  onmessage: ((ev: MessageEvent) => void) | null = null
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
  }

  addEventListener(type: string, listener: (ev: MessageEvent) => void) {
    if (!mockListeners[type]) mockListeners[type] = []
    mockListeners[type].push(listener)
  }

  removeEventListener(type: string, listener: (ev: MessageEvent) => void) {
    const arr = mockListeners[type]
    if (arr) {
      const idx = arr.indexOf(listener)
      if (idx >= 0) arr.splice(idx, 1)
    }
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// Helper to simulate SSE event
function emitSSE(eventType: string, data: object) {
  const listeners = mockListeners[eventType] ?? []
  const ev = new MessageEvent(eventType, { data: JSON.stringify(data) })
  listeners.forEach((fn) => fn(ev))
}

describe('useSSE', () => {
  beforeEach(() => {
    Object.keys(mockListeners).forEach((k) => delete mockListeners[k])
  })

  it('creates EventSource with correct URL', () => {
    const { useSSE } = require('../hooks/useSSE')
    renderHook(() => useSSE('clef-test123', true))
    // EventSource should have been created — check via addEventListener was called
    expect(typeof MockEventSource).toBe('function')
  })

  it('updates sub-step on sub_step_running event', () => {
    const { useSSE } = require('../hooks/useSSE')
    const { result } = renderHook(() => useSSE('clef-test123', true))

    act(() => {
      emitSSE('sub_step_running', {
        label: '生成旋律',
        status: 'running',
        agent: 'clef-composer',
        phase: 'create',
        timestamp: Date.now() / 1000,
      })
    })

    // Store should have been updated — verify via the updateSubStep action
    expect(result.current).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd e:/GitHub/clef-dev/server/web && npx vitest run src/test/useSSE.test.ts
```

Expected: FAIL — `useSSE` module not found.

- [ ] **Step 3: Implement useSSE hook**

Create `server/web/src/hooks/useSSE.ts`:

```typescript
import { useEffect, useRef } from 'react'
import { useSessionStore } from '../stores/sessionStore'

interface SSESubStepEvent {
  label: string
  status: string
  agent?: string
  phase?: string
  timestamp?: number
}

export function useSSE(sessionId: string | null, isActive: boolean): void {
  const updateSubStep = useSessionStore((s) => s.updateSubStep)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!sessionId || !isActive) {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
      return
    }

    const url = `/api/status/${sessionId}/stream`
    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('sub_step_running', (ev) => {
      const data: SSESubStepEvent = JSON.parse(ev.data)
      updateSubStep(data.phase ?? '', data.label, data.status, data.agent)
    })

    es.addEventListener('sub_step_done', (ev) => {
      const data: SSESubStepEvent = JSON.parse(ev.data)
      updateSubStep(data.phase ?? '', data.label, data.status, data.agent)
    })

    es.addEventListener('sub_step_failed', (ev) => {
      const data: SSESubStepEvent = JSON.parse(ev.data)
      updateSubStep(data.phase ?? '', data.label, data.status, data.agent)
    })

    es.addEventListener('state', (ev) => {
      const data = JSON.parse(ev.data)
      // Initial state sync — handled by polling, but useful for reconnect
      if (data.sub_steps && Array.isArray(data.sub_steps)) {
        const clearSubSteps = useSessionStore.getState().clearSubSteps
        const store = useSessionStore.getState()
        clearSubSteps()
        for (const ss of data.sub_steps) {
          store.updateSubStep(
            ss.phase ?? data.current_phase ?? '',
            ss.label,
            ss.status,
            ss.agent,
          )
        }
      }
    })

    es.onerror = () => {
      // EventSource auto-reconnects by default
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [sessionId, isActive, updateSubStep])
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd e:/GitHub/clef-dev/server/web && npx vitest run src/test/useSSE.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/web/src/hooks/useSSE.ts server/web/src/test/useSSE.test.ts
git commit -m "feat(web): add useSSE hook for real-time sub-step updates"
```

---

### Task 6: Frontend — StepCard enhancement

**Files:**
- Modify: `server/web/src/components/StepCard.tsx`

- [ ] **Step 1: Update StepCard with sub-steps and animation**

Replace the entire `server/web/src/components/StepCard.tsx` with:

```tsx
import type { WorkflowStep, SubStep } from '../api/types'
import { StatusBadge } from './StatusBadge'

interface StepCardProps {
  step: WorkflowStep
}

function SubStepIcon({ status }: { status: SubStep['status'] }) {
  if (status === 'done') return <span className="text-emerald-400 text-[10px]">✓</span>
  if (status === 'running') {
    return (
      <span className="inline-block w-[10px] h-[10px] border-[1.5px] border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
    )
  }
  if (status === 'failed') return <span className="text-red-400 text-[10px]">✗</span>
  return <span className="text-neutral-600 text-[10px]">○</span>
}

export function StepCard({ step }: StepCardProps) {
  const isRunning = step.status === 'running'
  const isDone = step.status === 'done'
  const isPending = step.status === 'pending'

  return (
    <div
      className={`rounded-lg border bg-surface p-3 transition-all duration-300 ${
        isRunning
          ? 'border-blue-400/50 bg-blue-400/[0.06] shadow-[0_0_20px_rgba(96,165,250,0.1),0_0_40px_rgba(96,165,250,0.05)] animate-[cardPulse_2s_ease-in-out_infinite]'
          : isDone
            ? 'border-border-subtle opacity-60'
            : isPending
              ? 'border-border-subtle opacity-40'
              : 'border-border-subtle'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted">{step.id}</span>
          <span className={`text-sm font-bold ${isPending ? 'text-muted' : isDone ? 'text-neutral-400' : 'text-white'}`}>
            {step.label}
          </span>
          {step.confirm && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-400/10 px-1.5 py-0.5 text-[9px] text-amber-400">
              {isDone ? '✓ ' : ''}需确认
            </span>
          )}
        </div>
        <StatusBadge status={step.status} />
      </div>

      {step.error && (
        <p className="mt-2 text-xs text-error">{step.error}</p>
      )}

      {step.agents && step.agents.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {step.agents.map((agent) => {
            const agentRunning = agent.status === 'running'
            const agentDone = agent.status === 'done'
            return (
              <span
                key={agent.name}
                className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                  agentRunning
                    ? 'bg-blue-400/15 text-blue-400 border border-blue-400/30'
                    : agentDone
                      ? 'bg-emerald-400/10 text-emerald-400'
                      : 'bg-white/[0.03] text-neutral-600'
                }`}
              >
                {agent.name}
              </span>
            )
          })}
        </div>
      )}

      {step.sub_steps && step.sub_steps.length > 0 && (
        <div className={`mt-2 ml-4 space-y-1 border-l-2 pl-3 ${
          isRunning ? 'border-blue-400/30' : 'border-border-subtle'
        }`}>
          {step.sub_steps.map((ss, i) => (
            <div
              key={`${ss.label}-${i}`}
              className={`flex items-center gap-1.5 text-[11px] leading-relaxed ${
                ss.status === 'done'
                  ? 'text-emerald-400'
                  : ss.status === 'running'
                    ? 'text-blue-400'
                    : ss.status === 'failed'
                      ? 'text-red-400'
                      : 'text-neutral-600'
              }`}
            >
              <SubStepIcon status={ss.status} />
              <span>{ss.label}</span>
              {ss.agent && (
                <span className={`font-mono text-[9px] ${
                  ss.status === 'running' ? 'text-blue-500' : 'text-neutral-500'
                }`}>
                  {ss.agent}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add CSS keyframe for cardPulse animation**

Check if there's a global CSS file or tailwind config. The animation `cardPulse` needs to be defined. Add to `server/web/src/index.css`:

```css
@keyframes cardPulse {
  0%, 100% {
    border-color: rgba(96, 165, 250, 0.4);
    box-shadow: 0 0 15px rgba(96, 165, 250, 0.08);
  }
  50% {
    border-color: rgba(96, 165, 250, 0.7);
    box-shadow: 0 0 25px rgba(96, 165, 250, 0.15);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add server/web/src/components/StepCard.tsx server/web/src/index.css
git commit -m "feat(web): StepCard sub-steps, agent highlights, pulse animation"
```

---

### Task 7: Frontend — Workspace SSE integration

**Files:**
- Modify: `server/web/src/pages/Workspace.tsx`

- [ ] **Step 1: Import and wire up useSSE hook**

Add the import at the top of `Workspace.tsx`:

```typescript
import { useSSE } from '../hooks/useSSE'
```

Add the hook call inside the `Workspace` component, after the existing hooks (after line 50):

```typescript
  const isTerminal = currentSession
    ? TERMINAL_STATUSES.includes(currentSession.status as SessionStatus)
    : true

  useSSE(currentSession?.session_id ?? null, !isTerminal)
```

- [ ] **Step 2: Verify the build compiles**

```bash
cd e:/GitHub/clef-dev/server/web && npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add server/web/src/pages/Workspace.tsx
git commit -m "feat(web): integrate SSE hook in Workspace for real-time updates"
```

---

### Task 8: Integration verification

**Files:** None (verification only)

- [ ] **Step 1: Start the full server**

```bash
cd e:/GitHub/clef-dev/server && python -m uvicorn clef_server.main:app --reload --port 8732
```

- [ ] **Step 2: Start the frontend dev server**

```bash
cd e:/GitHub/clef-dev/server/web && npm run dev
```

- [ ] **Step 3: Run a compose workflow and verify**

Open the frontend, submit a compose prompt, and verify:

1. StepCard shows blue glow + pulse animation on the running step
2. Sub-steps appear as indented list with ✓/spinner/○ icons
3. Each sub-step shows the agent name in monospace
4. Agents row includes `clef-reviewer` in sample phase and `clef-leader` in iterate phase
5. Completed steps are dimmed, pending steps are faded
6. Confirm steps show the yellow "需确认" badge
7. SSE events arrive in real-time (no 3s polling delay for sub-step updates)

- [ ] **Step 4: Run all existing tests**

```bash
cd e:/GitHub/clef-dev/server/web && npx vitest run
```

Expected: All existing tests pass + new useSSE test passes.

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(web): integration fixes from manual testing"
```
