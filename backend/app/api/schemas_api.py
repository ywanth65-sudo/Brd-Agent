"""HTTP request and response schemas for FastAPI endpoints.

Domain models in app.models remain the source of truth; these models define
HTTP-level payload validation and response structuring.
"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.assumption import Assumption
from app.models.project import Project, ProjectStatus
from app.models.question import Question
from app.models.requirement import Requirement
from app.models.validation import ValidationResult


class CreateProjectRequest(BaseModel):
    """Payload to initialize a new BRD generation project."""

    title: Optional[str] = Field(
        default=None,
        description="Optional title. Generated automatically from idea if omitted.",
    )
    idea: str = Field(
        ...,
        min_length=10,
        description="Raw business idea text (minimum 10 characters).",
    )


class CreateProjectResponse(BaseModel):
    """Response returned upon project initialization."""

    model_config = ConfigDict(use_enum_values=False)
    project: Project


class AnalyzeResponse(BaseModel):
    """Response returned from analysis iteration."""

    model_config = ConfigDict(use_enum_values=False)

    project: Project
    requirements: list[Requirement] = Field(default_factory=list)
    validation_result: ValidationResult = Field(default_factory=ValidationResult)
    open_questions: list[Question] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    next_status: ProjectStatus


class AnswerItem(BaseModel):
    """Individual answer submitted for an open clarification question."""

    question_id: str = Field(..., description="ID of the question being answered")
    value: str = Field(..., description="Stakeholder response text")


class SubmitAnswersRequest(BaseModel):
    """Payload to submit answers for open clarification questions."""

    answers: list[AnswerItem] = Field(
        ...,
        min_length=1,
        description="List of question answers to submit and merge.",
    )


class SubmitAnswersResponse(BaseModel):
    """Response returned after merging answers and re-evaluating readiness."""

    model_config = ConfigDict(use_enum_values=False)

    project: Project
    requirements: list[Requirement] = Field(default_factory=list)
    validation_result: ValidationResult = Field(default_factory=ValidationResult)
    open_questions: list[Question] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    next_status: ProjectStatus


class AssumptionDecisionRequest(BaseModel):
    """Payload to accept or reject an explicit assumption."""

    decision: Literal["accepted", "rejected", "ACCEPTED", "REJECTED"] = Field(
        ...,
        description="Review decision ('accepted' or 'rejected').",
    )


class ProjectDetailResponse(BaseModel):
    """Project metadata accompanied by aggregate entity counts."""

    model_config = ConfigDict(use_enum_values=False)

    project: Project
    requirement_count: int = Field(default=0)
    open_question_count: int = Field(default=0)
    assumption_count: int = Field(default=0)
    collaborator_count: int = Field(default=0)
    is_owner: bool = Field(default=True)


class SourceDocumentResponse(BaseModel):
    """Metadata response for an uploaded source document."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Unique document identifier")
    project_id: str = Field(..., description="Associated project identifier")
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="Document type: pdf, docx, or txt")
    file_size_bytes: Optional[int] = Field(
        default=None,
        description="Size of the uploaded file in bytes",
    )
    status: str = Field(..., description="Processing status")
    chunk_count: int = Field(default=0, description="Total extracted chunk count")
    created_at: Optional[str] = Field(
        default=None,
        description="Creation or upload timestamp ISO string",
    )
    uploaded_by: Optional[str] = Field(
        default=None,
        description="UUID of the user who uploaded the document",
    )
    uploader_email: Optional[str] = Field(
        default=None,
        description="Email address of the uploader",
    )


class SourceDocumentListResponse(BaseModel):
    """List container response of uploaded source documents."""

    model_config = ConfigDict(use_enum_values=False)

    items: list[SourceDocumentResponse] = Field(
        default_factory=list,
        description="List of uploaded source documents for project",
    )


ProjectResponse = Project
AssumptionResponse = Assumption


class AnswerResponse(BaseModel):
    """Response representing a recorded question answer with audit attribution."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Unique answer identifier")
    project_id: str = Field(..., description="Associated project ID")
    question_id: str = Field(..., description="ID of the question being answered")
    value: str = Field(..., description="Answer text or selected value")
    answered_at: Optional[str] = Field(default=None, description="Timestamp ISO string")
    answered_by: Optional[str] = Field(default=None, description="UUID of the answerer")
    answerer_email: Optional[str] = Field(default=None, description="Email address of the answerer")


class BRDVersionResponse(BaseModel):
    """Structured response representing a compiled BRD document version."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Unique BRD version identifier")
    project_id: str = Field(..., description="Associated project identifier")
    version_number: int = Field(..., description="Sequential version number")
    title: str = Field(..., description="Document title")
    content_json: dict = Field(..., description="Structured 7-section BRD JSON content")
    status: str = Field(..., description="Generation status (e.g. COMPLETED)")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of generation")


