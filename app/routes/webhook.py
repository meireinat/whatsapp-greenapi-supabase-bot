"""
HTTP routes that integrate with the Green API webhook flow.
"""

from __future__ import annotations

import logging
import datetime as dt
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
from app.services.manager_gpt_service import ManagerGPTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/green", tags=["green-api"])


# Greeting configuration
GREETING_TEXT = "שלום אני בוט נמלי"
NEW_CONVERSATION_THRESHOLD_SECONDS = 60 * 60  # 1 hour


# Determine whether we should treat this message as the start of a new conversation
def _should_add_greeting(conversation_history: list[dict] | None) -> bool:
    """
    Returns True if this looks like the first message in a new conversation
    (no history, or last message was more than NEW_CONVERSATION_THRESHOLD_SECONDS ago).
    """
    try:
        if not conversation_history:
            # No history at all -> definitely a new conversation
            return True

        last_entry = conversation_history[-1]
        created_at = last_entry.get("created_at")
        if not created_at:
            return False

        # Supabase timestamps are ISO strings, often with 'Z' suffix
        created_str = str(created_at)
        if created_str.endswith("Z"):
            created_str = created_str.replace("Z", "+00:00")

        last_dt = dt.datetime.fromisoformat(created_str)
        if last_dt.tzinfo is None:
            # Assume UTC if timezone is not present
            last_dt = last_dt.replace(tzinfo=dt.timezone.utc)

        now_utc = dt.datetime.now(dt.timezone.utc)
        diff_seconds = (now_utc - last_dt).total_seconds()
        return diff_seconds > NEW_CONVERSATION_THRESHOLD_SECONDS
    except Exception as e:
        logger.error("Failed to determine if greeting is needed: %s", e, exc_info=True)
        return False


def _maybe_prefix_greeting(
    response_text: str, conversation_history: list[dict] | None
) -> str:
    """
    Prefix the response with a standard greeting if this is a new conversation.
    """
    if _should_add_greeting(conversation_history):
        return f"{GREETING_TEXT}\n{response_text}"
    return response_text


# Static template mappings for short codes (e.g., WhatsApp quick replies)
SWE_TEMPLATE_MAP: dict[str, str] = {
    # SWE001: monthly container count for a specific month (here: January 2024)
    # This is mapped to a wording that our monthly intent reliably recognizes.
    "{{SWE001}}": "כמה מכולות הנמל עשה בינואר 2024",
}


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


