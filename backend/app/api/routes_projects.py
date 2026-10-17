"""FastAPI routes for Project lifecycle, analysis, questions, answers, and assumptions."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import (
    AuthenticatedUser,
    get_current_user,
    get_gemini_client,
    get_llm_client,
    get_repository,
)
from app.api.schemas_api import (
    AnalyzeResponse,
    AssumptionDecisionRequest,
    BRDGenerateResponse,
    BRDVersionResponse,
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    CollaboratorResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    InvitationResponse,
    InviteCollaboratorRequest,
    ProjectDetailResponse,
    SourceDocumentListResponse,
    SourceDocumentResponse,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from app.core.brd_generator import BRDGenerator
from app.core.document_parser import DocumentParser, ParsedChunk, ParsedDocument
from app.core.docx_renderer import render_brd_to_docx
from app.core.merge import merge_answers_into_requirements
from app.core.orchestrator import BRDOrchestrator
from app.core.state_machine import InvalidTransitionError
from app.core.validation_rules import (
    validate_project_completeness,
    validate_requirements,
)
from app.db.repository import ProjectRepository
from app.llm.llm_client import LLMClient, GeminiClient
from app.llm.prompts import (
    build_clarification_chat_prompt,
    ChatTurnEvaluation,
)
from app.models.answer import Answer
from app.models.assumption import Assumption, AssumptionStatus
from app.models.document import SourceChunk, SourceDocument, SourceDocumentStatus
from app.models.project import Project, ProjectStatus
from app.models.question import AnswerFormat, Question
from app.models.requirement import Requirement
from app.models.validation import ValidationResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])
user_router = APIRouter(prefix="/user", tags=["user"])
invitations_router = APIRouter(prefix="/invitations", tags=["invitations"])


def _require_project_access(
    repository: ProjectRepository,
    project_id: str,
    current_user: AuthenticatedUser,
    *,
    write: bool = False,
) -> tuple[Project, str]:
    """Return a project and effective role, enforcing owner/editor/viewer access."""
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if current_user.is_demo:
        return project, "owner"
    if project.owner_id and str(project.owner_id) == str(current_user.user_id):
        return project, "owner"

    collaborators = repository.get_collaborators(project_id)
    membership = next(
        (item for item in collaborators if str(item.get("user_id")) == str(current_user.user_id)),
        None,
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this project.")

    role = str(membership.get("role", "viewer")).lower()
    if write and role != "editor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Viewer access is read-only.")
    return project, role



@user_router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="Get active user profile",
)
@router.get(
    "/user/profile",
    response_model=UserProfileResponse,
    summary="Get active user profile",
)
def get_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> UserProfileResponse:
    """Retrieve the active authenticated user's profile from the database."""
    prof = repository.get_profile(current_user.user_id) if hasattr(repository, "get_profile") else None
    if not prof:
        return UserProfileResponse(
            id=current_user.user_id,
            email=current_user.email,
            full_name=None,
            role_title=None,
            avatar_url=None,
        )
    return UserProfileResponse(
        id=prof["id"],
        email=prof.get("email") or current_user.email,
        full_name=prof.get("full_name"),
        role_title=prof.get("role_title"),
        avatar_url=prof.get("avatar_url"),
    )