class BRDGenerateResponse(BaseModel):
    """Response returned upon successful BRD compilation and generation."""

    model_config = ConfigDict(use_enum_values=False)

    project: Project
    brd_version: BRDVersionResponse
    download_url: str = Field(..., description="Relative download URL for DOCX artifact")


class ChatMessage(BaseModel):
    """Message item in the conversational clarification interview."""

    model_config = ConfigDict(use_enum_values=False)

    role: str = Field(..., description="Message sender role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")
    timestamp: Optional[str] = Field(default=None, description="Optional timestamp string")


class ChatRequest(BaseModel):
    """Request payload for conversational clarification interview chat."""

    model_config = ConfigDict(use_enum_values=False)

    message: str = Field(..., min_length=1, description="Latest message from user")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior conversation history",
    )


class ChatResponse(BaseModel):
    """Response returned by the conversational clarification assistant."""

    model_config = ConfigDict(use_enum_values=False)

    reply: str = Field(..., description="Conversational reply from the AI assistant")
    answered_question_id: Optional[str] = Field(
        default=None,
        description="ID of the open question resolved by user's message, if any",
    )
    project_status: str = Field(..., description="Current status of the project")
    open_question_count: int = Field(..., description="Number of remaining open clarification questions")
    is_ready_to_generate: bool = Field(..., description="True if project is ready to generate")


class UserProfileResponse(BaseModel):
    """Authenticated user profile metadata."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = Field(default=None, description="User full display name")
    role_title: Optional[str] = Field(default=None, description="User organizational role title")
    avatar_url: Optional[str] = Field(default=None, description="User avatar image URL")


class UserProfileUpdateRequest(BaseModel):
    """Payload to update current user's profile."""

    model_config = ConfigDict(use_enum_values=False)

    full_name: Optional[str] = Field(default=None, description="User full display name")
    role_title: Optional[str] = Field(default=None, description="User organizational role title")
    avatar_url: Optional[str] = Field(default=None, description="User avatar image URL")


class CollaboratorResponse(BaseModel):
    """Team collaborator attached to a project."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Unique collaborator membership ID")
    project_id: str = Field(..., description="Project ID")
    user_id: str = Field(..., description="Collaborator user UUID")
    user_email: str = Field(..., description="Collaborator email address")
    full_name: Optional[str] = Field(default=None, description="Collaborator display name")
    role: str = Field(default="editor", description="Collaborator access role (e.g. editor, viewer)")
    created_at: Optional[str] = Field(default=None, description="Enrollment timestamp ISO string")


class ChatMessageRecord(BaseModel):
    """Stored conversational chat message record."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Unique chat message ID")
    project_id: str = Field(..., description="Project ID")
    sender_id: Optional[str] = Field(default=None, description="User UUID of sender (None for assistant)")
    sender_email: str = Field(..., description="Email address of sender")
    sender_name: Optional[str] = Field(default=None, description="Display name of sender")
    role: str = Field(..., description="Role of sender: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")
    created_at: str = Field(..., description="ISO creation timestamp")


class ChatHistoryResponse(BaseModel):
    """Collection of stored chat messages for a project."""

    model_config = ConfigDict(use_enum_values=False)

    messages: list[ChatMessageRecord] = Field(default_factory=list, description="List of chat messages ordered chronologically")


class InviteCollaboratorRequest(BaseModel):
    """Payload to invite a team collaborator via email."""

    model_config = ConfigDict(use_enum_values=False)

    email: str = Field(..., description="Invitee email address")
    role: Optional[str] = Field(default="editor", description="Collaborator access role")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: Optional[str]) -> str:
        normalized = (value or "editor").strip().lower()
        if normalized not in {"editor", "viewer"}:
            raise ValueError("Role must be either 'editor' or 'viewer'.")
        return normalized


class InvitationResponse(BaseModel):
    """Project invitation metadata record."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(..., description="Invitation UUID")
    project_id: str = Field(..., description="Project ID")
    project_title: Optional[str] = Field(default=None, description="Title of the invited project")
    inviter_email: str = Field(..., description="Email of inviting user")
    invitee_email: str = Field(..., description="Email of invited user")
    role: str = Field(default="editor", description="Collaborator role")
    status: str = Field(default="pending", description="Invitation status (pending, accepted, declined)")
    created_at: str = Field(..., description="ISO creation timestamp")
