export interface AgentProgress {
  name: string
  status: WorkflowStepStatus
}

export interface WorkflowStep {
  id: number
  name: string
  label: string
  status: WorkflowStepStatus
  agents?: AgentProgress[]
  error?: string
}

export type WorkflowStepStatus = 'pending' | 'running' | 'done' | 'failed'

export interface Session {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workdir?: string
  output_files: string[]
  error?: string
  workflow_steps?: WorkflowStep[]
  created_at?: number
  updated_at?: number
}

export type SessionStatus = 'created' | 'running' | 'done' | 'failed' | 'cancelled' | 'awaiting_confirm'

export interface ComposeRequest {
  prompt: string
  plan?: Record<string, unknown>
}

export interface ComposeResponse {
  session_id: string
  status: string
}

export interface StatusResponse {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workflow_steps?: WorkflowStep[]
  output_files: string[]
  error?: string
}

export interface CancelResponse {
  session_id: string
  status: string
}

export interface SessionsResponse {
  sessions: Session[]
}

export interface ResultResponse {
  session_id: string
  output_files: string[]
  workdir: string
}

export interface ChatMessage {
  id: string
  type: 'user' | 'system' | 'error'
  content: string
  timestamp: number
}

export interface OutputFile {
  filename: string
  path: string
  size?: number
}
