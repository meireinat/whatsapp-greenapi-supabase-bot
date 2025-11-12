"""
HTTP routes that integrate with the Green API webhook flow.
"""

from __future__ import annotations

import logging
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)

from app.models.greenapi import GreenWebhookPayload
from app.services.intent_engine import IntentEngine, IntentResult
from app.services.response_builder import (
    build_containers_range_response,
    build_daily_containers_response,
    build_fallback_response,
    build_vehicles_range_response,
)
from app.services.supabase_client import SupabaseService
from app.services.gemini_client import GeminiService
from app.services.greenapi_client import GreenAPIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/green", tags=["green-api"])


def get_intent_engine() -> IntentEngine:
    from app.main import app

    engine: IntentEngine = app.state.intent_engine
    return engine


def get_supabase_service() -> SupabaseService:
    from app.main import app

    service: SupabaseService = app.state.supabase_service
    return service


def get_green_api_client() -> GreenAPIClient:
    from app.main import app

    client: GreenAPIClient = app.state.green_api_client
    return client


def get_gemini_service() -> GeminiService | None:
    from app.main import app

    return app.state.gemini_service


def get_webhook_token() -> str | None:
    from app.main import app

    return getattr(app.state, "green_webhook_token", None)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Handle incoming Green API webhook notifications",
)
async def handle_webhook(
    payload: GreenWebhookPayload,
    background_tasks: BackgroundTasks,
    intent_engine: IntentEngine = Depends(get_intent_engine),
    supabase_service: SupabaseService = Depends(get_supabase_service),
    green_api_client: GreenAPIClient = Depends(get_green_api_client),
    gemini_service: GeminiService | None = Depends(get_gemini_service),
    authorization: str | None = Header(default=None),
    webhook_token: str | None = Depends(get_webhook_token),
) -> Response:
    logger.info("Webhook received: typeWebhook=%s, hasAuth=%s", 
                getattr(payload, 'typeWebhook', 'unknown'),
                authorization is not None)
    
    if webhook_token:
        if not authorization:
            logger.warning("Missing authorization header for webhook call")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        scheme, _, token = authorization.partition(" ")
        provided = token if scheme.lower() == "bearer" else authorization.strip()
        if provided != webhook_token:
            logger.warning("Invalid webhook token provided")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Only process incomingMessageReceived webhooks
    if payload.typeWebhook != "incomingMessageReceived":
        logger.info("Ignoring webhook type: %s", payload.typeWebhook)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Validate that we have the required fields for incoming messages
    if not payload.messageData or not payload.senderData:
        logger.warning("Missing messageData or senderData in incomingMessageReceived webhook")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if payload.messageData.typeMessage.lower() != "textmessage":
        logger.info("Ignoring non-text message (type=%s)", payload.messageData.typeMessage)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    chat_id = payload.senderData.chatId
    incoming_text = payload.messageData.textMessageData.textMessage if payload.messageData.textMessageData else ""
    if not incoming_text:
        logger.warning("Received text message with no text payload for chat %s", chat_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    logger.info("Received message from %s: %s", chat_id, incoming_text)
    intent: IntentResult | None = intent_engine.match(incoming_text)

    if not intent:
        if gemini_service:
            metrics = supabase_service.get_metrics_summary()
            response_text = await gemini_service.answer_question(
                question=incoming_text, metrics=metrics
            )
            if not response_text:
                response_text = build_fallback_response()
        else:
            response_text = build_fallback_response()
        background_tasks.add_task(green_api_client.send_text_message, chat_id, response_text)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    if intent.name == "daily_containers_count":
        target_date = intent.parameters["target_date"]
        count = supabase_service.get_daily_containers_count(target_date)
        response_text = build_daily_containers_response(count, target_date)
    elif intent.name == "containers_count_between":
        start_date = intent.parameters["start_date"]
        end_date = intent.parameters["end_date"]
        count = supabase_service.get_containers_count_between(start_date, end_date)
        response_text = build_containers_range_response(count, start_date, end_date)
    elif intent.name == "vehicles_count_between":
        start_date = intent.parameters["start_date"]
        end_date = intent.parameters["end_date"]
        count = supabase_service.get_vehicle_count_between(start_date, end_date)
        response_text = build_vehicles_range_response(count, start_date, end_date)
    elif intent.name == "llm_analysis":
        if not gemini_service:
            response_text = build_fallback_response()
        else:
            start_date = intent.parameters.get("start_date")
            end_date = intent.parameters.get("end_date")
            metrics = supabase_service.get_metrics_summary(
                start_date=start_date,
                end_date=end_date,
            )
            response_text = await gemini_service.answer_question(
                question=incoming_text,
                metrics=metrics,
            )
            if not response_text:
                response_text = build_fallback_response()
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Intent not implemented"
        )

    background_tasks.add_task(green_api_client.send_text_message, chat_id, response_text)
    supabase_service.log_query(
        user_phone=chat_id,
        user_text=incoming_text,
        intent=intent.name,
        parameters=dict(intent.parameters),
        response_text=response_text,
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)

