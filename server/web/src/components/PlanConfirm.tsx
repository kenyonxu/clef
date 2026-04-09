import type { ConfirmationData } from '../api/types'

interface PlanConfirmProps {
  data: ConfirmationData
}

const VOICE_LABELS: Record<string, string> = {
  melody: '旋律',
  harmony: '和声',
  bass: '低音',
  drums: '鼓',
}

interface PlanData {
  title?: string
  key?: string
  scale?: string
  bpm?: number
  time_signature?: string
  form?: string
  total_bars?: number
  demo_length_bars?: number
  generation_order?: string[]
  sections?: Record<string, unknown>[]
}

export function PlanConfirm({ data }: PlanConfirmProps) {
  const plan = (data.plan ?? {}) as PlanData
  const summary = data.summary
  const sections = Array.isArray(plan.sections) ? plan.sections : []

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-white">{data.title}</h3>

      {/* User prompt context */}
      {data.user_prompt && (
        <div className="rounded-lg bg-surface-mid p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1">创作需求</div>
          <p className="text-sm text-white/80">{data.user_prompt}</p>
        </div>
      )}

      {/* Key parameters grid */}
      <div className="grid grid-cols-2 gap-2">
        {plan.title && (
          <ParamCard label="标题" value={String(plan.title)} />
        )}
        {plan.key && (
          <ParamCard label="调性" value={`${plan.key} ${plan.scale === 'major' ? '大调' : '小调'}`} />
        )}
        {plan.bpm && (
          <ParamCard label="速度" value={`${plan.bpm} BPM`} />
        )}
        {summary?.duration && (
          <ParamCard label="时长" value={`${summary.duration}（${plan.total_bars} 小节）`} />
        )}
        {summary?.section_structure && (
          <ParamCard label="曲式" value={summary.section_structure} />
        )}
        {plan.demo_length_bars && (
          <ParamCard label="小样长度" value={summary?.demo_length ?? `${plan.demo_length_bars} bars`} />
        )}
        {plan.time_signature && (
          <ParamCard label="拍号" value={String(plan.time_signature)} />
        )}
        {plan.generation_order && (
          <ParamCard label="生成顺序" value={(plan.generation_order as string[]).map(o => VOICE_LABELS[o] ?? o).join(' → ')} />
        )}
      </div>

      {/* Orchestration */}
      {summary?.orchestration_desc && (
        <div className="rounded-lg bg-surface-mid p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1">配器方案</div>
          <p className="text-sm text-white">{summary.orchestration_desc}</p>
        </div>
      )}

      {/* SF2 Status */}
      {summary?.sf2_status && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <span>SF2 音色库：</span>
          <span className={summary.sf2_status.includes('未配置') ? 'text-muted' : 'text-green-400'}>
            {summary.sf2_status}
          </span>
        </div>
      )}

      {/* Section details */}
      {sections.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1.5">
            段落结构
          </div>
          <div className="space-y-0.5">
            {sections.map((section: Record<string, unknown>, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
                <span className="font-bold text-brand w-6">{String(section.id ?? String.fromCharCode(65 + i))}</span>
                <span className="flex-1 text-white">{String(section.name ?? `Section ${i + 1}`)}</span>
                <span className="text-muted">
                  {String(section.measures)} bars
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

function ParamCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-mid p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-white">{value}</div>
    </div>
  )
}
