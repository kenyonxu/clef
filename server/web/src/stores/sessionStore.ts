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

export const useSessionStore = create<SessionState>((set) => ({
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
      set({
        currentSession: data,
        workflowSteps: data.workflow_steps ?? [],
        outputFiles: data.output_files.map(fileFromPath),
      })
    } catch {
      // Silently ignore poll errors -- will retry on next interval
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
}))
