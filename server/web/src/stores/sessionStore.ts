import { create } from 'zustand'
import { apiClient } from '../api/client'
import type {
  Session,
  WorkflowStep,
  SubStep,
  ConfirmationData,
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
  confirmationData: ConfirmationData | null
  currentPhase: string | null
  sampleRound: number
  iterationCount: number

  submitPrompt: (prompt: string) => Promise<void>
  pollOnce: (sessionId: string) => Promise<void>
  confirmSession: (sessionId: string, action: 'continue' | 'revise' | 'cancel', feedback?: string) => Promise<void>
  cancelSession: (sessionId: string) => Promise<void>
  loadSessions: () => Promise<void>
  updateSubStep: (phase: string, label: string, status: string, agent?: string) => void
  clearSubSteps: () => void
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
  confirmationData: null,
  currentPhase: null,
  sampleRound: 0,
  iterationCount: 0,

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
      const res = await apiClient.post<ComposeResponse>('/compose', { prompt })
      set({
        currentSession: {
          session_id: res.session_id,
          status: 'created',
          user_prompt: prompt,
          output_files: [],
        },
      })
    } catch (err) {
      set((s) => ({
        messages: [
          ...s.messages,
          {
            id: createMessageId(),
            type: 'error',
            content: err instanceof Error ? err.message : 'Compose failed',
            timestamp: Date.now(),
          },
        ],
      }))
    }
  },

  pollOnce: async (sessionId: string) => {
    try {
      const data = await apiClient.get<StatusResponse>(`/status/${sessionId}`)
      const prevConfirmation = get().confirmationData
      set({
        currentSession: data,
        workflowSteps: data.workflow_steps ?? [],
        outputFiles: data.output_files.map(fileFromPath),
        confirmationData: data.confirmation_data ?? null,
        currentPhase: data.current_phase ?? null,
        sampleRound: data.sample_round ?? 0,
        iterationCount: data.iteration_count ?? 0,
      })
      if (data.confirmation_data && !prevConfirmation) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: createMessageId(),
              type: 'confirmation' as const,
              content: data.confirmation_data!.title,
              timestamp: Date.now(),
              confirmationData: data.confirmation_data!,
              isActive: true,
            },
          ],
        }))
      }
      if (!data.confirmation_data && prevConfirmation) {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.type === 'confirmation' && m.isActive
              ? { ...m, isActive: false }
              : m
          ),
        }))
      }
    } catch {
      // Silently ignore poll errors -- will retry on next interval
    }
  },

  confirmSession: async (sessionId: string, action: 'continue' | 'revise' | 'cancel', feedback?: string) => {
    const activeMessages = get().messages.filter((m) => m.type === 'confirmation' && m.isActive)
    try {
      set((s) => ({
        messages: s.messages.map((m) =>
          m.type === 'confirmation' && m.isActive
            ? { ...m, isActive: false }
            : m
        ),
      }))
      await apiClient.post(`/confirm/${sessionId}`, { action, feedback })
      await get().pollOnce(sessionId)
    } catch (err) {
      // Restore isActive so user can retry
      const activeIds = new Set(activeMessages.map((m) => m.id))
      set((s) => ({
        messages: s.messages.map((m) =>
          activeIds.has(m.id) ? { ...m, isActive: true } : m
        ),
        confirmationData: get().confirmationData ?? activeMessages[0]?.confirmationData ?? null,
      }))
      set((s) => ({
        messages: [
          ...s.messages,
          { id: createMessageId(), type: 'error', content: err instanceof Error ? err.message : 'Confirm failed', timestamp: Date.now() },
        ],
      }))
    }
  },

  cancelSession: async (sessionId: string) => {
    try {
      await apiClient.post(`/cancel/${sessionId}`, null)
      set((s) => ({
        currentSession: s.currentSession
          ? { ...s.currentSession, status: 'cancelled' }
          : null,
      }))
    } catch (err) {
      set((s) => ({
        messages: [
          ...s.messages,
          {
            id: createMessageId(),
            type: 'error',
            content: err instanceof Error ? err.message : 'Cancel failed',
            timestamp: Date.now(),
          },
        ],
      }))
    }
  },

  loadSessions: async () => {
    try {
      const data = await apiClient.get<SessionsResponse>('/sessions')
      set({ sessions: data.sessions })
    } catch {
      // Silent fail -- sessions page will show empty state
    }
  },

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
}))
