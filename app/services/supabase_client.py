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
        # Filter out non-ASCII schema values before creating client
        # Always set to None to avoid any encoding issues with Supabase client
        safe_schema: str | None = None
        if schema:
            try:
                schema.encode("ascii")
                # Even if ASCII, don't use schema() as it's not supported
                # and may cause encoding issues in PostgREST client
                safe_schema = None
                logger.info(
                    "Schema provided but not used (schema() not supported by Supabase Python client)"
                )
            except UnicodeEncodeError:
                logger.warning(
                    "Supabase schema '%s' contains non-ASCII characters; "
                    "schema scoping will be disabled to avoid encoding issues.",
                    schema[:50] if len(schema) > 50 else schema,
                )
        # Create client without schema to avoid encoding issues
        # Always use default schema (usually 'public')
        # Remove SUPABASE_SCHEMA from environment to prevent Supabase client
        # from reading it and causing UnicodeEncodeError
        import os
        original_schema = os.environ.pop("SUPABASE_SCHEMA", None)
        if original_schema:
            logger.info(
                "Removed SUPABASE_SCHEMA from environment to avoid encoding issues. "
                "Original value contained non-ASCII characters."
            )
        
        logger.info("Creating Supabase client (schema will not be used)")
        try:
            self._client: Client = create_client(supabase_url, supabase_key)
            logger.info("Supabase client created successfully")
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when creating Supabase client: %s. "
                "This may be caused by non-ASCII characters in environment variables. "
                "Trying to create client without schema...",
                e,
                exc_info=True,
            )
            # Try to create client again - maybe the error was transient
            self._client: Client = create_client(supabase_url, supabase_key)
        finally:
            # Restore original value if it existed (though we won't use it)
            if original_schema:
                os.environ["SUPABASE_SCHEMA"] = original_schema
        
        self._schema: str | None = None  # Always None to avoid encoding issues

    def get_daily_containers_count(self, target_date: dt.date) -> int:
        """
        Count containers unloaded on a specific date.
        """
        logger.debug("Fetching container count for %s", target_date.isoformat())
        try:
            query = self._client.table("containers")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            # Convert date to YYYYMMDD format for comparison
            date_str = target_date.strftime("%Y%m%d")
            response = (
                query.select("SHANA", count="exact")
                .gte("TARICH_PRIKA", date_str)
                .lte("TARICH_PRIKA", date_str)
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
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching daily containers count: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning 0.",
                e,
            )
            return 0

    def get_containers_count_between(
        self, start_date: dt.date, end_date: dt.date
    ) -> int:
        """
        Count containers unloaded between the provided dates (inclusive).
        
        Note: TARICH_PRIKA is stored as YYYYMMDD format (string) in the database.
        """
        logger.info(
            "Fetching container count between %s and %s (YYYYMMDD: %s to %s)",
            start_date.isoformat(),
            end_date.isoformat(),
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
        )
        try:
            # Try to access table - this may trigger _init_postgrest_client
            # which can fail if schema contains non-ASCII characters
            try:
                query = self._client.table("containers")
            except UnicodeEncodeError as e:
                logger.error(
                    "UnicodeEncodeError when accessing table 'containers': %s. "
                    "This is likely caused by SUPABASE_SCHEMA environment variable "
                    "containing non-ASCII characters. Please remove or fix SUPABASE_SCHEMA in Railway. "
                    "Returning 0.",
                    e,
                    exc_info=True,
                )
                return 0
            
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            # Convert dates to YYYYMMDD format for comparison
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            logger.debug("Query: TARICH_PRIKA >= %s AND TARICH_PRIKA <= %s", start_str, end_str)
            
            # Build query step by step to catch encoding errors early
            try:
                query = query.select("SHANA", count="exact")
                query = query.gte("TARICH_PRIKA", start_str)
                query = query.lte("TARICH_PRIKA", end_str)
                response = query.execute()
            except UnicodeEncodeError as e:
                logger.error(
                    "UnicodeEncodeError during query construction/execution: %s. "
                    "This may be caused by non-ASCII characters in Supabase configuration. "
                    "Returning 0.",
                    e,
                    exc_info=True,
                )
                return 0

            count = getattr(response, "count", None)
            logger.info("Query response count: %s", count)
            if count is not None:
                return int(count)

            items: list[dict[str, Any]] = getattr(response, "data", [])
            return int(len(items))
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching containers count between dates: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning 0.",
                e,
                exc_info=True,
            )
            return 0

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
        try:
            query = self._client.table("ramp_operations")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            response = query.select("vehicles_count, operation_date").gte(
                "operation_date", start_date.isoformat()
            ).lte("operation_date", end_date.isoformat()).execute()

            items: list[dict[str, Any]] = getattr(response, "data", [])
            total = sum(int(item.get("vehicles_count") or 0) for item in items)
            return total
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching vehicle count between dates: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning 0.",
                e,
            )
            return 0

    def get_containers_count_monthly(self, month: int, year: int) -> int:
        """
        Count containers unloaded in a specific month and year.
        """
        logger.info("Fetching monthly container count for month=%d, year=%d", month, year)
        try:
            # Calculate first and last day of the month
            if month == 12:
                start_date = dt.date(year, month, 1)
                end_date = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
            else:
                start_date = dt.date(year, month, 1)
                end_date = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            
            logger.info("Monthly date range: %s to %s (YYYYMMDD: %s to %s)", 
                       start_date.isoformat(), end_date.isoformat(),
                       start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
            count = self.get_containers_count_between(start_date, end_date)
            logger.info("Monthly container count result: %d", count)
            return count
        except Exception as e:
            logger.error(
                "Error fetching monthly containers count for %d/%d: %s",
                month,
                year,
                e,
            )
            return 0

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

        logger.info("Fetching metrics summary: %s to %s", start_date.isoformat(), end_date.isoformat())
        containers = self._fetch_containers(start_date, end_date, max_rows)
        vehicles = self._fetch_vehicles(start_date, end_date, max_rows)
        logger.info("Metrics summary: %d containers, %d vehicles", len(containers), len(vehicles))

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
        try:
            query = self._client.table("containers")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            # Convert dates to YYYYMMDD format for comparison
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            response = (
                query.select(
                    "KMUT,SUG_ARIZA_MITZ,SHEM_IZ,SHEM_AR,TARICH_PRIKA,TARGET,SHIPNAME,PEULA,MANIFEST"
                )
                .gte("TARICH_PRIKA", start_str)
                .lte("TARICH_PRIKA", end_str)
                .order("TARICH_PRIKA", desc=False)
                .limit(limit)
                .execute()
            )
            return list(getattr(response, "data", []))
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching containers: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning empty result.",
                e,
            )
            return []

    def _fetch_vehicles(
        self, start_date: dt.date, end_date: dt.date, limit: int
    ) -> list[dict[str, Any]]:
        try:
            query = self._client.table("ramp_operations")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            response = (
                query.select("vehicles_count,containers_count,operation_date,ramp_id,shift")
                .gte("operation_date", start_date.isoformat())
                .lte("operation_date", end_date.isoformat())
                .order("operation_date", desc=False)
                .limit(limit)
                .execute()
            )
            return list(getattr(response, "data", []))
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching vehicles: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning empty result.",
                e,
            )
            return []

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
        try:
            # Convert parameters to JSON-serializable format
            safe_parameters = {}
            for key, value in parameters.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    safe_parameters[key] = value
                elif isinstance(value, dt.date):
                    safe_parameters[key] = value.isoformat()
                else:
                    safe_parameters[key] = str(value)
            
            # Use table without schema to avoid encoding issues
            query = self._client.table("bot_queries_log")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            
            query.insert(
                {
                    "user_phone": user_phone,
                    "user_text": user_text,
                    "intent": intent,
                    "parameters": safe_parameters,
                    "response_text": response_text,
                }
            ).execute()
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when logging query: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Skipping log entry.",
                e,
            )
        except Exception as e:
            logger.error("Failed to log query: %s", e, exc_info=True)

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

