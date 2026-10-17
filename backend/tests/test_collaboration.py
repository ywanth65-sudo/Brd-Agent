"""Unit tests for User Profile management, Project Collaboration, and Sharing."""

from datetime import datetime, timezone
from typing import Any
import jwt
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.deps import get_gemini_client, get_llm_client, get_repository
from app.llm.prompts import ChatTurnEvaluation
from app.main import app
from app.models.project import Project, ProjectStatus
from tests.test_api_persistence import InMemoryProjectRepository


class MockLLMClient:
    def __init__(self) -> None:
        self.last_prompt: str = ""

    def generate_structured(self, prompt: str, response_schema: type) -> Any:
        self.last_prompt = prompt
        if response_schema == ChatTurnEvaluation:
            return ChatTurnEvaluation(
                answered_question_id=None,
                extracted_answer=None,
                reply="Hello! I acknowledge your collaborative input.",
            )
        raise ValueError(f"Unexpected schema: {response_schema}")


def _create_token(user_id: str, email: str, secret: str = "test-secret-hs256-key-with-more-than-32-bytes!") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def collab_setup():
    repo = InMemoryProjectRepository()
    mock_llm = MockLLMClient()

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm_client] = lambda: mock_llm
    app.dependency_overrides[get_gemini_client] = lambda: mock_llm

    client = TestClient(app)
    secret = "secret-key-hs256-collaboration-tests!"
    config.SUPABASE_JWT_SECRET = secret

    yield client, repo, mock_llm, secret

    config.SUPABASE_JWT_SECRET = ""
    app.dependency_overrides.clear()


