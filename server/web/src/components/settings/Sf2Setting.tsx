interface Sf2SettingProps {
  value: string
  sf2Name: string
  presetCount: number
  onChange: (value: string) => void
}

export function Sf2Setting({ value, sf2Name, presetCount, onChange }: Sf2SettingProps) {
  const hasProfile = sf2Name !== '' && presetCount > 0

  return (
    <div className="space-y-3">
      <label className="block text-sm font-bold text-white">SoundFont (SF2)</label>
      <p className="text-xs text-muted">
        SF2 音色库文件路径。配置后将根据真实音域约束生成 MIDI。
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="C:\SoundFonts\GeneralUser GS.sf2"
          className="flex-1 rounded-lg bg-surface-mid px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
        />
      </div>
      {hasProfile && (
        <div className="rounded-lg bg-surface-mid px-3 py-2 text-xs text-muted">
          <span className="font-semibold text-text-secondary">{sf2Name}</span>
          <span className="ml-2">{presetCount} presets</span>
        </div>
      )}
    </div>
  )
}
