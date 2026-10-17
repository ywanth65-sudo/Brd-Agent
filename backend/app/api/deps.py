"""FastAPI dependencies for injecting repository, LLM clients, and auth context.

Configured to support straightforward overriding in unit and integration tests
via `app.dependency_overrides`.
"""

from dataclasses import dataclass
from typing import Optional
import jwt
from fastapi import Header, HTTPException, status

from app import config
from app.db.repository import ProjectRepository
from app.db.supabase_client import get_supabase_client
from app.llm.llm_client import LLMClient, GeminiClient


@dataclass
class AuthenticatedUser:
    """Authenticated user representation extracted from JWT claims."""

    user_id: str
    email: Optional[str] = None
    is_demo: bool = False


DEFAULT_DEV_USER = AuthenticatedUser(
    user_id="dev-user-000",
    email="dev@example.com",
    is_demo=True,
)


def get_repository() -> ProjectRepository:
    """Dependency providing a connected ProjectRepository instance."""
    client = get_supabase_client()
    return ProjectRepository(client)


def get_llm_client() -> LLMClient:
    """Dependency providing a configured LLMClient instance."""
    return LLMClient()


# Alias for backward compatibility with existing tests and endpoints
get_gemini_client = get_llm_client


def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> AuthenticatedUser:
    """Dependency verifying Supabase JWT and extracting authenticated user claims.

    If an Authorization header is provided (format: 'Bearer <token>'), verifies
    the token with SUPABASE_JWT_SECRET (if configured) or decodes claims.
    If no header is provided and ALLOW_ANONYMOUS_DEV is True, falls back to
    DEFAULT_DEV_USER so local development and automated tests run seamlessly.
    """
    if not authorization:
        if config.ALLOW_ANONYMOUS_DEV:
            return DEFAULT_DEV_USER
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        if config.SUPABASE_JWT_SECRET:
            # Verify signature using Supabase symmetric secret (HS256)
            payload = jwt.decode(
                token,
                config.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        else:
            # In development without secret, extract claims without signature validation
            payload = jwt.decode(token, options={"verify_signature": False})

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing 'sub' claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUser(
            user_id=str(user_id),
            email=payload.get("email"),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
