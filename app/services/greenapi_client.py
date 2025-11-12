"""
Client for interacting with the Green API HTTP endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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
            response.raise_for_status()
            result = response.json()
            logger.info("Message sent successfully to chat %s. Response: %s", chat_id, result)
            return result
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Failed to send WhatsApp message to %s: HTTP %s - %s",
                chat_id,
                exc.response.status_code if exc.response else "unknown",
                exc.response.text if exc.response else str(exc),
            )
            raise
        except Exception as exc:
            logger.exception("Unexpected error sending message to %s: %s", chat_id, exc)
            raise

