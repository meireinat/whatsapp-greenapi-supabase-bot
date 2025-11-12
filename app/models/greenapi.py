"""
Pydantic models describing the structure of Green API webhook payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MessageTextData(BaseModel):
    """Text message information nested within `messageData`."""

    model_config = ConfigDict(extra="ignore")

    textMessage: str | None = None


class MessageData(BaseModel):
    """Subset of message data relevant for text-based automations."""

    model_config = ConfigDict(extra="ignore")

    typeMessage: str
    textMessageData: MessageTextData | None = None


class SenderData(BaseModel):
    """Metadata about the sender of an incoming message."""

    model_config = ConfigDict(extra="ignore")

    chatId: str
    sender: str | None = None
    senderName: str | None = None


class GreenWebhookPayload(BaseModel):
    """
    Root payload for webhook notifications from Green API.

    The API exposes a broad schema; we extract the fields required for the bot flow.
    """

    model_config = ConfigDict(extra="allow")

    typeWebhook: str
    timestamp: int | None = None
    messageData: MessageData
    senderData: SenderData

