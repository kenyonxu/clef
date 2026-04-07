import type { OutputFile } from '../api/types'

interface FileListProps {
  files: OutputFile[]
}

export function FileList({ files }: FileListProps) {
  if (files.length === 0) return null

  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted">Output Files</h3>
      {files.map((file) => (
        <a
          key={file.path}
          href={`/result/${file.path.split('/').slice(-2).join('/')}`}
          className="flex items-center gap-2 rounded-lg bg-surface-mid px-3 py-2 text-sm text-silver hover:text-white transition-colors duration-150"
          download={file.filename}
        >
          <span className="text-brand">&darr;</span>
          <span className="font-mono text-xs">{file.filename}</span>
        </a>
      ))}
    </div>
  )
}
