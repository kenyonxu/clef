import { create } from 'zustand'
import { apiClient } from '../api/client'
import type {
  Settings,
  ProviderList,
  ProviderUpdate,
  AgentList,
  AgentUpdate,
  Diagnostics,
} from '../api/types'

interface SettingsState {
  settings: Settings | null
  providers: ProviderList | null
  agents: AgentList | null
  diagnostics: Diagnostics | null
  isLoading: boolean
  isSaving: boolean
  providerError: string | null

  loadSettings: () => Promise<void>
  saveSettings: (update: Partial<Settings>) => Promise<void>
  loadProviders: () => Promise<void>
  saveProviders: (update: ProviderUpdate) => Promise<void>
  loadAgents: () => Promise<void>
  saveAgents: (update: AgentUpdate) => Promise<void>
  loadDiagnostics: () => Promise<void>
  cleanupSessions: () => Promise<number>
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: null,
  providers: null,
  agents: null,
  diagnostics: null,
  isLoading: false,
  isSaving: false,
  providerError: null,

  loadSettings: async () => {
    set({ isLoading: true })
    try {
      const data = await apiClient.get<Settings>('/settings')
      set({ settings: data })
    } catch {
      // Silent fail — page will show defaults
    } finally {
      set({ isLoading: false })
    }
  },

  saveSettings: async (update) => {
    set({ isSaving: true })
    try {
      const data = await apiClient.put<Settings>('/settings', update)
      set({ settings: data })
    } finally {
      set({ isSaving: false })
    }
  },

  loadProviders: async () => {
    try {
      const data = await apiClient.get<ProviderList>('/settings/providers')
      set({ providers: data, providerError: null })
    } catch (err) {
      set({ providerError: err instanceof Error ? err.message : 'Failed to load providers' })
    }
  },

  saveProviders: async (update) => {
    set({ isSaving: true })
    try {
      const data = await apiClient.put<ProviderList>('/settings/providers', update)
      set({ providers: data })
    } finally {
      set({ isSaving: false })
    }
  },

  loadAgents: async () => {
    try {
      const data = await apiClient.get<AgentList>('/settings/agents')
      set({ agents: data })
    } catch {
      // Silent fail
    }
  },

  saveAgents: async (update) => {
    set({ isSaving: true })
    try {
      const data = await apiClient.put<AgentList>('/settings/agents', update)
      set({ agents: data })
    } finally {
      set({ isSaving: false })
    }
  },

  loadDiagnostics: async () => {
    try {
      const data = await apiClient.get<Diagnostics>('/settings/diagnostics')
      set({ diagnostics: data })
    } catch {
      // Silent fail
    }
  },

  cleanupSessions: async () => {
    const data = await apiClient.post<{ removed_sessions: number }>('/settings/cleanup', null)
    return data.removed_sessions
  },
}))
