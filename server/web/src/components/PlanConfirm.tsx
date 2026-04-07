import type { ConfirmationData } from '../api/types'

interface PlanConfirmProps {
  data: ConfirmationData
}

const PARAM_KEYS = ['title', 'key', 'scale', 'bpm', 'time_signature', 'form', 'demo_length_bars', 'generation_order'] as const

const PARAM_LABELS: Record<string, string> = {
  title: '标题',
  key: '调性',
  scale: '调式',
  bpm: '速度',
  time_signature: '拍号',
  form: '曲式',
  demo_length_bars: '小样长度',
  generation_order: '生成顺序',
}

function formatValue(key: string, value: unknown): string {
  if (key === 'generation_order' && Array.isArray(value)) {
    return (value as string[]).join(' → ')
  }
  if (key === 'demo_length_bars' && typeof value === 'number') {
    return `${value} bars`
  }
  if (key === 'scale') {
    return value === 'major' ? '大调' : '小调'
  }
  return String(value)
}

const VOICE_LABELS: Record<string, string> = {
  melody: 'V:1 旋律',
  harmony: 'V:2 和声',
  bass: 'V:3 低音',
  drums: 'V:4 鼓',
}

export function PlanConfirm({ data }: PlanConfirmProps) {
  const plan = data.plan ?? {}

  const params = PARAM_KEYS.filter((k) => plan[k] != null && plan[k] !== '')
  const orchestration = plan.orchestration as Record<string, Record<string, string>> | null
  const sections = Array.isArray(plan.sections) ? plan.sections : []

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-white">{data.title}</h3>

      {params.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {params.map((key) => (
            <div key={key} className="rounded-lg bg-surface-mid p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                {PARAM_LABELS[key] ?? key}
              </div>
              <div className="mt-0.5 text-sm font-semibold text-white">
                {formatValue(key, plan[key])}
              </div>
            </div>
          ))}
        </div>
      )}

      {orchestration && typeof orchestration === 'object' && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1.5">
            配器方案
          </div>
          <div className="space-y-0.5">
            {Object.entries(orchestration).map(([voice, info]) => (
              <div key={voice} className="flex items-center gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
                <span className="w-16 text-muted">{VOICE_LABELS[voice] ?? voice}</span>
                <span className="flex-1 text-white">{info.name ?? info.instrument ?? voice}</span>
                <span className="text-muted text-[11px]">{info.register ?? info.range ?? ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {sections.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1.5">
            段落结构
          </div>
          <div className="space-y-0.5">
            {sections.map((section: { id?: string; name?: string; measures?: number | string; energy_level?: number }, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
                <span className="font-bold text-brand w-6">{section.id ?? String.fromCharCode(65 + i)}</span>
                <span className="flex-1 text-white">{section.name ?? `Section ${i + 1}`}</span>
                <span className="text-muted">
                  {section.measures} bars
                  {section.energy_level != null && ` · energy ${section.energy_level}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
