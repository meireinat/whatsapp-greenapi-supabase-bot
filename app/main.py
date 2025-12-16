"""
FastAPI application entry point for the WhatsApp bot.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.constants import VERSION, APP_NAME, DEFAULT_BOT_DISPLAY_NAME
from app.routes import webhook
from app.services.gemini_client import GeminiService
from app.services.council_client import CouncilService
from app.services.hazard_knowledge import HazardKnowledgeBase
from app.services.topic_knowledge import TopicKnowledgeBase
from app.services.greenapi_client import GreenAPIClient
from app.services.intent_engine import IntentEngine
from app.services.supabase_client import SupabaseService
from app.services.container_status import ContainerStatusService
from app.services.manager_gpt_service import ManagerGPTService

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
    application.state.hazard_knowledge = HazardKnowledgeBase()
    application.state.topic_knowledge = TopicKnowledgeBase()
    application.state.container_status_service = ContainerStatusService()
    if settings.gemini_api_key:
        application.state.gemini_service = GeminiService(
            api_key=settings.gemini_api_key,
        )
    else:
        application.state.gemini_service = None
    
    # Initialize Council Service (preferred over Gemini for multi-model responses)
    if settings.openrouter_api_key:
        application.state.council_service = CouncilService(
            api_key=settings.openrouter_api_key,
        )
        logger.info("Council service initialized with OpenRouter API")
    else:
        application.state.council_service = None
        logger.info("Council service not available (OPENROUTER_API_KEY not set)")
    
    # Initialize Manager GPT Service
    if settings.openrouter_api_key:
        try:
            application.state.manager_gpt_service = ManagerGPTService(
                api_key=settings.openrouter_api_key,
            )
            logger.info("Manager GPT service initialized with OpenRouter API")
        except Exception as e:
            logger.error("Failed to initialize Manager GPT service: %s", e)
            application.state.manager_gpt_service = None
    else:
        application.state.manager_gpt_service = None
        logger.info("Manager GPT service not available (OPENROUTER_API_KEY not set)")

    try:
        yield
    finally:
        logger.info("Shutting down Green API client")
        await application.state.green_api_client.close()


app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    body = await request.body()
    logger.error(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    logger.error("Request body: %s", body.decode("utf-8", errors="replace"))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": body.decode("utf-8", errors="replace")},
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(webhook.router)

