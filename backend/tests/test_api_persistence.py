"""Integration and persistence tests for FastAPI endpoints with state machine enforcement."""

from datetime import datetime, timezone
from typing import Any, Optional, Sequence, Union
import uuid
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_gemini_client, get_repository
from app.core.state_machine import InvalidTransitionError, ProjectStateMachine
from app.llm.schemas import ExtractionResult, QuestionDraft
from app.main import app
from app.models.answer import Answer
from app.models.assumption import Assumption, AssumptionStatus, ImpactLevel
from app.models.document import (
    BRDDocumentVersion,
    SourceChunk,
    SourceDocument,
    SourceDocumentStatus,
)
from app.models.project import Project, ProjectStatus
from app.models.question import AnswerFormat, Question
from app.models.requirement import Priority, Requirement, RequirementType
from app.models.validation import ValidationIssue, ValidationResult


class InMemoryProjectRepository:
    """In-memory implementation of ProjectRepository for fast, durable-style unit tests."""

    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}
        self.requirements: dict[str, list[Requirement]] = {}
        self.questions: dict[str, list[Question]] = {}
        self.answers: dict[str, list[Answer]] = {}
        self.assumptions: dict[str, list[Assumption]] = {}
        self.validation_issues: dict[str, list[ValidationIssue]] = {}
        self.state_transitions: dict[str, list[dict[str, Any]]] = {}
        self.source_documents: dict[str, SourceDocument] = {}
        self.source_chunks: dict[str, list[SourceChunk]] = {}
        self.brd_versions: dict[str, list[BRDDocumentVersion]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.project_collaborators: dict[str, list[dict[str, Any]]] = {}
        self.project_chat_messages: dict[str, list[dict[str, Any]]] = {}
        self.project_invitations: dict[str, dict[str, Any]] = {}



    def create_project(
        self,
        title: str,
        idea: str,
        project_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        owner_email: Optional[str] = None,
    ) -> Project:
        pid = project_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        self.projects[pid] = {
            "id": pid,
            "title": title,
            "idea": idea,
            "status": ProjectStatus.DRAFT.value,
            "input_revision": 1,
            "previous_valid_status": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
            "owner_id": owner_id,
            "owner_email": owner_email,
        }
        self.requirements[pid] = []
        self.questions[pid] = []
        self.answers[pid] = []
        self.assumptions[pid] = []
        self.validation_issues[pid] = []
        self.state_transitions[pid] = []

        self.log_state_transition(
            project_id=pid,
            from_state="NONE",
            to_state=ProjectStatus.DRAFT.value,
            event="create_project",
        )
        return self._to_project(self.projects[pid])

    def get_project(self, project_id: str) -> Project:
        if project_id not in self.projects:
            raise ValueError(f"Project with id '{project_id}' not found.")
        return self._to_project(self.projects[project_id])

    def list_projects(
        self, limit: int = 20, owner_id: Optional[str] = None
    ) -> list[Project]:
        sorted_projs = sorted(
            self.projects.values(), key=lambda p: p["created_at"], reverse=True
        )
        if owner_id:
            matching = []
            for p in sorted_projs:
                pid = p["id"]
                collabs = self.project_collaborators.get(pid, [])
                is_collab = any(c.get("user_id") == owner_id for c in collabs)
                if p.get("owner_id") == owner_id or is_collab or p.get("owner_id") is None:
                    p_copy = dict(p)
                    p_copy["is_owner"] = (p.get("owner_id") == owner_id or p.get("owner_id") is None)
                    p_copy["collaborator_count"] = len(collabs)
                    matching.append(p_copy)
            return [self._to_project(p) for p in matching[:limit]]
        return [self._to_project(p) for p in sorted_projs[:limit]]

    get_projects = list_projects

    def get_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        return self.profiles.get(user_id)

    def upsert_profile(
        self,
        user_id: str,
        email: str,
        full_name: Optional[str] = None,
        role_title: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> dict[str, Any]:
        prof = self.profiles.setdefault(
            user_id,
            {"id": user_id, "email": email, "created_at": datetime.now(timezone.utc).isoformat()},
        )
        prof["email"] = email
        if full_name is not None:
            prof["full_name"] = full_name
        if role_title is not None:
            prof["role_title"] = role_title
        if avatar_url is not None:
            prof["avatar_url"] = avatar_url
        prof["updated_at"] = datetime.now(timezone.utc).isoformat()
        return prof

    def add_collaborator(
        self, project_id: str, user_id: str, user_email: str, role: str = "editor"
    ) -> dict[str, Any]:
        collabs = self.project_collaborators.setdefault(project_id, [])
        for c in collabs:
            if c.get("user_id") == user_id:
                return c
        now = datetime.now(timezone.utc).isoformat()
        collab = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "user_id": user_id,
            "user_email": user_email,
            "role": role,
            "created_at": now,
        }
        collabs.append(collab)
        return collab

    def get_collaborators(self, project_id: str) -> list[dict[str, Any]]:
        collabs = [dict(c) for c in self.project_collaborators.get(project_id, [])]
        for c in collabs:
            uid = c.get("user_id")
            if uid and uid in self.profiles:
                c["full_name"] = self.profiles[uid].get("full_name")
        return collabs

    def remove_collaborator(self, project_id: str, user_id: str) -> bool:
        if project_id in self.project_collaborators:
            self.project_collaborators[project_id] = [
                c for c in self.project_collaborators[project_id] if c.get("user_id") != user_id
            ]
        return True

    def save_chat_message(
        self,
        project_id: str,
        sender_id: Optional[str],
        sender_email: str,
        sender_name: Optional[str],
        role: str,
        content: str,
    ) -> dict[str, Any]:
        msgs = self.project_chat_messages.setdefault(project_id, [])
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "sender_id": sender_id,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "role": role,
            "content": content,
            "created_at": now,
        }
        msgs.append(row)
        return row

    def get_chat_history(self, project_id: str) -> list[dict[str, Any]]:
        return list(self.project_chat_messages.get(project_id, []))

    def create_invitation(
        self,
        project_id: str,
        inviter_id: str,
        inviter_email: str,
        invitee_email: str,
        role: str = "editor",
    ) -> dict[str, Any]:
        for existing in self.project_invitations.values():
            if (
                existing.get("project_id") == project_id
                and existing.get("invitee_email") == invitee_email.strip().lower()
                and existing.get("status") == "pending"
            ):
                return dict(existing)
        now = datetime.now(timezone.utc).isoformat()
        clean_invitee_email = invitee_email.strip().lower()
        inv_id = str(uuid.uuid4())
        token = str(uuid.uuid4())
        project_title = None
        if project_id in self.projects:
            project_title = self.projects[project_id].get("title")

        row = {
            "id": inv_id,
            "project_id": project_id,
            "project_title": project_title,
            "inviter_id": inviter_id,
            "inviter_email": inviter_email,
            "invitee_email": clean_invitee_email,
            "role": role,
            "status": "pending",
            "token": token,
            "created_at": now,
            "accepted_at": None,
        }
        self.project_invitations[inv_id] = row
        return dict(row)

    def get_project_invitations(self, project_id: str) -> list[dict[str, Any]]:
        return [
            dict(inv)
            for inv in self.project_invitations.values()
            if inv.get("project_id") == project_id
        ]

    def get_pending_invitations_for_email(self, email: str) -> list[dict[str, Any]]:
        clean_email = email.strip().lower()
        res = []
        for inv in self.project_invitations.values():
            if (
                inv.get("invitee_email", "").strip().lower() == clean_email
                and inv.get("status") == "pending"
            ):
                item = dict(inv)
                if not item.get("project_title") and item.get("project_id") in self.projects:
                    item["project_title"] = self.projects[item["project_id"]].get("title")
                res.append(item)
        return sorted(res, key=lambda x: x.get("created_at", ""), reverse=True)

    def accept_invitation(
        self, invitation_id: str, user_id: str, user_email: str
    ) -> dict[str, Any]:
        if invitation_id not in self.project_invitations:
            raise ValueError(f"Invitation with id '{invitation_id}' not found.")
        inv = self.project_invitations[invitation_id]
        if inv.get("status") != "pending":
            raise ValueError("Invitation is no longer pending.")

        clean_user_email = user_email.strip().lower()
        clean_invitee_email = inv.get("invitee_email", "").strip().lower()
        if clean_user_email != clean_invitee_email:
            raise ValueError(
                f"User email '{clean_user_email}' does not match invitation recipient '{clean_invitee_email}'."
            )

        now = datetime.now(timezone.utc).isoformat()
        inv["status"] = "accepted"
        inv["accepted_at"] = now

        # Add user to collaborators
        self.add_collaborator(inv["project_id"], user_id, user_email, inv.get("role", "editor"))
        return dict(inv)


    def update_project(self, project: Project) -> Project:
        if project.id not in self.projects:
            raise ValueError(f"Project with id '{project.id}' not found.")
        row = self.projects[project.id]
        row["title"] = project.title
        row["idea"] = project.idea
        row["status"] = project.status.value
        row["input_revision"] = project.input_revision
        row["last_error"] = project.last_error
        row["updated_at"] = datetime.now(timezone.utc)
        return self._to_project(row)

    def increment_input_revision(self, project_id: str) -> int:
        proj = self.get_project(project_id)
        new_rev = proj.input_revision + 1
        self.projects[project_id]["input_revision"] = new_rev
        self.projects[project_id]["updated_at"] = datetime.now(timezone.utc)
        return new_rev

    def set_status_with_transition(
        self,
        project_id: str,
        new_status: Union[ProjectStatus, str],
        event: Optional[str] = None,
        last_error: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> Project:
        if project_id not in self.projects:
            raise ValueError(f"Project with id '{project_id}' not found.")

        row = self.projects[project_id]
        current_status = ProjectStatus(row["status"])
        prev_valid = row.get("previous_valid_status")
        target_status = (
            new_status
            if isinstance(new_status, ProjectStatus)
            else ProjectStatus(str(new_status))
        )

        evt = event
        if not evt:
            if target_status == ProjectStatus.GENERATING:
                evt = "generate"
            elif target_status in (ProjectStatus.COMPLETED, ProjectStatus.GENERATED):
                evt = "quality_passed"
            elif target_status == ProjectStatus.FAILED:
                evt = "generation_or_quality_failed"
            elif target_status == ProjectStatus.READY_TO_GENERATE:
                evt = "retry" if current_status == ProjectStatus.FAILED else "no_blocking_gaps"
            elif target_status == ProjectStatus.AWAITING_CLARIFICATION:
                evt = "assumption_rejected" if current_status == ProjectStatus.READY_TO_GENERATE else "blocking_gaps_found"
            elif target_status == ProjectStatus.ANALYZING:
                evt = "analyze"
            else:
                evt = reason or "transition"

        if (
            current_status == ProjectStatus.READY_TO_GENERATE
            and target_status == ProjectStatus.AWAITING_CLARIFICATION
            and evt in ("assumption_rejected", "answer_or_source_changed", "inputs_changed")
        ):
            validated_status = ProjectStatus.AWAITING_CLARIFICATION
        elif (
            current_status == ProjectStatus.GENERATING
            and target_status in (ProjectStatus.COMPLETED, ProjectStatus.GENERATED)
            and evt in ("completed", "quality_passed")
        ):
            validated_status = target_status
        elif (
            current_status == ProjectStatus.GENERATING
            and target_status == ProjectStatus.GENERATING
        ):
            validated_status = ProjectStatus.GENERATING
        elif (
            current_status == ProjectStatus.FAILED
            and target_status == ProjectStatus.READY_TO_GENERATE
            and evt == "retry"
        ):
            validated_status = ProjectStatus.READY_TO_GENERATE
        else:
            effective_prev = ProjectStatus(prev_valid) if prev_valid else None
            if current_status == ProjectStatus.FAILED and effective_prev == ProjectStatus.GENERATING:
                effective_prev = ProjectStatus.READY_TO_GENERATE
            validated_status = ProjectStateMachine.transition(
                current=current_status,
                event=evt,
                previous_valid_state=effective_prev,
                target_status=target_status,
            )

        if validated_status == ProjectStatus.FAILED:
            row["previous_valid_status"] = (
                ProjectStatus.READY_TO_GENERATE.value
                if current_status == ProjectStatus.GENERATING
                else current_status.value
            )
            row["last_error"] = last_error or "Failed"
        elif current_status == ProjectStatus.FAILED and evt == "retry":
            row["last_error"] = None
        else:
            row["previous_valid_status"] = current_status.value
            row["last_error"] = None

        row["status"] = validated_status.value
        row["updated_at"] = datetime.now(timezone.utc)

        self.log_state_transition(
            project_id=project_id,
            from_state=current_status.value,
            to_state=validated_status.value,
            event=evt,
        )
        return self._to_project(row)

    def save_requirements(
        self, project_id: str, requirements: Sequence[Requirement]
    ) -> list[Requirement]:
        current = {r.id: r for r in self.requirements.get(project_id, [])}
        for r in requirements:
            current[r.id] = r
        self.requirements[project_id] = list(current.values())
        return self.requirements[project_id]

    def get_requirements(self, project_id: str) -> list[Requirement]:
        return list(self.requirements.get(project_id, []))

    def save_questions(
        self, project_id: str, questions: Sequence[Question]
    ) -> list[Question]:
        current = {q.id: q for q in self.questions.get(project_id, [])}
        for q in questions:
            current[q.id] = q
        self.questions[project_id] = list(current.values())
        return self.questions[project_id]

    def get_open_questions(self, project_id: str) -> list[Question]:
        qs = [q for q in self.questions.get(project_id, []) if q.status == "open"]
        return sorted(qs, key=lambda q: q.priority, reverse=True)

    def get_all_questions(self, project_id: str) -> list[Question]:
        return list(self.questions.get(project_id, []))

    def get_already_asked_field_paths(self, project_id: str) -> set[str]:
        return {q.field_path for q in self.questions.get(project_id, [])}

    def save_answers(
        self, project_id: str, answers: Sequence[Answer]
    ) -> list[Answer]:
        current = {a.id: a for a in self.answers.get(project_id, [])}
        for a in answers:
            current[a.id] = a
        self.answers[project_id] = list(current.values())

        # Mark corresponding questions as answered
        ans_q_ids = {a.question_id for a in answers}
        if project_id in self.questions:
            updated_qs = []
            for q in self.questions[project_id]:
                if q.id in ans_q_ids:
                    updated_qs.append(q.model_copy(update={"status": "answered"}))
                else:
                    updated_qs.append(q)
            self.questions[project_id] = updated_qs

        return list(answers)

    def save_answer(self, project_id: str, answer: Answer) -> Answer:
        saved = self.save_answers(project_id, [answer])
        return saved[0]

    def get_answers(self, project_id: str) -> list[Answer]:
        return list(self.answers.get(project_id, []))

    def save_assumptions(
        self, project_id: str, assumptions: Sequence[Assumption]
    ) -> list[Assumption]:
        current = {a.id: a for a in self.assumptions.get(project_id, [])}
        for a in assumptions:
            current[a.id] = a
        self.assumptions[project_id] = list(current.values())
        return self.assumptions[project_id]

    def get_assumptions(self, project_id: str) -> list[Assumption]:
        return list(self.assumptions.get(project_id, []))

    def update_assumption_status(
        self,
        project_id: str,
        assumption_id: str,
        status: Union[AssumptionStatus, str],
        reviewed_by: Optional[str] = None,
        reviewer_email: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
    ) -> Assumption:
        asms = self.assumptions.get(project_id, [])
        status_val = status.value if hasattr(status, "value") else str(status)
        rev_dt = reviewed_at or datetime.now(timezone.utc)
        for idx, a in enumerate(asms):
            if a.id == assumption_id:
                updated = a.model_copy(
                    update={
                        "status": AssumptionStatus(status_val),
                        "reviewed_by": reviewed_by,
                        "reviewer_email": reviewer_email,
                        "reviewed_at": rev_dt,
                    }
                )
                asms[idx] = updated
                return updated
        raise ValueError(f"Assumption '{assumption_id}' not found.")

    def record_assumption_decision(
        self,
        project_id: str,
        assumption_id: str,
        status: Union[AssumptionStatus, str],
        reviewed_by: Optional[str] = None,
        reviewer_email: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
    ) -> Assumption:
        return self.update_assumption_status(
            project_id=project_id,
            assumption_id=assumption_id,
            status=status,
            reviewed_by=reviewed_by,
            reviewer_email=reviewer_email,
            reviewed_at=reviewed_at,
        )

    def save_validation_issues(
        self, project_id: str, validation_result: ValidationResult
    ) -> None:
        self.validation_issues[project_id] = list(validation_result.issues)

    def get_latest_validation_issues(self, project_id: str) -> list[ValidationIssue]:
        return list(self.validation_issues.get(project_id, []))

    def log_state_transition(
        self, project_id: str, from_state: str, to_state: str, event: str
    ) -> None:
        if project_id not in self.state_transitions:
            self.state_transitions[project_id] = []
        self.state_transitions[project_id].append(
            {
                "project_id": project_id,
                "from_state": from_state,
                "to_state": to_state,
                "event": event,
                "created_at": datetime.now(timezone.utc),
            }
        )

    def get_state_history(self, project_id: str) -> list[dict[str, Any]]:
        return list(self.state_transitions.get(project_id, []))

    def save_source_document(self, document: SourceDocument) -> SourceDocument:
        self.source_documents[document.id] = document
        return document

    def save_source_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]:
        for c in chunks:
            self.source_chunks.setdefault(c.document_id, []).append(c)
        return chunks

    def get_source_documents_by_project(self, project_id: str) -> list[SourceDocument]:
        return [doc for doc in self.source_documents.values() if doc.project_id == project_id]

    def get_source_document_by_id(self, document_id: str) -> Optional[SourceDocument]:
        return self.source_documents.get(document_id)

    def get_source_chunks_by_document(self, document_id: str) -> list[SourceChunk]:
        chunks = self.source_chunks.get(document_id, [])
        return sorted(chunks, key=lambda c: c.chunk_index)

    def get_source_chunks_by_project(self, project_id: str) -> list[SourceChunk]:
        project_docs = {doc.id for doc in self.get_source_documents_by_project(project_id)}
        res = []
        for doc_id in project_docs:
            res.extend(self.source_chunks.get(doc_id, []))
        return sorted(res, key=lambda c: c.chunk_index)

    def save_brd_version(self, brd_version: BRDDocumentVersion) -> BRDDocumentVersion:
        versions = self.brd_versions.setdefault(brd_version.project_id, [])
        for idx, v in enumerate(versions):
            if v.id == brd_version.id:
                versions[idx] = brd_version
                return brd_version
        versions.append(brd_version)
        return brd_version

    def get_brd_versions_by_project(self, project_id: str) -> list[BRDDocumentVersion]:
        versions = self.brd_versions.get(project_id, [])
        return sorted(versions, key=lambda v: v.version)

    def get_latest_brd_version(self, project_id: str) -> Optional[BRDDocumentVersion]:
        versions = self.brd_versions.get(project_id, [])
        if not versions:
            return None
        return sorted(versions, key=lambda v: v.version, reverse=True)[0]

    @staticmethod
    def _to_project(row: dict[str, Any]) -> Project:
        return Project(
            id=row["id"],
            title=row["title"],
            idea=row["idea"],
            status=ProjectStatus(row["status"]),
            input_revision=row["input_revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_error=row.get("last_error"),
            owner_id=row.get("owner_id"),
            owner_email=row.get("owner_email"),
            collaborator_count=int(row.get("collaborator_count", 0)),
            is_owner=bool(row.get("is_owner", True)),
        )


class FakeGeminiTestClient:
    """Mock Gemini client returning incomplete requirement on round 1 and resolved on round 2."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_structured(self, prompt: str, response_schema: type):
        if response_schema == QuestionDraft:
            return QuestionDraft(
                question_text="Which user role books service appointments?",
                why_it_matters="Identifies the primary actor executing booking operations.",
                answer_format=AnswerFormat.TEXT,
                options=None,
            )

        if response_schema == ExtractionResult:
            self.call_count += 1
            # Check if clarification answer is present in prompt context
            is_clarified = "Registered Customer" in prompt

            return ExtractionResult(
                requirements=[
                    Requirement(
                        id="REQ-BIZ-01",
                        type=RequirementType.BUSINESS,
                        title="Service Growth",
                        statement="Expand bookings by 25% year over year.",
                        outcome="Achieve 25% booking growth.",
                        priority=Priority.MUST,
                        confidence=1.0,
                    ),
                    Requirement(
                        id="REQ-FUNC-01",
                        type=RequirementType.FUNCTIONAL,
                        title="Book Service Slot",
                        statement="Allow booking appointments with local service specialists.",
                        actor="Registered Customer" if is_clarified else None,
                        outcome="Appointment confirmed.",
                        priority=Priority.MUST,
                        acceptance_criteria=[
                            "User selects date and provider",
                            "Confirmation notice is dispatched",
                        ],
                        confidence=0.95,
                    ),
                ],
                proposed_assumptions=[
                    Assumption(
                        id="ASM-01",
                        project_id="test",
                        statement="Assume providers manage their own schedule availability.",
                        rationale="Standard industry provider workflow.",
                        impact=ImpactLevel.LOW,
                        status=AssumptionStatus.PROPOSED,
                    )
                ],
            )
        raise ValueError(f"Unexpected schema: {response_schema}")


@pytest.fixture
def test_setup():
    """Setup TestClient with injected fake repository and fake Gemini client."""
    repo = InMemoryProjectRepository()
    gemini = FakeGeminiTestClient()

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_gemini_client] = lambda: gemini

    client = TestClient(app)
    yield client, repo, gemini

    app.dependency_overrides.clear()


def test_create_project_endpoint(test_setup):
    """POST /projects initializes project in DRAFT status with input_revision=1."""
    client, repo, _ = test_setup

    payload = {
        "title": "On-Demand Car Detailing Platform",
        "idea": "An Uber-like platform for mobile auto detailing services.",
    }
    response = client.post("/projects", json=payload)
    assert response.status_code == 201

    data = response.json()["project"]
    assert data["title"] == "On-Demand Car Detailing Platform"
    assert data["status"] == "DRAFT"
    assert data["input_revision"] == 1
    assert "id" in data

    # State transition logged
    history = repo.get_state_history(data["id"])
    assert len(history) == 1
    assert history[0]["to_state"] == "DRAFT"


def test_get_project_detail_and_listing(test_setup):
    """GET /projects and GET /projects/{id} return project details and counts."""
    client, repo, _ = test_setup

    create_res = client.post(
        "/projects",
        json={"idea": "Mobile app allowing local tutors to teach students nearby."},
    )
    assert create_res.status_code == 201
    project_id = create_res.json()["project"]["id"]

    # Detail endpoint
    detail_res = client.get(f"/projects/{project_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["project"]["id"] == project_id
    assert detail["requirement_count"] == 0
    assert detail["open_question_count"] == 0

    # List endpoint
    list_res = client.get("/projects?limit=10")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_analyze_and_clarification_loop(test_setup):
    """Test full HTTP loop:
    1. POST /projects/{id}/analyze transitions to AWAITING_CLARIFICATION with open questions.
    2. GET /projects/{id}/questions returns open questions.
    3. POST /projects/{id}/answers increments input_revision and resolves blockers to READY_TO_GENERATE.
    """
    client, repo, _ = test_setup

    # Create project
    create_res = client.post(
        "/projects",
        json={"idea": "I want an app where users can book appointments with local service providers."},
    )
    project_id = create_res.json()["project"]["id"]

    # 1. Run Analyze (Round 1 -> gap detected)
    analyze_res = client.post(f"/projects/{project_id}/analyze")
    assert analyze_res.status_code == 200
    data = analyze_res.json()

    assert data["next_status"] == "AWAITING_CLARIFICATION"
    assert data["project"]["status"] == "AWAITING_CLARIFICATION"
    assert len(data["open_questions"]) >= 1

    question = data["open_questions"][0]
    assert "actor" in question["field_path"].lower()

    # 2. Get open questions endpoint
    q_res = client.get(f"/projects/{project_id}/questions")
    assert q_res.status_code == 200
    questions_list = q_res.json()
    assert len(questions_list) >= 1
    assert questions_list[0]["id"] == question["id"]

    # 3. Submit Answers (Round 2 -> resolved)
    answers_payload = {
        "answers": [
            {
                "question_id": question["id"],
                "value": "Registered Customer",
            }
        ]
    }
    submit_res = client.post(f"/projects/{project_id}/answers", json=answers_payload)
    assert submit_res.status_code == 200
    submit_data = submit_res.json()

    # Assert project resolved to READY_TO_GENERATE
    assert submit_data["next_status"] == "READY_TO_GENERATE"
    assert submit_data["project"]["status"] == "READY_TO_GENERATE"
    assert submit_data["project"]["input_revision"] == 2
    assert len(submit_data["open_questions"]) == 0

    # Verify state transitions were recorded
    history = repo.get_state_history(project_id)
    events = [h["event"] for h in history]
    assert "create_project" in events
    assert "analyze" in events
    assert "blocking_gaps_found" in events
    assert "answers_submitted" in events
    assert "no_blocking_gaps" in events


def test_generate_guard_enforcement(test_setup):
    """POST /projects/{id}/generate rejects DRAFT status with 400, and generates successfully when READY_TO_GENERATE."""
    client, repo, _ = test_setup

    create_res = client.post(
        "/projects",
        json={"idea": "Platform for renting specialized construction equipment."},
    )
    project_id = create_res.json()["project"]["id"]

    # Attempt generate from DRAFT -> Rejected with 400
    gen_res = client.post(f"/projects/{project_id}/generate")
    assert gen_res.status_code == 400
    assert "READY_TO_GENERATE" in gen_res.json()["detail"]

    # Attempt generate from ANALYZING -> Rejected with 400
    repo.projects[project_id]["status"] = ProjectStatus.ANALYZING.value
    gen_analyzing_res = client.post(f"/projects/{project_id}/generate")
    assert gen_analyzing_res.status_code == 400

    # Seed a grounded requirement and place project in READY_TO_GENERATE
    req = Requirement(
        id="REQ-TEST-001",
        title="Equipment Availability Search",
        statement="Users can filter equipment by geographic radius.",
        type=RequirementType.FUNCTIONAL,
        priority=Priority.MUST,
        actor="Contractor",
        outcome="Equipment list within 50 miles.",
        acceptance_criteria=["Search returns items within radius."],
        trace_refs=["ANSWER:A1"],
    )
    repo.save_requirements(project_id, [req])
    repo.projects[project_id]["status"] = ProjectStatus.READY_TO_GENERATE.value

    # Attempt generate from READY_TO_GENERATE -> Returns 200 and transitions to COMPLETED
    gen_ready_res = client.post(f"/projects/{project_id}/generate")
    assert gen_ready_res.status_code == 200
    res_data = gen_ready_res.json()
    assert res_data["project"]["status"] == "COMPLETED"
    assert res_data["brd_version"]["version_number"] == 1
    assert res_data["download_url"] == f"/projects/{project_id}/brd/download"

    # Verify latest BRD endpoint
    brd_res = client.get(f"/projects/{project_id}/brd")
    assert brd_res.status_code == 200
    assert brd_res.json()["version_number"] == 1
    assert brd_res.json()["status"] == "COMPLETED"

    # Verify DOCX download endpoint
    dl_res = client.get(f"/projects/{project_id}/brd/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment; filename=" in dl_res.headers["content-disposition"]
    assert dl_res.content[:4] == b"PK\x03\x04"



def test_assumption_decision_endpoint(test_setup):
    """POST /projects/{id}/assumptions/{id}/decision accepts or rejects assumptions."""
    client, repo, _ = test_setup

    create_res = client.post(
        "/projects",
        json={"idea": "SaaS analytics tool for warehouse inventory optimization."},
    )
    project_id = create_res.json()["project"]["id"]

    # Seed an assumption
    asm = Assumption(
        id="ASM-TEST-01",
        project_id=project_id,
        statement="Assume standard cloud hosting on AWS.",
        rationale="Client requested cloud deployment.",
        impact=ImpactLevel.MEDIUM,
        status=AssumptionStatus.PROPOSED,
    )
    repo.save_assumptions(project_id, [asm])

    # Accept assumption
    decide_res = client.post(
        f"/projects/{project_id}/assumptions/ASM-TEST-01/decision",
        json={"decision": "accepted"},
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["status"] == "ACCEPTED"

    # Revision incremented
    proj = repo.get_project(project_id)
    assert proj.input_revision == 2

    # Reject assumption
    decide_reject_res = client.post(
        f"/projects/{project_id}/assumptions/ASM-TEST-01/decision",
        json={"decision": "rejected"},
    )
    assert decide_reject_res.status_code == 200
    assert decide_reject_res.json()["status"] == "REJECTED"

    # Rejection creates an open question
    open_qs = repo.get_open_questions(project_id)
    assert any("ASM-TEST-01" in q.field_path for q in open_qs)
