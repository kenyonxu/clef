interface WorkflowParamsProps {
  maxIterations: number
  onMaxIterationsChange: (value: number) => void
  reviewThreshold: number
  onReviewThresholdChange: (value: number) => void
  skipReview: boolean
  onSkipReviewChange: (value: boolean) => void
}

export function WorkflowParams({
  maxIterations,
  onMaxIterationsChange,
  reviewThreshold,
  onReviewThresholdChange,
  skipReview,
  onSkipReviewChange,
}: WorkflowParamsProps) {
  return (
    <div className="space-y-4">
      <label className="block text-sm font-bold text-white">Workflow Parameters</label>

      <div>
        <div className="flex items-center justify-between">
          <label className="text-xs text-silver">Max Iterations</label>
          <span className="text-xs font-mono text-white">{maxIterations}</span>
        </div>
        <input
          type="range"
          min={1}
          max={20}
          value={maxIterations}
          onChange={(e) => onMaxIterationsChange(Number(e.target.value))}
          className="w-full accent-brand"
        />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <label className="text-xs text-silver">Review Threshold</label>
          <span className="text-xs font-mono text-white">{reviewThreshold}/10</span>
        </div>
        <input
          type="range"
          min={1}
          max={10}
          value={reviewThreshold}
          onChange={(e) => onReviewThresholdChange(Number(e.target.value))}
          className="w-full accent-brand"
        />
      </div>

      <label className="flex items-center gap-2 text-xs text-silver cursor-pointer select-none">
        <input
          type="checkbox"
          checked={skipReview}
          onChange={(e) => onSkipReviewChange(e.target.checked)}
          className="accent-brand"
        />
        Skip Review (fast test mode)
      </label>
    </div>
  )
}
