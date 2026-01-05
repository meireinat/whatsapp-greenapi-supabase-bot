"""
Configuration utilities for the WhatsApp bot service.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from app.constants import DEFAULT_BOT_DISPLAY_NAME


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    green_api_instance_id: str
    green_api_token: str
    green_api_webhook_token: Optional[str] = None
    supabase_url: str
    supabase_service_role_key: str
    supabase_schema: Optional[str] = None
    bot_display_name: str = DEFAULT_BOT_DISPLAY_NAME
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_cloud_project_number: Optional[str] = None
    notebooklm_location: str = "global"
    notebooklm_endpoint_location: str = "global"
    notebooklm_notebook_id: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    """
    Load settings from environment variables.

    Uses python-dotenv to support local development with `.env` files.
    """
    load_dotenv()
    credentials = _load_credentials_file()

    try:
        return Settings(
            green_api_instance_id=_require_env("GREEN_API_INSTANCE_ID", credentials),
            green_api_token=_require_env("GREEN_API_TOKEN", credentials),
            green_api_webhook_token=_optional_env(
                "GREEN_API_WEBHOOK_TOKEN", credentials
            ),
            supabase_url=_require_env("SUPABASE_URL", credentials),
            supabase_service_role_key=_require_env(
                "SUPABASE_SERVICE_ROLE_KEY", credentials
            ),
            supabase_schema=_safe_schema_env(credentials),
            bot_display_name=os.getenv("BOT_DISPLAY_NAME", DEFAULT_BOT_DISPLAY_NAME),
            gemini_api_key=_optional_env("GEMINI_API_KEY", credentials),
            openrouter_api_key=_optional_env("OPENROUTER_API_KEY", credentials),
            openai_api_key=_optional_env("OPENAI_API_KEY", credentials),
            google_cloud_project_number=_optional_env("GOOGLE_CLOUD_PROJECT_NUMBER", credentials),
            notebooklm_location=os.getenv("NOTEBOOKLM_LOCATION", "global"),
            notebooklm_endpoint_location=os.getenv("NOTEBOOKLM_ENDPOINT_LOCATION", "global"),
            notebooklm_notebook_id=_optional_env("NOTEBOOKLM_NOTEBOOK_ID", credentials),
        )
    except (ValidationError, KeyError) as exc:
        missing = ", ".join(sorted(_missing_keys()))
        raise RuntimeError(
            "Missing required environment variables. "
            f"Ensure the following keys are defined: {missing}"
        ) from exc


def _require_env(name: str, credentials: dict[str, str] | None = None) -> str:
    credentials = credentials or {}
    key_map = {
        "SUPABASE_URL": "supabase_url",
        "SUPABASE_SERVICE_ROLE_KEY": "supabase_service_role_key",
        "GREEN_API_INSTANCE_ID": "green_api_instance_id",
        "GREEN_API_TOKEN": "green_api_token",
    }

    value = os.getenv(name) or credentials.get(key_map.get(name, name.lower()))
    if not value:
        raise KeyError(name)
    return value


def _missing_keys() -> set[str]:
    credentials = _load_credentials_file()
    required = {
        "GREEN_API_INSTANCE_ID",
        "GREEN_API_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
    }
    key_map = {
        "SUPABASE_URL": "supabase_url",
        "SUPABASE_SERVICE_ROLE_KEY": "supabase_service_role_key",
        "GREEN_API_INSTANCE_ID": "green_api_instance_id",
        "GREEN_API_TOKEN": "green_api_token",
    }

    missing: set[str] = set()
    for key in required:
        mapped = key_map.get(key, key.lower())
        if not (os.getenv(key) or credentials.get(mapped)):
            missing.add(key)
    return missing


def _optional_env(name: str, credentials: dict[str, str] | None = None) -> Optional[str]:
    credentials = credentials or {}
    key_map = {
        "GEMINI_API_KEY": "gemini_api_key",
        "GREEN_API_WEBHOOK_TOKEN": "green_api_webhook_token",
        "OPENROUTER_API_KEY": "openrouter_api_key",
        "OPENAI_API_KEY": "openai_api_key",
    }
    return os.getenv(name) or credentials.get(key_map.get(name, name.lower()))


def _safe_schema_env(credentials: dict[str, str] | None = None) -> Optional[str]:
    """
    Load SUPABASE_SCHEMA and validate it's ASCII-only to avoid encoding errors.
    Returns None always to avoid encoding issues with Supabase Python client.
    
    Note: Supabase Python client's schema() method is not supported and causes
    UnicodeEncodeError when schema contains non-ASCII characters. We always
    use the default schema (usually 'public').
    """
    credentials = credentials or {}
    schema = os.getenv("SUPABASE_SCHEMA") or credentials.get("supabase_schema")
    if not schema:
        return None
    
    # Always return None to avoid encoding issues
    # Supabase Python client doesn't support schema() method properly
    import logging
    logger = logging.getLogger(__name__)
    try:
        schema.encode("ascii")
        logger.info(
            "SUPABASE_SCHEMA is set but will not be used "
            "(schema() not supported by Supabase Python client)"
        )
    except UnicodeEncodeError:
        logger.warning(
            "SUPABASE_SCHEMA contains non-ASCII characters; "
            "schema scoping will be disabled. Value: %s",
            schema[:50] if len(schema) > 50 else schema,
        )
    return None  # Always return None to avoid encoding issues


def _load_credentials_file() -> dict[str, str]:
    credentials_path = Path(__file__).resolve().parent.parent / "config" / "supabase_credentials.json"
    if not credentials_path.exists():
        return {}

    try:
        with credentials_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Failed to read Supabase credentials file at {credentials_path}"
        ) from exc

