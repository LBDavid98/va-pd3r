/** TypeScript types mirroring backend Pydantic models (src/api/models.py) */

export type Phase =
  | "init"
  | "interview"
  | "requirements"
  | "drafting"
  | "review"
  | "complete"
  | "unknown"

export type ElementStatus = "pending" | "draft" | "drafted" | "qa_passed" | "approved" | "locked" | "needs_revision"

// --- LLM Config ---

export interface LLMConfigResponse {
  has_key: boolean
  base_url: string | null
}

// --- Session ---

export interface CreateSessionResponse {
  session_id: string
  phase: Phase
  message: string
}

export interface FESFactorSummary {
  factor_num: number | string
  factor_name: string
  level_code: string
  points: number
}

export interface FESEvaluationSummary {
  grade: string
  total_points: number
  factors: FESFactorSummary[]
}

export interface SessionState {
  session_id: string
  phase: Phase
  position_title: string | null
  collected_fields: string[]
  current_field: string | null
  missing_fields: string[]
  fields_needing_confirmation: string[]
  interview_data_values: Record<string, unknown>
  is_supervisor: boolean | null
  draft_element_count: number
  current_element_name: string | null
  should_end: boolean
  fes_evaluation: FESEvaluationSummary | null
}

// --- Messages ---

export interface SendMessageRequest {
  content: string
  field_overrides?: Record<string, unknown>
}

export interface AgentMessage {
  role: "agent" | "system"
  content: string
  phase?: Phase
  current_field?: string
  missing_fields?: string[]
}

export interface SendMessageResponse {
  messages: AgentMessage[]
  phase: Phase
  session_state: SessionState
}

// --- QA ---

export interface QACheckSummary {
  requirement_id: string
  passed: boolean
  explanation: string
  severity: "critical" | "warning" | "info"
  suggestion?: string | null
}

export interface QAReviewSummary {
  passes: boolean
  overall_feedback: string
  checks: QACheckSummary[]
  passed_count: number
  failed_count: number
}

// --- Draft ---

export interface DraftElementSummary {
  name: string
  display_name: string
  status: ElementStatus
  content: string | null
  locked: boolean
  /** User-added notes — included as context on regeneration */
  notes?: string
  /** True if the user hand-edited the content (auto-locks) */
  edited?: boolean
  /** QA review results from backend */
  qa_review?: QAReviewSummary | null
}

export interface DraftState {
  session_id: string
  phase: Phase
  elements: DraftElementSummary[]
}

// --- WebSocket ---

export interface WSIncoming {
  type: "agent_message" | "state_update" | "element_update" | "done" | "stopped" | "error" | "pong"
  data: Record<string, unknown>
}

export interface WSAgentMessage {
  content: string
  phase?: Phase
  prompt?: string
  current_field?: string
  missing_fields?: string[]
}

export interface WSStateUpdate extends Partial<SessionState> {}

export interface WSElementUpdate {
  name: string
  status: ElementStatus
  content?: string
  qa_review?: Record<string, unknown>
}

// --- Chat UI ---

export type ChatMessageType = "normal" | "system"

export interface ChatMessage {
  id: string
  role: "user" | "agent"
  content: string
  timestamp: number
  type?: ChatMessageType
}
