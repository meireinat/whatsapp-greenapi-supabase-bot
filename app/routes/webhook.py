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

from app.constants import (
    MAX_CONVERSATION_HISTORY,
    DEFAULT_METRICS_YEARS_BACK,
    DEFAULT_MAX_ROWS_FOR_LLM,
)
from app.models.greenapi import GreenWebhookPayload
from app.services.intent_engine import IntentEngine, IntentResult
from app.services.response_builder import (
    build_containers_range_response,
    build_daily_containers_response,
    build_fallback_response,
    build_monthly_containers_response,
    build_comparison_containers_response,
    build_vehicles_range_response,
    build_container_status_response,
)
from app.services.supabase_client import SupabaseService
from app.services.gemini_client import GeminiService
from app.services.council_client import CouncilService
from app.services.greenapi_client import GreenAPIClient, GreenAPIQuotaExceededError
from app.services.hazard_knowledge import HazardKnowledgeBase
from app.services.topic_knowledge import TopicKnowledgeBase
from app.services.container_status import ContainerStatusService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/green", tags=["green-api"])


async def send_message_with_error_handling(
    client: GreenAPIClient, chat_id: str, message: str, 
    supabase_service: SupabaseService | None = None,
    user_text: str | None = None,
    intent: str | None = None,
    intent_params: dict | None = None,
) -> None:
    """
    Send a message via Green API with proper error handling.
    Logs quota exceeded errors but doesn't crash the webhook.
    Also logs the query to Supabase even if sending fails.
    """
    send_success = False
    error_type = None
    try:
        await client.send_text_message(chat_id, message)
        logger.info("Message sent successfully to %s", chat_id)
        send_success = True
    except GreenAPIQuotaExceededError as e:
        error_type = "quota_exceeded"
        logger.error(
            "Failed to send message to %s: Green API quota exceeded. "
            "User will not receive response. Error: %s",
            chat_id,
            e,
        )
        # Don't re-raise - allow webhook to complete
        # The user won't get a response, but at least we logged it
    except Exception as e:
        error_type = "send_error"
        logger.error(
            "Failed to send message to %s: %s",
            chat_id,
            e,
            exc_info=True,
        )
        # Don't re-raise - allow webhook to complete
    
    # Log to Supabase even if sending failed (for analytics)
    if supabase_service and user_text:
        try:
            # Append error info to response if sending failed
            response_text = message
            if not send_success:
                if error_type == "quota_exceeded":
                    response_text = f"{message}\n\n[⚠️ הודעה לא נשלחה: מגבלת quota חודשי הושגה]"
                else:
                    response_text = f"{message}\n\n[⚠️ שגיאה בשליחת הודעה]"
            
            supabase_service.log_query(
                user_phone=chat_id,
                user_text=user_text,
                intent=intent or "unknown",
                parameters=intent_params or {},
                response_text=response_text,
            )
            logger.info("Query logged to Supabase for %s (send_success=%s)", chat_id, send_success)
        except Exception as e:
            logger.error("Failed to log query to Supabase: %s", e, exc_info=True)


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


def get_council_service() -> CouncilService | None:
    from app.main import app

    return getattr(app.state, "council_service", None)


def get_hazard_knowledge() -> HazardKnowledgeBase | None:
    from app.main import app

    return getattr(app.state, "hazard_knowledge", None)


def get_topic_knowledge() -> TopicKnowledgeBase | None:
    from app.main import app

    return getattr(app.state, "topic_knowledge", None)


def get_webhook_token() -> str | None:
    from app.main import app

    return getattr(app.state, "green_webhook_token", None)


