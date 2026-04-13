export interface AgentProgress {
  name: string
  status?: WorkflowStepStatus
  model?: string
}

export interface SubStep {
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
  agent?: string
  phase?: string
  timestamp?: number
}

export interface PlanSummary {
  duration: string
  section_structure: string
  orchestration_desc: string
  sf2_status: string
  demo_length: string
}

export interface ConfirmationData {
  phase: 'parse' | 'sample' | 'review'
  title: string
  plan?: Record<string, unknown>
  summary?: PlanSummary
  user_prompt?: string
  sample_file?: string
  review_file?: string
  review?: ReviewData
  iterations?: number
  sample_round?: number
  output_file?: string
}

export interface ReviewData {
  verdict?: 'pass' | 'revise'
  scores?: Record<string, number>
  overall_score?: number
  summary?: string
  issues?: string[]
}

export interface PhaseStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  confirm: boolean
  agents?: AgentProgress[]
  sub_steps?: SubStep[]
}

export interface WorkflowStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  agents?: AgentProgress[]
  sub_steps?: SubStep[]
  error?: string
  confirm?: boolean
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
  profile?: string
}

export interface ComposeResponse {
  session_id: string
  status: string
}

export interface ProfileItem {
  id: string
  display_name: string
  agents: Record<string, string>
}

export interface ProfileListResponse {
  profiles: ProfileItem[]
}

export interface ProfileSaveRequest {
  id: string
  display_name: string
  agents: Record<string, string>
}

export interface StatusResponse {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workflow_steps?: PhaseStep[]
  output_files: string[]
  error?: string
  current_phase?: string
  confirmation_data?: ConfirmationData
  sample_round?: number
  iteration_count?: number
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
  type: 'user' | 'system' | 'error' | 'confirmation'
  content: string
  timestamp: number
  confirmationData?: ConfirmationData
  isActive?: boolean
}

export interface OutputFile {
  filename: string
  path: string
  size?: number
}

// === Settings ===

export interface Settings {
  output_dir: string
  sf2_path: string
  sf2_name: string
  sf2_preset_count: number
  max_iterations: number
  review_threshold: number
  skip_review: boolean
}

export interface SettingsUpdate {
  output_dir?: string
  sf2_path?: string
  max_iterations?: number
  review_threshold?: number
  skip_review?: boolean
}

export interface ProviderInfo {
  alias: string
  model_id: string
  base_url: string
  api_key_masked: string
  is_configured: boolean
}

export interface ProviderList {
  anthropic: ProviderInfo | null
  anthropic_compat: ProviderInfo[]
  openai_compat: ProviderInfo[]
}

export interface ProviderUpdate {
  anthropic_api_key?: string
  anthropic_model?: string
  anthropic_compat?: Record<string, { model_id: string; base_url: string; api_key: string }>
  remove_anthropic_compat?: string[]
  openai_compat?: Record<string, { model_id: string; base_url: string; api_key: string }>
  remove_openai_compat?: string[]
}

export interface AgentInfo {
  name: string
  model_alias: string
  temperature: number
  skills: string[]
  tools: string[]
}

export interface AgentList {
  agents: AgentInfo[]
}

export interface AgentUpdate {
  agents: Record<string, { model_alias: string; temperature: number }>
}

export interface DependencyStatus {
  name: string
  installed: boolean
}

export interface Diagnostics {
  version: string
  uptime_seconds: number
  temp_workdir: string
  temp_session_count: number
  temp_disk_usage_mb: number
  dependencies: DependencyStatus[]
}
