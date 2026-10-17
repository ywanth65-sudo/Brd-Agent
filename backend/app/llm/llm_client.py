"""Client for structured LLM generation.

Provides a provider-neutral interface for structured Pydantic generation
backed by Groq API (e.g. Llama-3.3-70b-versatile).
"""

import base64
import copy
import json
import logging
import time
from typing import Any, Optional, Type, TypeVar

from groq import APIConnectionError, APIError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError

from app import config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = (
    "You are a precise JSON generation engine. You must respond with ONLY valid JSON "
    "matching the exact structure described. Do not include markdown code fences, "
    "explanations, or any text outside the JSON object."
)


def clean_schema_for_gemini(schema: dict) -> dict:
    """Legacy helper for cleaning JSON schemas (kept for backward compatibility)."""
    return copy.deepcopy(schema)


def _compact_schema_for_prompt(value: Any) -> Any:
    """Remove prose metadata from schemas to leave more context for source content."""
    if isinstance(value, dict):
        return {
            key: _compact_schema_for_prompt(item)
            for key, item in value.items()
            if key not in {"description", "title", "default"}
        }
    if isinstance(value, list):
        return [_compact_schema_for_prompt(item) for item in value]
    return value


class LLMClient:
    """LLM client generating structured Pydantic responses using the Groq API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Initialize Groq client with API credentials and model configuration.

        Args:
            api_key: Optional override for Groq API key. Defaults to config.GROQ_API_KEY.
            model_name: Optional override for model name. Defaults to config.GROQ_MODEL.
        """
        self.api_key = api_key or config.GROQ_API_KEY
        self.model_name = model_name or config.GROQ_MODEL
        self.client = Groq(api_key=self.api_key)

    def _require_api_key(self) -> None:
        """Fail before making network calls when local configuration is incomplete."""
        if not self.api_key or self.api_key in ("your_groq_key_here", "your_groq_api_key_here"):
            raise RuntimeError(
                "GROQ_API_KEY is missing or still set to a placeholder. "
                "Add a valid Groq API key to backend/.env and restart the backend."
            )

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """Strip markdown code fence wrappers (```json or ```) and surrounding whitespace."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def _call_chat_completion_with_backoff(
        self,
        messages: list[dict[str, str]],
        max_retries: int = 2,
        initial_backoff_sec: float = 2.0,
    ) -> Any:
        """Execute chat completion with exponential backoff on API-level failures.

        Retries on RateLimitError, APIConnectionError, and APIError starting with a
        2-second delay and doubling up to 2 retries (3 total attempts).
        """
        self._require_api_key()
        delay = initial_backoff_sec

        for attempt in range(max_retries + 1):
            try:
                return self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=2048,
                )
            except (RateLimitError, APIConnectionError, APIError) as api_err:
                error_text = str(api_err).lower()
                if "request too large" in error_text or "413" in error_text:
                    raise RuntimeError(
                        "The AI analysis request is too large for the configured Groq model. "
                        "Reduce the uploaded document content or run analysis on fewer source documents."
                    ) from api_err
                # If model is not found, dynamically find an available chat model on this key
                if "model_not_found" in str(api_err):
                    try:
                        available_models = [m.id for m in self.client.models.list().data]
                        preferred_fallbacks = [
                            "openai/gpt-oss-120b",
                            "qwen/qwen3.8-27b",
                            "openai/gpt-oss-20b",
                            "llama-3.3-70b-versatile",
                            "llama-3.1-70b-versatile",
                            "llama3-70b-8192",
                        ]
                        for candidate in preferred_fallbacks:
                            if candidate in available_models and candidate != self.model_name:
                                logger.warning(
                                    "Configured Groq model '%s' not accessible with this API key. "
                                    "Automatically switching to available model '%s'.",
                                    self.model_name,
                                    candidate,
                                    )
                                self.model_name = candidate
                                break
                    except Exception:
                        pass

                if attempt < max_retries:
                    logger.warning(
                        "Groq API call attempt %d failed with error: %s. "
                        "Backing off for %.1f seconds before retry...",
                        attempt + 1,
                        api_err,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2.0
                else:
                    logger.error(
                        "Groq API call failed after %d retries: %s",
                        max_retries,
                        api_err,
                    )
                    raise RuntimeError(
                        f"Groq API call failed after {max_retries} retries: {api_err}"
                    ) from api_err
            except Exception as unhandled_err:
                logger.error("Unexpected error during Groq chat completion: %s", unhandled_err)
                raise unhandled_err

    def generate_structured(self, prompt: str, response_schema: Type[T]) -> T:
        """Generate content from Groq and parse it into an instance of response_schema.

        Enforces JSON mode via Groq's response_format and appends the schema description
        to the user prompt. If JSON decoding or schema validation fails, retries once
        with a corrective follow-up message appended to the conversation.

        Args:
            prompt: Formatted prompt string instructing the model.
            response_schema: Pydantic model class to validate and return.

        Returns:
            An instance of response_schema populated with model output.

        Raises:
            RuntimeError: If the model output fails schema validation even after a correction retry.
        """
        schema_json_str = json.dumps(
            _compact_schema_for_prompt(response_schema.model_json_schema()),
            separators=(",", ":"),
        )
        user_prompt_with_schema = (
            f"{prompt}\n\n"
            f"EXPECTED JSON SCHEMA:\n"
            f"You must return a JSON object conforming strictly to the following JSON Schema:\n"
            f"{schema_json_str}\n\n"
            f"Respond with ONLY the valid JSON object matching this schema."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_with_schema},
        ]

        response = self._call_chat_completion_with_backoff(messages)
        raw_text = response.choices[0].message.content or ""
        cleaned_text = self._clean_json_text(raw_text)

        try:
            parsed_json = json.loads(cleaned_text)
            return response_schema.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError, ValueError) as parse_error:
            logger.warning(
                "Initial Groq response failed validation against %s: %s. "
                "Retrying with corrective follow-up prompt...",
                response_schema.__name__,
                parse_error,
            )

            # Append assistant's invalid response and corrective message to conversation
            messages.append({"role": "assistant", "content": raw_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"CRITICAL VALIDATION ERROR: Your previous response failed schema validation:\n"
                        f"{parse_error}\n\n"
                        f"Please fix all errors and return ONLY valid JSON matching the "
                        f"{response_schema.__name__} schema exactly."
                    ),
                }
            )

            retry_response = self._call_chat_completion_with_backoff(messages)
            retry_raw = retry_response.choices[0].message.content or ""
            retry_cleaned = self._clean_json_text(retry_raw)

            try:
                retry_parsed = json.loads(retry_cleaned)
                return response_schema.model_validate(retry_parsed)
            except Exception as second_error:
                logger.error(
                    "Groq response failed schema validation after correction retry: %s\nRaw output: %s",
                    second_error,
                    retry_raw,
                )
                raise RuntimeError(
                    f"Failed to generate valid {response_schema.__name__} from Groq after retry. "
                    f"Validation error: {second_error}. Raw output: {retry_raw}"
                ) from second_error

    def transcribe_image(self, image_bytes: bytes, mime_type: str) -> str:
        """Transcribe a whiteboard photo, architecture diagram, or handwritten note into Markdown.

        Base64-encodes image_bytes, sends payload with data URI to Groq Multimodal Vision model,
        and returns detailed structured Markdown.

        Args:
            image_bytes: Raw binary bytes of the image file.
            mime_type: MIME type of the image (e.g. 'image/png', 'image/jpeg', 'image/webp').

        Returns:
            Extracted detailed Markdown text transcription.
        """
        self._require_api_key()
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_str}"
        prompt = (
            "You are an expert technical business analyst and OCR transcription specialist. "
            "Transcribe this whiteboard photo or architecture diagram into structured, detailed Markdown. "
            "Capture all handwritten notes, system boxes, workflow flows, actors, requirements, bullets, "
            "and constraints. Do not summarize or omit technical specifics; preserve all diagrams as text "
            "flowcharts (e.g. A -> B)."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                ],
            },
        ]

        vision_model = getattr(config, "GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
        delay = 2.0
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=vision_model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4096,
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, APIConnectionError, APIError) as api_err:
                err_msg = str(api_err).lower()
                if (
                    "model_not_found" in err_msg
                    or "decommissioned" in err_msg
                    or "not supported" in err_msg
                ) and attempt < max_retries:
                    preferred_vision_fallbacks = [
                        "qwen/qwen3.8-27b",
                        "meta-llama/llama-4-scout-17b-16e-instruct",
                    ]
                    for candidate in preferred_vision_fallbacks:
                        if candidate != vision_model:
                            logger.warning(
                                "Groq vision model '%s' unavailable (%s). Switching to fallback vision model '%s'.",
                                vision_model,
                                api_err,
                                candidate,
                            )
                            vision_model = candidate
                            break

                if attempt < max_retries:
                    logger.warning(
                        "Groq Vision API call attempt %d failed: %s. Backing off for %.1f seconds...",
                        attempt + 1,
                        api_err,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2.0
                else:
                    logger.error(
                        "Groq Vision API call failed after %d retries: %s",
                        max_retries,
                        api_err,
                    )
                    raise RuntimeError(
                        f"Groq Vision API call failed after {max_retries} retries: {api_err}"
                    ) from api_err
            except Exception as unhandled_err:
                logger.error("Unexpected error during Groq Vision chat completion: %s", unhandled_err)
                raise unhandled_err


# Backward compatibility alias
GeminiClient = LLMClient