@user_router.put(
    "/profile",
    response_model=UserProfileResponse,
    summary="Update active user profile",
)
@router.put(
    "/user/profile",
    response_model=UserProfileResponse,
    summary="Update active user profile",
)
def update_user_profile(
    request: UserProfileUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> UserProfileResponse:
    """Update full_name, role_title, and avatar_url in user's profile."""
    prof = repository.upsert_profile(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=request.full_name,
        role_title=request.role_title,
        avatar_url=request.avatar_url,
    )
    return UserProfileResponse(
        id=prof["id"],
        email=prof.get("email") or current_user.email,
        full_name=prof.get("full_name"),
        role_title=prof.get("role_title"),
        avatar_url=prof.get("avatar_url"),
    )


@router.post(
    "",
    response_model=CreateProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
def create_project(
    request: CreateProjectRequest,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CreateProjectResponse:
    """Initialize a new project in DRAFT status with input_revision=1 and audit owner."""
    title = request.title
    if not title or not title.strip():
        # Derive concise default title from first 7 words of idea
        words = request.idea.strip().split()
        title = " ".join(words[:7]).capitalize()
        if len(words) > 7:
            title += "..."

    try:
        project = repository.create_project(
            title=title,
            idea=request.idea,
            owner_id=None if current_user.is_demo else current_user.user_id,
            owner_email=current_user.email,
        )
        return CreateProjectResponse(project=project)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get(
    "",
    response_model=list[Project],
    summary="List recent projects",
)
def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[Project]:
    """Retrieve recent projects owned by the authenticated user ordered by creation date descending."""
    try:
        return repository.list_projects(
            limit=limit,
            owner_id=None if current_user.is_demo else current_user.user_id,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get project details with counts",
)
def get_project_detail(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProjectDetailResponse:
    """Fetch project details accompanied by counts of requirements, open questions, assumptions, and collaborators."""
    try:
        project, _ = _require_project_access(repository, project_id, current_user)
        requirements = repository.get_requirements(project_id)
        open_questions = repository.get_open_questions(project_id)
        assumptions = repository.get_assumptions(project_id)
        collabs = repository.get_collaborators(project_id) if hasattr(repository, "get_collaborators") else []

        is_owner = current_user.is_demo or (
            project.owner_id is not None
            and str(project.owner_id) == str(current_user.user_id)
        )
        collab_count = len(collabs)
        updated_project = project.model_copy(update={"is_owner": is_owner, "collaborator_count": collab_count})

        return ProjectDetailResponse(
            project=updated_project,
            requirement_count=len(requirements),
            open_question_count=len(open_questions),
            assumption_count=len(assumptions),
            collaborator_count=collab_count,
            is_owner=is_owner,
        )
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/{project_id}/join",
    response_model=Project,
    summary="Join project via share link",
)
def join_project(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Project:
    """Enrolls current authenticated user into project_collaborators and returns the updated project."""
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # Add as collaborator with 'editor' role if not already owner
    if project.owner_id != current_user.user_id:
        repository.add_collaborator(
            project_id=project_id,
            user_id=current_user.user_id,
            user_email=current_user.email,
            role="editor",
        )

    collabs = repository.get_collaborators(project_id) if hasattr(repository, "get_collaborators") else []
    is_owner = (project.owner_id == current_user.user_id)
    return project.model_copy(update={"is_owner": is_owner, "collaborator_count": len(collabs)})


@router.get(
    "/{project_id}/collaborators",
    response_model=list[CollaboratorResponse],
    summary="Get project team collaborators",
)
def get_collaborators(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[CollaboratorResponse]:
    """Retrieve all collaborators enrolled in a project."""
    try:
        _require_project_access(repository, project_id, current_user)
        collabs = repository.get_collaborators(project_id) if hasattr(repository, "get_collaborators") else []
        return [
            CollaboratorResponse(
                id=c["id"],
                project_id=c["project_id"],
                user_id=c["user_id"],
                user_email=c["user_email"],
                full_name=c.get("full_name"),
                role=c.get("role", "editor"),
                created_at=c.get("created_at"),
            )
            for c in collabs
        ]
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.delete(
    "/{project_id}/collaborators/{collaborator_user_id}",
    summary="Remove a collaborator from project",
)
def remove_collaborator(
    project_id: str,
    collaborator_user_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Allows project owner to remove a collaborator."""
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if not current_user.is_demo and (
        not project.owner_id or str(project.owner_id) != str(current_user.user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can remove collaborators.",
        )

    repository.remove_collaborator(project_id, collaborator_user_id)
    return {"status": "removed", "user_id": collaborator_user_id}


@router.post(
    "/{project_id}/sources",
    response_model=SourceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a source document",
)
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
) -> SourceDocumentResponse:
    """Upload and process a source document (PDF, DOCX, TXT, PNG, JPG, JPEG, WEBP), parse chunks, and persist."""
    # 1. Guard against invalid project IDs and enforce editor access
    _require_project_access(repository, project_id, current_user, write=True)
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # 2. Only allow uploading sources if the project is in a valid state
    valid_states = {
        ProjectStatus.DRAFT,
        ProjectStatus.ANALYZING,
        ProjectStatus.AWAITING_CLARIFICATION,
        ProjectStatus.READY_TO_GENERATE,
        ProjectStatus.GENERATED,
    }
    if project.status not in valid_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot upload sources when project is in status '{project.status.value}'. "
                f"Project must be in DRAFT, ANALYZING, AWAITING_CLARIFICATION, or READY_TO_GENERATE."
            ),
        )

    # 3. Read file and enforce 10MB limit
    try:
        content_bytes = await file.read()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {err}",
        )

    if len(content_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of 10MB ({len(content_bytes)} bytes uploaded).",
        )

    if not content_bytes or len(content_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 4. Parse and chunk file using DocumentParser (with multimodal vision if image)
    filename = file.filename or "uploaded_document.txt"
    parser = DocumentParser()
    suffix = Path(filename).suffix.lower().lstrip(".")
    try:
        if suffix in {"png", "jpg", "jpeg", "webp"}:
            if current_user.is_demo:
                parser.detect_and_validate_format(filename, content_bytes)
                parsed_doc = ParsedDocument(
                    filename=filename,
                    file_type="image",
                    raw_text=(
                        f"Image source uploaded: {filename}. "
                        "Vision transcription is unavailable in demo mode until "
                        "GROQ_API_KEY is configured."
                    ),
                    chunks=[
                        ParsedChunk(
                            chunk_index=0,
                            content=(
                                f"Image source uploaded: {filename}. "
                                "Vision transcription is unavailable in demo mode "
                                "until GROQ_API_KEY is configured."
                            ),
                            page_number=1,
                            metadata={"file_type": "image", "mime_type": file.content_type or ""},
                        )
                    ],
                    total_pages=1,
                )
            else:
                parsed_doc = parser.parse_image(filename, content_bytes, llm_client)
        else:
            parsed_doc = parser.parse_file(filename, content_bytes)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse document: {err}",
        )
    except Exception as err:
        logger.error("Unexpected error parsing file '%s': %s", filename, err)
        if "GROQ_API_KEY" in str(err) or "Groq" in str(err):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(err),
            ) from err
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse document: {err}",
        )

    # 5. Create SourceDocument and SourceChunks
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    source_doc = SourceDocument(
        id=doc_id,
        project_id=project_id,
        filename=filename,
        file_type=parsed_doc.file_type,  # type: ignore[arg-type]
        status=SourceDocumentStatus.READY,
        storage_path=f"projects/{project_id}/sources/{filename}",
        error_message=None,
        file_size_bytes=len(content_bytes),
        created_at=now.isoformat(),
        uploaded_by=None if current_user.is_demo else current_user.user_id,
        uploader_email=current_user.email,
    )

    source_chunks: list[SourceChunk] = []
    for p_chunk in parsed_doc.chunks:
        # Guarantee a valid UUID for chunk id
        candidate_uuid = getattr(p_chunk, "id", None) or p_chunk.metadata.get("uuid")
        try:
            chunk_uuid = str(uuid.UUID(str(candidate_uuid)))
        except (ValueError, TypeError, AttributeError):
            chunk_uuid = str(uuid.uuid4())

        chunk_label = (
            p_chunk.metadata.get("chunk_label")
            or p_chunk.metadata.get("id")
            or f"CHUNK-{doc_id[:8]}-{p_chunk.chunk_index}"
        )
        source_chunks.append(
            SourceChunk(
                id=chunk_uuid,
                document_id=doc_id,
                project_id=project_id,
                text=p_chunk.content,
                page_number=p_chunk.page_number,
                heading=p_chunk.metadata.get("heading") or chunk_label,
                chunk_index=p_chunk.chunk_index,
                chunk_label=chunk_label,
            )
        )

    # 6. Persist models in repository
    try:
        saved_doc = repository.save_source_document(source_doc)
        if source_chunks:
            repository.save_source_chunks(source_chunks)
        repository.increment_input_revision(project_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    created_at_val = getattr(saved_doc, "created_at", None)
    if isinstance(created_at_val, datetime):
        created_at_str = created_at_val.isoformat()
    elif created_at_val:
        created_at_str = str(created_at_val)
    else:
        created_at_str = now.isoformat()

    return SourceDocumentResponse(
        id=saved_doc.id,
        project_id=saved_doc.project_id,
        filename=saved_doc.filename,
        file_type=saved_doc.file_type,
        file_size_bytes=saved_doc.file_size_bytes or len(content_bytes),
        status=saved_doc.status.value if isinstance(saved_doc.status, SourceDocumentStatus) else str(saved_doc.status),
        chunk_count=len(source_chunks),
        created_at=created_at_str,
        uploaded_by=saved_doc.uploaded_by,
        uploader_email=saved_doc.uploader_email,
    )


@router.get(
    "/{project_id}/sources",
    response_model=SourceDocumentListResponse,
    summary="List uploaded source documents for a project",
)
def get_source_documents(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SourceDocumentListResponse:
    """Retrieve all uploaded source documents for a project along with chunk counts."""
    try:
        _require_project_access(repository, project_id, current_user)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    try:
        docs = repository.get_source_documents_by_project(project_id)
        all_chunks = repository.get_source_chunks_by_project(project_id)
        chunk_counts: dict[str, int] = {}
        for c in all_chunks:
            chunk_counts[c.document_id] = chunk_counts.get(c.document_id, 0) + 1

        items = []
        for d in docs:
            c_at = getattr(d, "created_at", None)
            created_at_str = c_at.isoformat() if isinstance(c_at, datetime) else (str(c_at) if c_at else None)
            items.append(
                SourceDocumentResponse(
                    id=d.id,
                    project_id=d.project_id,
                    filename=d.filename,
                    file_type=d.file_type,
                    file_size_bytes=getattr(d, "file_size_bytes", None),
                    status=d.status.value if isinstance(d.status, SourceDocumentStatus) else str(d.status),
                    chunk_count=chunk_counts.get(d.id, 0),
                    created_at=created_at_str,
                )
            )
        return SourceDocumentListResponse(items=items)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/{project_id}/analyze",
    response_model=AnalyzeResponse,
    summary="Run AI analysis and validation loop on project",
)
def analyze_project(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    gemini_client: GeminiClient = Depends(get_gemini_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """Transition project into ANALYZING, execute extraction and validation, and transition to next state."""
    # 1. Load project and validate state transition into ANALYZING
    project, _ = _require_project_access(repository, project_id, current_user, write=True)

    # Determine permitted event leading to ANALYZING
    if project.status == ProjectStatus.DRAFT:
        analyze_event = "analyze"
    elif project.status == ProjectStatus.GENERATED:
        analyze_event = "answer_or_source_changed"
    elif project.status == ProjectStatus.AWAITING_CLARIFICATION:
        analyze_event = "answers_submitted"
    elif project.status == ProjectStatus.ANALYZING:
        analyze_event = "analyze"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot run analysis from status '{project.status.value}'. "
                f"Project must be in DRAFT, AWAITING_CLARIFICATION, or GENERATED."
            ),
        )

    try:
        # Move state to ANALYZING
        if project.status != ProjectStatus.ANALYZING:
            project = repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.ANALYZING,
                event=analyze_event,
            )

        # 2. Load historical context and source document chunks
        existing_reqs = repository.get_requirements(project_id)
        all_questions = repository.get_all_questions(project_id)
        all_answers = repository.get_answers(project_id)
        already_asked_paths = repository.get_already_asked_field_paths(project_id)
        chunks = repository.get_source_chunks_by_project(project_id)

        # Ensure project has either idea text or uploaded source chunks
        has_idea = bool(project.idea and project.idea.strip())
        if not has_idea and not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project has neither idea text nor uploaded source documents to analyze.",
            )

        # 3. Execute AI Core Loop orchestrator
        orchestrator = BRDOrchestrator(gemini_client=gemini_client)
        workflow_result = orchestrator.run_analysis(
            idea_text=project.idea if has_idea else None,
            existing_requirements=existing_reqs,
            answered_questions=all_questions,
            answers=all_answers,
            already_asked_field_paths=already_asked_paths,
            project_id=project_id,
            chunks=chunks,
        )

        # 4. Persist newly extracted and validated entities
        saved_reqs = repository.save_requirements(project_id, workflow_result.requirements)
        saved_qs = repository.save_questions(project_id, workflow_result.open_questions)
        saved_asms = repository.save_assumptions(project_id, workflow_result.assumptions)
        repository.save_validation_issues(project_id, workflow_result.validation_result)

        # 5. Transition ANALYZING to final outcome (AWAITING_CLARIFICATION or READY_TO_GENERATE)
        if workflow_result.validation_result.has_blockers:
            project = repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.AWAITING_CLARIFICATION,
                event="blocking_gaps_found",
            )
        else:
            project = repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.READY_TO_GENERATE,
                event="no_blocking_gaps",
            )

        open_questions = repository.get_open_questions(project_id)

        return AnalyzeResponse(
            project=project,
            requirements=saved_reqs,
            validation_result=workflow_result.validation_result,
            open_questions=open_questions,
            assumptions=saved_asms,
            next_status=project.status,
        )
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except HTTPException:
        raise
    except Exception as err:
        err_msg = str(err)
        if (
            "GROQ_API_KEY" in err_msg
            or "Groq" in err_msg
            or "groq" in str(type(err)).lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Groq API failure during analysis: {err_msg}",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)


@router.get(
    "/{project_id}/requirements",
    response_model=list[Requirement],
    summary="Get all project requirements",
)
def get_requirements(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[Requirement]:
    """Retrieve all requirements currently captured for the project."""
    try:
        _require_project_access(repository, project_id, current_user)
        return repository.get_requirements(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get(
    "/{project_id}/questions",
    response_model=list[Question],
    summary="Get open clarification questions",
)
def get_open_questions(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[Question]:
    """Retrieve open clarification questions for a project ordered by priority descending."""
    try:
        _require_project_access(repository, project_id, current_user)
        return repository.get_open_questions(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/{project_id}/answers",
    response_model=SubmitAnswersResponse,
    summary="Submit answers to clarification questions and re-analyze",
)
def submit_answers(
    project_id: str,
    request: SubmitAnswersRequest,
    repository: ProjectRepository = Depends(get_repository),
    gemini_client: LLMClient = Depends(get_gemini_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SubmitAnswersResponse:
    """Submit answers, increment input_revision, transition via answers_submitted, and re-run analysis."""
    _require_project_access(repository, project_id, current_user, write=True)
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    # Enforce state constraint
    if project.status != ProjectStatus.AWAITING_CLARIFICATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Answers can only be submitted when project status is AWAITING_CLARIFICATION. "
                f"Current status is '{project.status.value}'."
            ),
        )

    try:
        # 1. Create and persist Answer models with user audit attribution
        now = datetime.now(timezone.utc)
        answer_models = [
            Answer(
                id=f"ANS-{uuid.uuid4().hex[:6].upper()}",
                project_id=project_id,
                question_id=item.question_id,
                value=item.value,
                answered_at=now,
                answered_by=current_user.user_id,
                answerer_email=current_user.email,
            )
            for item in request.answers
        ]
        repository.save_answers(project_id, answer_models)

        # 2. Increment input revision
        repository.increment_input_revision(project_id)

        # 3. Transition back to ANALYZING via answers_submitted
        project = repository.set_status_with_transition(
            project_id=project_id,
            new_status=ProjectStatus.ANALYZING,
            event="answers_submitted",
        )

        # 4. Load full updated state, source chunks, and re-run orchestrator
        existing_reqs = repository.get_requirements(project_id)
        all_questions = repository.get_all_questions(project_id)
        all_answers = repository.get_answers(project_id)
        already_asked_paths = repository.get_already_asked_field_paths(project_id)
        chunks = repository.get_source_chunks_by_project(project_id)

        orchestrator = BRDOrchestrator(gemini_client=gemini_client)
        workflow_result = orchestrator.run_analysis(
            idea_text=project.idea,
            existing_requirements=existing_reqs,
            answered_questions=all_questions,
            answers=all_answers,
            already_asked_field_paths=already_asked_paths,
            project_id=project_id,
            chunks=chunks,
        )

        # 5. Persist merged and re-evaluated findings
        saved_reqs = repository.save_requirements(project_id, workflow_result.requirements)
        saved_qs = repository.save_questions(project_id, workflow_result.open_questions)
        saved_asms = repository.save_assumptions(project_id, workflow_result.assumptions)
        repository.save_validation_issues(project_id, workflow_result.validation_result)

        # 6. Transition to next status
        if workflow_result.validation_result.has_blockers:
            project = repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.AWAITING_CLARIFICATION,
                event="blocking_gaps_found",
            )
        else:
            project = repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.READY_TO_GENERATE,
                event="no_blocking_gaps",
            )

        open_questions = repository.get_open_questions(project_id)

        return SubmitAnswersResponse(
            project=project,
            requirements=saved_reqs,
            validation_result=workflow_result.validation_result,
            open_questions=open_questions,
            assumptions=saved_asms,
            next_status=project.status,
        )
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except HTTPException:
        raise
    except Exception as err:
        err_msg = str(err)
        if "gemini" in str(type(err)).lower() or "google" in str(type(err)).lower():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini API failure during re-analysis: {err_msg}",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)


@router.post(
    "/{project_id}/chat",
    response_model=ChatResponse,
    summary="Interactive conversational clarification interview",
)
def clarification_chat(
    project_id: str,
    request: ChatRequest,
    repository: ProjectRepository = Depends(get_repository),
    gemini_client: LLMClient = Depends(get_gemini_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatResponse:
    """Conversational interview mode with a Senior Business Analyst / Requirements Engineer.

    Provides the assistant with full project context (idea, requirements, open questions, source chunks).
    If the user's message provides the answer to an open question:
      - Automatically saves an Answer stamped with the current user's ID and email.
      - Merges the answer into requirements and updates trace_refs.
      - Re-run validation rules. If zero blockers remain, transitions project status to READY_TO_GENERATE.
    Otherwise, answers conversationally and prompts for the next prioritized clarification gap.
    """
    _require_project_access(repository, project_id, current_user, write=True)
    try:
        project = repository.get_project(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id '{project_id}' not found.",
        )

    try:
        # 1. Load full project context
        requirements = repository.get_requirements(project_id)
        open_questions = repository.get_open_questions(project_id)
        chunks = repository.get_source_chunks_by_project(project_id)

        # 2. Format sender identity for collaborative interview grounding
        sender_prof = (
            repository.get_profile(current_user.user_id)
            if hasattr(repository, "get_profile") and not current_user.is_demo
            else None
        )
        sender_name = (sender_prof.get("full_name") if sender_prof else None) or current_user.email or "Stakeholder"
        role_title = (sender_prof.get("role_title") if sender_prof else None) or "Team Member"
        sender_prefixed_message = f"[Sender: {sender_name} ({role_title})]: {request.message}"

        # 3. Build prompt and evaluate chat turn with LLM
        prompt = build_clarification_chat_prompt(
            project=project,
            requirements=requirements,
            open_questions=open_questions,
            history=request.history,
            new_message=sender_prefixed_message,
            chunks=chunks,
        )

        try:
            chat_eval = gemini_client.generate_structured(prompt, ChatTurnEvaluation)
        except Exception as err:
            logger.error("Failed to generate chat evaluation from LLM: %s", err)
            chat_eval = ChatTurnEvaluation(
                answered_question_id=None,
                extracted_answer=None,
                reply="I'm having trouble processing your response right now. Could you please clarify your answer?",
            )

        answered_qid = chat_eval.answered_question_id
        extracted_val = chat_eval.extracted_answer or request.message

        target_question = next((q for q in open_questions if q.id == answered_qid), None) if answered_qid else None

        # 3. If an open question was answered, save answer, merge requirements, and re-validate
        if target_question and extracted_val:
            now = datetime.now(timezone.utc)
            answer = Answer(
                id=f"ANS:{uuid.uuid4().hex[:6].upper()}",
                project_id=project_id,
                question_id=target_question.id,
                value=extracted_val,
                answered_at=now,
                answered_by=current_user.user_id,
                answerer_email=current_user.email,
            )
            repository.save_answer(project_id, answer)

            all_questions = repository.get_all_questions(project_id)
            all_answers = repository.get_answers(project_id)
            merged_reqs = merge_answers_into_requirements(
                requirements=requirements,
                questions=all_questions,
                answers=all_answers,
            )
            repository.save_requirements(project_id, merged_reqs)

            # Re-run validation rules
            req_val = validate_requirements(merged_reqs)
            comp_val = validate_project_completeness(merged_reqs)
            combined_issues = req_val.issues + comp_val.issues
            val_result = ValidationResult(issues=combined_issues)
            repository.save_validation_issues(project_id, val_result)

            refreshed_open_questions = repository.get_open_questions(project_id)
            has_zero_blockers = (not val_result.has_blockers) and (len(refreshed_open_questions) == 0)

            if has_zero_blockers:
                try:
                    if project.status == ProjectStatus.AWAITING_CLARIFICATION:
                        project = repository.set_status_with_transition(
                            project_id=project_id,
                            new_status=ProjectStatus.ANALYZING,
                            event="answers_submitted",
                        )
                        project = repository.set_status_with_transition(
                            project_id=project_id,
                            new_status=ProjectStatus.READY_TO_GENERATE,
                            event="no_blocking_gaps",
                        )
                    elif project.status == ProjectStatus.ANALYZING:
                        project = repository.set_status_with_transition(
                            project_id=project_id,
                            new_status=ProjectStatus.READY_TO_GENERATE,
                            event="no_blocking_gaps",
                        )
                    elif project.status == ProjectStatus.DRAFT:
                        project = repository.set_status_with_transition(
                            project_id=project_id,
                            new_status=ProjectStatus.ANALYZING,
                            event="analyze",
                        )
                        project = repository.set_status_with_transition(
                            project_id=project_id,
                            new_status=ProjectStatus.READY_TO_GENERATE,
                            event="no_blocking_gaps",
                        )
                except Exception as exc:
                    logger.warning("Could not transition project status: %s", exc)
        else:
            answered_qid = None

        final_open_questions = repository.get_open_questions(project_id)
        current_status_val = project.status.value if hasattr(project.status, "value") else str(project.status)

        # Persist conversation turn in database
        if hasattr(repository, "save_chat_message"):
            sender_full_name = (sender_prof.get("full_name") if sender_prof else None) or sender_name
            repository.save_chat_message(
                project_id=project_id,
                sender_id=current_user.user_id,
                sender_email=current_user.email,
                sender_name=sender_full_name,
                role="user",
                content=request.message,
            )
            repository.save_chat_message(
                project_id=project_id,
                sender_id=None,
                sender_email="ai@brdagent.local",
                sender_name="BRD Assistant",
                role="assistant",
                content=chat_eval.reply,
            )

        return ChatResponse(
            reply=chat_eval.reply,
            answered_question_id=answered_qid,
            project_status=current_status_val,
            open_question_count=len(final_open_questions),
            is_ready_to_generate=(project.status == ProjectStatus.READY_TO_GENERATE),
        )

    except HTTPException:
        raise
    except Exception as err:
        logger.error("Error during clarification chat: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clarification chat error: {err}",
        )


@router.get(
    "/{project_id}/chat/history",
    response_model=ChatHistoryResponse,
    summary="Get chronological chat history for project",
)
def get_project_chat_history(
    project_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> ChatHistoryResponse:
    """Retrieve full chronological chat history for a project."""
    _require_project_access(repository, project_id, current_user)
    raw_msgs = (
        repository.get_chat_history(project_id)
        if hasattr(repository, "get_chat_history")
        else []
    )
    records = [
        ChatMessageRecord(
            id=str(m.get("id")),
            project_id=str(m.get("project_id")),
            sender_id=m.get("sender_id"),
            sender_email=m.get("sender_email") or "",
            sender_name=m.get("sender_name"),
            role=m.get("role") or "user",
            content=m.get("content") or "",
            created_at=m.get("created_at") or "",
        )
        for m in raw_msgs
    ]
    return ChatHistoryResponse(messages=records)


# ----------------------------------------------------------------------
# Project Invitations Routes
# ----------------------------------------------------------------------


@router.post(
    "/{project_id}/invitations",
    response_model=InvitationResponse,
    summary="Invite a team collaborator via email",
)
def invite_collaborator(
    project_id: str,
    request: InviteCollaboratorRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> InvitationResponse:
    """Send an email invitation to collaborate on a project (owner-only)."""
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id '{project_id}' not found.",
        )

    # Guard: only project owners can invite
    if not current_user.is_demo and (
        not project.owner_id or str(project.owner_id) != str(current_user.user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can invite collaborators.",
        )

    clean_email = request.email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.rsplit("@", 1)[-1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address provided for invitation.",
        )

    inv = repository.create_invitation(
        project_id=project_id,
        inviter_id=current_user.user_id,
        inviter_email=current_user.email,
        invitee_email=clean_email,
        role=(request.role or "editor").strip().lower(),
    )
    return InvitationResponse(
        id=str(inv.get("id")),
        project_id=str(inv.get("project_id")),
        project_title=inv.get("project_title") or project.title,
        inviter_email=inv.get("inviter_email") or current_user.email,
        invitee_email=inv.get("invitee_email") or clean_email,
        role=inv.get("role") or "editor",
        status=inv.get("status") or "pending",
        created_at=inv.get("created_at") or datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/{project_id}/invitations",
    response_model=list[InvitationResponse],
    summary="List persisted project invitations",
)
def get_project_invitations(
    project_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> list[InvitationResponse]:
    """List invitations for project owners; do not fabricate client-side records."""
    project, _ = _require_project_access(repository, project_id, current_user)
    if not current_user.is_demo and project.owner_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the project owner can view invitations.")
    raw_invs = repository.get_project_invitations(project_id)
    return [
        InvitationResponse(
            id=str(inv.get("id")),
            project_id=str(inv.get("project_id")),
            project_title=inv.get("project_title") or project.title,
            inviter_email=inv.get("inviter_email") or current_user.email,
            invitee_email=inv.get("invitee_email") or "",
            role=inv.get("role") or "editor",
            status=inv.get("status") or "pending",
            created_at=inv.get("created_at") or "",
        )
        for inv in raw_invs
    ]


@user_router.get(
    "/invitations",
    response_model=list[InvitationResponse],
    summary="Get pending project invitations for active user",
)
@router.get(
    "/user/invitations",
    response_model=list[InvitationResponse],
    summary="Get pending project invitations for active user",
)
def get_user_invitations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> list[InvitationResponse]:
    """Retrieve all pending project invitations addressed to the active user's email."""
    raw_invs = (
        repository.get_pending_invitations_for_email(current_user.email)
        if hasattr(repository, "get_pending_invitations_for_email")
        else []
    )
    return [
        InvitationResponse(
            id=str(inv.get("id")),
            project_id=str(inv.get("project_id")),
            project_title=inv.get("project_title"),
            inviter_email=inv.get("inviter_email") or "",
            invitee_email=inv.get("invitee_email") or current_user.email,
            role=inv.get("role") or "editor",
            status=inv.get("status") or "pending",
            created_at=inv.get("created_at") or "",
        )
        for inv in raw_invs
    ]


@invitations_router.post(
    "/{invitation_id}/accept",
    response_model=Project,
    summary="Accept a project invitation",
)
@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=Project,
    summary="Accept a project invitation",
)
def accept_project_invitation(
    invitation_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_repository),
) -> Project:
    """Accept an email invitation and add the active user as an editor collaborator."""
    try:
        inv = repository.accept_invitation(
            invitation_id=invitation_id,
            user_id=current_user.user_id,
            user_email=current_user.email,
        )
    except ValueError as exc:
        err_msg = str(exc)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "not match" in err_msg.lower() or "not authorized" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

    project_id = inv.get("project_id")
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id '{project_id}' not found.",
        )

    # Calculate collaborators and ownership
    collabs = (
        repository.get_collaborators(project_id)
        if hasattr(repository, "get_collaborators")
        else []
    )
    is_owner = (project.owner_id is not None) and (
        str(project.owner_id) == str(current_user.user_id)
    )
    return project.model_copy(update={"is_owner": is_owner, "collaborator_count": len(collabs)})



@router.get(
    "/{project_id}/assumptions",
    response_model=list[Assumption],
    summary="Get all project assumptions",
)
def get_assumptions(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[Assumption]:
    """Retrieve all assumptions proposed or accepted for the project."""
    try:
        _require_project_access(repository, project_id, current_user)
        return repository.get_assumptions(project_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/{project_id}/assumptions/{assumption_id}/decision",
    response_model=Assumption,
    summary="Accept or reject a proposed assumption",
)
def decide_assumption(
    project_id: str,
    assumption_id: str,
    request: AssumptionDecisionRequest,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Assumption:
    """Accept or reject an assumption, updating revision, recording reviewer audit, and triggering question on rejection."""
    project, _ = _require_project_access(repository, project_id, current_user, write=True)

    decision_str = request.decision.lower()
    new_status = (
        AssumptionStatus.ACCEPTED
        if decision_str == "accepted"
        else AssumptionStatus.REJECTED
    )

    now = datetime.now(timezone.utc)
    try:
        updated_asm = repository.update_assumption_status(
            project_id=project_id,
            assumption_id=assumption_id,
            status=new_status,
            reviewed_by=current_user.user_id,
            reviewer_email=current_user.email,
            reviewed_at=now,
        )
        repository.increment_input_revision(project_id)

        # If rejected, create an open question to capture stakeholder input
        if decision_str == "rejected":
            new_question = Question(
                id=f"Q-ASM-{uuid.uuid4().hex[:6].upper()}",
                project_id=project_id,
                field_path=f"assumptions[{assumption_id}]",
                question_text=(
                    f"The assumption was rejected: '{updated_asm.statement}'. "
                    f"What is the correct requirement or rule that should apply?"
                ),
                why_it_matters=(
                    f"Replacing rejected assumption with verified stakeholder rule "
                    f"(Original rationale: {updated_asm.rationale})."
                ),
                answer_format=AnswerFormat.TEXT,
                options=None,
                impact=2,
                gap_confidence=0.9,
                priority=1.8,
                status="open",
                created_at=datetime.now(timezone.utc),
            )
            repository.save_questions(project_id, [new_question])

            # If project was READY_TO_GENERATE, move back to AWAITING_CLARIFICATION
            if project.status == ProjectStatus.READY_TO_GENERATE:
                repository.set_status_with_transition(
                    project_id=project_id,
                    new_status=ProjectStatus.AWAITING_CLARIFICATION,
                    event="assumption_rejected",
                )

        return updated_asm
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/{project_id}/generate",
    response_model=BRDGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate final BRD document artifact and DOCX export",
)
def generate_brd(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    gemini_client: GeminiClient = Depends(get_gemini_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BRDGenerateResponse:
    """Compile structured BRD JSON, enforce quality checks, render DOCX, and persist version."""
    project, _ = _require_project_access(repository, project_id, current_user, write=True)

    # Guard: Generation is permitted when project status is READY_TO_GENERATE or recovering from FAILED (or already GENERATING)
    if project.status not in (ProjectStatus.READY_TO_GENERATE, ProjectStatus.FAILED, ProjectStatus.GENERATING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Generation is only allowed when project status is READY_TO_GENERATE. "
                f"Current status is '{project.status.value}'. Please resolve all blockers first."
            ),
        )

    # If recovering from FAILED, transition via retry to previous valid state first
    if project.status == ProjectStatus.FAILED:
        project = repository.set_status_with_transition(
            project_id=project_id,
            new_status=ProjectStatus.READY_TO_GENERATE,
            event="retry",
            reason="Recovering from failed state to retry generation",
        )

    # Transition 1: Call repository.set_status_with_transition(project_id, ProjectStatus.GENERATING, reason="Starting BRD compilation")
    if project.status != ProjectStatus.GENERATING:
        project = repository.set_status_with_transition(
            project_id=project_id,
            new_status=ProjectStatus.GENERATING,
            event="generate",
            reason="Starting BRD compilation",
        )

    try:
        # 2. Fetch all project entities
        requirements = repository.get_requirements(project_id)
        assumptions = repository.get_assumptions(project_id)
        source_docs = repository.get_source_documents_by_project(project_id)

        # 3. Apply traceability grounding fallback for requirements derived from initial idea or linked assumptions
        linked_asm_map: dict[str, list[str]] = {}
        for asm in assumptions:
            for rid in asm.linked_requirement_ids:
                linked_asm_map.setdefault(rid, []).append(asm.id)

        updated_reqs: list[Requirement] = []
        reqs_modified = False
        for req in requirements:
            curr_traces = list(req.trace_refs or [])
            if req.id in linked_asm_map:
                for aid in linked_asm_map[req.id]:
                    asm_ref = f"ASSUMPTION:{aid}"
                    if asm_ref not in curr_traces:
                        curr_traces.append(asm_ref)

            is_explicit_ungrounded = "ungrounded" in req.id.lower() or "ungrounded" in req.title.lower()
            if not curr_traces and not req.source_chunk_ids and project.idea and not is_explicit_ungrounded:
                curr_traces.append("IDEA")

            if curr_traces != req.trace_refs:
                req = req.model_copy(update={"trace_refs": curr_traces})
                reqs_modified = True
            updated_reqs.append(req)

        if reqs_modified:
            requirements = repository.save_requirements(project_id, updated_reqs)
        else:
            requirements = updated_reqs

        # 4. Deterministic Quality & Traceability Check
        generator = BRDGenerator(gemini_client=gemini_client)
        quality_passed, ungrounded_ids = generator.check_traceability_quality(
            requirements, assumptions=assumptions
        )
        if not quality_passed:
            err_msg = (
                f"Traceability check failed: {len(ungrounded_ids)} ungrounded requirement(s) found "
                f"({', '.join(ungrounded_ids)}). Every requirement must have trace citations."
            )
            repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.FAILED,
                event="generation_or_quality_failed",
                last_error=err_msg,
                reason="Quality check failed: ungrounded requirements",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err_msg,
            )

        # 5. Determine next sequential version number
        latest_ver = repository.get_latest_brd_version(project_id)
        next_version_num = (latest_ver.version + 1) if latest_ver else 1

        # 6. Compile structured BRD JSON & Render DOCX bytes
        brd_version = generator.compile_brd(
            project=project,
            requirements=requirements,
            assumptions=assumptions,
            source_documents=source_docs,
            version_number=next_version_num,
            strict_quality=True,
        )

        docx_bytes = render_brd_to_docx(brd_version.content_json)
        brd_version.docx_bytes = docx_bytes

        # 7. Persist compiled BRD version
        saved_ver = repository.save_brd_version(brd_version)

        # Transition 2: Call repository.set_status_with_transition(project_id, ProjectStatus.COMPLETED, reason="BRD generation succeeded")
        project = repository.set_status_with_transition(
            project_id=project_id,
            new_status=ProjectStatus.COMPLETED,
            event="quality_passed",
            reason="BRD generation succeeded",
        )

        created_at_str = (
            saved_ver.generated_at.isoformat()
            if saved_ver.generated_at
            else datetime.now(timezone.utc).isoformat()
        )
        brd_resp = BRDVersionResponse(
            id=saved_ver.id,
            project_id=saved_ver.project_id,
            version_number=saved_ver.version_number,
            title=saved_ver.title or project.title,
            content_json=saved_ver.content_json,
            status=saved_ver.status or "COMPLETED",
            created_at=created_at_str,
        )

        return BRDGenerateResponse(
            project=project,
            brd_version=brd_resp,
            download_url=f"/projects/{project_id}/brd/download",
        )
    except HTTPException:
        raise
    except Exception as exc:
        err_text = str(exc)
        logger.error("BRD generation failed for project '%s': %s", project_id, exc)
        try:
            repository.set_status_with_transition(
                project_id=project_id,
                new_status=ProjectStatus.FAILED,
                event="generation_or_quality_failed",
                last_error=err_text,
                reason="BRD generation failed",
            )
        except Exception as trans_err:
            logger.error("Failed to transition project '%s' to FAILED: %s", project_id, trans_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"BRD generation failed: {err_text}",
        ) from exc


@router.get(
    "/{project_id}/brd",
    response_model=BRDVersionResponse,
    summary="Get latest generated BRD document version",
)
def get_latest_brd(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BRDVersionResponse:
    """Retrieve the latest compiled BRD version metadata and structured JSON content."""
    try:
        project, _ = _require_project_access(repository, project_id, current_user)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    latest_version = repository.get_latest_brd_version(project_id)
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generated BRD version exists for project '{project_id}'.",
        )

    created_at_str = (
        latest_version.generated_at.isoformat()
        if latest_version.generated_at
        else datetime.now(timezone.utc).isoformat()
    )
    return BRDVersionResponse(
        id=latest_version.id,
        project_id=latest_version.project_id,
        version_number=latest_version.version_number,
        title=latest_version.title or project.title,
        content_json=latest_version.content_json,
        status=latest_version.status or "COMPLETED",
        created_at=created_at_str,
    )


@router.get(
    "/{project_id}/brd/download",
    summary="Download latest generated BRD as a Microsoft Word (.docx) document",
)
def download_brd_docx(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    """Export and stream the latest BRD version formatted as a clean Microsoft Word document."""
    try:
        project, _ = _require_project_access(repository, project_id, current_user)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    latest_version = repository.get_latest_brd_version(project_id)
    if not latest_version:
        preview_requirements = repository.get_requirements(project_id)
        preview_sources = repository.get_source_documents_by_project(project_id)
        if not current_user.is_demo or not preview_requirements and not preview_sources:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No generated BRD version exists for project '{project_id}'.",
            )

        # Demo mode should remain browsable even when AI generation has not run.
        # Build a preview from the currently persisted project data.
        preview_version = 1
        preview_content = {
            "title": project.title,
            "version": preview_version,
            "input_revision": project.input_revision,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quality_check_passed": False,
            "quality_report": {
                "total_requirements": len(preview_requirements),
                "grounded_count": 0,
                "ungrounded_count": 0,
                "ungrounded_requirement_ids": [],
            },
            "executive_summary": project.idea,
            "project_objectives": [project.idea],
            "scope": {"in_scope": [], "out_of_scope": []},
            "stakeholders_and_personas": [],
            "functional_requirements": [],
            "nonfunctional_requirements": [],
            "constraints": [],
            "assumptions": [],
            "dependencies": [],
            "traceability_matrix": [],
            "business_requirements": [],
            "open_questions": [],
            "source_documents": [
                {"id": source.id, "filename": source.filename, "file_type": source.file_type}
                for source in preview_sources
            ],
            "traceability_note": "Demo preview generated from the current project workspace.",
        }
        docx_bytes = render_brd_to_docx(preview_content)
        clean_title = project.title.replace(" ", "_")
        filename = f"BRD_{clean_title}_preview.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    docx_bytes = latest_version.docx_bytes
    if not docx_bytes:
        docx_bytes = render_brd_to_docx(latest_version.content_json)

    clean_title = project.title.replace(" ", "_")
    filename = f"BRD_{clean_title}_v{latest_version.version_number}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{project_id}/retry",
    response_model=Project,
    summary="Recover from FAILED status back to previous valid state",
)
def retry_project(
    project_id: str,
    repository: ProjectRepository = Depends(get_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Project:
    """Recover from FAILED status back to the stored previous valid state."""
    try:
        project, _ = _require_project_access(repository, project_id, current_user, write=True)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    if project.status != ProjectStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Retry is only permitted when project status is FAILED. "
                f"Current status is '{project.status.value}'."
            ),
        )

    try:
        recovered = repository.set_status_with_transition(
            project_id=project_id,
            new_status=ProjectStatus.READY_TO_GENERATE,  # Target dynamic via previous_valid_status in repo
            event="retry",
        )
        return recovered
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
