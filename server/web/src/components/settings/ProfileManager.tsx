import { useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { useUIStore } from '../../stores/uiStore'

export function ProfileManager() {
  const agents = useSettingsStore((s) => s.agents)
  const agentEdits = useSettingsStore((s) => s.agentEdits)
  const profiles = useSettingsStore((s) => s.profiles)
  const isSaving = useSettingsStore((s) => s.isSaving)
  const saveProfile = useSettingsStore((s) => s.saveProfile)
  const deleteProfile = useSettingsStore((s) => s.deleteProfile)
  const showToast = useUIStore((s) => s.showToast)

  const [newId, setNewId] = useState('')
  const [newName, setNewName] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const handleSave = async () => {
    const id = newId.trim()
    const name = newName.trim()
    if (!id || !name) {
      showToast('Profile ID and display name are required', 'error')
      return
    }
    if (!agents) return
    const agentMap: Record<string, string> = {}
    for (const a of agents.agents) {
      agentMap[a.name] = agentEdits[a.name]?.model_alias ?? a.model_alias
    }
    try {
      await saveProfile(id, name, agentMap)
      showToast(`Profile "${name}" saved`, 'success')
      setNewId('')
      setNewName('')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Save failed', 'error')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteProfile(id)
      if (expandedId === id) setExpandedId(null)
      showToast(`Profile "${id}" deleted`, 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Delete failed', 'error')
    }
  }

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  const agentEntries = (p: typeof profiles[number]) =>
    Object.entries(p.agents).sort(([a], [b]) => a.localeCompare(b))

  return (
    <div className="space-y-4 mt-6 pt-4 border-t border-border-subtle">
      <label className="block text-sm font-bold text-white">Provider Profiles</label>

      {/* Existing profiles */}
      {profiles.length > 0 && (
        <div className="overflow-auto rounded-lg border border-border-subtle">
          <table className="w-full text-sm text-left">
            <thead className="border-b border-border-subtle bg-surface-mid">
              <tr>
                <th className="px-3 py-2 text-xs font-bold text-silver">ID</th>
                <th className="px-3 py-2 text-xs font-bold text-silver">Display Name</th>
                <th className="px-3 py-2 text-xs font-bold text-silver w-20"></th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => (
                <ProfileRow
                  key={p.id}
                  profile={p}
                  expanded={expandedId === p.id}
                  onToggle={() => toggleExpand(p.id)}
                  onDelete={() => handleDelete(p.id)}
                  agentEntries={agentEntries(p)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Save current as profile */}
      <div className="flex items-end gap-2">
        <div>
          <label className="block text-[10px] text-muted mb-1">Profile ID</label>
          <input
            type="text"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            placeholder="e.g. my-profile"
            className="w-32 rounded-lg bg-surface-mid px-2 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <div>
          <label className="block text-[10px] text-muted mb-1">Display Name</label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="e.g. My Custom Profile"
            className="w-48 rounded-lg bg-surface-mid px-2 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving || !newId.trim() || !newName.trim()}
          className="rounded-[500px] bg-surface-mid px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-silver hover:bg-border-subtle disabled:opacity-40"
        >
          Save Current as Profile
        </button>
      </div>
    </div>
  )
}

interface ProfileRowProps {
  profile: { id: string; display_name: string }
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
  agentEntries: [string, string][]
}

function ProfileRow({ profile, expanded, onToggle, onDelete, agentEntries }: ProfileRowProps) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="border-b border-border-subtle last:border-b-0 cursor-pointer hover:bg-surface-mid/50 transition-colors"
      >
        <td className="px-3 py-2">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-muted select-none">{expanded ? '\u25BC' : '\u25B6'}</span>
            <span className="text-xs text-white font-mono">{profile.id}</span>
          </div>
        </td>
        <td className="px-3 py-2 text-xs text-silver">{profile.display_name}</td>
        <td className="px-3 py-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="text-xs text-error hover:underline"
          >
            Delete
          </button>
        </td>
      </tr>
      {expanded && agentEntries.length > 0 && (
        <tr className="bg-surface-mid/30">
          <td colSpan={3} className="px-6 py-2">
            <div className="grid grid-cols-2 gap-x-6 gap-y-0.5">
              {agentEntries.map(([agent, model]) => (
                <div key={agent} className="flex items-center gap-2">
                  <span className="text-[11px] text-muted font-mono min-w-30">{agent}</span>
                  <span className="text-[11px] text-white font-mono">{model}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
