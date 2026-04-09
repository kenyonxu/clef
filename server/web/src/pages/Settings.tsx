import { useEffect, useState } from 'react'
import { useSettingsStore } from '../stores/settingsStore'
import { useUIStore } from '../stores/uiStore'
import { OutputDirSetting } from '../components/settings/OutputDirSetting'
import { Sf2Setting } from '../components/settings/Sf2Setting'
import { WorkflowParams } from '../components/settings/WorkflowParams'
import { ProviderList } from '../components/settings/ProviderList'
import { AgentTable } from '../components/settings/AgentTable'
import { DiagnosticsPanel } from '../components/settings/DiagnosticsPanel'

type Tab = 'general' | 'providers' | 'agents' | 'diagnostics'

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'providers', label: 'Providers' },
  { id: 'agents', label: 'Agents' },
  { id: 'diagnostics', label: 'Diagnostics' },
]

export function Settings() {
  const [activeTab, setActiveTab] = useState<Tab>('general')

  // General tab form state — lifted from child components
  const [outputDir, setOutputDir] = useState('')
  const [sf2Path, setSf2Path] = useState('')
  const [maxIterations, setMaxIterations] = useState(3)
  const [reviewThreshold, setReviewThreshold] = useState(7)
  const [skipReview, setSkipReview] = useState(false)

  const settings = useSettingsStore((s) => s.settings)
  const isSaving = useSettingsStore((s) => s.isSaving)
  const saveSettings = useSettingsStore((s) => s.saveSettings)
  const loadSettings = useSettingsStore((s) => s.loadSettings)
  const loadProviders = useSettingsStore((s) => s.loadProviders)
  const loadAgents = useSettingsStore((s) => s.loadAgents)
  const loadDiagnostics = useSettingsStore((s) => s.loadDiagnostics)
  const showToast = useUIStore((s) => s.showToast)

  // Sync form state when settings load from server
  useEffect(() => {
    if (settings) {
      setOutputDir(settings.output_dir)
      setSf2Path(settings.sf2_path)
      setMaxIterations(settings.max_iterations)
      setReviewThreshold(settings.review_threshold)
      setSkipReview(settings.skip_review)
    }
  }, [settings])

  useEffect(() => {
    loadSettings()
    loadProviders()
    loadAgents()
  }, [loadSettings, loadProviders, loadAgents])

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    if (tab === 'diagnostics') {
      loadDiagnostics()
    }
  }

  const handleSaveGeneral = async () => {
    try {
      await saveSettings({
        output_dir: outputDir,
        sf2_path: sf2Path,
        max_iterations: maxIterations,
        review_threshold: reviewThreshold,
        skip_review: skipReview,
      })
      showToast('Settings saved', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Save failed', 'error')
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-bold text-white mb-6">Settings</h1>

      <div role="tablist" className="flex gap-1 border-b border-border-subtle mb-6">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            role="tab"
            aria-selected={activeTab === id}
            tabIndex={activeTab === id ? 0 : -1}
            onClick={() => handleTabChange(id)}
            className={`px-4 py-2 text-sm font-bold transition-colors duration-150 ${
              activeTab === id
                ? 'text-white border-b-2 border-brand'
                : 'text-muted hover:text-silver'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="space-y-6">
        {activeTab === 'general' && (
          <>
            <div className="rounded-xl border border-border-subtle bg-surface p-5 space-y-6">
              <OutputDirSetting value={outputDir} onChange={setOutputDir} />
              <Sf2Setting
                value={sf2Path}
                sf2Name={settings?.sf2_name ?? ''}
                presetCount={settings?.sf2_preset_count ?? 0}
                onChange={setSf2Path}
              />
              <WorkflowParams
                maxIterations={maxIterations}
                onMaxIterationsChange={setMaxIterations}
                reviewThreshold={reviewThreshold}
                onReviewThresholdChange={setReviewThreshold}
                skipReview={skipReview}
                onSkipReviewChange={setSkipReview}
              />
            </div>
            <button
              onClick={handleSaveGeneral}
              disabled={isSaving}
              className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black hover:opacity-90 disabled:opacity-40"
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </>
        )}

        {activeTab === 'providers' && (
          <div className="rounded-xl border border-border-subtle bg-surface p-5">
            <ProviderList />
          </div>
        )}

        {activeTab === 'agents' && (
          <div className="rounded-xl border border-border-subtle bg-surface p-5">
            <AgentTable />
          </div>
        )}

        {activeTab === 'diagnostics' && (
          <div className="rounded-xl border border-border-subtle bg-surface p-5">
            <DiagnosticsPanel />
          </div>
        )}
      </div>
    </div>
  )
}
