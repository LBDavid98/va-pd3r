"""Request/response models for the PD3r API."""

from typing import Any

from pydantic import BaseModel, Field


# --- Session models ---

class CreateSessionResponse(BaseModel):
    session_id: str
    phase: str = "init"
    message: str = "Session created"


class SeedSessionRequest(BaseModel):
    """Request to create a session pre-populated at a specific phase."""
    script_id: str = Field(..., description="Test script ID (e.g. 'program-analyst')")
    phase: str = Field(..., description="Target phase to seed at")


class FESFactorSummary(BaseModel):
    factor_num: int | str
    factor_name: str
    level_code: str
    points: int


class FESEvaluationSummary(BaseModel):
    grade: str
    total_points: int
    factors: list[FESFactorSummary] = []


class SessionState(BaseModel):
    session_id: str
    phase: str
    position_title: str | None = None
    collected_fields: list[str] = []
    current_field: str | None = None
    missing_fields: list[str] = []
    fields_needing_confirmation: list[str] = []
    interview_data_values: dict[str, Any] = {}
    is_supervisor: bool | None = None
    draft_element_count: int = 0
    current_element_name: str | None = None
    should_end: bool = False
    fes_evaluation: FESEvaluationSummary | None = None


# --- Message models ---

class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    field_overrides: dict[str, Any] | None = None


class AgentMessage(BaseModel):
    role: str  # "agent" or "system"
    content: str
    phase: str | None = None
    current_field: str | None = None
    missing_fields: list[str] | None = None


class SendMessageResponse(BaseModel):
    messages: list[AgentMessage]
    phase: str
    session_state: SessionState


# --- Draft models ---

class QACheckSummary(BaseModel):
    """Lightweight QA check result for the frontend."""
    requirement_id: str
    passed: bool
    explanation: str
    severity: str = "critical"  # "critical" | "warning" | "info"
    suggestion: str | None = None


class QAReviewSummary(BaseModel):
    """Lightweight QA review for the frontend."""
    passes: bool
    overall_feedback: str = ""
    checks: list[QACheckSummary] = []
    passed_count: int = 0
    failed_count: int = 0


class DraftElementSummary(BaseModel):
    name: str
    display_name: str
    status: str  # "pending", "draft", "approved", "locked"
    content: str | None = None
    locked: bool = False
    qa_review: QAReviewSummary | None = None


class DraftState(BaseModel):
    session_id: str
    phase: str
    elements: list[DraftElementSummary]


class LLMConfigRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    base_url: str | None = Field(default=None, description="Custom OpenAI-compatible endpoint URL")


class LLMConfigResponse(BaseModel):
    has_key: bool
    base_url: str | None = None


class PatchFieldsRequest(BaseModel):
    field_overrides: dict[str, Any] = Field(..., min_length=1)


class LockElementRequest(BaseModel):
    locked: bool


class RegenerateElementRequest(BaseModel):
    feedback: str = Field(default="", description="Optional feedback for regeneration")


# --- WebSocket models ---

class WSMessage(BaseModel):
    """Message format for WebSocket communication."""
    type: str  # "user_message", "agent_message", "phase_change", "element_update", "error", "ping"
    data: dict = {}


class WSAgentMessage(BaseModel):
    type: str = "agent_message"
    content: str
    phase: str | None = None
    prompt: str | None = None  # The interrupt prompt
    interview_progress: dict | None = None


class WSElementUpdate(BaseModel):
    type: str = "element_update"
    name: str
    status: str
    content: str | None = None
