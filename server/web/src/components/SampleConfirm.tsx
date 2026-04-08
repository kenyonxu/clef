import type { ConfirmationData } from '../api/types'
import { ScoreBar, SCORE_LABELS } from './ScoreBar'

interface SampleConfirmProps {
  data: ConfirmationData
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

      {(data.review?.issues?.length ?? 0) > 0 && (
        <div className="space-y-1 rounded-lg bg-surface-mid p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            改进建议
          </div>
          <ul className="list-disc list-inside space-y-0.5">
            {data.review!.issues!.map((issue, i) => (
              <li key={i} className="text-xs text-text-secondary">{issue}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
