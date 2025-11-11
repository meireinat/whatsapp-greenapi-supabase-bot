"""
Send a WhatsApp message via Green API using project configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re

from dotenv import load_dotenv

from app.config import get_settings
from app.services.greenapi_client import GreenAPIClient

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a WhatsApp message via Green API.")
    parser.add_argument(
        "--phone",
        help="Phone number (local or international). Converted to chatId automatically.",
    )
    parser.add_argument(
        "--chat-id",
        help="Explicit chatId (e.g. 972501234567@c.us). Overrides --phone if provided.",
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Message text to send.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the message without sending.",
    )
    return parser.parse_args()


def phone_to_chat_id(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    if not digits.endswith("@c.us"):
        digits = f"{digits}@c.us"
    return digits


async def send_message(chat_id: str, message: str, dry_run: bool = False) -> None:
    load_dotenv()
    settings = get_settings()

    if dry_run:
        logger.info("Dry run: message to %s -> %s", chat_id, message)
        return

    client = GreenAPIClient(
        instance_id=settings.green_api_instance_id,
        api_token=settings.green_api_token,
    )
    try:
        await client.send_text_message(chat_id, message)
        logger.info("Message sent successfully to %s", chat_id)
    finally:
        await client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    chat_id = args.chat_id or (phone_to_chat_id(args.phone) if args.phone else None)
    if not chat_id:
        raise SystemExit("Either --phone or --chat-id must be provided.")

    asyncio.run(send_message(chat_id, args.message, args.dry_run))


if __name__ == "__main__":
    main()

