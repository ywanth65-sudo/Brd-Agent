"""Integration tests for Supabase JWT authentication verification and audit attribution."""

from datetime import datetime, timezone
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.deps import get_gemini_client, get_llm_client, get_repository
from app.llm.schemas import ExtractionResult, QuestionDraft
from app.main import app
from app.models.assumption import Assumption, AssumptionStatus, ImpactLevel
from app.models.project import Project, ProjectStatus
from app.models.question import AnswerFormat, Question
from tests.test_api_persistence import InMemoryProjectRepository


class MockLLMForAuthTests:
    def generate_structured(self, prompt: str, response_schema: type):
        if response_schema == QuestionDraft:
            return QuestionDraft(
                question_text="Could you clarify authentication requirement?",
                why_it_matters="Needed for security.",
                answer_format=AnswerFormat.TEXT,
                options=None,
            )
        if response_schema == ExtractionResult:
            return ExtractionResult(requirements=[], assumptions=[])
        raise ValueError(f"Unexpected schema: {response_schema}")


@pytest.fixture
def auth_setup():
    repo = InMemoryProjectRepository()
    mock_llm = MockLLMForAuthTests()

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm_client] = lambda: mock_llm
    app.dependency_overrides[get_gemini_client] = lambda: mock_llm

    client = TestClient(app)
    original_secret = config.SUPABASE_JWT_SECRET
    original_anon = config.ALLOW_ANONYMOUS_DEV

    yield client, repo

    config.SUPABASE_JWT_SECRET = original_secret
    config.ALLOW_ANONYMOUS_DEV = original_anon
    app.dependency_overrides.clear()


def _create_token(user_id: str, email: str, secret: str = "test-secret-hs256-key-with-more-than-32-bytes!") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_jwt_auth_valid_token_with_secret(auth_setup):
    """Valid JWT signed with configured SUPABASE_JWT_SECRET establishes user ownership."""
    client, repo = auth_setup
    secret = "supa-secret-jwt-signing-key-12345"
    config.SUPABASE_JWT_SECRET = secret

    token = _create_token(user_id="user-uuid-111", email="owner1@example.com", secret=secret)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/projects",
        json={"title": "Secured Project", "idea": "Enterprise project idea with strict auth."},
        headers=headers,
    )
    assert res.status_code == 201
    proj_data = res.json()["project"]
    assert proj_data["owner_id"] == "user-uuid-111"
    assert proj_data["owner_email"] == "owner1@example.com"

    # Confirm in repo
    stored = repo.get_project(proj_data["id"])
    assert stored.owner_id == "user-uuid-111"
    assert stored.owner_email == "owner1@example.com"


def test_jwt_auth_invalid_signature_rejected(auth_setup):
    """JWT signed with an incorrect secret is rejected with 401 Unauthorized."""
    client, _ = auth_setup
    config.SUPABASE_JWT_SECRET = "correct-signing-key"

    wrong_token = _create_token(user_id="bad-user", email="bad@example.com", secret="tampered-key")
    headers = {"Authorization": f"Bearer {wrong_token}"}

    res = client.post(
        "/projects",
        json={"title": "Unauthorized Project", "idea": "Attempting project creation with bad token."},
        headers=headers,
    )
    assert res.status_code == 401
    assert "Invalid authentication token" in res.json()["detail"]


def test_jwt_auth_malformed_header_rejected(auth_setup):
    """Malformed Authorization headers return 401."""
    client, _ = auth_setup
    config.SUPABASE_JWT_SECRET = "any-key"

    res = client.post(
        "/projects",
        json={"title": "Bad Header Project", "idea": "Attempting project creation with bad header."},
        headers={"Authorization": "Basic 12345678"},
    )
    assert res.status_code == 401
    assert "Invalid Authorization header format" in res.json()["detail"]


def test_dev_mode_token_without_secret_extracts_claims(auth_setup):
    """In development without configured secret, valid claims are still parsed gracefully."""
    client, repo = auth_setup
    config.SUPABASE_JWT_SECRET = None

    token = _create_token(user_id="dev-sub-999", email="devclaims@example.com", secret="any-arbitrary-key")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/projects",
        json={"title": "Dev Project", "idea": "Testing unverified dev token claims extraction."},
        headers=headers,
    )
    assert res.status_code == 201
    proj = res.json()["project"]
    assert proj["owner_id"] == "dev-sub-999"
    assert proj["owner_email"] == "devclaims@example.com"


