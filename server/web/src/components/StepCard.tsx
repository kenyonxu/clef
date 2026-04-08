import type { WorkflowStep } from '../api/types'
import { StatusBadge } from './StatusBadge'

interface StepCardProps {
  step: WorkflowStep
}

export function StepCard({ step }: StepCardProps) {
  return (
    <div className={`rounded-lg border border-border-subtle bg-surface p-3 transition-colors duration-150 ${
      step.status === 'running' ? 'border-info/30' : ''
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted">Step {step.id}</span>
          <span className="text-sm font-bold text-white">{step.label}</span>
        </div>
        <StatusBadge status={step.status} />
      </div>

      {step.error && (
        <p className="mt-2 text-xs text-error">{step.error}</p>
      )}

      {step.agents && step.agents.length > 0 && (
        <div className="mt-2 ml-6 space-y-1.5 border-l border-border-subtle pl-3">
          {step.agents.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs text-silver">{agent.name}</span>
                {agent.model && (
                  <span className="rounded bg-surface-mid px-1.5 py-0.5 text-[10px] font-mono text-muted">
                    {agent.model}
                  </span>
                )}
              </div>
              {agent.status && <StatusBadge status={agent.status} />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