def get_container_status_service() -> ContainerStatusService | None:
    from app.main import app

    return getattr(app.state, "container_status_service", None)


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
    council_service: CouncilService | None = Depends(get_council_service),
    hazard_knowledge: HazardKnowledgeBase | None = Depends(get_hazard_knowledge),
    topic_knowledge: TopicKnowledgeBase | None = Depends(get_topic_knowledge),
    container_status_service: ContainerStatusService | None = Depends(get_container_status_service),
    authorization: str | None = Header(default=None),
    webhook_token: str | None = Depends(get_webhook_token),
) -> Response:
    logger.info("=== WEBHOOK RECEIVED ===")
    logger.info("Type: %s, HasAuth: %s, Timestamp: %s", 
                getattr(payload, 'typeWebhook', 'unknown'),
                authorization is not None,
                getattr(payload, 'timestamp', 'unknown'))
    
    if webhook_token:
        if not authorization:
            logger.warning("Missing authorization header for webhook call")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        logger.info("Authorization header received: %s", authorization[:50] + "..." if len(authorization) > 50 else authorization)
        scheme, _, token = authorization.partition(" ")
        provided = token if scheme.lower() == "bearer" else authorization.strip()
        logger.info("Extracted token: %s (scheme: %s)", provided[:20] + "..." if len(provided) > 20 else provided, scheme)
        if provided != webhook_token:
            logger.warning("Invalid webhook token provided. Expected: %s, Got: %s", 
                         webhook_token[:20] + "..." if len(webhook_token) > 20 else webhook_token,
                         provided[:20] + "..." if len(provided) > 20 else provided)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        logger.info("Authorization successful")

    # Only process incomingMessageReceived webhooks
    if payload.typeWebhook != "incomingMessageReceived":
        logger.info("Ignoring webhook type: %s (not incomingMessageReceived)", payload.typeWebhook)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    
    logger.info("Processing incomingMessageReceived webhook")

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
    logger.info("Intent matched: %s (parameters: %s)", intent.name if intent else "None", intent.parameters if intent else "None")
    
    # Get conversation history for context
    conversation_history = supabase_service.get_recent_user_queries(
        user_phone=chat_id,
        limit=MAX_CONVERSATION_HISTORY,
        exclude_current=True,
    )
    if conversation_history:
        logger.info("Retrieved %d previous queries for context", len(conversation_history))
    
    # Get knowledge sections from both hazard and topic knowledge bases
    hazard_sections = (
        hazard_knowledge.build_sections(incoming_text)
        if hazard_knowledge and hazard_knowledge.is_available()
        else None
    )
    
    topic_sections = (
        topic_knowledge.build_sections(incoming_text)
        if topic_knowledge and topic_knowledge.is_available()
        else None
    )
    
    # Combine knowledge sections (hazard first, then topic)
    knowledge_sections = []
    if hazard_sections:
        knowledge_sections.extend(hazard_sections)
    if topic_sections:
        knowledge_sections.extend(topic_sections)
    
    # Use None if empty to maintain compatibility
    combined_knowledge = knowledge_sections if knowledge_sections else None

    if not intent:
        logger.info("No intent matched, using Council/Gemini or fallback")
        # Prefer Council service (multi-model with ranking) over Gemini
        import datetime as dt
        end_date = dt.date.today()
        start_date = dt.date(end_date.year - DEFAULT_METRICS_YEARS_BACK, 1, 1)
        metrics = supabase_service.get_metrics_summary(
            start_date=start_date,
            end_date=end_date,
            max_rows=DEFAULT_MAX_ROWS_FOR_LLM,
        )
        
        if council_service:
            logger.info("Council service available, fetching metrics and using multi-model approach...")
            logger.info("Metrics fetched (period: %s to %s), calling Council with question: %s", 
                       start_date.isoformat(), end_date.isoformat(), incoming_text)
            response_text = await council_service.answer_question(
                question=incoming_text,
                metrics=metrics,
                knowledge_sections=combined_knowledge,
                conversation_history=conversation_history,
            )
            logger.info("Council response: %s", response_text[:200] if response_text else "None")
            if not response_text:
                response_text = build_fallback_response()
        elif gemini_service:
            logger.info("Council service not available, using Gemini service...")
            logger.info("Metrics fetched (period: %s to %s), calling Gemini with question: %s", 
                       start_date.isoformat(), end_date.isoformat(), incoming_text)
            response_text = await gemini_service.answer_question(
                question=incoming_text,
                metrics=metrics,
                knowledge_sections=combined_knowledge,
                conversation_history=conversation_history,
            )
            logger.info("Gemini response: %s", response_text[:200] if response_text else "None")
            if not response_text:
                response_text = build_fallback_response()
        else:
            logger.info("Neither Council nor Gemini service available, using fallback")
            response_text = build_fallback_response()
        background_tasks.add_task(
            send_message_with_error_handling,
            green_api_client,
            chat_id,
            response_text,
            supabase_service,
            incoming_text,
            None,
            {},
        )
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
    elif intent.name == "containers_count_monthly":
        month = intent.parameters["month"]
        year = intent.parameters["year"]
        logger.info("Fetching monthly containers: month=%d, year=%d", month, year)
        count = supabase_service.get_containers_count_monthly(month, year)
        logger.info("Monthly containers count result: %d", count)
        
        # If count is 0, double-check with Council/Gemini (might be missing data or wrong date interpretation)
        if count == 0 and (council_service or gemini_service):
            logger.info("Count is 0, verifying with Council/Gemini for month=%d, year=%d", month, year)
            import datetime as dt
            # Fetch extended metrics for the specific year
            start_date = dt.date(year, 1, 1)
            end_date = dt.date(year, 12, 31)
            metrics = supabase_service.get_metrics_summary(
                start_date=start_date,
                end_date=end_date,
                max_rows=DEFAULT_MAX_ROWS_FOR_LLM,
            )
            
            # Prefer Council over Gemini
            if council_service:
                llm_response = await council_service.answer_question(
                    question=incoming_text,
                    metrics=metrics,
                    knowledge_sections=combined_knowledge,
                    conversation_history=conversation_history,
                )
            else:
                llm_response = await gemini_service.answer_question(
                    question=incoming_text,
                    metrics=metrics,
                    knowledge_sections=combined_knowledge,
                    conversation_history=conversation_history,
                )
            
            if llm_response and "לא מצאתי" not in llm_response and "חסר" not in llm_response.lower():
                logger.info("LLM found data, using LLM response")
                response_text = llm_response
            else:
                logger.info("LLM also found no data, using 0 count")
                response_text = build_monthly_containers_response(count, month, year)
        else:
            response_text = build_monthly_containers_response(count, month, year)
    elif intent.name == "containers_count_comparison":
        month1 = intent.parameters["month1"]
        year1 = intent.parameters["year1"]
        month2 = intent.parameters["month2"]
        year2 = intent.parameters["year2"]
        logger.info(
            "Fetching comparison: month1=%d, year1=%d vs month2=%d, year2=%d",
            month1, year1, month2, year2
        )
        comparison = supabase_service.get_containers_count_comparison(
            month1, year1, month2, year2
        )
        logger.info(
            "Comparison result: %d vs %d (difference: %d)",
            comparison["count1"], comparison["count2"], comparison["difference"]
        )
        response_text = build_comparison_containers_response(
            comparison["count1"], month1, year1,
            comparison["count2"], month2, year2,
            comparison["difference"],
        )
        logger.info("Response text: %s", response_text)
    elif intent.name == "llm_analysis":
        start_date = intent.parameters.get("start_date")
        end_date = intent.parameters.get("end_date")
        metrics = supabase_service.get_metrics_summary(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Prefer Council over Gemini
        if council_service:
            response_text = await council_service.answer_question(
                question=incoming_text,
                metrics=metrics,
                knowledge_sections=combined_knowledge,
                conversation_history=conversation_history,
            )
        elif gemini_service:
            response_text = await gemini_service.answer_question(
                question=incoming_text,
                metrics=metrics,
                knowledge_sections=combined_knowledge,
                conversation_history=conversation_history,
            )
        else:
            response_text = build_fallback_response()
        
        if not response_text:
            response_text = build_fallback_response()
    elif intent.name == "container_status_lookup":
        container_id = str(intent.parameters["container_id"])
        if not container_status_service:
            response_text = "שירות בדיקת הסטטוס אינו זמין כרגע."
        else:
            logger.info("Fetching container status for %s across all ports", container_id)
            statuses = await container_status_service.lookup(container_id)
            response_text = build_container_status_response(container_id, statuses)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Intent not implemented"
        )

    logger.info("=== PREPARING RESPONSE ===")
    logger.info("Chat ID: %s, Response length: %d chars", chat_id, len(response_text))
    logger.info("Response preview: %s", response_text[:150])
    
    # Queue message with proper error handling (logging happens inside the function)
    background_tasks.add_task(
        send_message_with_error_handling,
        green_api_client,
        chat_id,
        response_text,
        supabase_service,
        incoming_text,
        intent.name,
        dict(intent.parameters),
    )
    logger.info("Message queued for sending to %s", chat_id)
    
    logger.info("=== WEBHOOK PROCESSING COMPLETE ===")
    return Response(status_code=status.HTTP_202_ACCEPTED)

