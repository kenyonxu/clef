import { create } from 'zustand'

export interface ToastData {
  message: string
  type: 'info' | 'error' | 'success'
}

interface UIState {
  currentPage: 'workspace' | 'settings' | 'sessions'
  toast: ToastData | null
  showToast: (message: string, type: ToastData['type']) => void
  clearToast: () => void
}

export const useUIStore = create<UIState>((set) => ({
  currentPage: 'workspace',
  toast: null,
  showToast: (message, type) => {
    set({ toast: { message, type } })
    setTimeout(() => set({ toast: null }), 4000)
  },
  clearToast: () => set({ toast: null }),
}))
