import type { WorkflowStep, SubStep } from '../api/types'
import { StatusBadge } from './StatusBadge'

interface StepCardProps {
  step: WorkflowStep
}

function SubStepIcon({ status }: { status: SubStep['status'] }) {
  if (status === 'done') return <span className="text-emerald-400 text-[10px]">&#10003;</span>
  if (status === 'running') {
    return (
      <span className="inline-block w-2.5 h-2.5 border-[1.5px] border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
    )
  }
  if (status === 'failed') return <span className="text-red-400 text-[10px]">&#10007;</span>
  return <span className="text-neutral-600 text-[10px]">&#9675;</span>
}

export function StepCard({ step }: StepCardProps) {
  const isRunning = step.status === 'running'
  const isDone = step.status === 'done'
  const isPending = step.status === 'pending'

  return (
    <div
      className={`rounded-lg border bg-surface p-3 transition-all duration-300 ${
        isRunning
          ? 'border-blue-400/50 bg-blue-400/6 shadow-[0_0_20px_rgba(96,165,250,0.1),0_0_40px_rgba(96,165,250,0.05)] animate-[cardPulse_2s_ease-in-out_infinite]'
          : isDone
            ? 'border-border-subtle opacity-60'
            : isPending
              ? 'border-border-subtle opacity-40'
              : 'border-border-subtle'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted">{step.id}</span>
          <span className={`text-sm font-bold ${isPending ? 'text-muted' : isDone ? 'text-neutral-400' : 'text-white'}`}>
            {step.label}
          </span>
          {step.confirm && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-400/10 px-1.5 py-0.5 text-[9px] text-amber-400">
              {isDone ? '\u2713 ' : ''}需确认
            </span>
          )}
        </div>
        <StatusBadge status={step.status} />
      </div>

      {step.error && (
        <p className="mt-2 text-xs text-error">{step.error}</p>
      )}

      {step.agents && step.agents.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {step.agents.map((agent) => {
            const agentRunning = agent.status === 'running'
            const agentDone = agent.status === 'done'
            return (
              <span
                key={agent.name}
                className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                  agentRunning
                    ? 'bg-blue-400/15 text-blue-400 border border-blue-400/30'
                    : agentDone
                      ? 'bg-emerald-400/10 text-emerald-400'
                      : 'bg-white/3 text-neutral-600'
                }`}
              >
                {agent.name}
              </span>
            )
          })}
        </div>
      )}

      {step.sub_steps && step.sub_steps.length > 0 && (
        <div className={`mt-2 ml-4 space-y-1 border-l-2 pl-3 ${
          isRunning ? 'border-blue-400/30' : 'border-border-subtle'
        }`}>
          {step.sub_steps.map((ss, i) => (
            <div
              key={`${ss.label}-${i}`}
              className={`flex items-center gap-1.5 text-[11px] leading-relaxed ${
                ss.status === 'done'
                  ? 'text-emerald-400'
                  : ss.status === 'running'
                    ? 'text-blue-400'
                    : ss.status === 'failed'
                      ? 'text-red-400'
                      : 'text-neutral-600'
              }`}
            >
              <SubStepIcon status={ss.status} />
              <span>{ss.label}</span>
              {ss.agent && (
                <span className={`font-mono text-[9px] ${
                  ss.status === 'running' ? 'text-blue-500' : 'text-neutral-500'
                }`}>
                  {ss.agent}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
