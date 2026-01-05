"""
Client for querying Google NotebookLM Enterprise API when information is not available in local knowledge base.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# NotebookLM base URL
NOTEBOOKLM_BASE_URL = "https://notebooklm.google.com"
NOTEBOOKLM_NOTEBOOK_ID = "66688b34-ca77-4097-8ac8-42ca8285681f"

# NotebookLM Enterprise API base URL
NOTEBOOKLM_API_BASE = "https://{endpoint_location}-discoveryengine.googleapis.com/v1alpha"


class NotebookLMClient:
    """
    Client for interacting with Google NotebookLM Enterprise API.
    
    Supports querying notebooks, adding sources, and managing data sources.
    """

    def __init__(
        self,
        api_key: str | None = None,
        project_number: str | None = None,
        location: str = "global",
        endpoint_location: str = "global",
        notebook_id: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize NotebookLM client.
        
        Args:
            api_key: Google Cloud API key or access token
            project_number: Google Cloud project number
            location: Geographic location (default: "global")
            endpoint_location: API endpoint location - "us-", "eu-", or "global" (default: "global")
            notebook_id: Notebook ID (defaults to configured one)
            timeout: Request timeout in seconds
        """
        self._timeout = timeout
        self._api_key = api_key
        self._project_number = project_number or os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER")
        self._location = location
        self._endpoint_location = endpoint_location
        self._notebook_id = notebook_id or NOTEBOOKLM_NOTEBOOK_ID
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_access_token(self) -> str | None:
        """
        Get Google Cloud access token using gcloud CLI.
        
        Returns:
            Access token or None if not available
        """
        if self._api_key:
            # If API key is provided, assume it's already an access token
            return self._api_key
        
        try:
            # Try to get access token from gcloud
            result = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug("Failed to get access token from gcloud: %s", e)
        
        return None

    async def query(
        self, question: str, notebook_id: str | None = None
    ) -> dict[str, Any]:
        """
        Query NotebookLM Enterprise API with a question.
        
        Args:
            question: The question to ask
            notebook_id: Optional notebook ID (defaults to the configured one)
            
        Returns:
            A dictionary with the response or error information
        """
        notebook_id = notebook_id or self._notebook_id
        
        if not self._project_number:
            logger.warning(
                "NotebookLM Enterprise API requires project number. Manual access required at: %s/notebook/%s",
                NOTEBOOKLM_BASE_URL,
                notebook_id,
            )
            return {
                "success": False,
                "error": "Project number not configured",
                "message": (
                    f"למידע נוסף, אנא בדוק ב-NotebookLM: "
                    f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}"
                ),
                "notebook_url": f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}",
            }
        
        access_token = await self._get_access_token()
        if not access_token:
            logger.warning(
                "NotebookLM Enterprise API requires authentication. Manual access required at: %s/notebook/%s",
                NOTEBOOKLM_BASE_URL,
                notebook_id,
            )
            return {
                "success": False,
                "error": "Authentication required",
                "message": (
                    f"למידע נוסף, אנא בדוק ב-NotebookLM: "
                    f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}"
                ),
                "notebook_url": f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}",
            }
        
        # Build API URL
        api_base = NOTEBOOKLM_API_BASE.format(endpoint_location=self._endpoint_location)
        url = (
            f"{api_base}/projects/{self._project_number}/locations/{self._location}/"
            f"notebooks/{notebook_id}:query"
        )
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "query": question,
        }
        
        try:
            logger.info("Querying NotebookLM Enterprise API: %s", url)
            response = await self._client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                response_text = data.get("response") or data.get("answer") or str(data)
                return {
                    "success": True,
                    "response": response_text,
                    "message": response_text,
                    "sources": data.get("sources", []),
                }
            else:
                logger.error(
                    "NotebookLM Enterprise API error: %s - %s",
                    response.status_code,
                    response.text[:500],
                )
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}",
                    "message": (
                        f"למידע נוסף, אנא בדוק ב-NotebookLM: "
                        f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}"
                    ),
                    "notebook_url": f"{NOTEBOOKLM_BASE_URL}/notebook/{notebook_id}",
                }
        except Exception as e:
            logger.error("NotebookLM Enterprise API query failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
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

