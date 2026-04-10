import { useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { useUIStore } from '../../stores/uiStore'
import type { ProviderUpdate } from '../../api/types'

export function ProviderList() {
  const providers = useSettingsStore((s) => s.providers)
  const providerError = useSettingsStore((s) => s.providerError)
  const loadProviders = useSettingsStore((s) => s.loadProviders)
  const saveProviders = useSettingsStore((s) => s.saveProviders)
  const isSaving = useSettingsStore((s) => s.isSaving)
  const showToast = useUIStore((s) => s.showToast)

  const [editing, setEditing] = useState<string | null>(null)
  const [editKey, setEditKey] = useState('')
  const [editModel, setEditModel] = useState('')
  const [editBaseUrl, setEditBaseUrl] = useState('')

  const [showAdd, setShowAdd] = useState(false)
  const [newAlias, setNewAlias] = useState('')
  const [newModel, setNewModel] = useState('')
  const [newBaseUrl, setNewBaseUrl] = useState('')
  const [newKey, setNewKey] = useState('')

  const handleSaveEdit = async () => {
    const update: ProviderUpdate = {}
    if (editing === 'anthropic') {
      if (editKey) update.anthropic_api_key = editKey
      if (editModel) update.anthropic_model = editModel
    } else if (editing && editing.startsWith('ac:')) {
      const alias = editing.slice(3)
      update.anthropic_compat = {
        [alias]: { model_id: editModel, base_url: editBaseUrl, api_key: editKey },
      }
    } else if (editing) {
      update.openai_compat = {
        [editing]: { model_id: editModel, base_url: editBaseUrl, api_key: editKey },
      }
    }
    try {
      await saveProviders(update)
      setEditing(null)
      showToast('Provider updated', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Update failed', 'error')
    }
  }

  const handleRemove = async (alias: string) => {
    try {
      await saveProviders({ remove_openai_compat: [alias] })
      showToast(`Removed ${alias}`, 'info')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Remove failed', 'error')
    }
  }

  const handleAdd = async () => {
    if (!newAlias.trim()) return
    try {
      await saveProviders({
        openai_compat: {
          [newAlias.trim()]: { model_id: newModel, base_url: newBaseUrl, api_key: newKey },
        },
      })
      setShowAdd(false)
      setNewAlias('')
      setNewModel('')
      setNewBaseUrl('')
      setNewKey('')
      showToast(`Added ${newAlias}`, 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Add failed', 'error')
    }
  }

  if (!providers) {
    if (providerError) {
      return (
        <div className="space-y-2">
          <p className="text-sm text-error">{providerError}</p>
          <button onClick={loadProviders} className="text-xs text-info hover:underline">Retry</button>
        </div>
      )
    }
    return <p className="text-sm text-muted">Loading providers...</p>
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-bold text-white">LLM Providers</label>

      {providers.anthropic && (
        <div className="rounded-lg border border-border-subtle bg-surface p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-white">Anthropic</span>
            <div className="flex gap-2">
              <span className="text-xs font-mono text-muted">{providers.anthropic.model_id}</span>
              {providers.anthropic.is_configured ? (
                <span className="text-xs text-brand">configured</span>
              ) : (
                <span className="text-xs text-error">no key</span>
              )}
            </div>
          </div>
          <p className="text-xs font-mono text-muted">Key: {providers.anthropic.api_key_masked}</p>
          {editing === 'anthropic' ? (
            <div className="space-y-2 border-t border-border-subtle pt-2">
              <input type="text" placeholder="API Key" value={editKey} onChange={(e) => setEditKey(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <input type="text" placeholder="Model" value={editModel} onChange={(e) => setEditModel(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <div className="flex gap-2">
                <button onClick={handleSaveEdit} disabled={isSaving}
                  className="rounded-[500px] bg-brand px-4 py-1 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40">Save</button>
                <button onClick={() => setEditing(null)}
                  className="rounded-[500px] border border-border-standard px-4 py-1 text-xs font-bold uppercase tracking-wider text-silver hover:opacity-80">Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={() => { setEditing('anthropic'); setEditModel(providers?.anthropic?.model_id ?? ''); setEditKey('') }}
              className="text-xs text-info hover:underline">Edit</button>
          )}
        </div>
      )}

      {providers.anthropic_compat.length > 0 && (
        <label className="block text-xs font-bold text-muted uppercase tracking-wider mt-2">Anthropic-Compatible</label>
      )}
      {providers.anthropic_compat.map((p) => (
        <div key={p.alias} className="rounded-lg border border-border-subtle bg-surface p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-white">{p.alias}</span>
            <div className="flex items-center gap-2">
              {p.is_configured ? (
                <span className="text-xs text-brand">configured</span>
              ) : (
                <span className="text-xs text-error">no key</span>
              )}
              <button onClick={() => { setEditing(`ac:${p.alias}`); setEditModel(p.model_id); setEditBaseUrl(p.base_url); setEditKey('') }}
                className="text-xs text-info hover:underline">Edit</button>
            </div>
          </div>
          <p className="text-xs font-mono text-muted">{p.model_id}</p>
          <p className="text-xs font-mono text-muted truncate">{p.base_url}</p>
          <p className="text-xs font-mono text-muted">Key: {p.api_key_masked}</p>
          {editing === `ac:${p.alias}` ? (
            <div className="space-y-2 border-t border-border-subtle pt-2">
              <input type="text" placeholder="API Key" value={editKey} onChange={(e) => setEditKey(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <input type="text" placeholder="Model ID" value={editModel} onChange={(e) => setEditModel(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <input type="text" placeholder="Base URL" value={editBaseUrl} onChange={(e) => setEditBaseUrl(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <div className="flex gap-2">
                <button onClick={handleSaveEdit} disabled={isSaving}
                  className="rounded-[500px] bg-brand px-4 py-1 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40">Save</button>
                <button onClick={() => setEditing(null)}
                  className="rounded-[500px] border border-border-standard px-4 py-1 text-xs font-bold uppercase tracking-wider text-silver hover:opacity-80">Cancel</button>
              </div>
            </div>
          ) : null}
        </div>
      ))}

      {providers.openai_compat.length > 0 && (
        <label className="block text-xs font-bold text-muted uppercase tracking-wider mt-2">OpenAI-Compatible</label>
      )}
      {providers.openai_compat.map((p) => (
        <div key={p.alias} className="rounded-lg border border-border-subtle bg-surface p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-white">{p.alias}</span>
            <div className="flex items-center gap-2">
              {p.is_configured ? (
                <span className="text-xs text-brand">configured</span>
              ) : (
                <span className="text-xs text-error">no key</span>
              )}
              <button onClick={() => handleRemove(p.alias)} className="text-xs text-error hover:underline">Remove</button>
            </div>
          </div>
          <p className="text-xs font-mono text-muted">{p.model_id}</p>
          <p className="text-xs font-mono text-muted truncate">{p.base_url}</p>
          <p className="text-xs font-mono text-muted">Key: {p.api_key_masked}</p>
          {editing === p.alias ? (
            <div className="space-y-2 border-t border-border-subtle pt-2">
              <input type="text" placeholder="API Key" value={editKey} onChange={(e) => setEditKey(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <input type="text" placeholder="Model ID" value={editModel} onChange={(e) => setEditModel(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <input type="text" placeholder="Base URL" value={editBaseUrl} onChange={(e) => setEditBaseUrl(e.target.value)}
                className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
              <div className="flex gap-2">
                <button onClick={handleSaveEdit} disabled={isSaving}
                  className="rounded-[500px] bg-brand px-4 py-1 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40">Save</button>
                <button onClick={() => setEditing(null)}
                  className="rounded-[500px] border border-border-standard px-4 py-1 text-xs font-bold uppercase tracking-wider text-silver hover:opacity-80">Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={() => { setEditing(p.alias); setEditModel(p.model_id); setEditBaseUrl(p.base_url); setEditKey('') }}
              className="text-xs text-info hover:underline">Edit</button>
          )}
        </div>
      ))}

      {!showAdd ? (
        <button onClick={() => setShowAdd(true)} className="text-xs text-info hover:underline">+ Add Provider</button>
      ) : (
        <div className="rounded-lg border border-border-subtle bg-surface p-3 space-y-2">
          <input type="text" placeholder="Alias (e.g. grok)" value={newAlias} onChange={(e) => setNewAlias(e.target.value)}
            className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
          <input type="text" placeholder="Model ID" value={newModel} onChange={(e) => setNewModel(e.target.value)}
            className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
          <input type="text" placeholder="Base URL" value={newBaseUrl} onChange={(e) => setNewBaseUrl(e.target.value)}
            className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
          <input type="text" placeholder="API Key" value={newKey} onChange={(e) => setNewKey(e.target.value)}
            className="w-full rounded-lg bg-surface-mid px-3 py-1.5 text-xs text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand" />
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={isSaving || !newAlias.trim()}
              className="rounded-[500px] bg-brand px-4 py-1 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40">Add</button>
            <button onClick={() => setShowAdd(false)}
              className="rounded-[500px] border border-border-standard px-4 py-1 text-xs font-bold uppercase tracking-wider text-silver hover:opacity-80">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