def test_source_document_audit_attribution(auth_setup):
    """Source document upload records uploaded_by and uploader_email."""
    client, repo = auth_setup
    secret = "doc-upload-secret"
    config.SUPABASE_JWT_SECRET = secret

    # Create project as User 1
    t1 = _create_token("user-1", "user1@example.com", secret=secret)
    create_res = client.post(
        "/projects",
        json={"title": "Document Project", "idea": "Project to test document uploader audit."},
        headers={"Authorization": f"Bearer {t1}"},
    )
    project_id = create_res.json()["project"]["id"]

    # Upload document as User 2 (collaborator/uploader)
    t2 = _create_token("uploader-2", "uploader2@example.com", secret=secret)
    join_res = client.post(
        f"/projects/{project_id}/join",
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert join_res.status_code == 200
    files = {"file": ("requirements_v1.txt", b"System shall support multi-factor authentication.", "text/plain")}
    res_upload = client.post(
        f"/projects/{project_id}/sources",
        files=files,
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert res_upload.status_code == 201
    doc_data = res_upload.json()
    assert doc_data["uploaded_by"] == "uploader-2"
    assert doc_data["uploader_email"] == "uploader2@example.com"

    stored_doc = repo.get_source_document_by_id(doc_data["id"])
    assert stored_doc is not None
    assert stored_doc.uploaded_by == "uploader-2"
    assert stored_doc.uploader_email == "uploader2@example.com"


def test_answer_audit_attribution(auth_setup):
    """Submitting clarification answers records answered_by and answerer_email."""
    client, repo = auth_setup
    secret = "answer-audit-secret"
    config.SUPABASE_JWT_SECRET = secret

    token = _create_token("expert-3", "expert3@example.com", secret=secret)
    headers = {"Authorization": f"Bearer {token}"}

    # Setup project in AWAITING_CLARIFICATION
    create_res = client.post(
        "/projects",
        json={"title": "Q&A Project", "idea": "Project requiring domain clarification answers."},
        headers=headers,
    )
    project_id = create_res.json()["project"]["id"]
    repo.projects[project_id]["status"] = ProjectStatus.AWAITING_CLARIFICATION.value

    # Seed an open question
    q_id = "Q-TEST-001"
    repo.save_questions(
        project_id,
        [
            Question(
                id=q_id,
                project_id=project_id,
                field_path="requirements.auth",
                question_text="Which identity provider should be used?",
                why_it_matters="Core architecture decision.",
                answer_format=AnswerFormat.TEXT,
                options=None,
                impact=3,
                gap_confidence=0.9,
                status="open",
                created_at=datetime.now(timezone.utc),
            )
        ],
    )

    # Submit answer as expert-3
    ans_res = client.post(
        f"/projects/{project_id}/answers",
        json={"answers": [{"question_id": q_id, "value": "Use Okta SSO with SAML 2.0"}]},
        headers=headers,
    )
    assert ans_res.status_code == 200

    saved_answers = repo.get_answers(project_id)
    assert len(saved_answers) == 1
    assert saved_answers[0].answered_by == "expert-3"
    assert saved_answers[0].answerer_email == "expert3@example.com"


def test_assumption_decision_audit_attribution(auth_setup):
    """Deciding on an assumption records reviewed_by, reviewer_email, and reviewed_at."""
    client, repo = auth_setup
    secret = "assumption-audit-secret"
    config.SUPABASE_JWT_SECRET = secret

    token = _create_token("lead-architect-4", "architect4@example.com", secret=secret)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/projects",
        json={"title": "Assumption Project", "idea": "Project with architectural assumptions."},
        headers=headers,
    )
    project_id = create_res.json()["project"]["id"]

    asm_id = "ASM-ARCH-001"
    repo.save_assumptions(
        project_id,
        [
            Assumption(
                id=asm_id,
                project_id=project_id,
                statement="Database will use PostgreSQL with row-level security enabled.",
                rationale="Ensures multi-tenant data segregation.",
                impact=ImpactLevel.HIGH,
                status=AssumptionStatus.PROPOSED,
            )
        ],
    )

    # Reviewer accepts assumption
    res = client.post(
        f"/projects/{project_id}/assumptions/{asm_id}/decision",
        json={"decision": "accepted"},
        headers=headers,
    )
    assert res.status_code == 200
    asm_data = res.json()
    assert asm_data["status"] == AssumptionStatus.ACCEPTED.value
    assert asm_data["reviewed_by"] == "lead-architect-4"
    assert asm_data["reviewer_email"] == "architect4@example.com"
    assert asm_data["reviewed_at"] is not None

    stored_asm = repo.get_assumptions(project_id)[0]
    assert stored_asm.reviewed_by == "lead-architect-4"
    assert stored_asm.reviewer_email == "architect4@example.com"
    assert stored_asm.reviewed_at is not None


def test_project_listing_filtered_by_owner(auth_setup):
    """GET /projects returns only the projects owned by the requesting user."""
    client, _ = auth_setup
    secret = "isolation-secret"
    config.SUPABASE_JWT_SECRET = secret

    token_a = _create_token("user-alice", "alice@example.com", secret=secret)
    token_b = _create_token("user-bob", "bob@example.com", secret=secret)

    # Alice creates Project A
    res_a = client.post(
        "/projects",
        json={"title": "Alice's Mobile App", "idea": "An application solely managed by Alice."},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a.status_code == 201

    # Bob creates Project B
    res_b = client.post(
        "/projects",
        json={"title": "Bob's Cloud Portal", "idea": "A web portal solely managed by Bob."},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 201

    # Alice lists projects
    list_alice = client.get("/projects", headers={"Authorization": f"Bearer {token_a}"})
    assert list_alice.status_code == 200
    titles_alice = [p["title"] for p in list_alice.json()]
    assert "Alice's Mobile App" in titles_alice
    assert "Bob's Cloud Portal" not in titles_alice

    # Bob lists projects
    list_bob = client.get("/projects", headers={"Authorization": f"Bearer {token_b}"})
    assert list_bob.status_code == 200
    titles_bob = [p["title"] for p in list_bob.json()]
    assert "Bob's Cloud Portal" in titles_bob
    assert "Alice's Mobile App" not in titles_bob
