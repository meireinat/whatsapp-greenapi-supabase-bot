"""
Wrapper around the Supabase Python client for domain-specific queries.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Iterable, List, Mapping

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Encapsulates data access operations used by the bot.
    """

    def __init__(
        self,
        *,
        supabase_url: str,
        supabase_key: str,
        schema: str | None = None,
    ) -> None:
        self._client: Client = create_client(supabase_url, supabase_key)
        if schema:
            self._client.postgrest.schema = schema

    def get_daily_containers_count(self, target_date: dt.date) -> int:
        """
        Count containers unloaded on a specific date.
        """
        logger.debug("Fetching container count for %s", target_date.isoformat())
        response = (
            self._client.table("containers")
            .select("SHANA", count="exact")
            .gte("TARICH_PRIKA", target_date.isoformat())
            .lte("TARICH_PRIKA", target_date.isoformat())
            .execute()
        )

        count = getattr(response, "count", None)
        if count is not None:
            logger.info("Container count for %s is %s", target_date.isoformat(), count)
            return int(count)

        items: list[dict[str, Any]] = getattr(response, "data", [])
        total = len(items)
        logger.info(
            "Container count for %s derived from row count=%s",
            target_date.isoformat(),
            total,
        )
        return int(total)

    def get_containers_count_between(
        self, start_date: dt.date, end_date: dt.date
    ) -> int:
        """
        Count containers unloaded between the provided dates (inclusive).
        """
        logger.debug(
            "Fetching container count between %s and %s",
            start_date.isoformat(),
            end_date.isoformat(),
        )
        response = (
            self._client.table("containers")
            .select("SHANA", count="exact")
            .gte("TARICH_PRIKA", start_date.isoformat())
            .lte("TARICH_PRIKA", end_date.isoformat())
            .execute()
        )

        count = getattr(response, "count", None)
        if count is not None:
            return int(count)

        items: list[dict[str, Any]] = getattr(response, "data", [])
        return int(len(items))

    def get_vehicle_count_between(
        self, start_date: dt.date, end_date: dt.date
    ) -> int:
        """
        Sum vehicles_count from ramp_operations table across the date range.
        """
        logger.debug(
            "Fetching vehicle count between %s and %s",
            start_date.isoformat(),
            end_date.isoformat(),
        )
        response = (
            self._client.table("ramp_operations")
            .select("vehicles_count, operation_date")
            .gte("operation_date", start_date.isoformat())
            .lte("operation_date", end_date.isoformat())
            .execute()
        )

        items: list[dict[str, Any]] = getattr(response, "data", [])
        total = sum(int(item.get("vehicles_count") or 0) for item in items)
        return total

    def get_metrics_summary(
        self,
        *,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        max_rows: int = 2000,
    ) -> Mapping[str, Any]:
        """
        Fetch operational metrics for the provided period to feed LLM analysis.
        """
        if end_date is None:
            end_date = dt.date.today()
        if start_date is None:
            start_date = end_date - dt.timedelta(days=30)

        containers = self._fetch_containers(start_date, end_date, max_rows)
        vehicles = self._fetch_vehicles(start_date, end_date, max_rows)

        container_daily: dict[str, int] = {}
        container_by_line: dict[str, int] = {}
        container_quantity = 0.0

        for row in containers:
            date_str = row.get("TARICH_PRIKA")
            if date_str:
                container_daily[date_str] = container_daily.get(date_str, 0) + 1
            line = row.get("SUG_ARIZA_MITZ") or row.get("SHEM_IZ")
            if line:
                container_by_line[line] = container_by_line.get(line, 0) + 1
            kmut = row.get("KMUT")
            if kmut is not None:
                container_quantity += float(kmut)

        vehicle_daily: dict[str, int] = {}
        for row in vehicles:
            date_str = row.get("operation_date")
            if date_str:
                vehicle_daily[date_str] = (
                    vehicle_daily.get(date_str, 0)
                    + int(row.get("vehicles_count") or 0)
                )

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "containers": {
                "total_records": len(containers),
                "total_quantity": container_quantity,
                "daily_counts": container_daily,
                "by_line_code": container_by_line,
            },
            "vehicles": {
                "total_records": len(vehicles),
                "daily_vehicle_counts": vehicle_daily,
            },
            "sample": {
                "containers": containers[:50],
                "vehicles": vehicles[:50],
            },
        }

    def _fetch_containers(
        self, start_date: dt.date, end_date: dt.date, limit: int
    ) -> list[dict[str, Any]]:
        response = (
            self._client.table("containers")
            .select(
                "KMUT,SUG_ARIZA_MITZ,SHEM_IZ,SHEM_AR,TARICH_PRIKA,TARGET,SHIPNAME,PEULA,MANIFEST"
            )
            .gte("TARICH_PRIKA", start_date.isoformat())
            .lte("TARICH_PRIKA", end_date.isoformat())
            .order("TARICH_PRIKA", desc=False)
            .limit(limit)
            .execute()
        )
        return list(getattr(response, "data", []))

    def _fetch_vehicles(
        self, start_date: dt.date, end_date: dt.date, limit: int
    ) -> list[dict[str, Any]]:
        response = (
            self._client.table("ramp_operations")
            .select("vehicles_count,containers_count,operation_date,ramp_id,shift")
            .gte("operation_date", start_date.isoformat())
            .lte("operation_date", end_date.isoformat())
            .order("operation_date", desc=False)
            .limit(limit)
            .execute()
        )
        return list(getattr(response, "data", []))

    def log_query(
        self,
        *,
        user_phone: str,
        user_text: str,
        intent: str,
        parameters: dict[str, Any],
        response_text: str,
    ) -> None:
        """
        Persist interactions for auditing and analytics.
        """
        logger.debug("Logging query for user %s intent %s", user_phone, intent)
        self._client.table("bot_queries_log").insert(
            {
                "user_phone": user_phone,
                "user_text": user_text,
                "intent": intent,
                "parameters": parameters,
                "response_text": response_text,
            }
        ).execute()

    def bulk_insert(
        self,
        *,
        table: str,
        rows: Iterable[dict[str, Any]],
        batch_size: int = 500,
    ) -> None:
        """
        Insert CSV-derived rows into Supabase in batches to avoid timeouts.
        """
        for index, batch in enumerate(_chunked(rows, batch_size), start=1):
            logger.info("Uploading batch %s to table %s", index, table)
            self._client.table(table).insert(batch).execute()


def _chunked(iterable: Iterable[dict[str, Any]], size: int) -> Iterable[List[dict[str, Any]]]:
    batch: List[dict[str, Any]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch

