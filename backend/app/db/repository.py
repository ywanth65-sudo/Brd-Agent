"""Durable persistence repository using Supabase Postgres.

Encapsulates all database read and write operations for projects, requirements,
clarification questions, answers, assumptions, and validation history.
Translates between Supabase rows and Step 1 Pydantic domain models.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional, Sequence, Union
import uuid
from uuid import UUID

from supabase import Client

from app.core.state_machine import InvalidTransitionError, ProjectStateMachine
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
from app.models.validation import Severity, ValidationIssue, ValidationResult

logger = logging.getLogger(__name__)


def _nullable_uuid(value: Optional[str]) -> Optional[str]:
    """Keep development identities out of Postgres UUID columns."""
    if not value:
        return None
    try:
        UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    return str(value)


class ProjectRepository:
    """Repository managing database persistence and state transitions in Supabase."""

    def __init__(self, client: Client) -> None:
        """Initialize repository with a Supabase client.

        Args:
            client: Configured Supabase client.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Project CRUD & State Machine Management
    # ------------------------------------------------------------------

    def create_project(
        self,
        title: str,
        idea: str,
        project_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        owner_email: Optional[str] = None,
    ) -> Project:
        """Create and persist a new Project in DRAFT status.

        Args:
            title: Human-readable title for the project.
            idea: Raw business idea text.
            project_id: Optional specific UUID string; generated if None.
            owner_id: Optional UUID of the user who owns the project.
            owner_email: Optional email address of the owner.

        Returns:
            Project domain model.

        Raises:
            ValueError: If database insertion fails.
        """
        pid = project_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = {
            "id": pid,
            "title": title,
            "idea": idea,
            "status": ProjectStatus.DRAFT.value,
            "input_revision": 1,
            "previous_valid_status": None,
            "last_error": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "owner_id": owner_id,
            "owner_email": owner_email,
        }

        try:
            res = self.client.table("projects").insert(row).execute()
            if not res.data:
                raise ValueError("Database insert returned empty result for project.")
            created_row = res.data[0]
            # Log initial creation state transition
            self.log_state_transition(
                project_id=pid,
                from_state="NONE",
                to_state=ProjectStatus.DRAFT.value,
                event="create_project",
            )
            return self._row_to_project(created_row)
        except Exception as exc:
            logger.error("Failed to create project in database: %s", exc)
            raise ValueError(f"Failed to create project: {exc}") from exc

    def get_project(self, project_id: str) -> Project:
        """Retrieve a project by ID, raising ValueError (404) if not found.

        Args:
            project_id: Target project UUID.

        Returns:
            Project domain model.

        Raises:
            ValueError: If project is not found or database fails.
        """
        try:
            res = (
                self.client.table("projects")
                .select("*")
                .eq("id", project_id)
                .execute()
            )
            if not res.data or len(res.data) == 0:
                raise ValueError(f"Project with id '{project_id}' not found.")
            return self._row_to_project(res.data[0])
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Error retrieving project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to retrieve project '{project_id}': {exc}") from exc

    def list_projects(
        self, limit: int = 20, owner_id: Optional[str] = None
    ) -> list[Project]:
        """List recently updated projects, filtered by ownership or collaboration.

        Args:
            limit: Maximum count to return.
            owner_id: Optional user UUID to filter projects by owner or collaboration.

        Returns:
            List of Project models with collaborator_count and is_owner flags.
        """
        try:
            if owner_id:
                # 1. Projects owned by user
                owned_res = (
                    self.client.table("projects")
                    .select("*")
                    .eq("owner_id", owner_id)
                    .execute()
                )
                owned_rows = owned_res.data or []

                # 2. Projects where user is enrolled as collaborator
                collab_res = (
                    self.client.table("project_collaborators")
                    .select("project_id")
                    .eq("user_id", owner_id)
                    .execute()
                )
                collab_pids = [
                    c["project_id"] for c in (collab_res.data or []) if c.get("project_id")
                ]

                collab_rows = []
                if collab_pids:
                    c_res = (
                        self.client.table("projects")
                        .select("*")
                        .in_("id", collab_pids)
                        .execute()
                    )
                    collab_rows = c_res.data or []

                combined: dict[str, dict[str, Any]] = {}
                for r in owned_rows + collab_rows:
                    combined[str(r["id"])] = r

                rows = sorted(
                    combined.values(),
                    key=lambda r: str(r.get("created_at", "")),
                    reverse=True,
                )[:limit]
            else:
                res = (
                    self.client.table("projects")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                rows = res.data or []

            projects = []
            for r in rows:
                p = self._row_to_project(r)
                is_owner = (p.owner_id == owner_id) if owner_id else True
                try:
                    c_cnt_res = (
                        self.client.table("project_collaborators")
                        .select("id", count="exact")
                        .eq("project_id", p.id)
                        .execute()
                    )
                    c_count = c_cnt_res.count or len(c_cnt_res.data or [])
                except Exception:
                    c_count = 0
                projects.append(
                    p.model_copy(update={"is_owner": is_owner, "collaborator_count": c_count})
                )
            return projects
        except Exception as exc:
            logger.error("Error listing projects: %s", exc)
            raise ValueError(f"Failed to list projects: {exc}") from exc

    # Alias for naming consistency across callers
    get_projects = list_projects

    # ------------------------------------------------------------------
    # User Profile & Project Collaboration
    # ------------------------------------------------------------------

    def get_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        """Retrieve user profile by auth user ID."""
        try:
            res = self.client.table("profiles").select("*").eq("id", user_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as exc:
            logger.error("Failed to get profile for user '%s': %s", user_id, exc)
            return None

    def upsert_profile(
        self,
        user_id: str,
        email: str,
        full_name: Optional[str] = None,
        role_title: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Insert or update user profile."""
        now = datetime.now(timezone.utc).isoformat()
        row: dict[str, Any] = {
            "id": user_id,
            "email": email,
            "updated_at": now,
        }
        if full_name is not None:
            row["full_name"] = full_name
        if role_title is not None:
            row["role_title"] = role_title
        if avatar_url is not None:
            row["avatar_url"] = avatar_url

        try:
            res = self.client.table("profiles").upsert(row).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return row
        except Exception as exc:
            logger.error("Failed to upsert profile for user '%s': %s", user_id, exc)
            raise ValueError(f"Failed to upsert profile: {exc}") from exc

    def add_collaborator(
        self, project_id: str, user_id: str, user_email: str, role: str = "editor"
    ) -> dict[str, Any]:
        """Add user as collaborator to project if not already enrolled."""
        role = role.strip().lower()
        if role not in {"editor", "viewer"}:
            raise ValueError("Role must be either 'editor' or 'viewer'.")
        user_email = user_email.strip().lower()
        try:
            existing = (
                self.client.table("project_collaborators")
                .select("*")
                .eq("project_id", project_id)
                .eq("user_id", user_id)
                .execute()
            )
            if existing.data and len(existing.data) > 0:
                return existing.data[0]

            now = datetime.now(timezone.utc).isoformat()
            row = {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "user_id": user_id,
                "user_email": user_email,
                "role": role,
                "created_at": now,
            }
            res = self.client.table("project_collaborators").insert(row).execute()
            return res.data[0] if res.data else row
        except Exception as exc:
            logger.error("Failed to add collaborator to project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to add collaborator: {exc}") from exc

    def get_collaborators(self, project_id: str) -> list[dict[str, Any]]:
        """Retrieve all collaborators enrolled in a project with profile details if available."""
        try:
            res = (
                self.client.table("project_collaborators")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=False)
                .execute()
            )
            collaborators = res.data or []
            for c in collaborators:
                uid = c.get("user_id")
                if uid:
                    prof = self.get_profile(uid)
                    if prof:
                        c["full_name"] = prof.get("full_name")
            return collaborators
        except Exception as exc:
            logger.error("Failed to get collaborators for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get collaborators: {exc}") from exc

    def remove_collaborator(self, project_id: str, user_id: str) -> bool:
        """Remove a collaborator from a project."""
        try:
            self.client.table("project_collaborators").delete().eq(
                "project_id", project_id
            ).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(
                "Failed to remove collaborator '%s' from '%s': %s", user_id, project_id, exc
            )
            raise ValueError(f"Failed to remove collaborator: {exc}") from exc

    # ------------------------------------------------------------------
    # Multi-User Chat Persistence
    # ------------------------------------------------------------------

    def save_chat_message(
        self,
        project_id: str,
        sender_id: Optional[str],
        sender_email: str,
        sender_name: Optional[str],
        role: str,
        content: str,
    ) -> dict[str, Any]:
        """Persist a chat message to project_chat_messages table."""
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "sender_id": _nullable_uuid(sender_id),
            "sender_email": sender_email,
            "sender_name": sender_name,
            "role": role,
            "content": content,
            "created_at": now,
        }
        try:
            res = self.client.table("project_chat_messages").insert(row).execute()
            return res.data[0] if (res.data and len(res.data) > 0) else row
        except Exception as exc:
            logger.error("Failed to save chat message for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to save chat message: {exc}") from exc

    def get_chat_history(self, project_id: str) -> list[dict[str, Any]]:
        """Retrieve all chat messages for a project ordered chronologically."""
        try:
            res = (
                self.client.table("project_chat_messages")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("Failed to get chat history for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get chat history: {exc}") from exc

    # ------------------------------------------------------------------
    # Project Email Invitations
    # ------------------------------------------------------------------

    def create_invitation(
        self,
        project_id: str,
        inviter_id: str,
        inviter_email: str,
        invitee_email: str,
        role: str = "editor",
    ) -> dict[str, Any]:
        """Create and store a project invitation."""
        role = role.strip().lower()
        if role not in {"editor", "viewer"}:
            raise ValueError("Role must be either 'editor' or 'viewer'.")
        now = datetime.now(timezone.utc).isoformat()
        clean_invitee_email = invitee_email.strip().lower()
        token = str(uuid.uuid4())
        clean_inviter_email = inviter_email.strip().lower()

        try:
            existing = (
                self.client.table("project_invitations")
                .select("*")
                .eq("project_id", project_id)
                .eq("invitee_email", clean_invitee_email)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            if existing.data:
                return existing.data[0]
        except Exception as exc:
            logger.error("Failed to check duplicate invitation: %s", exc)
            raise ValueError(f"Failed to check existing invitation: {exc}") from exc

        # Check project title if available
        project_title = None
        try:
            p_res = self.client.table("projects").select("title").eq("id", project_id).execute()
            if p_res.data and len(p_res.data) > 0:
                project_title = p_res.data[0].get("title")
        except Exception:
            pass

        row = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "inviter_id": inviter_id,
            "inviter_email": clean_inviter_email,
            "invitee_email": clean_invitee_email,
            "role": role,
            "status": "pending",
            "token": token,
            "created_at": now,
            "accepted_at": None,
        }
        try:
            res = self.client.table("project_invitations").insert(row).execute()
            saved = res.data[0] if (res.data and len(res.data) > 0) else row
            if project_title and "project_title" not in saved:
                saved["project_title"] = project_title
            return saved
        except Exception as exc:
            logger.error(
                "Failed to create invitation for '%s' to project '%s': %s",
                clean_invitee_email,
                project_id,
                exc,
            )
            raise ValueError(f"Failed to create invitation: {exc}") from exc

    def get_pending_invitations_for_email(self, email: str) -> list[dict[str, Any]]:
        """Retrieve all pending invitations for a given invitee email."""
        clean_email = email.strip().lower()
        try:
            res = (
                self.client.table("project_invitations")
                .select("*")
                .ilike("invitee_email", clean_email)
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute()
            )
            invites = res.data or []
            for inv in invites:
                if not inv.get("project_title"):
                    pid = inv.get("project_id")
                    if pid:
                        try:
                            p_res = (
                                self.client.table("projects").select("title").eq("id", pid).execute()
                            )
                            if p_res.data and len(p_res.data) > 0:
                                inv["project_title"] = p_res.data[0].get("title")
                        except Exception:
                            pass
            return invites
        except Exception as exc:
            logger.error("Failed to get pending invitations for '%s': %s", clean_email, exc)
            raise ValueError(f"Failed to get invitations: {exc}") from exc

    def get_project_invitations(self, project_id: str) -> list[dict[str, Any]]:
        """Retrieve persisted invitations for a project, newest first."""
        try:
            res = (
                self.client.table("project_invitations")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("Failed to get invitations for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get project invitations: {exc}") from exc

    def accept_invitation(
        self, invitation_id: str, user_id: str, user_email: str
    ) -> dict[str, Any]:
        """Accept an invitation, enroll user as collaborator, and update status."""
        try:
            res = (
                self.client.table("project_invitations")
                .select("*")
                .eq("id", invitation_id)
                .execute()
            )
            if not res.data or len(res.data) == 0:
                raise ValueError(f"Invitation with id '{invitation_id}' not found.")
            invitation = res.data[0]

            clean_user_email = user_email.strip().lower()
            clean_invitee_email = invitation.get("invitee_email", "").strip().lower()
            if clean_user_email != clean_invitee_email:
                raise ValueError(
                    f"User email '{clean_user_email}' does not match invitation recipient '{clean_invitee_email}'."
                )
            if invitation.get("status", "pending").lower() != "pending":
                raise ValueError("Invitation is no longer pending.")

            now = datetime.now(timezone.utc).isoformat()
            upd = (
                self.client.table("project_invitations")
                .update({"status": "accepted", "accepted_at": now})
                .eq("id", invitation_id)
                .execute()
            )
            updated_inv = upd.data[0] if (upd.data and len(upd.data) > 0) else invitation
            updated_inv["status"] = "accepted"
            updated_inv["accepted_at"] = now

            # Enroll user into project_collaborators
            project_id = invitation["project_id"]
            role = invitation.get("role", "editor").strip().lower()
            self.add_collaborator(project_id, user_id, user_email, role)

            return updated_inv
        except Exception as exc:
            logger.error("Failed to accept invitation '%s': %s", invitation_id, exc)
            raise ValueError(f"Failed to accept invitation: {exc}") from exc



    def update_project(self, project: Project) -> Project:
        """Update mutable fields of a project.

        Args:
            project: Updated Project domain model.

        Returns:
            Persisted Project.
        """
        now = datetime.now(timezone.utc)
        update_data = {
            "title": project.title,
            "idea": project.idea,
            "status": project.status.value,
            "input_revision": project.input_revision,
            "last_error": project.last_error,
            "updated_at": now.isoformat(),
        }
        try:
            res = (
                self.client.table("projects")
                .update(update_data)
                .eq("id", project.id)
                .execute()
            )
            if not res.data:
                raise ValueError(f"Project with id '{project.id}' not found for update.")
            return self._row_to_project(res.data[0])
        except Exception as exc:
            logger.error("Error updating project '%s': %s", project.id, exc)
            raise ValueError(f"Failed to update project '{project.id}': {exc}") from exc

    def increment_input_revision(self, project_id: str) -> int:
        """Atomically increment the input revision number of a project.

        Args:
            project_id: Target project UUID.

        Returns:
            New input_revision integer.
        """
        project = self.get_project(project_id)
        new_rev = project.input_revision + 1
        now = datetime.now(timezone.utc)
        try:
            self.client.table("projects").update(
                {"input_revision": new_rev, "updated_at": now.isoformat()}
            ).eq("id", project_id).execute()
            return new_rev
        except Exception as exc:
            logger.error("Error incrementing revision for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to increment revision: {exc}") from exc

    def set_status_with_transition(
        self,
        project_id: str,
        new_status: Union[ProjectStatus, str],
        event: Optional[str] = None,
        last_error: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> Project:
        """Transition project status using ProjectStateMachine rules and record audit trail.

        Args:
            project_id: Target project UUID.
            new_status: Desired next ProjectStatus enum or string.
            event: Lifecycle event triggering the transition.
            last_error: Diagnostic error message when transitioning to FAILED.
            reason: Optional human-readable reason for the transition.

        Returns:
            Updated Project model.

        Raises:
            InvalidTransitionError: If the transition is prohibited by state machine.
            ValueError: If database operation fails.
        """
        # Fetch current project row directly to inspect previous_valid_status
        try:
            res = (
                self.client.table("projects")
                .select("*")
                .eq("id", project_id)
                .execute()
            )
            if not res.data:
                raise ValueError(f"Project with id '{project_id}' not found.")
            row = res.data[0]
        except Exception as exc:
            raise ValueError(f"Could not load project '{project_id}': {exc}") from exc

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

        # Handle assumption rejection edge case: READY_TO_GENERATE -> AWAITING_CLARIFICATION
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
            # Validate transition using deterministic StateMachine
            effective_prev = ProjectStatus(prev_valid) if prev_valid else None
            if current_status == ProjectStatus.FAILED and effective_prev == ProjectStatus.GENERATING:
                effective_prev = ProjectStatus.READY_TO_GENERATE
            validated_status = ProjectStateMachine.transition(
                current=current_status,
                event=evt,
                previous_valid_state=effective_prev,
                target_status=target_status,
            )

        now = datetime.now(timezone.utc)
        update_fields: dict[str, Any] = {
            "status": validated_status.value,
            "updated_at": now.isoformat(),
        }

        # Track previous valid state for FAILED recovery
        if validated_status == ProjectStatus.FAILED:
            update_fields["previous_valid_status"] = (
                ProjectStatus.READY_TO_GENERATE.value
                if current_status == ProjectStatus.GENERATING
                else current_status.value
            )
            update_fields["last_error"] = last_error or "Project generation or quality failed."
        elif current_status == ProjectStatus.FAILED and evt == "retry":
            # Recovered from FAILED
            update_fields["last_error"] = None
        else:
            update_fields["previous_valid_status"] = current_status.value
            update_fields["last_error"] = None

        try:
            upd_res = (
                self.client.table("projects")
                .update(update_fields)
                .eq("id", project_id)
                .execute()
            )
            # Log transition to audit log
            self.log_state_transition(
                project_id=project_id,
                from_state=current_status.value,
                to_state=validated_status.value,
                event=evt,
            )
            return self._row_to_project(upd_res.data[0])
        except Exception as exc:
            logger.error("Failed to update status for project '%s': %s", project_id, exc)
            raise ValueError(f"Database error during status transition: {exc}") from exc

    # ------------------------------------------------------------------
    # Requirements Persistence
    # ------------------------------------------------------------------

    def save_requirements(
        self, project_id: str, requirements: Sequence[Requirement]
    ) -> list[Requirement]:
        """Upsert a list of Requirement models for a project.

        Args:
            project_id: Associated project UUID.
            requirements: Requirements to save.

        Returns:
            List of saved Requirement models.
        """
        if not requirements:
            return []

        rows = [
            {
                "id": req.id,
                "project_id": project_id,
                "type": req.type.value,
                "title": req.title,
                "statement": req.statement,
                "actor": req.actor,
                "outcome": req.outcome,
                "priority": req.priority.value,
                "acceptance_criteria": req.acceptance_criteria,
                "trace_refs": req.trace_refs,
                "confidence": req.confidence,
            }
            for req in requirements
        ]

        try:
            res = self.client.table("requirements").upsert(rows).execute()
            return [self._row_to_requirement(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to save requirements for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to save requirements: {exc}") from exc

    def get_requirements(self, project_id: str) -> list[Requirement]:
        """Fetch all requirements associated with a project.

        Args:
            project_id: Associated project UUID.

        Returns:
            List of Requirement domain models.
        """
        try:
            res = (
                self.client.table("requirements")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return [self._row_to_requirement(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get requirements for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get requirements: {exc}") from exc

    # ------------------------------------------------------------------
    # Clarification Questions & Answers Persistence
    # ------------------------------------------------------------------

    def save_questions(
        self, project_id: str, questions: Sequence[Question]
    ) -> list[Question]:
        """Upsert questions into the database.

        Args:
            project_id: Associated project UUID.
            questions: Questions to persist.

        Returns:
            List of persisted Question models.
        """
        if not questions:
            return []

        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": q.id,
                "project_id": project_id,
                "field_path": q.field_path,
                "question_text": q.question_text,
                "why_it_matters": q.why_it_matters,
                "answer_format": q.answer_format.value,
                "options": q.options,
                "impact": q.impact,
                "gap_confidence": q.gap_confidence,
                "priority": q.priority,
                "status": q.status,
                "created_at": (q.created_at or now).isoformat(),
            }
            for q in questions
        ]

        try:
            res = self.client.table("questions").upsert(rows).execute()
            return [self._row_to_question(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to save questions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to save questions: {exc}") from exc

    def get_open_questions(self, project_id: str) -> list[Question]:
        """Retrieve open questions for a project ordered by priority descending.

        Args:
            project_id: Associated project UUID.

        Returns:
            List of open Question models.
        """
        try:
            res = (
                self.client.table("questions")
                .select("*")
                .eq("project_id", project_id)
                .eq("status", "open")
                .order("priority", desc=True)
                .execute()
            )
            return [self._row_to_question(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get open questions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get open questions: {exc}") from exc

    def get_all_questions(self, project_id: str) -> list[Question]:
        """Retrieve all questions for a project regardless of status."""
        try:
            res = (
                self.client.table("questions")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return [self._row_to_question(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get questions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get questions: {exc}") from exc

    def get_already_asked_field_paths(self, project_id: str) -> set[str]:
        """Return the set of all field_path values queried across the project's history."""
        questions = self.get_all_questions(project_id)
        return {q.field_path for q in questions}

    def save_answers(
        self, project_id: str, answers: Sequence[Answer]
    ) -> list[Answer]:
        """Persist answers and mark corresponding questions as 'answered'.

        Args:
            project_id: Associated project UUID.
            answers: Answers submitted by stakeholder.

        Returns:
            List of persisted Answer models.
        """
        if not answers:
            return []

        rows = [
            {
                "id": a.id,
                "project_id": project_id,
                "question_id": a.question_id,
                "value": a.value,
                "answered_at": (a.answered_at or datetime.now(timezone.utc)).isoformat(),
                "answered_by": _nullable_uuid(a.answered_by),
                "answerer_email": a.answerer_email,
            }
            for a in answers
        ]

        try:
            res = self.client.table("answers").upsert(rows).execute()

            # Mark corresponding questions as answered
            for a in answers:
                self.client.table("questions").update({"status": "answered"}).eq(
                    "id", a.question_id
                ).execute()

            return [self._row_to_answer(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to save answers for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to save answers: {exc}") from exc

    def save_answer(self, project_id: str, answer: Answer) -> Answer:
        """Persist a single Answer model."""
        saved = self.save_answers(project_id, [answer])
        return saved[0]

    def get_answers(self, project_id: str) -> list[Answer]:
        """Retrieve all answers submitted for a project."""
        try:
            res = (
                self.client.table("answers")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return [self._row_to_answer(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get answers for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get answers: {exc}") from exc

    # ------------------------------------------------------------------
    # Assumptions Persistence
    # ------------------------------------------------------------------

    def save_assumptions(
        self, project_id: str, assumptions: Sequence[Assumption]
    ) -> list[Assumption]:
        """Upsert explicit assumptions.

        Args:
            project_id: Associated project UUID.
            assumptions: List of assumptions to persist.

        Returns:
            List of persisted Assumption models.
        """
        if not assumptions:
            return []

        rows = [
            {
                "id": asm.id,
                "project_id": project_id,
                "statement": asm.statement,
                "rationale": asm.rationale,
                "impact": asm.impact.value,
                "status": asm.status.value,
                "linked_requirement_ids": asm.linked_requirement_ids,
            }
            for asm in assumptions
        ]

        try:
            res = self.client.table("assumptions").upsert(rows).execute()
            return [self._row_to_assumption(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to save assumptions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to save assumptions: {exc}") from exc

    def get_assumptions(self, project_id: str) -> list[Assumption]:
        """Retrieve all assumptions for a project."""
        try:
            res = (
                self.client.table("assumptions")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return [self._row_to_assumption(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get assumptions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get assumptions: {exc}") from exc

    def update_assumption_status(
        self,
        project_id: str,
        assumption_id: str,
        status: Union[AssumptionStatus, str],
        reviewed_by: Optional[str] = None,
        reviewer_email: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
    ) -> Assumption:
        """Update an assumption's review status (e.g. ACCEPTED or REJECTED) with audit attribution.

        Args:
            project_id: Associated project UUID.
            assumption_id: Target assumption ID.
            status: New AssumptionStatus.
            reviewed_by: Optional UUID of the reviewing user.
            reviewer_email: Optional email of the reviewing user.
            reviewed_at: Optional timestamp when the decision was made.

        Returns:
            Updated Assumption model.
        """
        status_val = status.value if hasattr(status, "value") else str(status)
        rev_dt = reviewed_at or datetime.now(timezone.utc)
        update_data: dict[str, Any] = {"status": status_val}
        if reviewed_by is not None:
            update_data["reviewed_by"] = _nullable_uuid(reviewed_by)
        if reviewer_email is not None:
            update_data["reviewer_email"] = reviewer_email
        if rev_dt is not None:
            update_data["reviewed_at"] = rev_dt.isoformat()

        try:
            res = (
                self.client.table("assumptions")
                .update(update_data)
                .eq("id", assumption_id)
                .eq("project_id", project_id)
                .execute()
            )
            if not res.data:
                raise ValueError(
                    f"Assumption '{assumption_id}' not found for project '{project_id}'."
                )
            return self._row_to_assumption(res.data[0])
        except ValueError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to update assumption '%s' for project '%s': %s",
                assumption_id,
                project_id,
                exc,
            )
            raise ValueError(f"Failed to update assumption: {exc}") from exc

    def record_assumption_decision(
        self,
        project_id: str,
        assumption_id: str,
        status: Union[AssumptionStatus, str],
        reviewed_by: Optional[str] = None,
        reviewer_email: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
    ) -> Assumption:
        """Record an assumption decision with reviewer audit attribution."""
        return self.update_assumption_status(
            project_id=project_id,
            assumption_id=assumption_id,
            status=status,
            reviewed_by=reviewed_by,
            reviewer_email=reviewer_email,
            reviewed_at=reviewed_at,
        )

    # ------------------------------------------------------------------
    # Validation Issues Persistence
    # ------------------------------------------------------------------

    def save_validation_issues(
        self, project_id: str, validation_result: ValidationResult
    ) -> None:
        """Replace current validation issues with the latest validation check findings.

        Deletes existing issues for the project, then inserts new findings.
        """
        try:
            # Delete previous findings
            self.client.table("validation_issues").delete().eq(
                "project_id", project_id
            ).execute()

            if not validation_result.issues:
                return

            rows = [
                {
                    "project_id": project_id,
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "field_path": issue.field_path,
                    "entity_id": issue.entity_id,
                    "message": issue.message,
                }
                for issue in validation_result.issues
            ]
            self.client.table("validation_issues").insert(rows).execute()
        except Exception as exc:
            logger.error("Failed to save validation issues for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to persist validation issues: {exc}") from exc

    def get_latest_validation_issues(self, project_id: str) -> list[ValidationIssue]:
        """Fetch active validation issues for a project."""
        try:
            res = (
                self.client.table("validation_issues")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return [
                ValidationIssue(
                    code=r["code"],
                    severity=Severity(r["severity"]),
                    field_path=r["field_path"],
                    entity_id=r.get("entity_id"),
                    message=r["message"],
                )
                for r in (res.data or [])
            ]
        except Exception as exc:
            logger.error("Failed to get validation issues for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get validation issues: {exc}") from exc

    # ------------------------------------------------------------------
    # Audit Trail & State History
    # ------------------------------------------------------------------

    def log_state_transition(
        self, project_id: str, from_state: str, to_state: str, event: str
    ) -> None:
        """Record an entry in the state_transitions audit log table."""
        try:
            row = {
                "project_id": project_id,
                "from_state": from_state,
                "to_state": to_state,
                "event": event,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.client.table("state_transitions").insert(row).execute()
        except Exception as exc:
            logger.warning("Failed to log state transition for '%s': %s", project_id, exc)

    def get_state_history(self, project_id: str) -> list[dict[str, Any]]:
        """Retrieve the historical sequence of state transitions for a project."""
        try:
            res = (
                self.client.table("state_transitions")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=False)
                .execute()
            )
            return list(res.data or [])
        except Exception as exc:
            logger.error("Failed to get state history for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get state history: {exc}") from exc

    # ------------------------------------------------------------------
    # Deserialization Helpers (Row -> Pydantic Model)
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_project(row: dict[str, Any]) -> Project:
        return Project(
            id=str(row["id"]),
            title=row["title"],
            idea=row["idea"],
            status=ProjectStatus(row["status"]),
            input_revision=int(row.get("input_revision", 1)),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_error=row.get("last_error"),
            owner_id=row.get("owner_id"),
            owner_email=row.get("owner_email"),
        )

    @staticmethod
    def _row_to_requirement(row: dict[str, Any]) -> Requirement:
        return Requirement(
            id=row["id"],
            type=RequirementType(row["type"]),
            title=row["title"],
            statement=row["statement"],
            actor=row.get("actor"),
            outcome=row.get("outcome"),
            priority=Priority(row.get("priority", Priority.SHOULD.value)),
            acceptance_criteria=row.get("acceptance_criteria") or [],
            trace_refs=row.get("trace_refs") or [],
            confidence=float(row.get("confidence", 1.0)),
        )

    @staticmethod
    def _row_to_question(row: dict[str, Any]) -> Question:
        return Question(
            id=row["id"],
            project_id=str(row.get("project_id", "")),
            field_path=row["field_path"],
            question_text=row["question_text"],
            why_it_matters=row["why_it_matters"],
            answer_format=AnswerFormat(row["answer_format"]),
            options=row.get("options"),
            impact=int(row["impact"]),
            gap_confidence=float(row["gap_confidence"]),
            priority=float(row.get("priority", 0.0)),
            status=row.get("status", "open"),
            created_at=row.get("created_at") or datetime.now(timezone.utc),
        )

    @staticmethod
    def _row_to_answer(row: dict[str, Any]) -> Answer:
        return Answer(
            id=row["id"],
            project_id=str(row["project_id"]),
            question_id=row["question_id"],
            value=row["value"],
            answered_at=row.get("answered_at") or datetime.now(timezone.utc),
            answered_by=row.get("answered_by"),
            answerer_email=row.get("answerer_email"),
        )

    @staticmethod
    def _row_to_assumption(row: dict[str, Any]) -> Assumption:
        rev_at = row.get("reviewed_at")
        if isinstance(rev_at, str):
            try:
                rev_dt = datetime.fromisoformat(rev_at.replace("Z", "+00:00"))
            except Exception:
                rev_dt = None
        elif isinstance(rev_at, datetime):
            rev_dt = rev_at
        else:
            rev_dt = None

        return Assumption(
            id=row["id"],
            project_id=str(row.get("project_id", "")),
            statement=row["statement"],
            rationale=row["rationale"],
            impact=ImpactLevel(row["impact"]),
            status=AssumptionStatus(row.get("status", AssumptionStatus.PROPOSED.value)),
            linked_requirement_ids=row.get("linked_requirement_ids") or [],
            reviewed_by=row.get("reviewed_by"),
            reviewer_email=row.get("reviewer_email"),
            reviewed_at=rev_dt,
        )

    # ------------------------------------------------------------------
    # Source Documents & Source Chunks Persistence
    # ------------------------------------------------------------------

    def save_source_document(self, document: SourceDocument) -> SourceDocument:
        """Insert or upsert a source document record into source_documents table.

        Args:
            document: SourceDocument domain model instance.

        Returns:
            The saved SourceDocument domain model.

        Raises:
            ValueError: If database operation fails.
        """
        row = self._source_document_to_row(document)
        try:
            res = self.client.table("source_documents").upsert(row).execute()
            if not res.data:
                return document
            return self._row_to_source_document(res.data[0])
        except Exception as exc:
            logger.error("Failed to save source document '%s': %s", document.id, exc)
            raise ValueError(f"Failed to save source document: {exc}") from exc

    def save_source_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]:
        """Batch-insert or upsert source chunks into source_chunks table.

        Args:
            chunks: List of SourceChunk domain model instances.

        Returns:
            List of saved SourceChunk domain models.

        Raises:
            ValueError: If database batch operation fails.
        """
        if not chunks:
            return []

        rows = [self._source_chunk_to_row(chunk) for chunk in chunks]
        try:
            res = self.client.table("source_chunks").upsert(rows).execute()
            if not res.data:
                return chunks
            return [self._row_to_source_chunk(r) for r in res.data]
        except Exception as exc:
            logger.error("Failed to batch save source chunks: %s", exc)
            raise ValueError(f"Failed to save source chunks: {exc}") from exc

    def get_source_documents_by_project(self, project_id: str) -> list[SourceDocument]:
        """Fetch all source documents for a project ordered by created_at ASC.

        Args:
            project_id: Associated project UUID string.

        Returns:
            List of SourceDocument models.

        Raises:
            ValueError: If database query fails.
        """
        try:
            res = (
                self.client.table("source_documents")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=False)
                .execute()
            )
            return [self._row_to_source_document(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get source documents for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get source documents for project: {exc}") from exc

    def get_source_document_by_id(self, document_id: str) -> Optional[SourceDocument]:
        """Fetch a single source document by its ID.

        Args:
            document_id: Document UUID string.

        Returns:
            SourceDocument if found, None otherwise.

        Raises:
            ValueError: If database query fails.
        """
        try:
            res = (
                self.client.table("source_documents")
                .select("*")
                .eq("id", document_id)
                .execute()
            )
            if not res.data:
                return None
            return self._row_to_source_document(res.data[0])
        except Exception as exc:
            logger.error("Failed to get source document '%s': %s", document_id, exc)
            raise ValueError(f"Failed to get source document: {exc}") from exc

    def get_source_chunks_by_document(self, document_id: str) -> list[SourceChunk]:
        """Fetch all chunks belonging to a document ordered by chunk_index ASC.

        Args:
            document_id: Source document UUID string.

        Returns:
            List of SourceChunk domain models.

        Raises:
            ValueError: If database query fails.
        """
        try:
            res = (
                self.client.table("source_chunks")
                .select("*")
                .eq("document_id", document_id)
                .order("chunk_index", desc=False)
                .execute()
            )
            return [self._row_to_source_chunk(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get chunks for document '%s': %s", document_id, exc)
            raise ValueError(f"Failed to get source chunks: {exc}") from exc

    def get_source_chunks_by_project(self, project_id: str) -> list[SourceChunk]:
        """Fetch all chunks for an entire project ordered by chunk index.

        Args:
            project_id: Project UUID string.

        Returns:
            List of SourceChunk domain models.

        Raises:
            ValueError: If database query fails.
        """
        try:
            res = (
                self.client.table("source_chunks")
                .select("*")
                .eq("project_id", project_id)
                .order("chunk_index", desc=False)
                .execute()
            )
            return [self._row_to_source_chunk(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get chunks for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get project source chunks: {exc}") from exc

    @staticmethod
    def _source_document_to_row(doc: SourceDocument) -> dict[str, Any]:
        row = {
            "id": doc.id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "status": doc.status.value if isinstance(doc.status, SourceDocumentStatus) else str(doc.status),
            "storage_path": doc.storage_path,
            "error_message": doc.error_message,
            "file_size_bytes": doc.file_size_bytes,
            "uploaded_by": doc.uploaded_by,
            "uploader_email": doc.uploader_email,
        }
        if doc.created_at:
            row["created_at"] = (
                doc.created_at.isoformat()
                if isinstance(doc.created_at, datetime)
                else str(doc.created_at)
            )
        return row

    @staticmethod
    def _row_to_source_document(row: dict[str, Any]) -> SourceDocument:
        raw_status = row.get("status", "UPLOADED")
        if isinstance(raw_status, str):
            try:
                status_val = SourceDocumentStatus(raw_status.upper())
            except ValueError:
                status_val = SourceDocumentStatus.UPLOADED
        else:
            status_val = SourceDocumentStatus.UPLOADED

        return SourceDocument(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            filename=row["filename"],
            file_type=row["file_type"],
            status=status_val,
            storage_path=row.get("storage_path"),
            error_message=row.get("error_message"),
            file_size_bytes=row.get("file_size_bytes"),
            created_at=str(row["created_at"]) if row.get("created_at") else None,
            uploaded_by=row.get("uploaded_by"),
            uploader_email=row.get("uploader_email"),
        )

    @staticmethod
    def _is_valid_uuid(val: Any) -> bool:
        """Check whether val is a valid UUID string or UUID object."""
        if val is None:
            return False
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    @classmethod
    def _ensure_valid_uuid(cls, val: Any) -> str:
        """Return a valid UUID string; if val is not a UUID, generate a deterministic UUIDv5."""
        if cls._is_valid_uuid(val):
            return str(uuid.UUID(str(val)))
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(val)))

    @classmethod
    def _source_chunk_to_row(cls, chunk: SourceChunk) -> dict[str, Any]:
        chunk_uuid = cls._ensure_valid_uuid(chunk.id)
        heading = chunk.heading or getattr(chunk, "chunk_label", None)
        if not heading and chunk.id != chunk_uuid:
            heading = chunk.id

        return {
            "id": chunk_uuid,
            "document_id": cls._ensure_valid_uuid(chunk.document_id),
            "project_id": cls._ensure_valid_uuid(chunk.project_id),
            "text": chunk.text,
            "page_number": chunk.page_number,
            "heading": heading,
            "chunk_index": chunk.chunk_index,
        }

    @staticmethod
    def _row_to_source_chunk(row: dict[str, Any]) -> SourceChunk:
        return SourceChunk(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            text=row.get("text") or row.get("content") or "",
            page_number=row.get("page_number"),
            heading=row.get("heading"),
            chunk_index=int(row.get("chunk_index", 0)),
            chunk_label=row.get("heading"),
        )

    # ------------------------------------------------------------------
    # BRD Document Versions Persistence
    # ------------------------------------------------------------------

    def save_brd_version(self, brd_version: BRDDocumentVersion) -> BRDDocumentVersion:
        """Insert or upsert a BRD document version record.

        Args:
            brd_version: BRDDocumentVersion domain model.

        Returns:
            The saved BRDDocumentVersion model.

        Raises:
            ValueError: If database operation fails.
        """
        row = self._brd_version_to_row(brd_version)
        # Ensure raw docx bytes are excluded from Supabase row payload
        row.pop("docx_bytes", None)
        try:
            try:
                res = self.client.table("brd_document_versions").upsert(row).execute()
            except Exception as upsert_err:
                err_str = str(upsert_err).lower()
                if "could not find the" in err_str or "column" in err_str:
                    logger.warning("Retrying BRD version upsert with adapted column mapping: %s", upsert_err)
                    alt_row = dict(row)
                    if "version_number" in err_str:
                        alt_row["version_number"] = alt_row.pop("version", brd_version.version)
                    if brd_version.title and "title" not in alt_row:
                        alt_row["title"] = brd_version.title
                    if brd_version.status and "status" not in alt_row:
                        alt_row["status"] = brd_version.status
                    for col in ["quality_check_passed", "is_current", "prompt_version", "model_used", "input_revision", "docx_path", "title", "status"]:
                        if f"'{col}'" in err_str:
                            alt_row.pop(col, None)
                    res = self.client.table("brd_document_versions").upsert(alt_row).execute()
                else:
                    raise upsert_err

            if not res.data:
                saved = brd_version
            else:
                saved = self._row_to_brd_version(res.data[0])

            # Preserve in-memory docx_bytes on returned model instance
            if brd_version.docx_bytes and not saved.docx_bytes:
                saved.docx_bytes = brd_version.docx_bytes

            return saved
        except Exception as exc:
            logger.error("Failed to save BRD version '%s': %s", brd_version.id, exc)
            raise ValueError(f"Failed to save BRD version: {exc}") from exc

    def get_brd_versions_by_project(self, project_id: str) -> list[BRDDocumentVersion]:
        """Fetch all BRD document versions for a project ordered by version ascending.

        Args:
            project_id: Project UUID string.

        Returns:
            List of BRDDocumentVersion models.

        Raises:
            ValueError: If database query fails.
        """
        try:
            proj_uuid = self._ensure_valid_uuid(project_id)
            try:
                res = (
                    self.client.table("brd_document_versions")
                    .select("*")
                    .eq("project_id", proj_uuid)
                    .order("version", desc=False)
                    .execute()
                )
            except Exception:
                res = (
                    self.client.table("brd_document_versions")
                    .select("*")
                    .eq("project_id", proj_uuid)
                    .order("generated_at", desc=False)
                    .execute()
                )
            return [self._row_to_brd_version(r) for r in (res.data or [])]
        except Exception as exc:
            logger.error("Failed to get BRD versions for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get BRD versions for project: {exc}") from exc

    def get_latest_brd_version(self, project_id: str) -> Optional[BRDDocumentVersion]:
        """Fetch the latest/current BRD document version for a project.

        Args:
            project_id: Project UUID string.

        Returns:
            Latest BRDDocumentVersion if found, None otherwise.

        Raises:
            ValueError: If database query fails.
        """
        try:
            proj_uuid = self._ensure_valid_uuid(project_id)
            try:
                res = (
                    self.client.table("brd_document_versions")
                    .select("*")
                    .eq("project_id", proj_uuid)
                    .order("version", desc=True)
                    .limit(1)
                    .execute()
                )
            except Exception:
                res = (
                    self.client.table("brd_document_versions")
                    .select("*")
                    .eq("project_id", proj_uuid)
                    .order("generated_at", desc=True)
                    .limit(1)
                    .execute()
                )
            if not res.data:
                return None
            return self._row_to_brd_version(res.data[0])
        except Exception as exc:
            logger.error("Failed to get latest BRD version for project '%s': %s", project_id, exc)
            raise ValueError(f"Failed to get latest BRD version: {exc}") from exc

    @classmethod
    def _brd_version_to_row(cls, ver: BRDDocumentVersion) -> dict[str, Any]:
        """Convert a BRDDocumentVersion domain model to a Supabase table row."""
        row: dict[str, Any] = {
            "id": cls._ensure_valid_uuid(ver.id),
            "project_id": cls._ensure_valid_uuid(ver.project_id),
            "version": ver.version,
            "input_revision": ver.input_revision,
            "content_json": ver.content_json,
            "docx_path": ver.docx_path,
            "model_used": ver.model_used,
            "prompt_version": ver.prompt_version,
            "generated_at": (
                ver.generated_at.isoformat()
                if ver.generated_at
                else datetime.now(timezone.utc).isoformat()
            ),
            "quality_check_passed": ver.quality_check_passed,
            "is_current": ver.is_current,
        }
        return row

    @staticmethod
    def _row_to_brd_version(row: dict[str, Any]) -> BRDDocumentVersion:
        """Convert a Supabase row dictionary to a BRDDocumentVersion domain model."""
        ver_num = row.get("version") or row.get("version_number", 1)
        gen_raw = row.get("generated_at") or row.get("created_at")
        if isinstance(gen_raw, str):
            try:
                gen_dt = datetime.fromisoformat(gen_raw.replace("Z", "+00:00"))
            except Exception:
                gen_dt = datetime.now(timezone.utc)
        elif isinstance(gen_raw, datetime):
            gen_dt = gen_raw
        else:
            gen_dt = datetime.now(timezone.utc)

        content = row.get("content_json") or {}
        title = row.get("title") or content.get("title")

        return BRDDocumentVersion(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            version=int(ver_num),
            input_revision=int(row.get("input_revision", 1)),
            title=title,
            content_json=content,
            docx_path=row.get("docx_path"),
            model_used=row.get("model_used", "llama-3.3-70b-versatile"),
            prompt_version=row.get("prompt_version", "v1.0"),
            generated_at=gen_dt,
            quality_check_passed=bool(row.get("quality_check_passed", True)),
            is_current=bool(row.get("is_current", True)),
            status=row.get("status", "COMPLETED"),
        )
