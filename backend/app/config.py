"""Configuration management for the BRD Agent backend.

Loads environment variables, defines default LLM models, and ensures required
API keys and database credentials are present.
"""

import logging
import os
from typing import Optional
from dotenv import load_dotenv

# Load variables from .env file if present
load_dotenv()

logger = logging.getLogger("brd-agent")

# Default Supabase database configuration credentials
DEFAULT_SUPABASE_URL: str = "https://lcqkhvjzwqtiichbmcff.supabase.co"
DEFAULT_SUPABASE_SERVICE_KEY: str = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxjcWtodmp6d3F0aWljaGJtY2ZmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MjAyNzk4NiwiZXhwIjoyMTA3NjAzOTg2fQ."
    "rZvliKbkj9f3o-_aFGHHD8Phs22cmf74nuoKUGAl5Ps"
)

# Active Groq model identifier and API key (OpenAI-compatible LLM provider)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip() or os.getenv("DEMO_GROQ_API_KEY", "").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL: str = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")

if not GROQ_API_KEY or GROQ_API_KEY in ("your_groq_key_here", "your_groq_api_key_here"):
    logger.warning("WARNING: GROQ_API_KEY not configured. Extraction will require a valid key.")
    GROQ_API_KEY = ""


def has_valid_groq_api_key() -> bool:
    """Return whether a non-placeholder Groq credential is configured."""
    return bool(
        GROQ_API_KEY
        and GROQ_API_KEY not in ("your_groq_key_here", "your_groq_api_key_here")
    )

# Legacy Gemini settings (kept as unused legacy fields for reference)
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Supabase database configuration with graceful defaults
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip() or DEFAULT_SUPABASE_URL
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "").strip() or DEFAULT_SUPABASE_SERVICE_KEY
SUPABASE_JWT_SECRET: Optional[str] = os.getenv("SUPABASE_JWT_SECRET") or None
ALLOW_ANONYMOUS_DEV: bool = os.getenv("ALLOW_ANONYMOUS_DEV", "true").lower() in ("true", "1", "yes")


def get_groq_model() -> str:
    """Return the configured Groq model name."""
    return GROQ_MODEL


def get_groq_vision_model() -> str:
    """Return the configured Groq Multimodal Vision model name."""
    return GROQ_VISION_MODEL


def get_groq_api_key() -> str:
    """Return the configured Groq API key."""
    return GROQ_API_KEY


def get_gemini_model() -> str:
    """Legacy helper returning active model name."""
    return GROQ_MODEL or GEMINI_MODEL


def get_gemini_api_key() -> str:
    """Legacy helper returning active API key."""
    return GROQ_API_KEY or GEMINI_API_KEY


def validate_supabase_config() -> tuple[str, str]:
    """Validate that Supabase configuration exists when database client is accessed.

    Returns:
        tuple[str, str]: (SUPABASE_URL, SUPABASE_SERVICE_KEY)

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_SERVICE_KEY is missing.
    """
    url = os.getenv("SUPABASE_URL") or SUPABASE_URL
    key = os.getenv("SUPABASE_SERVICE_KEY") or SUPABASE_SERVICE_KEY

    if not url or not key:
        raise ValueError(
            "Supabase configuration is missing. Please create a Supabase project, "
            "copy your Project URL and service_role secret key, and set "
            "SUPABASE_URL and SUPABASE_SERVICE_KEY in your backend/.env file."
        )
    return url, key


def get_supabase_url() -> str:
    """Return verified Supabase Project URL."""
    url, _ = validate_supabase_config()
    return url


def get_supabase_service_key() -> str:
    """Return verified Supabase service_role key."""
    _, key = validate_supabase_config()
    return key
