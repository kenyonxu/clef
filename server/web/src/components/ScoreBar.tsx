export function ScoreBar({ label, value }: { label: string; value: number }) {
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

export const SCORE_LABELS: Record<string, string> = {
  melody: '旋律',
  harmony: '和声',
  rhythm: '节奏',
  structure: '结构',
  style: '风格',
  orchestration: '配器',
}
