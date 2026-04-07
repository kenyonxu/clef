import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSessionStore } from '../stores/sessionStore'

vi.mock('../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

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
      expect(messages[0]?.type).toBe('user')
      expect(messages[0]?.content).toBe('Test prompt')
    })

    it('adds error message on failure', async () => {
      mockedPost.mockRejectedValueOnce(new Error('Server error'))

      await useSessionStore.getState().submitPrompt('Test')

      const messages = useSessionStore.getState().messages
      expect(messages.some((m) => m.type === 'error')).toBe(true)
    })
  })

  describe('pollOnce', () => {
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

      useSessionStore.setState({
        currentSession: {
          session_id: 'clef-abc',
          status: 'created',
          user_prompt: '',
          output_files: [],
        },
      })
      await useSessionStore.getState().pollOnce('clef-abc')

      const steps = useSessionStore.getState().workflowSteps
      expect(steps[0]?.status).toBe('done')
      expect(steps[1]?.status).toBe('running')
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
