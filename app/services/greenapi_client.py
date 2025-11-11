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

        logger.debug("Sending message to chat %s via Green API", chat_id)
        response = await self._client.post(endpoint, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.exception("Failed to send WhatsApp message: %s", exc)
            raise

        logger.info("Message sent to chat %s", chat_id)
        return response.json()

