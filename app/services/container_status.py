"""
Utility service to query container status pages across all Israeli ports in parallel.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


@dataclass(slots=True)
class PortStatusResult:
    """Normalized response for a single port status lookup."""

    port_name: str
    url: str
    success: bool
    summary: str
    raw_excerpt: str | None = None
    error: str | None = None


class ContainerStatusService:
    """
    Fetch container status information from all four Israeli container terminals.

    The service performs the HTTP calls concurrently to keep the webhook latency low.
    """

    PORT_SPECS: tuple[Mapping[str, Any], ...] = (
        {
            "name": "נמל אשדוד",
            "url": "https://www.ashdodport.co.il/pages/statusmehola.aspx",
            "method": "GET",
            "params_key": "MISMHOLA",
        },
        {
            "name": "נמל חיפה",
            "url": "https://www.haifaport.co.il/container-status/",
            "method": "GET",
            "params_key": "container",
            "extra_params": {"lang-clear": "1"},
        },
        {
            "name": "נמל הדרום",
            "url": "https://hadct.co.il/account/page/10839",
            "method": "GET",
            "params_key": "containerId",
        },
        {
            "name": "נמל המפרץ",
            "url": "https://customer.sipgbayport.com/container-info-query",
            "method": "GET",
            "params_key": "containerId",
        },
    )

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds
        self._logger = logging.getLogger(__name__)
        self._tag_pattern = re.compile(r"<[^>]+>")

    async def lookup(self, container_id: str) -> list[PortStatusResult]:
        """
        Query all configured ports concurrently and return their individual responses.
        """
        headers = {
            "User-Agent": "WhatsappBot/1.0 (+https://github.com/meireinat/whatsapp-greenapi-supabase-bot)"
        }
        async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
            tasks = [
                self._fetch_port(client, spec, container_id) for spec in self.PORT_SPECS
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        normalized: list[PortStatusResult] = []
        for spec, response in zip(self.PORT_SPECS, responses, strict=False):
            if isinstance(response, PortStatusResult):
                normalized.append(response)
            else:
                error_message = str(response)
                self._logger.error(
                    "Failed to fetch container status from %s: %s", spec["name"], error_message
                )
                normalized.append(
                    PortStatusResult(
                        port_name=spec["name"],
                        url=spec["url"],
                        success=False,
                        summary="לא הצלחנו לקבל נתונים מהאתר.",
                        raw_excerpt=None,
                        error=error_message,
                    )
                )
        return normalized

    async def _fetch_port(
        self,
        client: httpx.AsyncClient,
        spec: Mapping[str, Any],
        container_id: str,
    ) -> PortStatusResult:
        params = {}
        if spec.get("params_key"):
            params[spec["params_key"]] = container_id
        if spec.get("extra_params"):
            params.update(spec["extra_params"])

        method = spec.get("method", "GET").upper()
        url = spec["url"]

        response = await client.request(method, url, params=params or None)
        success = response.status_code == httpx.codes.OK
        body_text = response.text

        summary = self._summarize(body_text, container_id) if success else ""
        raw_excerpt = summary if summary else None

        if not success:
            error_text = f"HTTP {response.status_code}"
            return PortStatusResult(
                port_name=spec["name"],
                url=str(response.request.url),
                success=False,
                summary="האתר החזיר שגיאה. אנא נסה שוב מאוחר יותר.",
                raw_excerpt=None,
                error=error_text,
            )

        return PortStatusResult(
            port_name=spec["name"],
            url=str(response.request.url),
            success=True,
            summary=summary or "הדף נטען בהצלחה, אך לא נמצאה התאמה ישירה למספר המכולה.",
            raw_excerpt=(body_text[:400] if not summary else raw_excerpt),
            error=None,
        )

    def _summarize(self, html: str, container_id: str) -> str:
        """
        Provide a lightweight textual summary by taking the surrounding text
        around the container identifier (if it exists in the HTML).
        """
        normalized_html = html
        lower_html = normalized_html.lower()
        lower_id = container_id.lower()

        idx = lower_html.find(lower_id)
        if idx == -1:
            snippet = normalized_html[:500]
        else:
            start = max(0, idx - 250)
            end = min(len(normalized_html), idx + 250)
            snippet = normalized_html[start:end]

        cleaned = self._tag_pattern.sub(" ", snippet)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:500]