def test_user_profile_crud(collab_setup):
    """Verify fetching initial profile and updating full_name and role_title."""
    client, repo, _, secret = collab_setup
    token = _create_token("user-profile-01", "dev_alice@example.com", secret)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initial GET /user/profile when no row in profiles
    res = client.get("/user/profile", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "user-profile-01"
    assert data["email"] == "dev_alice@example.com"
    assert data["full_name"] is None

    # 2. PUT /user/profile
    update_res = client.put(
        "/user/profile",
        headers=headers,
        json={
            "full_name": "Alice Smith",
            "role_title": "Lead Enterprise Architect",
            "avatar_url": "https://example.com/avatar/alice.png",
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["full_name"] == "Alice Smith"
    assert updated_data["role_title"] == "Lead Enterprise Architect"
    assert updated_data["avatar_url"] == "https://example.com/avatar/alice.png"

    # 3. GET /user/profile reflects updated data
    refetch_res = client.get("/user/profile", headers=headers)
    assert refetch_res.status_code == 200
    assert refetch_res.json()["full_name"] == "Alice Smith"


def test_join_project_and_collaborator_listing(collab_setup):
    """Verify a non-owner joining a project via /join appears in /projects for that collaborator."""
    client, repo, _, secret = collab_setup
    owner_token = _create_token("owner-uuid-1", "owner@example.com", secret)
    collab_token = _create_token("collab-uuid-2", "collab@example.com", secret)

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    collab_headers = {"Authorization": f"Bearer {collab_token}"}

    # 1. Owner creates project
    create_res = client.post(
        "/projects",
        headers=owner_headers,
        json={"title": "Cloud Migration BRD", "idea": "Enterprise migration from AWS to GCP."},
    )
    assert create_res.status_code == 201
    proj_id = create_res.json()["project"]["id"]

    # 2. Before joining, collab user does not see the project in their listing
    list_before = client.get("/projects", headers=collab_headers)
    assert list_before.status_code == 200
    assert not any(p["id"] == proj_id for p in list_before.json())

    # 3. Collab user joins via POST /projects/{project_id}/join
    join_res = client.post(f"/projects/{proj_id}/join", headers=collab_headers)
    assert join_res.status_code == 200
    joined_data = join_res.json()
    assert joined_data["id"] == proj_id
    assert joined_data["is_owner"] is False
    assert joined_data["collaborator_count"] == 1

    # 4. Collab user now sees the project in GET /projects
    list_after = client.get("/projects", headers=collab_headers)
    assert list_after.status_code == 200
    matching = [p for p in list_after.json() if p["id"] == proj_id]
    assert len(matching) == 1
    assert matching[0]["is_owner"] is False

    # 5. Owner also sees project with is_owner == True and collaborator_count == 1
    owner_list = client.get("/projects", headers=owner_headers)
    owner_proj = [p for p in owner_list.json() if p["id"] == proj_id][0]
    assert owner_proj["is_owner"] is True
    assert owner_proj["collaborator_count"] == 1


def test_collaborators_management_and_removal(collab_setup):
    """Verify listing collaborators and owner-only removal."""
    client, repo, _, secret = collab_setup
    owner_token = _create_token("owner-uuid-2", "boss@example.com", secret)
    collab1_token = _create_token("collab-uuid-3", "editor@example.com", secret)
    collab2_token = _create_token("collab-uuid-4", "guest@example.com", secret)

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    collab1_headers = {"Authorization": f"Bearer {collab1_token}"}
    collab2_headers = {"Authorization": f"Bearer {collab2_token}"}

    # Setup profile for collab1
    client.put(
        "/user/profile",
        headers=collab1_headers,
        json={"full_name": "Edward Editor", "role_title": "Senior BA"},
    )

    # 1. Owner creates project
    proj = client.post(
        "/projects",
        headers=owner_headers,
        json={"title": "Data Governance Portal", "idea": "Unified data catalog and compliance tracker."},
    ).json()["project"]
    pid = proj["id"]

    # 2. Both collaborators join
    client.post(f"/projects/{pid}/join", headers=collab1_headers)
    client.post(f"/projects/{pid}/join", headers=collab2_headers)

    # 3. GET /projects/{id}/collaborators
    collabs_res = client.get(f"/projects/{pid}/collaborators", headers=owner_headers)
    assert collabs_res.status_code == 200
    collabs = collabs_res.json()
    assert len(collabs) == 2
    # Verify profile full_name enriched
    edward = next((c for c in collabs if c["user_id"] == "collab-uuid-3"), None)
    assert edward is not None
    assert edward["full_name"] == "Edward Editor"
    assert edward["role"] == "editor"

    # 4. Collab1 attempts to remove Collab2 -> 403 Forbidden
    forbidden_res = client.delete(
        f"/projects/{pid}/collaborators/collab-uuid-4",
        headers=collab1_headers,
    )
    assert forbidden_res.status_code == 403
    assert "Only the project owner" in forbidden_res.json()["detail"]

    # 5. Owner removes Collab2 -> 200 OK
    remove_res = client.delete(
        f"/projects/{pid}/collaborators/collab-uuid-4",
        headers=owner_headers,
    )
    assert remove_res.status_code == 200
    assert remove_res.json()["status"] == "removed"

    # Verify only 1 collaborator remains
    collabs_after = client.get(f"/projects/{pid}/collaborators", headers=owner_headers).json()
    assert len(collabs_after) == 1
    assert collabs_after[0]["user_id"] == "collab-uuid-3"


def test_owner_invites_requested_role_and_recipient_accepts_once(collab_setup):
    client, repo, _, secret = collab_setup
    owner_token = _create_token("owner-invite-1", "owner@example.com", secret)
    invitee_token = _create_token("viewer-1", "viewer@example.com", secret)
    wrong_token = _create_token("wrong-recipient-1", "wrong@example.com", secret)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}
    wrong_headers = {"Authorization": f"Bearer {wrong_token}"}

    project = client.post(
        "/projects",
        headers=owner_headers,
        json={"title": "Invitation Project", "idea": "Collaborator workflow."},
    ).json()["project"]
    project_id = project["id"]

    invite = client.post(
        f"/projects/{project_id}/invitations",
        headers=owner_headers,
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert invite.status_code == 200
    invitation = invite.json()
    assert invitation["role"] == "viewer"

    listed = client.get(f"/projects/{project_id}/invitations", headers=owner_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["invitee_email"] == "viewer@example.com"

    pending = client.get("/user/invitations", headers=invitee_headers)
    assert pending.status_code == 200
    assert pending.json()[0]["role"] == "viewer"

    wrong_accept = client.post(
        f"/invitations/{invitation['id']}/accept",
        headers=wrong_headers,
    )
    assert wrong_accept.status_code == 403

    accepted = client.post(
        f"/invitations/{invitation['id']}/accept",
        headers=invitee_headers,
    )
    assert accepted.status_code == 200
    assert repo.get_collaborators(project_id)[0]["role"] == "viewer"

    viewer_write = client.post(
        f"/projects/{project_id}/sources",
        headers=invitee_headers,
        files={"file": ("notes.txt", b"viewer must not write", "text/plain")},
    )
    assert viewer_write.status_code == 403

    duplicate_accept = client.post(
        f"/invitations/{invitation['id']}/accept",
        headers=invitee_headers,
    )
    assert duplicate_accept.status_code == 400
    assert len(repo.get_collaborators(project_id)) == 1


def test_invitation_authorization_and_validation(collab_setup):
    client, _, _, secret = collab_setup
    owner_token = _create_token("owner-invite-2", "owner2@example.com", secret)
    non_owner_token = _create_token("non-owner-invite-2", "other@example.com", secret)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    non_owner_headers = {"Authorization": f"Bearer {non_owner_token}"}

    project = client.post(
        "/projects",
        headers=owner_headers,
        json={"title": "Protected Invitations", "idea": "Authorization checks."},
    ).json()["project"]
    project_id = project["id"]

    forbidden = client.post(
        f"/projects/{project_id}/invitations",
        headers=non_owner_headers,
        json={"email": "person@example.com", "role": "editor"},
    )
    assert forbidden.status_code == 403

    invalid_role = client.post(
        f"/projects/{project_id}/invitations",
        headers=owner_headers,
        json={"email": "person@example.com", "role": "admin"},
    )
    assert invalid_role.status_code == 422

    invalid_email = client.post(
        f"/projects/{project_id}/invitations",
        headers=owner_headers,
        json={"email": "not-an-email", "role": "editor"},
    )
    assert invalid_email.status_code == 400


def test_chat_sender_prefix_with_user_profile(collab_setup):
    """Verify chat input context prefixes the sender's full_name and role_title."""
    client, repo, mock_llm, secret = collab_setup
    token = _create_token("chat-user-uuid", "carol@example.com", secret)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Set user profile
    client.put(
        "/user/profile",
        headers=headers,
        json={"full_name": "Carol Danvers", "role_title": "Security Lead"},
    )

    # 2. Create project
    proj = client.post(
        "/projects",
        headers=headers,
        json={"title": "Zero Trust Security", "idea": "Enterprise IAM platform with RBAC."},
    ).json()["project"]

    # 3. Send chat message
    chat_res = client.post(
        f"/projects/{proj['id']}/chat",
        headers=headers,
        json={"message": "All database connections must be encrypted with TLS 1.3."},
    )
    assert chat_res.status_code == 200

    # 4. Check prompt passed to LLM
    assert mock_llm.last_prompt != ""
    assert "[Sender: Carol Danvers (Security Lead)]:" in mock_llm.last_prompt
    assert "All database connections must be encrypted with TLS 1.3." in mock_llm.last_prompt


def test_chat_message_persistence_and_history(collab_setup):
    """Verify user message and assistant reply are saved and retrieved via /chat/history."""
    client, repo, mock_llm, secret = collab_setup
    token = _create_token("chat-persist-user", "diana@example.com", secret)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Set user profile
    client.put(
        "/user/profile",
        headers=headers,
        json={"full_name": "Diana Prince", "role_title": "Solutions Architect"},
    )

    # 2. Create project
    proj = client.post(
        "/projects",
        headers=headers,
        json={"title": "Cloud Migration Hub", "idea": "Automated lift-and-shift pipeline."},
    ).json()["project"]
    pid = proj["id"]

    # 3. Post a clarification chat turn
    chat_res = client.post(
        f"/projects/{pid}/chat",
        headers=headers,
        json={"message": "We need 99.99% uptime for the payment gateway."},
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["reply"] == "Hello! I acknowledge your collaborative input."

    # 4. Fetch chat history
    hist_res = client.get(f"/projects/{pid}/chat/history", headers=headers)
    assert hist_res.status_code == 200
    messages = hist_res.json()["messages"]
    assert len(messages) == 2

    # Verify user message
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["sender_id"] == "chat-persist-user"
    assert user_msg["sender_email"] == "diana@example.com"
    assert user_msg["sender_name"] == "Diana Prince"
    assert user_msg["content"] == "We need 99.99% uptime for the payment gateway."
    assert user_msg["created_at"] != ""

    # Verify assistant message
    bot_msg = messages[1]
    assert bot_msg["role"] == "assistant"
    assert bot_msg["sender_id"] is None
    assert bot_msg["sender_email"] == "ai@brdagent.local"
    assert bot_msg["sender_name"] == "BRD Assistant"
    assert bot_msg["content"] == "Hello! I acknowledge your collaborative input."
    assert bot_msg["created_at"] != ""


def test_project_invitation_lifecycle(collab_setup):
    """Verify owner invitation creation, non-owner protection, and acceptance workflow."""
    client, repo, _, secret = collab_setup
    owner_token = _create_token("owner-uuid-inv", "inv_owner@example.com", secret)
    invitee_token = _create_token("invitee-uuid-inv", "invitee_user@example.com", secret)
    stranger_token = _create_token("stranger-uuid-inv", "stranger@example.com", secret)

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    # 1. Owner creates project
    proj = client.post(
        "/projects",
        headers=owner_headers,
        json={"title": "Team Collaboration Suite", "idea": "Real-time collaborative editing tool."},
    ).json()["project"]
    pid = proj["id"]

    # 2. Stranger attempts to invite someone -> 403 Forbidden
    forbidden_invite = client.post(
        f"/projects/{pid}/invitations",
        headers=stranger_headers,
        json={"email": "somebody@example.com", "role": "editor"},
    )
    assert forbidden_invite.status_code == 403
    assert "Only the project owner" in forbidden_invite.json()["detail"]

    # 3. Owner invites invitee
    invite_res = client.post(
        f"/projects/{pid}/invitations",
        headers=owner_headers,
        json={"email": "Invitee_User@Example.com", "role": "editor"},
    )
    assert invite_res.status_code == 200
    invite_data = invite_res.json()
    assert invite_data["project_id"] == pid
    assert invite_data["invitee_email"] == "invitee_user@example.com"
    assert invite_data["inviter_email"] == "inv_owner@example.com"
    assert invite_data["status"] == "pending"
    assert invite_data["role"] == "editor"
    inv_id = invite_data["id"]

    # 4. Invitee checks pending invitations via /user/invitations
    user_invs_res = client.get("/user/invitations", headers=invitee_headers)
    assert user_invs_res.status_code == 200
    pending_list = user_invs_res.json()
    assert len(pending_list) == 1
    assert pending_list[0]["id"] == inv_id
    assert pending_list[0]["project_title"] == "Team Collaboration Suite"

    # 5. Stranger attempts to accept invitee's invitation -> 403 Forbidden
    stranger_accept = client.post(
        f"/invitations/{inv_id}/accept",
        headers=stranger_headers,
    )
    assert stranger_accept.status_code == 403
    assert "does not match" in stranger_accept.json()["detail"].lower()

    # 6. Invitee accepts invitation via /invitations/{id}/accept
    accept_res = client.post(
        f"/invitations/{inv_id}/accept",
        headers=invitee_headers,
    )
    assert accept_res.status_code == 200
    accepted_proj = accept_res.json()
    assert accepted_proj["id"] == pid
    assert accepted_proj["collaborator_count"] == 1

    # 7. Check that invitee is now a collaborator
    collabs = client.get(f"/projects/{pid}/collaborators", headers=owner_headers).json()
    assert any(c["user_id"] == "invitee-uuid-inv" for c in collabs)

    # 8. Pending invitations list is now empty for invitee
    empty_invs_res = client.get("/user/invitations", headers=invitee_headers)
    assert empty_invs_res.status_code == 200
    assert len(empty_invs_res.json()) == 0
