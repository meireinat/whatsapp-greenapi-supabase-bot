"""
FastAPI application entry point for the WhatsApp bot.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes import webhook
from app.services.gemini_client import GeminiService
from app.services.greenapi_client import GreenAPIClient
from app.services.intent_engine import IntentEngine
from app.services.supabase_client import SupabaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Create and teardown singleton services used across the app.
    """
    settings = get_settings()
    logger.info("Initializing services with Green API instance %s", settings.green_api_instance_id)

    application.state.intent_engine = IntentEngine()
    application.state.supabase_service = SupabaseService(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        schema=settings.supabase_schema,
    )
    application.state.green_api_client = GreenAPIClient(
        instance_id=settings.green_api_instance_id,
        api_token=settings.green_api_token,
    )
    application.state.green_webhook_token = settings.green_api_webhook_token
    if settings.gemini_api_key:
        application.state.gemini_service = GeminiService(
            api_key=settings.gemini_api_key,
        )
    else:
        application.state.gemini_service = None

    try:
        yield
    finally:
        logger.info("Shutting down Green API client")
        await application.state.green_api_client.close()


app = FastAPI(
    title="WhatsApp Operations Bot",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(webhook.router)