def get_manager_gpt_service() -> ManagerGPTService | None:
    from app.main import app

    return getattr(app.state, "manager_gpt_service", None)


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
    manager_gpt_service: ManagerGPTService | None = Depends(get_manager_gpt_service),
    authorization: str | None = Header(default=None),
    webhook_token: str | None = Depends(get_webhook_token),
) -> Response:
    # Ensure datetime alias is available inside the function scope (avoids shadowing issues)
    import datetime as dt

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

    # Support both textMessage and extendedTextMessage (both contain text in textMessageData)
    message_type_lower = payload.messageData.typeMessage.lower()
    if message_type_lower not in ("textmessage", "extendedtextmessage"):
        logger.info("Ignoring non-text message (type=%s)", payload.messageData.typeMessage)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    chat_id = payload.senderData.chatId
    incoming_text = payload.messageData.textMessageData.textMessage if payload.messageData.textMessageData else ""
    if not incoming_text:
        logger.warning("Received text message with no text payload for chat %s", chat_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Map short template codes (like {{SWE001}}) to full user-facing questions
    original_text = incoming_text
    mapped_text = SWE_TEMPLATE_MAP.get(incoming_text.strip())
    if mapped_text:
        logger.info("Mapped template code '%s' to full question: %s", original_text, mapped_text)
        incoming_text = mapped_text

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
        end_date = dt.date.today()
        start_date = dt.date(end_date.year - DEFAULT_METRICS_YEARS_BACK, 1, 1)
        metrics = supabase_service.get_metrics_summary(
            start_date=start_date,
            end_date=end_date,
            max_rows=DEFAULT_MAX_ROWS_FOR_LLM,
        )
        
        try:
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
                if not response_text or not response_text.strip():
                    logger.warning("Council returned empty response, using fallback")
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
                if not response_text or not response_text.strip():
                    logger.warning("Gemini returned empty response, using fallback")
                    response_text = build_fallback_response()
            else:
                logger.info("Neither Council nor Gemini service available, using fallback")
                response_text = build_fallback_response()
        except Exception as e:
            logger.error("Error calling LLM service: %s", e, exc_info=True)
            response_text = build_fallback_response()
        
        # Ensure we always have a response
        if not response_text or not response_text.strip():
            logger.warning("Response is empty after all attempts, using fallback")
            response_text = build_fallback_response()

        # Add greeting prefix if this is a new conversation
        response_text = _maybe_prefix_greeting(response_text, conversation_history)
        
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
    elif intent.name == "manager_question":
        question = str(intent.parameters["question"])
        if not manager_gpt_service:
            logger.warning("Manager GPT service not available, using fallback")
            response_text = build_fallback_response()
        else:
            logger.info("Routing manager question to Manager GPT: %s", question)
            try:
                response_text = await manager_gpt_service.answer_manager_question(question)
                if not response_text or not response_text.strip():
                    response_text = build_fallback_response()
            except Exception as e:
                logger.error("Error calling Manager GPT service: %s", e, exc_info=True)
                response_text = build_fallback_response()
    elif intent.name == "monthly_containers_graph":
        # Graph of containers per month – last year, Ashdod port (by KMUT over time)
        logger.info("Building monthly containers graph (last year, Ashdod, bar)")
        series = supabase_service.get_monthly_containers_series_last_year()
        if not series:
            response_text = "לא הצלחתי לבנות גרף כרגע (אין נתונים חודשיים זמינים)."
        else:
            # Prepare labels and data for QuickChart
            labels = [f"{item['year']}-{item['month']:02d}" for item in series]
            data = [int(item["count"] or 0) for item in series]

            chart_config = {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": "מכולות לחודש (נמל אשדוד)",
                            "data": data,
                            "backgroundColor": "rgba(52, 152, 219, 0.7)",
                            "borderColor": "rgba(41, 128, 185, 1.0)",
                            "borderWidth": 1,
                        }
                    ],
                },
                "options": {
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "כמות מכולות לפי חודש – שנה אחרונה (נמל אשדוד)",
                        },
                        "legend": {"display": False},
                    },
                    "scales": {
                        "x": {
                            "title": {"display": True, "text": "חודש"},
                        },
                        "y": {
                            "title": {"display": True, "text": "מספר מכולות"},
                            "beginAtZero": True,
                        },
                    },
                },
            }

            import json, urllib.parse

            chart_url = (
                "https://quickchart.io/chart?c="
                + urllib.parse.quote(json.dumps(chart_config), safe="")
            )

            response_text = (
                "להלן גרף כמות המכולות לפי חודש בשנה האחרונה (נמל אשדוד):\n"
                f"{chart_url}\n\n"
                "אם הקישור לא נפתח, ניתן להעתיק אותו לדפדפן."
            )
    elif intent.name == "procedure_question":
        # Questions about procedures / operational queue rules.
        # ב-WhatsApp אי אפשר לפתוח אוטומטית את NotebookLM, לכן שולחים למשתמש הנחיה ברורה יחד עם הקישור והטקסט המדויק של השאלה.
        question = str(intent.parameters.get("question") or incoming_text)
        notebook_id = "66688b34-ca77-4097-8ac8-42ca8285681f"
        notebook_url = f"https://notebooklm.google.com/notebook/{notebook_id}"

        logger.info(
            "Procedure question detected, directing user to NotebookLM. Question: %s",
            question,
        )

        response_text = (
            "זאת שאלה על נהלים / תור תפעולי ולכן מופנית ל‑NotebookLM, שבו נמצאים המסמכים המלאים.\n\n"
            "כדי לקבל תשובה מדויקת:\n"
            f"1. פתח את הקישור: {notebook_url}\n"
            "2. הדבק שם את השאלה הבאה ושלח אותה:\n"
            f"\"{question}\"\n"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Intent not implemented"
        )

    # Add greeting prefix if this is a new conversation
    response_text = _maybe_prefix_greeting(response_text, conversation_history)

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

