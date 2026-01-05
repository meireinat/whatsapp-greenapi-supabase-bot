"""
Client for querying Google NotebookLM when information is not available in local knowledge base.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# NotebookLM base URL
NOTEBOOKLM_BASE_URL = "https://notebooklm.google.com"
NOTEBOOKLM_NOTEBOOK_ID = "66688b34-ca77-4097-8ac8-42ca8285681f"


class NotebookLMClient:
    """
    Client for interacting with Google NotebookLM.
    
    Note: NotebookLM doesn't have a public API, so this is a placeholder
    that can be extended if Google releases an API in the future.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def query(
        self, question: str, notebook_id: str | None = None
    ) -> dict[str, Any]:
        """
        Query NotebookLM with a question.
        
        Note: This is a placeholder implementation. NotebookLM doesn't currently
        provide a public API. This method can be extended if Google releases an API.
        
        Args:
            question: The question to ask
            notebook_id: Optional notebook ID (defaults to the configured one)
            
        Returns:
            A dictionary with the response or error information
        """
        notebook_id = notebook_id or NOTEBOOKLM_NOTEBOOK_ID
        
        # Since NotebookLM doesn't have a public API, we return a response
        # indicating that manual access is needed
        logger.warning(
            "NotebookLM doesn't have a public API. Manual access required at: %s/notebook/%s",
            NOTEBOOKLM_BASE_URL,
            notebook_id,
        )
        
        return {
            "success": False,
            "error": "NotebookLM doesn't have a public API",
            "message": (
                f"למידע נוסף, אנא בדוק ב-NotebookLM: "
                f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}"
            ),
            "notebook_url": f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}",
        }

    async def try_query_with_gemini_fallback(
        self, question: str, gemini_service: Any | None = None
    ) -> str:
        """
        Try to query NotebookLM directly, and if that fails, use Gemini with a prompt
        that references the NotebookLM context.
        
        Args:
            question: The question to ask
            gemini_service: Optional GeminiService instance to use as fallback
            
        Returns:
            Response text
        """
        result = await self.query(question)
        
        if result.get("success"):
            # Successfully got response from NotebookLM
            return result.get("response") or result.get("message", "")
        
        # If NotebookLM query failed, try using Gemini with NotebookLM context
        if gemini_service:
            logger.info("NotebookLM query failed, using Gemini with NotebookLM context reference")
            try:
                # Use Gemini to answer with reference to NotebookLM
                notebook_url = result.get("notebook_url", "")
                gemini_response = await gemini_service.answer_question(
                    question=f"{question}\n\nהערה: אם התשובה לא נמצאת בקבצים המקומיים, אנא הפנה למשתמש לבדוק ב-NotebookLM: {notebook_url}",
                    metrics={},
                    knowledge_sections=None,
                )
                return gemini_response
            except Exception as e:
                logger.error("Gemini fallback failed: %s", e)
        
        return result.get("message", "לא ניתן לגשת ל-NotebookLM כרגע.")

