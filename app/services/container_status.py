"""
Utility service to query container status pages across all Israeli ports in parallel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
from bs4 import BeautifulSoup


@dataclass(slots=True)
class PortStatusResult:
    """Normalized response for a single port status lookup."""

    port_name: str
    url: str
    success: bool
    summary: str
    error: str | None = None
    details: Sequence[tuple[str, str]] | None = None


class ContainerStatusService:
    """
    Fetch container status information from all four Israeli container terminals.

    Each port has a bespoke data source (HTML, JSON or AJAX). The service performs the
    HTTP calls concurrently to keep the webhook latency low.
    """

    ASHDOD_URL = "https://www.ashdodport.co.il/pages/statusmehola.aspx"
    HAIFA_AJAX_URL = "https://www.haifaport.co.il/wp-admin/admin-ajax.php"
    HADEROM_API = "https://hadct.co.il/Controls/60/Public/SearchApiHandler.ashx"
    BAYPORT_API = "https://customer.sipgbayport.com/customer-service/itos/query-container-info"

    CHROME_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.1 Safari/537.36"
    )

    ASHDOD_HEADERS = {
        "User-Agent": CHROME_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    HAIFA_HEADERS = {
        "User-Agent": CHROME_UA,
        "Referer": "https://www.haifaport.co.il/container-status/",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.haifaport.co.il",
        "Accept-Encoding": "gzip, deflate, br",
    }
    HADEROM_HEADERS = {
        "User-Agent": CHROME_UA,
        "Accept": "application/json",
    }
    BAYPORT_HEADERS = {
        "User-Agent": CHROME_UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self._timeout = timeout_seconds
        self._logger = logging.getLogger(__name__)

    async def lookup(self, container_id: str) -> list[PortStatusResult]:
        """
        Query all configured ports concurrently and return their individual responses.
        """
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            tasks = (
                self._fetch_ashdod(client, container_id),
                self._fetch_haifa(client, container_id),
                self._fetch_hadarom(client, container_id),
                self._fetch_bayport(client, container_id),
            )
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        port_names = ("נמל אשדוד", "נמל חיפה", "נמל הדרום", "נמל המפרץ")
        results: list[PortStatusResult] = []
        for port_name, response in zip(port_names, responses, strict=False):
            if isinstance(response, PortStatusResult):
                results.append(response)
            else:
                self._logger.error(
                    "Container status lookup failed for %s: %s", port_name, response
                )
                results.append(
                    PortStatusResult(
                        port_name=port_name,
                        url="",
                        success=False,
                        summary="שגיאה פנימית בזמן בדיקת הסטטוס.",
                        error=str(response),
                    )
                )
        return results

    async def _fetch_ashdod(
        self, client: httpx.AsyncClient, container_id: str
    ) -> PortStatusResult:
        try:
            html = await self._get_ashdod_html(client, container_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {403, 429, 503}:
                try:
                    html = await asyncio.to_thread(
                        self._get_ashdod_html_sync, container_id
                    )
                except Exception as fallback_exc:  # pragma: no cover - best effort
                    return self._build_error_result(
                        "נמל אשדוד",
                        self.ASHDOD_URL,
                        fallback_exc,
                    )
            else:
                return self._build_error_result("נמל אשדוד", self.ASHDOD_URL, exc)
        except Exception as exc:
            return self._build_error_result("נמל אשדוד", self.ASHDOD_URL, exc)

        summary = self._parse_ashdod_html(html)
        events = summary["events"]
        success = bool(events)
        details = (
            [(f"אירוע {idx + 1}", event) for idx, event in enumerate(events)]
            if events
            else None
        )
        summary_text = (
            f"נמצאו {len(events)} אירועים אחרונים."
            if events
            else "הדף נטען אך לא נמצאה רשומת מכולה."
        )
        return PortStatusResult(
            port_name="נמל אשדוד",
            url=self.ASHDOD_URL,
            success=success,
            summary=summary_text,
            details=details,
            error=None if success else "missing-data",
        )

    async def _get_ashdod_html(
        self, client: httpx.AsyncClient, container_id: str
    ) -> str:
        resp = await client.get(
            self.ASHDOD_URL,
            params={"MISMHOLA": container_id},
            headers=self.ASHDOD_HEADERS,
        )
        resp.raise_for_status()
        return resp.text

    def _get_ashdod_html_sync(self, container_id: str) -> str:
        with httpx.Client(
            headers=self.ASHDOD_HEADERS,
            timeout=self._timeout,
            follow_redirects=True,
            http2=True,
        ) as sync_client:
            resp = sync_client.get(
                self.ASHDOD_URL,
                params={"MISMHOLA": container_id},
            )
            resp.raise_for_status()
            return resp.text
    async def _fetch_haifa(
        self, client: httpx.AsyncClient, container_id: str
    ) -> PortStatusResult:
        """
        Haifa's admin-ajax endpoint blocks asyncio-based HTTP clients via bot mitigation.
        We therefore perform the request in a worker thread with httpx.Client (sync)
        to mimic a browser fingerprint.
        """

        def _call_sync() -> tuple[dict[str, Any], str]:
            with httpx.Client(
                timeout=self._timeout, follow_redirects=True, headers=self.HAIFA_HEADERS
            ) as sync_client:
                resp = sync_client.post(
                    self.HAIFA_AJAX_URL,
                    data={"action": "requestHandle", "path": f"containers/{container_id}"},
                )
                resp.raise_for_status()
                return resp.json(), str(resp.request.url)

        try:
            payload, url = await asyncio.to_thread(_call_sync)
            if "error" in payload:
                return PortStatusResult(
                    port_name="נמל חיפה",
                    url=url,
                    success=False,
                    summary="האתר החזיר שגיאה.",
                    error=str(payload.get("error")),
                )
            summary, details = self._summarize_haifa(payload)
            return PortStatusResult(
                port_name="נמל חיפה",
                url=url,
                success=True,
                summary=summary,
                details=details,
            )
        except Exception as exc:
            return self._build_error_result("נמל חיפה", self.HAIFA_AJAX_URL, exc)

    async def _fetch_hadarom(
        self, client: httpx.AsyncClient, container_id: str
    ) -> PortStatusResult:
        try:
            resp = await client.get(
                self.HADEROM_API,
                params={"action": "search", "type": "container", "id": container_id},
                headers=self.HADEROM_HEADERS,
            )
            resp.raise_for_status()
            payload = resp.json()
            summary, details = self._summarize_hadarom(payload)
            success = payload.get("result") == 1
            if not success and not summary:
                summary = "לא נמצאה התאמה במערכת."
            return PortStatusResult(
                port_name="נמל הדרום",
                url=str(resp.request.url),
                success=success,
                summary=summary,
                details=details if success else None,
                error=None if success else "missing-data",
            )
        except Exception as exc:
            return self._build_error_result("נמל הדרום", self.HADEROM_API, exc)

    async def _fetch_bayport(
        self, client: httpx.AsyncClient, container_id: str
    ) -> PortStatusResult:
        try:
            resp = await client.post(
                self.BAYPORT_API,
                headers=self.BAYPORT_HEADERS,
                json={
                    "cntrno": container_id,
                    "manifest": "",
                    "pageIndex": 0,
                    "pageSize": 10,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            summary, details, has_entries = self._summarize_bayport(payload)
            return PortStatusResult(
                port_name="נמל המפרץ",
                url=str(resp.request.url),
                success=has_entries,
                summary=summary,
                details=details if has_entries else None,
                error=None if has_entries else "missing-data",
            )
        except Exception as exc:
            return self._build_error_result("נמל המפרץ", self.BAYPORT_API, exc)

    def _parse_ashdod_html(self, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            return {"events": []}

        rows = table.find_all("tr")
        if len(rows) <= 1:
            return ""

        summaries: list[str] = []
        for row in rows[1:]:
            cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
            if len(cells) < 4:
                continue
            date, short_desc, long_desc = cells[1], cells[2], cells[3]
            movement = cells[4] if len(cells) > 4 else ""
            summaries.append(f"{date} | {short_desc} – {long_desc} ({movement})")
        return {"events": summaries[:5]}

    @staticmethod
    def _summarize_haifa(payload: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        current = payload.get("current") or {}
        if not current:
            return "לא נמצאו נתונים עבור המכולה.", []
        label_map = {
            "ContainerId": "מספר מכולה",
            "Category": "סיווג",
            "FreightKind": "סוג טעינה",
            "ContainerType": "סוג מכולה",
            "GrossWeight": "משקל ברוטו",
            "TimeFacilityIn": "תאריך כניסה",
            "TimeFacilityOut": "תאריך יציאה",
            "StorageCode": "קוד אחסנה",
            "LineOperator": "חברת קו",
            "ShippingAgentName": "סוכן אוניה",
            "CustomsAgentName": "סוכן מכס",
            "InboundMode": "מצב כניסה",
            "OutboundMode": "מצב יציאה",
            "InboundVesselName": "שם אוניה נכנסת",
            "OutboundVesselName": "שם אוניה יוצאת",
            "AppointmentTruckingCompanyName": "חברת הובלה",
        }
        details: list[tuple[str, str]] = []
        for key, label in label_map.items():
            value = current.get(key)
            if value not in (None, "", []):
                details.append((label, str(value)))
        summary = "נתונים עדכניים מהמערכת."
        return summary, details

    @staticmethod
    def _summarize_hadarom(payload: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        containers = (
            payload.get("payload", {}).get("containers", [])
            if isinstance(payload, dict)
            else []
        )
        if not containers:
            return "לא נמצאו נתונים עבור המכולה.", []

        cargo_list: Sequence[dict[str, Any]] = containers[0].get("CargoList", [])
        if not cargo_list:
            return "התקבלה תגובה אך ללא פרטי מטען.", []

        cargo = cargo_list[0]
        export_proc = cargo.get("ExportProcess") or {}
        details: list[tuple[str, str]] = [
            ("סוכן אוניה", cargo.get("ShipAgentName") or "-"),
            ("סוכן מכס", cargo.get("CustomsAgentName") or "-"),
            ("קו אחסנה", cargo.get("StorageLine") or "-"),
            ("חברת תובלה", cargo.get("TransportCompanyName") or "-"),
            ("מספר עסקה", cargo.get("TransactionMaster") or cargo.get("TransactionIDList") or "-"),
        ]
        if export_proc.get("PortStorageFeedbackDate"):
            details.append(
                (
                    "אישור יציאה",
                    export_proc.get("PortStorageFeedbackDate").replace("T", " "),
                )
            )
        if export_proc.get("StorageIDDate"):
            details.append(
                (
                    "אישור כניסה",
                    export_proc.get("StorageIDDate").replace("T", " "),
                )
            )
        summary = "פרטי מטען כפי שדווחו בנמל הדרום."
        return summary, details

    @staticmethod
    def _summarize_bayport(
        payload: dict[str, Any]
    ) -> tuple[str, list[tuple[str, str]], bool]:
        data_block = payload.get("data", {})
        inner = data_block.get("data")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                inner = {}
        if not isinstance(inner, dict):
            return "לא נמצאו נתונים עבור המכולה.", [], False

        entries = inner.get("list", [])
        if not entries:
            return "לא נמצאו נתונים עבור המכולה.", [], False

        details: list[tuple[str, str]] = []
        for entry in entries[:3]:
            label = f"{entry.get('terminalName','-')} / {entry.get('yardName','-')}"
            value = (
                f"בסטטוס {entry.get('statusCn','-')} | עדכון {entry.get('updateTime','-')} "
                f"| שטר מטען {entry.get('billNo','-')}"
            )
            details.append((label, value))
        total = inner.get("total")
        summary = f"נמצאו {total} רשומות בנמל המפרץ." if total else "רשומות זמינות בנמל המפרץ."
        return summary, details, True

    @staticmethod
    def _build_error_result(port: str, url: str, exc: Exception) -> PortStatusResult:
        return PortStatusResult(
            port_name=port,
            url=url,
            success=False,
            summary="האתר החזיר שגיאה. אנא נסה שוב מאוחר יותר.",
            error=str(exc),
        )


