import type { ConfirmationData } from '../api/types'

interface SampleConfirmProps {
  data: ConfirmationData
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 10)
  const color =
    value >= 8
      ? 'bg-[#1ed760]'
      : value >= 7
        ? 'bg-[#f59b23]'
        : 'bg-[#e91429]'
  const textColor =
    value >= 8
      ? 'text-[#1ed760]'
      : value >= 7
        ? 'text-[#f59b23]'
        : 'text-[#e91429]'

  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-muted">
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-surface-mid">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`w-6 text-right text-xs font-bold ${textColor}`}>{value}</span>
    </div>
  )
}

function VerdictBadge({ verdict }: { verdict?: string }) {
  if (!verdict) return null

  const isPass = verdict === 'pass'
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isPass ? 'bg-[#1ed760]/20 text-[#1ed760]' : 'bg-[#f59b23]/20 text-[#f59b23]'
      }`}
    >
      {isPass ? 'PASS' : 'REVISE'}
    </span>
  )
}

const SCORE_LABELS: Record<string, string> = {
  melody: '旋律',
  harmony: '和声',
  rhythm: '节奏',
  structure: '结构',
  style: '风格',
  orchestration: '配器',
}

export function SampleConfirm({ data }: SampleConfirmProps) {
  const scores = data.review?.scores ?? {}
  const verdict = data.review?.verdict

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">{data.title}</h3>
        <div className="flex items-center gap-2">
          {data.sample_round != null && (
            <span className="text-xs text-muted">Round {data.sample_round}</span>
          )}
          {data.review?.overall_score != null && (
            <span className="text-xs font-bold text-brand">
              {typeof data.review.overall_score === 'number'
                ? data.review.overall_score.toFixed(1)
                : data.review.overall_score}/10
            </span>
          )}
          <VerdictBadge verdict={verdict} />
        </div>
      </div>

      {data.sample_file && (
        <div className="rounded-lg bg-surface-mid p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Sample File
          </div>
          <div className="mt-0.5 text-sm font-mono text-text-secondary">
            {data.sample_file}
          </div>
        </div>
      )}

      {Object.keys(scores).length > 0 && (
        <div className="space-y-2 rounded-lg bg-surface-mid p-3">
          {Object.entries(scores).map(([key, value]) => (
            <ScoreBar
              key={key}
              label={SCORE_LABELS[key] ?? key}
              value={typeof value === 'number' ? value : 0}
            />
          ))}
        </div>
      )}

      {data.review?.summary && (
        <p className="text-xs text-text-secondary">{data.review.summary}</p>
      )}
    </div>
  )
}
