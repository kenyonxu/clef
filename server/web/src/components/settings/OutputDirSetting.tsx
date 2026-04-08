import { useMemo } from 'react'

function sanitizePrompt(prompt: string, maxLen = 20): string {
  let cleaned = prompt
    .trim()
    .slice(0, maxLen)
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '')
    .replace(/^[.\s]+|[.\s]+$/g, '')
  return cleaned || 'untitled'
}

interface OutputDirSettingProps {
  value: string
  onChange: (value: string) => void
}

export function OutputDirSetting({ value, onChange }: OutputDirSettingProps) {
  const preview = useMemo(() => {
    if (!value.trim()) return ''
    const taskName = sanitizePrompt('英雄觉醒 Boss Battle')
    const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15)
    return `${value}\\${taskName}_${ts}`
  }, [value])

  return (
    <div className="space-y-3">
      <label className="block text-sm font-bold text-white">Output Directory</label>
      <p className="text-xs text-muted">
        Compose outputs will be saved here. Leave empty to use the system temp directory.
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="E:\Music\Clef"
          className="flex-1 rounded-lg bg-surface-mid px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
        />
      </div>
      {preview && (
        <p className="text-xs text-muted font-mono">
          Preview: {preview}
        </p>
      )}
    </div>
  )
}

export { sanitizePrompt }
