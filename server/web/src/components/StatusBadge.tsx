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
