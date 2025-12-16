"""
Manager GPT service for handling manager-specific questions via Google Gemini API.
Routes questions to a specialized ChatGPT GPT for management queries.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ChatGPT GPT URL provided by user
MANAGER_GPT_URL = "https://chatgpt.com/g/g-693fcca05a348191b116de2a699902c7-mrkhb-bvdh-nyhvly-pytvkh-tpysh-nyhvl-tsmy-vhvblh"

DEFAULT_MODEL = "gemini-2.5-flash"


class ManagerGPTService:
    """
    Service for routing manager questions to ChatGPT GPT via Google Gemini API.
    Uses Gemini model with manager-specific system instructions.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required for Manager GPT service")
        os.environ.setdefault("GEMINI_API_KEY", api_key)
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def answer_manager_question(
        self,
        question: str,
        timeout: float = 120.0,
    ) -> str:
        """
        Answer a manager question using ChatGPT GPT via Google Gemini API.
        
        Args:
            question: The manager's question
            timeout: Request timeout in seconds
            
        Returns:
            The response from the GPT model
        """
        system_instruction = self._get_manager_system_instruction()

        def _call() -> str:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
            
            response = self._client.models.generate_content(
                model=self._model,
                contents=question,
                config=config,
            )
            
            if not response or not hasattr(response, 'text') or not response.text:
                logger.warning("Empty response from Manager GPT")
                return "מצטער, לא קיבלתי תשובה מהמערכת. אנא נסה שוב."
            
            content = response.text.strip()
            
            # Limit response to 4 lines as per user requirement
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            if len(lines) > 4:
                # Take first 4 non-empty lines
                content = "\n".join(lines[:4])
            else:
                content = "\n".join(lines)
            
            return content

        try:
            content = await asyncio.to_thread(_call)
            return content
        except Exception as e:
            logger.error("Error calling Manager GPT service: %s", e, exc_info=True)
            return "מצטער, אירעה שגיאה בקבלת תשובה מהמערכת. אנא נסה שוב מאוחר יותר."

    @staticmethod
    def _get_manager_system_instruction() -> str:
        """Get the system instruction for manager questions."""
        return (
            "אתה עוזר AI מיוחד לשאלות מנהליות עבור נמלים ותפעול ימי. "
            "תפקידך לענות על שאלות מנהליות, תפעוליות, רגולטוריות וניהוליות הקשורות לנמלים בישראל. "
            "\n\n"
            "הוראות חשובות:\n"
            "- ענה בעברית בלבד\n"
            "- שמור על תשובות קצרות וממוקדות - מקסימום 4 שורות\n"
            "- התחל עם תשובה ישירה לשאלה\n"
            "- השתמש בשפה מקצועית וברורה\n"
            "- אם השאלה מתייחסת למסמכים ספציפיים או נהלים, ציין זאת\n"
            "- תמיד תן תשובה מועילה, גם אם אין לך מידע ספציפי - השתמש בידע כללי על תפעול נמלים\n"
            "\n"
            "התשובה חייבת להיות קצרה וממוקדת - מקסימום 4 שורות."
        )

