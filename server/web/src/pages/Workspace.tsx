import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { usePolling } from '../hooks/usePolling'
import { useSSE } from '../hooks/useSSE'
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
  const fetchProfiles = useSessionStore((s) => s.fetchProfiles)
  const profiles = useSessionStore((s) => s.profiles)
  const selectedProfile = useSessionStore((s) => s.selectedProfile)
  const setSelectedProfile = useSessionStore((s) => s.setSelectedProfile)
  const showToast = useUIStore((s) => s.showToast)

  // Session recovery from URL
  const sessionIdFromUrl = searchParams.get('session')
  useEffect(() => {
    if (sessionIdFromUrl && !currentSession) {
      pollOnce(sessionIdFromUrl)
    }
  }, [sessionIdFromUrl, currentSession, pollOnce])

  // Fetch profiles on mount
  useEffect(() => { fetchProfiles() }, [fetchProfiles])

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

  useSSE(currentSession?.session_id ?? null, !isTerminal)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    const text = prompt.trim()
    setPrompt('')
    await submitPrompt(text)
  }

  const handleCancel = async () => {
    if (!currentSession?.session_id) return
    await cancelSession(currentSession.session_id)
    showToast('Session cancelled', 'info')
  }

  return (
    <div className="flex h-full">
      {/* Left column — Chat */}
      <div className="flex w-[60%] flex-col border-r border-border-subtle">
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

        <form onSubmit={handleSubmit} className="border-t border-border-subtle p-4">
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
        {currentSession && (
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">Workflow</h2>
            <StatusBadge status={currentSession.status as SessionStatus} />
          </div>
        )}

        <div className="space-y-2">
          {workflowSteps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
            />
          ))}
        </div>

        {outputFiles.length > 0 && <FileList files={outputFiles} />}

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
