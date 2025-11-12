"""
Client for interacting with the Green API HTTP endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GreenAPIQuotaExceededError(Exception):
    """Raised when Green API quota/tariff limit is exceeded (error 466)."""
    
    def __init__(self, message: str, response_body: dict[str, Any] | None = None):
        super().__init__(message)
        self.response_body = response_body


class GreenAPIClient:
    """
    Thin wrapper around Green API HTTP endpoints used by the bot.
    """

    def __init__(
        self,
        *,
        instance_id: str,
        api_token: str,
        base_url: str = "https://api.green-api.com",
        timeout: float = 10.0,
    ) -> None:
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def send_text_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """
        Send a standard text message to a WhatsApp chat via Green API.
        """
        endpoint = (
            f"{self.base_url}/waInstance{self.instance_id}/sendMessage/{self.api_token}"
        )
        payload = {
            "chatId": chat_id,
            "message": text,
        }

        logger.info("Sending message to chat %s via Green API endpoint: %s", chat_id, endpoint)
        logger.debug("Message payload: %s", payload)
        try:
            response = await self._client.post(endpoint, json=payload)
            
            # Log response details before raising for status
            logger.debug("Green API response status: %s", response.status_code)
            if response.status_code != 200:
                try:
                    error_body = response.json()
                    logger.warning(
                        "Green API returned non-200 status %s: %s",
                        response.status_code,
                        error_body,
                    )
                except Exception:
                    error_text = response.text
                    logger.warning(
                        "Green API returned non-200 status %s: %s",
                        response.status_code,
                        error_text[:500] if error_text else "No response body",
                    )
            
            response.raise_for_status()
            result = response.json()
            logger.info("Message sent successfully to chat %s. Response: %s", chat_id, result)
            return result
        except httpx.HTTPStatusError as exc:
            error_details = "unknown"
            if exc.response:
                try:
                    error_body = exc.response.json()
                    error_details = f"JSON: {error_body}"
                except Exception:
                    error_text = exc.response.text
                    error_details = f"Text: {error_text[:500] if error_text else 'No response body'}"
            
            # Error 466 is a quota/tariff exceeded error from Green API
            # The message has NOT been sent when this error occurs
            if exc.response and exc.response.status_code == 466:
                error_body = None
                if exc.response:
                    try:
                        error_body = exc.response.json()
                    except Exception:
                        pass
                
                error_msg = (
                    f"Green API quota/tariff exceeded (466). "
                    f"Message to {chat_id} was NOT sent. "
                    f"Details: {error_details}"
                )
                logger.error(error_msg)
                raise GreenAPIQuotaExceededError(error_msg, error_body)
            
            logger.error(
                "Failed to send WhatsApp message to %s: HTTP %s - %s",
                chat_id,
                exc.response.status_code if exc.response else "unknown",
                error_details,
            )
            raise
        except Exception as exc:
            logger.exception("Unexpected error sending message to %s: %s", chat_id, exc)
            raise

