import { useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { useUIStore } from '../../stores/uiStore'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export function DiagnosticsPanel() {
  const diagnostics = useSettingsStore((s) => s.diagnostics)
  const cleanupSessions = useSettingsStore((s) => s.cleanupSessions)
  const showToast = useUIStore((s) => s.showToast)
  const [cleaning, setCleaning] = useState(false)

  const handleCleanup = async () => {
    setCleaning(true)
    try {
      const result = await cleanupSessions()
      showToast(`Cleaned ${result} old session(s)`, 'success')
      // Reload diagnostics
      await useSettingsStore.getState().loadDiagnostics()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Cleanup failed', 'error')
    } finally {
      setCleaning(false)
    }
  }

  return (
    <div className="space-y-4">
      <label className="block text-sm font-bold text-white">System Diagnostics</label>

      {diagnostics ? (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-xs text-muted">Version</p>
              <p className="text-sm font-mono text-white">{diagnostics.version}</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-xs text-muted">Uptime</p>
              <p className="text-sm font-mono text-white">{formatUptime(diagnostics.uptime_seconds)}</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-xs text-muted">Temp Sessions</p>
              <p className="text-sm font-mono text-white">{diagnostics.temp_session_count}</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-xs text-muted">Temp Disk Usage</p>
              <p className="text-sm font-mono text-white">{diagnostics.temp_disk_usage_mb} MB</p>
            </div>
          </div>

          <div>
            <p className="text-xs text-muted mb-2">Temp Directory</p>
            <p className="text-xs font-mono text-silver break-all">{diagnostics.temp_workdir}</p>
          </div>

          <div>
            <p className="text-xs text-muted mb-2">Dependencies</p>
            <div className="space-y-1">
              {diagnostics.dependencies.map((dep) => (
                <div key={dep.name} className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${dep.installed ? 'bg-brand' : 'bg-error'}`} />
                  <span className="text-xs font-mono text-silver">{dep.name}</span>
                  <span className="text-xs text-muted">{dep.installed ? 'OK' : 'missing'}</span>
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error hover:opacity-80 disabled:opacity-40"
          >
            {cleaning ? 'Cleaning...' : 'Clean Old Sessions'}
          </button>
        </>
      ) : (
        <p className="text-sm text-muted">Loading diagnostics...</p>
      )}
    </div>
  )
}
