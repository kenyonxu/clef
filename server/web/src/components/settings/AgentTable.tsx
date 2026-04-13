import { useSettingsStore } from '../../stores/settingsStore'
import { useUIStore } from '../../stores/uiStore'

export function AgentTable() {
  const agents = useSettingsStore((s) => s.agents)
  const providers = useSettingsStore((s) => s.providers)
  const saveAgents = useSettingsStore((s) => s.saveAgents)
  const isSaving = useSettingsStore((s) => s.isSaving)
  const agentEdits = useSettingsStore((s) => s.agentEdits)
  const updateAgentEdits = useSettingsStore((s) => s.updateAgentEdits)
  const showToast = useUIStore((s) => s.showToast)

  const providerAliases = [
    providers?.anthropic ? 'anthropic' : null,
    ...(providers?.anthropic_compat.map((p) => p.alias) ?? []),
    ...(providers?.openai_compat.map((p) => p.alias) ?? []),
  ].filter(Boolean)

  const handleSave = async () => {
    try {
      await saveAgents({ agents: agentEdits })
      showToast('Agent config saved', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Save failed', 'error')
    }
  }

  if (!agents || !agents.agents.length) {
    return <p className="text-sm text-muted">Loading agents...</p>
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-bold text-white">Agent Configuration</label>
      <div className="overflow-auto rounded-lg border border-border-subtle">
        <table className="w-full text-sm text-left">
          <thead className="border-b border-border-subtle bg-surface-mid">
            <tr>
              <th className="px-3 py-2 text-xs font-bold text-silver">Name</th>
              <th className="px-3 py-2 text-xs font-bold text-silver">Model</th>
              <th className="px-3 py-2 text-xs font-bold text-silver">Temp</th>
              <th className="px-3 py-2 text-xs font-bold text-silver">Skills</th>
              <th className="px-3 py-2 text-xs font-bold text-silver">Tools</th>
            </tr>
          </thead>
          <tbody>
            {agents.agents.map((agent) => (
              <tr key={agent.name} className="border-b border-border-subtle last:border-b-0">
                <td className="px-3 py-2 text-xs text-white font-mono">{agent.name}</td>
                <td className="px-3 py-2">
                  <select
                    value={agentEdits[agent.name]?.model_alias ?? agent.model_alias}
                    onChange={(e) =>
                      updateAgentEdits(agent.name, {
                        model_alias: e.target.value,
                        temperature: agentEdits[agent.name]?.temperature ?? 0.7,
                      })
                    }
                    className="rounded bg-surface-mid px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    {providerAliases.map((alias) => (
                      <option key={alias ?? ''} value={alias ?? ''}>{alias}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.1}
                    value={agentEdits[agent.name]?.temperature ?? agent.temperature}
                    onChange={(e) =>
                      updateAgentEdits(agent.name, {
                        model_alias: agentEdits[agent.name]?.model_alias ?? '',
                        temperature: Number(e.target.value),
                      })
                    }
                    className="w-20 accent-brand"
                  />
                  <span className="ml-1 text-xs font-mono text-muted">
                    {(agentEdits[agent.name]?.temperature ?? agent.temperature).toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {agent.skills.map((s) => (
                      <span key={s} className="rounded-full bg-surface-mid px-2 py-0.5 text-[10px] text-muted">{s}</span>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {agent.tools.map((t) => (
                      <span key={t} className="rounded-full bg-surface-mid px-2 py-0.5 text-[10px] text-muted">{t}</span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        onClick={handleSave}
        disabled={isSaving}
        className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40"
      >
        Save Agent Config
      </button>
    </div>
  )
}
