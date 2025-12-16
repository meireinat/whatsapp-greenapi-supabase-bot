"""
Manager GPT service for handling manager-specific questions via OpenAI/OpenRouter API.
Routes questions to a specialized ChatGPT GPT for management queries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ChatGPT GPT URL provided by user
MANAGER_GPT_URL = "https://chatgpt.com/g/g-693fcca05a348191b116de2a699902c7-mrkhb-bvdh-nyhvly-pytvkh-tpysh-nyhvl-tsmy-vhvblh"


class ManagerGPTService:
    """
    Service for routing manager questions to ChatGPT GPT via OpenRouter API.
    Uses GPT-4o model with manager-specific system instructions.
    """

    def __init__(self, api_key: str, model: str = "openai/gpt-4o") -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required for Manager GPT service")
        self._api_key = api_key
        self._api_url = "https://openrouter.ai/api/v1/chat/completions"
        self._model = model

    async def answer_manager_question(
        self,
        question: str,
        timeout: float = 120.0,
    ) -> str:
        """
        Answer a manager question using ChatGPT GPT via OpenRouter.
        
        Args:
            question: The manager's question
            timeout: Request timeout in seconds
            
        Returns:
            The response from the GPT model
        """
        system_instruction = self._get_manager_system_instruction()
        
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": question},
        ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": MANAGER_GPT_URL,  # Reference to the GPT
        }

        payload = {
            "model": self._model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._api_url, headers=headers, json=payload
                )
                response.raise_for_status()

                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content", "").strip()

                if not content:
                    logger.warning("Empty response from Manager GPT")
                    return "מצטער, לא קיבלתי תשובה מהמערכת. אנא נסה שוב."

                # Limit response to 4 lines as per user requirement
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                if len(lines) > 4:
                    # Take first 4 non-empty lines
                    content = "\n".join(lines[:4])
                else:
                    content = "\n".join(lines)

                return content

        except httpx.TimeoutException:
            logger.error("Timeout calling Manager GPT service")
            return "מצטער, התשובה לוקחת יותר מדי זמן. אנא נסה שוב מאוחר יותר."
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error calling Manager GPT: %s", e.response.status_code)
            return "מצטער, אירעה שגיאה בקבלת תשובה מהמערכת. אנא נסה שוב מאוחר יותר."
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

