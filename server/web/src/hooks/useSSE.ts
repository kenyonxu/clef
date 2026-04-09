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
