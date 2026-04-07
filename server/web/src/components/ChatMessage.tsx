import type { ChatMessage as ChatMessageType } from '../api/types'

interface ChatMessageProps {
  message: ChatMessageType
}

const MESSAGE_STYLES: Record<ChatMessageType['type'], string> = {
  user: 'bg-surface-mid text-white ml-auto',
  system: 'bg-surface text-silver',
  error: 'bg-error/10 text-error',
}

export function ChatMessage({ message }: ChatMessageProps) {
  const time = new Date(message.timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${MESSAGE_STYLES[message.type]}`}>
      <p className="whitespace-pre-wrap">{message.content}</p>
      <span className="mt-1 block text-right text-[10px] text-muted">{time}</span>
    </div>
  )
}
