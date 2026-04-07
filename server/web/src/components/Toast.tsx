import { useUIStore } from '../stores/uiStore'

export function Toast() {
  const toast = useUIStore((s) => s.toast)
  const clearToast = useUIStore((s) => s.clearToast)

  if (!toast) return null

  const bg =
    toast.type === 'error'
      ? 'bg-error/20 border-error'
      : toast.type === 'success'
        ? 'bg-brand/20 border-brand'
        : 'bg-info/20 border-info'

  return (
    <div className="fixed top-4 right-4 z-50" role="alert">
      <div
        className={`${bg} border rounded-lg px-4 py-3 text-sm text-white shadow-dialog max-w-sm`}
        onClick={clearToast}
      >
        {toast.message}
      </div>
    </div>
  )
}
