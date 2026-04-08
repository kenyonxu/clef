import { useState } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { PlanConfirm } from './PlanConfirm'
import { SampleConfirm } from './SampleConfirm'
import { ReviewConfirm } from './ReviewConfirm'
import type { ChatMessage } from '../api/types'

interface ConfirmationCardProps {
  message: ChatMessage
}

export function ConfirmationCard({ message }: ConfirmationCardProps) {
  const currentSession = useSessionStore((s) => s.currentSession)
  const confirmSession = useSessionStore((s) => s.confirmSession)
  const [feedback, setFeedback] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const data = message.confirmationData
  if (!data) return null

  const isActive = message.isActive ?? false
  const sessionId = currentSession?.session_id ?? ''

  const handleAction = async (action: 'continue' | 'revise' | 'cancel', includeFeedback: boolean) => {
    if (!isActive || isSubmitting) return
    setIsSubmitting(true)
    await confirmSession(sessionId, action, includeFeedback ? feedback || undefined : undefined)
    setFeedback('')
    setIsSubmitting(false)
  }

  const renderContent = () => {
    switch (data.phase) {
      case 'parse':
        return <PlanConfirm data={data} />
      case 'sample':
        return <SampleConfirm data={data} />
      case 'review':
        return <ReviewConfirm data={data} />
      default:
        return <p className="text-sm text-error">Unknown phase: {data.phase}</p>
    }
  }

  const renderButtons = () => {
    if (!isActive) return null

    switch (data.phase) {
      case 'parse':
        return (
          <div className="flex items-center justify-end gap-2 mt-3">
            <button
              onClick={() => handleAction('cancel', false)}
              disabled={isSubmitting}
              className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error hover:opacity-80 disabled:opacity-40"
            >
              取消
            </button>
            <button
              onClick={() => handleAction('continue', true)}
              disabled={isSubmitting}
              className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40"
            >
              确认规划
            </button>
          </div>
        )
      case 'sample':
        return (
          <div className="flex items-center justify-end gap-2 mt-3">
            <button
              onClick={() => handleAction('cancel', false)}
              disabled={isSubmitting}
              className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error hover:opacity-80 disabled:opacity-40"
            >
              取消
            </button>
            <button
              onClick={() => handleAction('revise', true)}
              disabled={isSubmitting}
              className="rounded-[500px] border border-border-subtle px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-white hover:opacity-80 disabled:opacity-40"
            >
              迭代
            </button>
            <button
              onClick={() => handleAction('continue', false)}
              disabled={isSubmitting}
              className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40"
            >
              通过 · 继续创作
            </button>
          </div>
        )
      case 'review':
        return (
          <div className="flex items-center justify-end gap-2 mt-3">
            <button
              onClick={() => handleAction('cancel', false)}
              disabled={isSubmitting}
              className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error hover:opacity-80 disabled:opacity-40"
            >
              取消
            </button>
            <button
              onClick={() => handleAction('revise', true)}
              disabled={isSubmitting}
              className="rounded-[500px] border border-border-subtle px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-white hover:opacity-80 disabled:opacity-40"
            >
              迭代
            </button>
            <button
              onClick={() => handleAction('continue', false)}
              disabled={isSubmitting}
              className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40"
            >
              确认 · 注入表现力
            </button>
          </div>
        )
    }
  }

  return (
    <div className={`max-w-[90%] rounded-xl border bg-surface-elevated p-4 space-y-3 ${
      isActive ? 'border-brand/30' : 'border-border-subtle opacity-70'
    }`}>
      {renderContent()}
      {isActive && (
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="反馈建议（可选）..."
          rows={2}
          className="w-full resize-none rounded-lg bg-surface-mid px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
          disabled={isSubmitting}
        />
      )}
      {renderButtons()}
      {!isActive && (
        <div className="text-[10px] text-muted text-right">已处理</div>
      )}
    </div>
  )
}
