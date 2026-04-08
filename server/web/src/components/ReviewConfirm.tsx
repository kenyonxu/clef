import type { ConfirmationData } from '../api/types'
import { ScoreBar, SCORE_LABELS } from './ScoreBar'

interface ReviewConfirmProps {
  data: ConfirmationData
}

export function ReviewConfirm({ data }: ReviewConfirmProps) {
  const scores = data.review?.scores ?? {}

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">{data.title}</h3>
        {data.iterations != null && (
          <span className="text-xs text-muted">
            {data.iterations} iteration{data.iterations !== 1 ? 's' : ''}
          </span>
        )}
        {data.review?.overall_score != null && (
          <span className="text-xs font-bold text-brand">
            {typeof data.review.overall_score === 'number'
              ? data.review.overall_score.toFixed(1)
              : data.review.overall_score}/10
          </span>
        )}
      </div>

      {data.output_file && (
        <div className="rounded-lg bg-surface-mid p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Output File
          </div>
          <div className="mt-0.5 text-sm font-mono text-text-secondary">
            {data.output_file}
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

      <div className="rounded-lg border border-brand/20 bg-brand/5 p-3">
        <p className="text-xs text-text-secondary">
          确认后将注入表现力（CC7 音量 / CC10 声相 / CC91 混响 / 弯音），生成最终 MIDI 文件。
        </p>
      </div>

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
